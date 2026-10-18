import pytest

from mcp_faultlab.model import Call, Matcher, VirtualClock
from mcp_faultlab.scenario import Scenario


def test_occurrences_count_attempts_before_argument_filter():
    scenario = Scenario.parse(
        {
            "schema_version": 1,
            "name": "match",
            "rules": [
                {
                    "name": "second",
                    "tool": "read",
                    "occurrence": 2,
                    "fault": "timeout",
                    "arguments": {"account": "a"},
                },
                {"name": "third-global", "tool": "*", "occurrence": 3, "fault": "crash"},
            ],
        }
    )
    matcher = Matcher(scenario)
    assert matcher.select(Call("1", "read", {"account": "b"})) is None
    assert matcher.select(Call("2", "read", {"account": "a"})).name == "second"
    assert matcher.select(Call("3", "write")).name == "third-global"
    assert matcher.select(Call("4", "read", {"account": "a"})) is None


def test_first_rule_wins_and_is_consumed():
    s = Scenario.parse(
        {
            "schema_version": 1,
            "name": "overlap",
            "rules": [{"name": "a", "fault": "timeout"}, {"name": "b", "fault": "crash"}],
        }
    )
    matcher = Matcher(s)
    assert matcher.select(Call("1", "read")).name == "a"
    assert matcher.fired == {"a"}


def test_virtual_clock_never_moves_backwards():
    clock = VirtualClock()
    clock.advance(100)
    assert clock.now_ms == 100
    with pytest.raises(ValueError):
        clock.advance(-1)
