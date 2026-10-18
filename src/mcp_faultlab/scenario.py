"""Strict, versioned scenario documents. Unknown keys fail rather than silently doing nothing."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

FAULTS = frozenset(
    {
        "tool_error", "permission_denied", "rate_limit", "timeout", "malformed",
        "stale", "response_loss", "duplicate_execution", "crash",
    }
)


class ScenarioError(ValueError):
    """A scenario cannot be interpreted without ambiguity."""


def fields(value: Any, allowed: set[str], where: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) - allowed:
        raise ScenarioError(f"{where}: expected object with keys {sorted(allowed)}")
    return value


def integer(value: Any, where: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ScenarioError(f"{where}: expected integer >= {minimum}")
    return value


def string(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ScenarioError(f"{where}: expected nonempty string")
    return value


def reject_constant(value: str) -> None:
    raise ScenarioError(f"non-finite JSON number: {value}")


@dataclass(frozen=True)
class Rule:
    name: str
    tool: str
    occurrence: int
    fault: str
    arguments: dict[str, Any] = field(default_factory=dict)
    value: Any = None
    delay_ms: int = 0

    @classmethod
    def parse(cls, raw: Any) -> Rule:
        d = fields(raw, {"name", "tool", "occurrence", "fault", "arguments", "value", "delay_ms"}, "rule")
        name = string(d.get("name"), "rule.name")
        fault = string(d.get("fault"), "rule.fault")
        if fault not in FAULTS:
            raise ScenarioError(f"rule {name}: unknown fault {fault!r}")
        args = d.get("arguments", {})
        if not isinstance(args, dict):
            raise ScenarioError("rule.arguments: expected object")
        return cls(name, string(d.get("tool", "*"), "rule.tool"),
                   integer(d.get("occurrence", 1), "rule.occurrence", 1), fault,
                   args, d.get("value"), integer(d.get("delay_ms", 0), "rule.delay_ms"))


@dataclass(frozen=True)
class Scenario:
    name: str
    rules: tuple[Rule, ...] = ()
    contracts: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def parse(cls, raw: Any) -> Scenario:
        d = fields(raw, {"schema_version", "name", "rules", "contracts"}, "scenario")
        if type(d.get("schema_version")) is not int or d["schema_version"] != 1:
            raise ScenarioError("schema_version must be 1")
        rules = d.get("rules", [])
        if not isinstance(rules, list):
            raise ScenarioError("rules must be a list")
        parsed = tuple(Rule.parse(r) for r in rules)
        if len({r.name for r in parsed}) != len(parsed):
            raise ScenarioError("rule names must be unique")
        contracts = d.get("contracts", {})
        if not isinstance(contracts, dict):
            raise ScenarioError("contracts must be an object")
        from .contracts import validate_contracts

        validate_contracts(contracts)
        return cls(string(d.get("name"), "scenario.name"), parsed, contracts)

    @classmethod
    def load(cls, path: str | Path) -> Scenario:
        try:
            return cls.parse(json.loads(Path(path).read_text(), parse_constant=reject_constant))
        except json.JSONDecodeError as exc:
            raise ScenarioError(f"invalid scenario JSON: {exc.msg}") from exc
