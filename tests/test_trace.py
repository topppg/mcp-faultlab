import copy

import pytest

from mcp_faultlab.engine import Harness
from mcp_faultlab.model import Call
from mcp_faultlab.scenario import Scenario
from mcp_faultlab.trace import Replay, digest, make_trace, read_trace, validate_trace, write_trace


class Backend:
    def execute(self, call):
        return {"content": [{"type": "text", "text": "synthetic"}]}


def record():
    h = Harness(Scenario("capture"), Backend())
    h.invoke(Call("1", "read", {"x": 1}))
    return make_trace(h)


def test_replay_round_trip_and_exact_arguments(tmp_path):
    trace = record()
    path = tmp_path / "trace.json"
    write_trace(path, trace)
    replay = Replay(read_trace(path))
    with pytest.raises(ValueError, match="diverged"):
        replay.invoke(Call("1", "read", {"x": 2}))
    assert replay.invoke(Call("1", "read", {"x": 1})).ok
    replay.assert_complete()
    with pytest.raises(ValueError, match="diverged"):
        replay.invoke(Call("2", "read"))


def test_hash_is_deterministic_and_mutation_detected():
    assert record() == record()
    trace = record()
    trace["events"][0]["call"]["tool"] = "tampered"
    with pytest.raises(ValueError, match="SHA-256"):
        validate_trace(trace)


def test_hash_is_not_a_substitute_for_structural_validation():
    trace = copy.deepcopy(record())
    trace["events"][-1]["call_id"] = "wrong"
    trace["sha256"] = digest({k: v for k, v in trace.items() if k != "sha256"})
    with pytest.raises(ValueError, match="matching"):
        validate_trace(trace)


def test_trace_size_limit(tmp_path):
    path = tmp_path / "big"
    path.write_text("x" * 101)
    with pytest.raises(ValueError, match="size"):
        read_trace(path, max_bytes=100)


@pytest.mark.parametrize(
    "event",
    [
        {"kind": "dispatch", "call_id": "unknown"},
        {"kind": "dispatch", "call_id": []},
        {"kind": "invented"},
        {"kind": ["not-a-kind"]},
        {"kind": "approval", "call": []},
    ],
)
def test_rehashed_invalid_trace_events_are_rejected(event):
    body = {
        "trace_version": 1,
        "scenario": {"name": "untrusted", "rules": [], "contracts": {}},
        "events": [{"seq": 0, "time_ms": 0, **event}],
    }
    with pytest.raises(ValueError):
        validate_trace({**body, "sha256": digest(body)})


def test_invalid_outcome_payload_rejected_even_with_valid_hash():
    trace = record()
    trace["events"][-1]["outcome"]["result"] = []
    trace["sha256"] = digest({k: v for k, v in trace.items() if k != "sha256"})
    with pytest.raises(ValueError, match="outcome"):
        validate_trace(trace)
