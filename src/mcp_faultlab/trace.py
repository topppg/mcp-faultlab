"""Canonical trace hashing and exact ordered replay, without re-executing tools."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from .engine import Harness, Outcome
from .jsonutil import loads
from .model import Call
from .scenario import FAULTS, Scenario


def canonical(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def make_trace(harness: Harness) -> dict[str, Any]:
    from dataclasses import asdict

    body = {
        "trace_version": 1,
        "scenario": asdict(harness.scenario),
        "events": copy.deepcopy(harness.events),
    }
    return {**body, "sha256": digest(body)}


def validate_trace(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict) or set(raw) != {"trace_version", "scenario", "events", "sha256"}:
        raise ValueError("invalid trace envelope")
    body = {key: value for key, value in raw.items() if key != "sha256"}
    if (
        type(raw["trace_version"]) is not int
        or raw["trace_version"] != 1
        or raw["sha256"] != digest(body)
    ):
        raise ValueError("trace version or SHA-256 mismatch")
    if not isinstance(raw["events"], list):
        raise ValueError("trace events must be a list")
    scenario = loads(canonical(raw["scenario"]))
    if not isinstance(scenario, dict):
        raise ValueError("trace scenario must be an object")
    Scenario.parse({"schema_version": 1, **scenario})
    outstanding: set[str] = set()
    seen: set[str] = set()
    previous_time = 0

    def parse_call(value: Any) -> Call:
        if not isinstance(value, dict) or set(value) != {"id", "tool", "arguments", "operation"}:
            raise ValueError("invalid trace call payload")
        return Call(**value)

    for i, event in enumerate(raw["events"]):
        if (
            not isinstance(event, dict)
            or type(event.get("seq")) is not int
            or event.get("seq") != i
        ):
            raise ValueError("trace sequence is not contiguous")
        time = event.get("time_ms")
        if type(time) is not int or time < previous_time:
            raise ValueError("trace time is invalid")
        previous_time = time
        kind = event.get("kind")
        payloads = {
            "call": {"call"},
            "approval": {"call"},
            "dispatch": {"call_id"},
            "fault": {"call_id", "rule", "fault"},
            "response_discarded": {"call_id", "upstream_ok"},
            "outcome": {"call_id", "outcome"},
        }
        if (
            not isinstance(kind, str)
            or kind not in payloads
            or set(event) != {"seq", "time_ms", "kind"} | payloads[kind]
        ):
            raise ValueError("invalid trace event kind or fields")
        if kind == "approval":
            parse_call(event["call"])
        elif kind == "call":
            call = parse_call(event["call"])
            if call.id in seen or outstanding:
                raise ValueError("trace calls must be unique and sequential")
            seen.add(call.id)
            outstanding.add(call.id)
        elif kind in {"dispatch", "fault", "response_discarded"}:
            if not isinstance(event.get("call_id"), str) or event["call_id"] not in outstanding:
                raise ValueError("event has no matching outstanding call")
            if kind == "fault" and (
                not isinstance(event["fault"], str)
                or event["fault"] not in FAULTS
                or not isinstance(event["rule"], str)
            ):
                raise ValueError("invalid fault event")
            if kind == "response_discarded" and type(event["upstream_ok"]) is not bool:
                raise ValueError("invalid response-discard event")
        elif kind == "outcome":
            if not isinstance(event.get("call_id"), str) or event["call_id"] not in outstanding:
                raise ValueError("outcome has no matching call")
            value = event["outcome"]
            if not isinstance(value, dict) or set(value) != {
                "result",
                "failure",
                "uncertain",
                "protocol_error",
            }:
                raise ValueError("invalid outcome fields")
            outcome = Outcome(**value)
            if (
                (outcome.result is None) == (outcome.failure is None)
                or (outcome.result is not None and not isinstance(outcome.result, dict))
                or (outcome.failure is not None and not isinstance(outcome.failure, str))
                or type(outcome.uncertain) is not bool
            ):
                raise ValueError("invalid outcome payload")
            if outcome.protocol_error is not None:
                error = outcome.protocol_error
                if (
                    not isinstance(error, dict)
                    or type(error.get("code")) is not int
                    or not isinstance(error.get("message"), str)
                    or outcome.failure is None
                ):
                    raise ValueError("invalid protocol error payload")
            outstanding.remove(event["call_id"])
    if outstanding:
        raise ValueError("trace ends with an incomplete call")
    return copy.deepcopy(raw)


def write_trace(path: str | Path, trace: dict[str, Any]) -> None:
    validate_trace(trace)
    Path(path).write_text(json.dumps(trace, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def read_trace(path: str | Path, max_bytes: int = 10_000_000) -> dict[str, Any]:
    with Path(path).open("rb") as handle:
        data = handle.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError("trace exceeds size limit")
    return validate_trace(loads(data))


class Replay:
    """Exact replay of captured calls and outcomes, including call IDs and arguments."""

    def __init__(self, trace: dict[str, Any]):
        data = validate_trace(trace)
        self.calls = [e["call"] for e in data["events"] if e["kind"] == "call"]
        self.outcomes = [e["outcome"] for e in data["events"] if e["kind"] == "outcome"]
        self.position = 0

    def invoke(self, call: Call) -> Outcome:
        if self.position >= len(self.calls) or call.to_dict() != self.calls[self.position]:
            raise ValueError(f"replay diverged at call {self.position}")
        outcome = Outcome(**copy.deepcopy(self.outcomes[self.position]))
        self.position += 1
        return outcome

    def assert_complete(self) -> None:
        if self.position != len(self.calls):
            raise ValueError("replay did not consume every recorded call")
