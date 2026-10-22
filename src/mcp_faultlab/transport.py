"""Bounded sequential stdio JSON-RPC client for the MCP 2025-11-25 subset."""

from __future__ import annotations

import json
import math
import os
import queue
import select
import subprocess
import threading
import time
from typing import Any

from .engine import ProtocolError, TransportError
from .jsonutil import loads
from .model import Call

PROTOCOL_VERSION = "2025-11-25"
MAX_FRAME_BYTES = 1_048_576


def decode_response(raw: bytes, request_id: int | str) -> dict[str, Any]:
    try:
        message = loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise TransportError("invalid_json_response") from exc
    if (not isinstance(message, dict) or message.get("jsonrpc") != "2.0"
        or type(message.get("id")) not in (str, int) or message["id"] != request_id
        or ("result" in message) == ("error" in message)):
        raise TransportError("invalid_response_envelope_or_id")
    if "error" in message:
        error = message["error"]
        if (not isinstance(error, dict) or type(error.get("code")) is not int
            or not isinstance(error.get("message"), str)):
            raise TransportError("invalid_error_response")
        raise ProtocolError(error)
    if not isinstance(message["result"], dict):
        raise TransportError("result_must_be_object")
    return message["result"]


def timeout_value(value: float) -> float:
    if not math.isfinite(value) or not 0 < value <= 60:
        raise ValueError("timeout must be finite and in (0, 60] seconds")
    return value


class StdioClient:
    """One request at a time, no client callbacks, with a hard real-time read deadline.

    A transport timeout closes the child process. It never implies rollback.
    stderr is discarded to prevent deadlocks and accidental trace capture.
    """

    def __init__(self, command: list[str], timeout: float = 5.0):
        if not command or any(not isinstance(x, str) or not x for x in command):
            raise ValueError("command must be a nonempty argv list")
        self.timeout = timeout_value(timeout)
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, bufsize=0)
        assert self.process.stdin is not None
        os.set_blocking(self.process.stdin.fileno(), False)
        self.messages: queue.Queue[bytes | Exception] = queue.Queue(maxsize=100)
        self.closed = False
        self.counter = 0
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self) -> None:
        assert self.process.stdout is not None
        while not self.closed:
            try:
                line = self.process.stdout.readline(MAX_FRAME_BYTES + 1)
            except (OSError, ValueError):
                return
            item: bytes | Exception = line
            if len(line) > MAX_FRAME_BYTES:
                item = TransportError("response_frame_too_large")
            elif not line:
                item = TransportError("upstream_eof")
            try:
                self.messages.put(item, timeout=self.timeout)
            except queue.Full:
                return
            if isinstance(item, Exception):
                return

    def _send(self, message: dict[str, Any]) -> None:
        if self.closed:
            raise TransportError("transport_closed")
        data = json.dumps(message, separators=(",", ":"), allow_nan=False).encode() + b"\n"
        if len(data) > MAX_FRAME_BYTES:
            raise ValueError("request_frame_too_large")
        assert self.process.stdin is not None
        deadline = time.monotonic() + self.timeout
        try:
            offset = 0
            while offset < len(data):
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not select.select([], [self.process.stdin], [], remaining)[1]:
                    self.close()
                    raise TransportError("upstream_write_timeout_outcome_unknown")
                try:
                    offset += os.write(self.process.stdin.fileno(), data[offset:])
                except BlockingIOError:
                    continue
        except (BrokenPipeError, OSError) as exc:
            raise TransportError("upstream_write_failed") from exc

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        self._send({"jsonrpc": "2.0", "method": method, **({"params": params} if params else {})})

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.counter += 1
        self._send({"jsonrpc": "2.0", "id": self.counter, "method": method,
                    **({"params": params} if params is not None else {})})
        deadline = time.monotonic() + self.timeout
        for _ in range(100):
            try:
                item = self.messages.get(timeout=max(0, deadline - time.monotonic()))
                if isinstance(item, Exception):
                    raise item
                message = loads(item)
                if (isinstance(message, dict) and message.get("jsonrpc") == "2.0"
                    and "method" in message and "id" not in message):
                    continue  # bounded unsolicited notifications, not tool responses
                return decode_response(item, self.counter)
            except queue.Empty as exc:
                self.close()
                raise TransportError("upstream_timeout_outcome_unknown") from exc
            except (ValueError, UnicodeError, TransportError) as exc:
                if isinstance(exc, ProtocolError):
                    raise
                self.close()
                if isinstance(exc, TransportError):
                    raise
                raise TransportError("invalid_json_response") from exc
        self.close()
        raise TransportError("too_many_upstream_notifications")

    def initialize(self) -> dict[str, Any]:
        response = self.request("initialize", {"protocolVersion": PROTOCOL_VERSION,
                                               "capabilities": {},
                                               "clientInfo": {"name": "mcp-faultlab", "version": "0.1.0"}})
        if response.get("protocolVersion") != PROTOCOL_VERSION:
            self.close()
            raise TransportError("unsupported_protocol_version")
        self.notify("notifications/initialized")
        return response

    def execute(self, call: Call) -> dict[str, Any]:
        return self.request("tools/call", {"name": call.tool, "arguments": call.arguments})

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=1)
        for stream in (self.process.stdin, self.process.stdout):
            if stream:
                stream.close()
        self.reader.join(timeout=1)

    def __enter__(self) -> StdioClient:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
