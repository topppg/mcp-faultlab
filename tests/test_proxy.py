import json
import sys

import pytest

from mcp_faultlab.engine import TransportError
from mcp_faultlab.model import Call
from mcp_faultlab.proxy import ToolEndpoint
from mcp_faultlab.scenario import Scenario
from mcp_faultlab.trace import read_trace
from mcp_faultlab.transport import PROTOCOL_VERSION, StdioClient


def test_reference_server_real_mcp_lifecycle():
    with StdioClient([sys.executable, "-m", "mcp_faultlab", "reference-server"]) as client:
        assert client.initialize()["protocolVersion"] == PROTOCOL_VERSION
        assert len(client.request("tools/list")["tools"]) == 3
        result = client.execute(Call("charge", "ledger.charge", {"operation": "o", "amount": 10}))
        assert result["structuredContent"]["entry"]["amount"] == 10


def test_proxy_roundtrip_and_lost_response_preserve_trace(tmp_path):
    scenario = tmp_path / "scenario.json"
    trace = tmp_path / "trace.json"
    scenario.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": "loss",
                "rules": [{"name": "drop", "tool": "ledger.charge", "fault": "response_loss"}],
            }
        )
    )
    command = [
        sys.executable,
        "-m",
        "mcp_faultlab",
        "proxy",
        "--scenario",
        str(scenario),
        "--trace",
        str(trace),
        "--",
        sys.executable,
        "-m",
        "mcp_faultlab",
        "reference-server",
    ]
    with StdioClient(command) as client:
        client.initialize()
        assert len(client.request("tools/list")["tools"]) == 3
        with pytest.raises(TransportError, match="eof"):
            client.execute(Call("1", "ledger.charge", {"operation": "o", "amount": 10}))
        client.process.wait(timeout=2)
    events = read_trace(trace)["events"]
    assert next(e for e in events if e["kind"] == "response_discarded")["upstream_ok"]
    assert events[-1]["outcome"]["uncertain"]


def test_endpoint_requires_handshake_and_rejects_wrong_version():
    endpoint = ToolEndpoint(Scenario("test"))
    assert (
        endpoint.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["error"]["code"]
        == -32002
    )
    error = endpoint.handle(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "initialize",
            "params": {"protocolVersion": "2026-07-28"},
        }
    )
    assert error["error"]["code"] == -32602
