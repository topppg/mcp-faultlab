import pytest

from mcp_faultlab.engine import Harness
from mcp_faultlab.model import Call
from mcp_faultlab.scenario import Scenario


class Counter:
    def __init__(self):
        self.calls = 0

    def execute(self, call):
        self.calls += 1
        return {"content": [{"type": "text", "text": "ok"}], "isError": False}


def harness(fault, **kwargs):
    return Harness(Scenario.parse({"schema_version": 1, "name": "injection", "rules": [
        {"name": "first", "fault": fault, **kwargs}
    ]}), Counter())


@pytest.mark.parametrize("fault", ["tool_error", "permission_denied", "rate_limit"])
def test_tool_errors_do_not_dispatch(fault):
    h = harness(fault, delay_ms=75)
    outcome = h.invoke(Call("1", "write"))
    assert not outcome.ok
    assert outcome.result["isError"] is True
    assert outcome.failure is None
    assert h.backend.calls == 0
    assert h.clock.now_ms == 75
    assert h.invoke(Call("2", "write")).ok
    assert h.backend.calls == 1


def test_pre_execution_timeout_and_unique_ids():
    h = harness("timeout", delay_ms=400)
    outcome = h.invoke(Call("1", "write"))
    assert outcome.failure == "timeout"
    assert outcome.uncertain is False
    assert h.backend.calls == 0
    with pytest.raises(ValueError, match="duplicate"):
        h.invoke(Call("1", "write"))
