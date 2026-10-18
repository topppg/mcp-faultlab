"""Scripted recovery strategies against synthetic data; no language model is involved."""

from __future__ import annotations

from typing import Any

from .contracts import evaluate
from .engine import Harness, Outcome
from .ledger import Ledger
from .model import Call
from .scenario import Scenario
from .trace import make_trace


def default_scenario() -> Scenario:
    return Scenario.parse(
        {
            "schema_version": 1,
            "name": "confirmation-lost-after-charge",
            "rules": [
                {
                    "name": "lose-first-confirmation",
                    "tool": "ledger.charge",
                    "fault": "response_loss",
                    "delay_ms": 250,
                }
            ],
            "contracts": {
                "allowed_tools": ["ledger.charge", "ledger.lookup"],
                "side_effect_tools": ["ledger.charge"],
                "require_approval": True,
                "max_retries": 1,
                "max_calls": 3,
                "max_elapsed_ms": 1000,
            },
        }
    )


def _entry_valid(entry: Any) -> bool:
    return (
        isinstance(entry, dict)
        and entry.get("operation") == "order-001"
        and type(entry.get("amount")) is int
        and entry["amount"] == 100
        and isinstance(entry.get("id"), str)
    )


def _confirmed(outcome: Outcome) -> bool:
    data = outcome.result.get("structuredContent") if outcome.ok else None
    return isinstance(data, dict) and _entry_valid(data.get("entry"))


def run_demo(strategy: str = "safe", scenario: Scenario | None = None) -> dict[str, Any]:
    if strategy not in {"safe", "naive"}:
        raise ValueError("strategy must be safe or naive")
    scenario = scenario or default_scenario()
    ledger = Ledger()
    harness = Harness(scenario, ledger)
    arguments = {"operation": "order-001", "amount": 100}
    if strategy == "safe":
        arguments["idempotency_key"] = "order-001"
    counter = 0

    def invoke(tool: str, args: dict[str, Any]) -> Outcome:
        nonlocal counter
        counter += 1
        call = Call(str(counter), tool, args, operation="order-001")
        if tool == "ledger.charge":
            harness.approve(call)
        return harness.invoke(call)

    first = invoke("ledger.charge", arguments)
    completed = _confirmed(first)
    terminal = first.failure == "transport_closed" or (
        first.result is not None
        and first.result.get("isError")
        and first.result.get("structuredContent", {}).get("code") == "permission_denied"
    )
    if not completed and not terminal:
        if strategy == "safe" and (first.uncertain or first.ok):
            lookup = invoke("ledger.lookup", {"operation": "order-001"})
            data = lookup.result.get("structuredContent") if lookup.ok else None
            entries = data.get("entries") if isinstance(data, dict) else None
            completed = isinstance(entries, list) and len(entries) == 1 and _entry_valid(entries[0])
        if not completed:
            completed = _confirmed(invoke("ledger.charge", arguments))
    trace = make_trace(harness)
    violations = evaluate(harness.events, scenario.contracts)
    snapshot = ledger.snapshot()
    metrics = {
        "calls": counter,
        "dispatches": sum(e["kind"] == "dispatch" for e in harness.events),
        "virtual_elapsed_ms": harness.clock.now_ms,
        "completed": completed,
        "side_effects": snapshot["side_effects"],
        "duplicate_effects": snapshot["duplicate_effects"],
        "contract_violations": len(violations),
    }
    return {
        "scenario": scenario.name,
        "strategy": strategy,
        "metrics": metrics,
        "passed": completed and not violations and snapshot["duplicate_effects"] == 0,
        "violations": violations,
        "ledger": snapshot,
        "trace": trace,
    }


def compare(scenario: Scenario | None = None) -> dict[str, Any]:
    return {strategy: run_demo(strategy, scenario) for strategy in ("naive", "safe")}
