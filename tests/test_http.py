import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from mcp_faultlab.engine import TransportError
from mcp_faultlab.http_transport import JsonHttpClient
from mcp_faultlab.transport import PROTOCOL_VERSION


@pytest.fixture
def endpoint():
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            message = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            received.append((dict(self.headers), message))
            if "id" not in message:
                self.send_response(202)
                self.end_headers()
                return
            method = message["method"]
            if method == "slow":
                time.sleep(0.3)
            version = "wrong" if method == "wrong-version" else PROTOCOL_VERSION
            result = {"protocolVersion": version} if method == "initialize" else {"ok": True}
            body = json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream" if method == "sse" else "application/json")
            self.send_header("MCP-Session-Id", "test-session")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except BrokenPipeError:
                pass

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/mcp", received
    server.shutdown()
    server.server_close()
    thread.join(timeout=1)


def test_json_post_lifecycle_session_and_headers(endpoint):
    url, received = endpoint
    client = JsonHttpClient(url)
    assert client.initialize()["protocolVersion"] == PROTOCOL_VERSION
    assert client.request("tools/list")["ok"]
    assert received[-1][0]["MCP-Session-Id"] == "test-session"
    assert received[-1][0]["MCP-Protocol-Version"] == PROTOCOL_VERSION
    assert received[-1][1]["method"] == "tools/list"


def test_sse_is_rejected_explicitly(endpoint):
    with pytest.raises(TransportError, match="no_sse"):
        JsonHttpClient(endpoint[0]).request("sse")


def test_http_deadline(endpoint):
    start = time.monotonic()
    with pytest.raises(TransportError):
        JsonHttpClient(endpoint[0], timeout=0.05).request("slow")
    assert time.monotonic() - start < 1


@pytest.mark.parametrize("url", ["https://example.com/mcp", "http://localhost:3/mcp",
                                "http://192.0.2.1/mcp", "http://u:p@127.0.0.1/mcp",
                                "http://127.0.0.1/mcp?secret=x"])
def test_only_literal_loopback_without_credentials(url):
    with pytest.raises(ValueError):
        JsonHttpClient(url)


@pytest.mark.parametrize("protocol", ["HTTP/1.0", "HTTP/1.1"])
def test_deadline_interrupts_slow_drip_body_even_when_response_owns_socket(protocol):
    class Drip(BaseHTTPRequestHandler):
        protocol_version = protocol

        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            body = b'{"jsonrpc":"2.0","id":1,"result":{"ok":true}}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                for byte in body:
                    self.wfile.write(bytes([byte]))
                    self.wfile.flush()
                    time.sleep(0.025)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Drip)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        start = time.monotonic()
        with pytest.raises(TransportError):
            JsonHttpClient(f"http://127.0.0.1:{server.server_port}/mcp", timeout=0.1).request("x")
        assert time.monotonic() - start < 0.6
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)
