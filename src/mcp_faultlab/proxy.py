"""Sequential stdio endpoint: initialize, ping, tools/list, tools/call only."""

from __future__ import annotations

import json
from typing import Any, BinaryIO

from .engine import Harness, ProtocolError
from .ledger import TOOLS, Ledger
from .model import Call
from .scenario import Scenario
from .transport import MAX_FRAME_BYTES, PROTOCOL_VERSION, StdioClient


class DropConnection(Exception):
    """Injected response loss: close the stream without inventing a success/error reply."""


def rpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


class ToolEndpoint:
    def __init__(self, scenario: Scenario, upstream: StdioClient | None = None):
        self.upstream = upstream
        self.harness = Harness(scenario, upstream or Ledger())
        self.initialized = False
        self.ready = False

    def handle(self, message: Any) -> dict[str, Any] | None:
        if (not isinstance(message, dict) or message.get("jsonrpc") != "2.0"
            or not isinstance(message.get("method"), str)
            or ("id" in message and type(message["id"]) not in (int, str))):
            return rpc_error(None, -32600, "Invalid JSON-RPC request")
        method = message["method"]
        request_id = message.get("id")
        params = message.get("params", {})
        if "id" not in message:
            if method == "notifications/initialized" and self.initialized:
                self.ready = True
            return None
        if not isinstance(params, dict):
            return rpc_error(request_id, -32602, "params must be an object")
        try:
            if method == "initialize":
                if self.initialized:
                    return rpc_error(request_id, -32600, "Already initialized")
                if params.get("protocolVersion") != PROTOCOL_VERSION:
                    return rpc_error(request_id, -32602, f"Supported version: {PROTOCOL_VERSION}")
                if self.upstream:
                    self.upstream.initialize()
                self.initialized = True
                result = {"protocolVersion": PROTOCOL_VERSION, "capabilities": {"tools": {}},
                          "serverInfo": {"name": "mcp-faultlab", "version": "0.1.0"}}
            elif method == "ping":
                result = {}
            elif not self.ready:
                return rpc_error(request_id, -32002, "Initialize and send notifications/initialized first")
            elif method == "tools/list":
                result = (self.upstream.request(method, params) if self.upstream
                          else {"tools": TOOLS})
            elif method == "tools/call":
                if (not isinstance(params.get("name"), str)
                    or not isinstance(params.get("arguments", {}), dict)):
                    return rpc_error(request_id, -32602, "tools/call requires name and object arguments")
                if not self.upstream and params["name"] not in {t["name"] for t in TOOLS}:
                    return rpc_error(request_id, -32602, "Unknown tool")
                arguments = params.get("arguments", {})
                operation = arguments.get("operation", str(request_id))
                if not isinstance(operation, str) or not operation:
                    operation = str(request_id)
                call = Call(json.dumps(request_id), params["name"], arguments, operation)
                outcome = self.harness.invoke(call)
                if outcome.protocol_error is not None:
                    return {"jsonrpc": "2.0", "id": request_id, "error": outcome.protocol_error}
                if outcome.result is None:
                    raise DropConnection(outcome.failure)
                result = outcome.result
            else:
                return rpc_error(request_id, -32601, f"Method outside supported subset: {method}")
        except ProtocolError as exc:
            return {"jsonrpc": "2.0", "id": request_id, "error": exc.error}
        except ValueError as exc:
            return rpc_error(request_id, -32602, str(exc))
        return {"jsonrpc": "2.0", "id": request_id, "result": result}


def serve(endpoint: ToolEndpoint, source: BinaryIO, sink: BinaryIO) -> None:
    while True:
        line = source.readline(MAX_FRAME_BYTES + 1)
        if not line:
            return
        if len(line) > MAX_FRAME_BYTES:
            return  # close, never try to resynchronize a truncated frame
        try:
            message = json.loads(line)
        except (ValueError, UnicodeError):
            response = rpc_error(None, -32700, "Invalid JSON")
        else:
            try:
                response = endpoint.handle(message)
            except DropConnection:
                return
        if response is not None:
            data = json.dumps(response, separators=(",", ":"), allow_nan=False).encode() + b"\n"
            if len(data) > MAX_FRAME_BYTES:
                return
            sink.write(data)
            sink.flush()
