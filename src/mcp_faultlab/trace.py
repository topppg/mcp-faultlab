"""Canonical trace hashing and exact ordered replay, without re-executing tools."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from .engine import Harness, Outcome
from .model import Call


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def make_trace(harness: Harness) -> dict[str, Any]:
    from dataclasses import asdict

    body = {"trace_version": 1, "scenario": asdict(harness.scenario),
            "events": copy.deepcopy(harness.events)}
    return {**body, "sha256": digest(body)}


def validate_trace(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict) or set(raw) != {"trace_version", "scenario", "events", "sha256"}:
        raise ValueError("invalid trace envelope")
    body = {key: value for key, value in raw.items() if key != "sha256"}
    if raw["trace_version"] != 1 or raw["sha256"] != digest(body):
        raise ValueError("trace version or SHA-256 mismatch")
    if not isinstance(raw["events"], list):
        raise ValueError("trace events must be a list")
    outstanding: set[str] = set()
    seen: set[str] = set()
    previous_time = 0
    for i, event in enumerate(raw["events"]):
        if not isinstance(event, dict) or event.get("seq") != i:
            raise ValueError("trace sequence is not contiguous")
        time = event.get("time_ms")
        if type(time) is not int or time < previous_time:
            raise ValueError("trace time is invalid")
        previous_time = time
        if event.get("kind") == "call":
            call = Call(**event["call"])
            if call.id in seen or outstanding:
                raise ValueError("trace calls must be unique and sequential")
            seen.add(call.id)
            outstanding.add(call.id)
        elif event.get("kind") == "outcome":
            if event.get("call_id") not in outstanding:
                raise ValueError("outcome has no matching call")
            Outcome(**event["outcome"])
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
    return validate_trace(json.loads(data))


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
