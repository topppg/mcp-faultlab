"""Loopback-only JSON POST upstream adapter, pinned to MCP 2025-11-25.

This deliberately rejects SSE and is not a full Streamable HTTP implementation.
It opens no listening socket, follows no redirects, and accepts no credentials.
"""

from __future__ import annotations

import http.client
import ipaddress
import json
import socket
import threading
from typing import Any
from urllib.parse import urlsplit

from .engine import TransportError
from .model import Call
from .transport import MAX_FRAME_BYTES, PROTOCOL_VERSION, decode_response, timeout_value


class JsonHttpClient:
    def __init__(self, url: str, timeout: float = 5.0):
        parsed = urlsplit(url)
        try:
            loopback = ipaddress.ip_address(parsed.hostname or "").is_loopback
        except ValueError:
            loopback = False
        if (
            parsed.scheme != "http"
            or not loopback
            or parsed.username
            or parsed.password
            or parsed.fragment
            or parsed.query
        ):
            raise ValueError(
                "HTTP upstream requires a literal loopback http URL without credentials/query"
            )
        self.host = parsed.hostname
        self.port = parsed.port or 80
        self.path = parsed.path or "/mcp"
        self.timeout = timeout_value(timeout)
        self.session: str | None = None
        self.counter = 0

    def _post(self, message: dict[str, Any]) -> bytes:
        body = json.dumps(message, allow_nan=False).encode()
        if len(body) > MAX_FRAME_BYTES:
            raise ValueError("request_frame_too_large")
        connection = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)
        expired = threading.Event()
        connected_socket: list[socket.socket] = []

        def expire() -> None:
            expired.set()
            for active_socket in connected_socket:
                try:
                    active_socket.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            connection.close()

        timer = threading.Timer(self.timeout, expire)
        timer.daemon = True
        timer.start()
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": PROTOCOL_VERSION,
        }
        if self.session:
            headers["MCP-Session-Id"] = self.session
        try:
            connection.connect()
            assert connection.sock is not None
            connected_socket.append(connection.sock)
            if expired.is_set():
                raise TransportError("http_deadline_outcome_unknown")
            connection.request("POST", self.path, body=body, headers=headers)
            response = connection.getresponse()
            if response.status == 202 and "id" not in message:
                return b""
            if response.status != 200:
                raise TransportError(f"http_status_{response.status}_outcome_unknown")
            if response.getheader("Content-Type", "").split(";")[0].strip() != "application/json":
                raise TransportError("unsupported_http_content_type_no_sse_support")
            declared = response.getheader("Content-Length")
            if declared is not None and (not declared.isdigit() or int(declared) > MAX_FRAME_BYTES):
                raise TransportError("response_frame_too_large_or_invalid_length")
            data = response.read(MAX_FRAME_BYTES + 1)
            if len(data) > MAX_FRAME_BYTES:
                raise TransportError("response_frame_too_large")
            if expired.is_set():
                raise TransportError("http_deadline_outcome_unknown")
            session = response.getheader("MCP-Session-Id")
            if session:
                if len(session) > 512 or any(not 0x21 <= ord(c) <= 0x7E for c in session):
                    raise TransportError("invalid_http_session_id")
                self.session = session
            return data
        except (OSError, http.client.HTTPException) as exc:
            raise TransportError("http_transport_failure_outcome_unknown") from exc
        finally:
            timer.cancel()
            connection.close()

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.counter += 1
        raw = self._post(
            {
                "jsonrpc": "2.0",
                "id": self.counter,
                "method": method,
                **({"params": params} if params is not None else {}),
            }
        )
        return decode_response(raw, self.counter)

    def initialize(self) -> dict[str, Any]:
        response = self.request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "mcp-faultlab", "version": "0.1.0"},
            },
        )
        if response.get("protocolVersion") != PROTOCOL_VERSION:
            raise TransportError("unsupported_protocol_version")
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return response

    def execute(self, call: Call) -> dict[str, Any]:
        return self.request("tools/call", {"name": call.tool, "arguments": call.arguments})

    def close(self) -> None:
        """Connections are per-request. Session DELETE is intentionally not implemented."""

    def __enter__(self) -> JsonHttpClient:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
