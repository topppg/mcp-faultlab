import io
import json
from pathlib import Path

import pytest

from mcp_faultlab.cli import main
from mcp_faultlab.engine import TransportError
from mcp_faultlab.proxy import ToolEndpoint, serve
from mcp_faultlab.scenario import Scenario
from mcp_faultlab.suite import run_suite
from mcp_faultlab.transport import decode_response


def test_all_example_expectations(tmp_path):
    result = run_suite(Path(__file__).parents[1] / "examples/suite.json", tmp_path)
    assert result["passed"]
    assert result["matched"] == result["total"] == 18


def test_cli_demo_exit_codes_and_reports(tmp_path, capsys):
    assert main(["demo", "--strategy", "safe", "--out", str(tmp_path / "safe")]) == 0
    assert main(["demo", "--strategy", "naive", "--out", str(tmp_path / "naive")]) == 1
    assert main(["demo", "--out", str(tmp_path / "comparison")]) == 0
    assert (tmp_path / "comparison/safe/report.html").exists()
    assert json.loads(capsys.readouterr().out.splitlines()[0])["passed"]


@pytest.mark.parametrize("payload", [b'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"ledger.charge","arguments":{"amount":NaN}}}',
                                   b'{"jsonrpc":"2.0","id":1,"id":2,"method":"ping"}'])
def test_invalid_wire_json_never_records_call(payload):
    endpoint = ToolEndpoint(Scenario("strict-json"))
    sink = io.BytesIO()
    serve(endpoint, io.BytesIO(payload + b"\n"), sink)
    assert json.loads(sink.getvalue())["error"]["code"] == -32700
    assert not endpoint.harness.events


def test_invalid_upstream_json_is_transport_failure():
    with pytest.raises(TransportError, match="invalid_json"):
        decode_response(b'{"jsonrpc":"2.0","id":1,"result":{"x":NaN}}', 1)


def test_unknown_contract_and_nonfinite_programmatic_scenario_fail():
    with pytest.raises(ValueError):
        Scenario.parse({"schema_version": 1, "name": "bad", "contracts": {"max_callz": 1}})
    with pytest.raises(ValueError):
        Scenario.parse({"schema_version": 1, "name": "bad", "rules": [
            {"name": "x", "fault": "stale", "value": {"x": float("nan")}}]})
