import pytest

from mcp_faultlab.scenario import Scenario, ScenarioError


def test_valid_scenario():
    s = Scenario.parse({"schema_version": 1, "name": "timeout", "rules": [
        {"name": "first-read", "tool": "read", "fault": "timeout", "delay_ms": 50}
    ]})
    assert s.rules[0].delay_ms == 50


@pytest.mark.parametrize("patch", [
    {"schema_version": True}, {"schema_version": 2}, {"unknown": 1},
    {"rules": {}}, {"name": ""}, {"contracts": []},
    {"rules": [{"name": "x", "fault": "typo"}]},
    {"rules": [{"name": "x", "fault": "timeout", "occurrence": 0}]},
    {"rules": [{"name": "x", "fault": "timeout", "delay_ms": True}]},
    {"rules": [{"name": "x", "fault": "timeout", "arguments": []}]},
])
def test_invalid_scenario(patch):
    with pytest.raises(ScenarioError):
        Scenario.parse({"schema_version": 1, "name": "test", **patch})


def test_nonfinite_json(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('{"schema_version": 1, "name": "bad", "contracts": {"budget": NaN}}')
    with pytest.raises(ScenarioError):
        Scenario.load(path)
