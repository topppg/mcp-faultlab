import pytest

from mcp_faultlab.demo import compare, run_demo
from mcp_faultlab.scenario import Scenario
from mcp_faultlab.trace import Replay


def test_lost_confirmation_exposes_duplicate_side_effects():
    comparison = compare()
    assert comparison["naive"]["metrics"]["duplicate_effects"] == 1
    assert comparison["naive"]["metrics"]["side_effects"] == 2
    assert not comparison["naive"]["passed"]
    assert comparison["safe"]["metrics"]["duplicate_effects"] == 0
    assert comparison["safe"]["metrics"]["side_effects"] == 1
    assert comparison["safe"]["passed"]
    assert comparison["safe"]["metrics"]["virtual_elapsed_ms"] == 250
    assert comparison == compare()
    Replay(comparison["safe"]["trace"])


@pytest.mark.parametrize(
    "fault,effects,completed",
    [
        ("timeout", 1, True),
        ("rate_limit", 1, True),
        ("tool_error", 1, True),
        ("malformed", 1, True),
        ("response_loss", 1, True),
        ("duplicate_execution", 1, True),
        ("permission_denied", 0, False),
        ("crash", 0, False),
    ],
)
def test_safe_strategy_bounds_side_effects(fault, effects, completed):
    scenario = Scenario.parse(
        {"schema_version": 1, "name": fault, "rules": [{"name": "inject", "fault": fault}]}
    )
    report = run_demo("safe", scenario)
    assert report["metrics"]["side_effects"] == effects
    assert report["metrics"]["completed"] == completed
    assert report["metrics"]["calls"] <= 3
