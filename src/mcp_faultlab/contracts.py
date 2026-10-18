"""Offline trace contracts. These audit trusted harness events; they are not a sandbox."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .scenario import fields, integer, string
from .trace import canonical


def validate_contracts(raw: Any) -> dict[str, Any]:
    d = fields(
        raw,
        {
            "allowed_tools",
            "side_effect_tools",
            "require_approval",
            "max_retries",
            "max_calls",
            "max_elapsed_ms",
        },
        "contracts",
    )
    for key in ("allowed_tools", "side_effect_tools"):
        if key in d:
            if not isinstance(d[key], list):
                raise ValueError(f"{key} must be a list")
            for item in d[key]:
                string(item, key)
    for key in ("max_retries", "max_calls", "max_elapsed_ms"):
        if key in d:
            integer(d[key], key)
    if "require_approval" in d and type(d["require_approval"]) is not bool:
        raise ValueError("require_approval must be a boolean")
    return d


def binding(call: dict[str, Any]) -> str:
    return canonical({k: call[k] for k in ("tool", "arguments", "operation")})


def evaluate(events: list[dict[str, Any]], contracts: dict[str, Any]) -> list[dict[str, Any]]:
    """Report all violations; enforcement belongs to the agent/tool host."""
    d = validate_contracts(contracts)
    violations: list[dict[str, Any]] = []
    calls: dict[str, dict[str, Any]] = {}
    attempts: Counter[tuple[str, str]] = Counter()
    dispatches: Counter[str] = Counter()
    approvals: set[str] = set()

    def fail(code: str, event: dict[str, Any], message: str) -> None:
        violations.append({"code": code, "seq": event["seq"], "message": message})

    for event in events:
        kind = event["kind"]
        if kind == "approval":
            approvals.add(binding(event["call"]))
        elif kind == "call":
            call = event["call"]
            calls[call["id"]] = call
            key = (call["operation"], call["tool"])
            attempts[key] += 1
            if "allowed_tools" in d and call["tool"] not in d["allowed_tools"]:
                fail("tool_not_allowed", event, f"Tool {call['tool']} is outside the allowlist")
            if "max_retries" in d and attempts[key] - 1 > d["max_retries"]:
                fail("retry_limit", event, f"Retry ceiling exceeded for {key}")
            if "max_calls" in d and len(calls) > d["max_calls"]:
                fail("call_budget", event, "Call budget exceeded")
        elif kind == "dispatch":
            call = calls[event["call_id"]]
            dispatches[call["id"]] += 1
            if dispatches[call["id"]] > 1:
                fail("duplicate_dispatch", event, "One logical call was dispatched more than once")
            if (
                d.get("require_approval", False)
                and call["tool"] in d.get("side_effect_tools", [])
                and binding(call) not in approvals
            ):
                fail(
                    "approval_missing", event, "No prior approval for this operation and arguments"
                )
    if events and "max_elapsed_ms" in d and events[-1]["time_ms"] > d["max_elapsed_ms"]:
        fail("time_budget", events[-1], "Injected virtual elapsed budget exceeded")
    return violations
