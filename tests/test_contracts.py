import pytest

from mcp_faultlab.contracts import evaluate, validate_contracts
from mcp_faultlab.engine import Harness
from mcp_faultlab.ledger import Ledger
from mcp_faultlab.model import Call
from mcp_faultlab.scenario import Scenario


def test_approval_must_precede_exact_side_effect_arguments():
    h = Harness(Scenario("approval"), Ledger())
    h.approve(Call("approval", "ledger.charge", {"operation": "o", "amount": 11}))
    h.invoke(Call("1", "ledger.charge", {"operation": "o", "amount": 10}))
    h.approve(Call("2", "ledger.charge", {"operation": "o", "amount": 10}))
    h.invoke(Call("2", "ledger.charge", {"operation": "o", "amount": 10}))
    violations = evaluate(h.events, {"side_effect_tools": ["ledger.charge"], "require_approval": True})
    assert [v["code"] for v in violations] == ["approval_missing"]


def test_allowlist_retry_and_budgets_are_independent():
    h = Harness(Scenario.parse({"schema_version": 1, "name": "budget", "rules": [
        {"name": "delay", "fault": "timeout", "delay_ms": 50}
    ]}), Ledger())
    h.invoke(Call("1", "ledger.read"))
    h.invoke(Call("2", "ledger.read"))
    codes = {v["code"] for v in evaluate(h.events, {
        "allowed_tools": [], "max_retries": 0, "max_calls": 1, "max_elapsed_ms": 40})}
    assert codes == {"tool_not_allowed", "retry_limit", "call_budget", "time_budget"}


@pytest.mark.parametrize("contracts", [{"max_calls": True}, {"max_retries": -1},
                                        {"allowed_tools": "read"}, {"typo": 1},
                                        {"require_approval": "true"}])
def test_invalid_contracts_fail_early(contracts):
    with pytest.raises(ValueError):
        validate_contracts(contracts)
