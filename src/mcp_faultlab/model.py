"""Serializable calls and deterministic rule selection."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .scenario import Rule, Scenario, ScenarioError, string
from .jsonutil import validate_value


@dataclass(frozen=True)
class Call:
    id: str
    tool: str
    arguments: dict[str, Any] = field(default_factory=dict)
    operation: str = "default"

    def __post_init__(self) -> None:
        for key in ("id", "tool", "operation"):
            string(getattr(self, key), f"call.{key}")
        if not isinstance(self.arguments, dict):
            raise ScenarioError("call.arguments must be an object")
        validate_value(self.arguments)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VirtualClock:
    """Injected elapsed milliseconds; never sleeps and is not wall-clock latency."""

    now_ms: int = 0

    def advance(self, milliseconds: int) -> None:
        if type(milliseconds) is not int or milliseconds < 0:
            raise ValueError("clock advance must be a nonnegative integer")
        self.now_ms += milliseconds


class Matcher:
    """Count every attempted call. First matching rule wins; each rule fires once.

    Tool-specific occurrences count attempts for that tool, including attempts
    whose arguments do not match. Wildcard occurrences count all tool attempts.
    """

    def __init__(self, scenario: Scenario):
        self.scenario = scenario
        self.total = 0
        self.counts: dict[str, int] = {}
        self.fired: set[str] = set()

    def select(self, call: Call) -> Rule | None:
        self.total += 1
        self.counts[call.tool] = self.counts.get(call.tool, 0) + 1
        for rule in self.scenario.rules:
            occurrence = self.total if rule.tool == "*" else self.counts[call.tool]
            if (rule.name not in self.fired and rule.tool in ("*", call.tool)
                and occurrence == rule.occurrence
                and all(k in call.arguments and call.arguments[k] == v
                        for k, v in rule.arguments.items())):
                self.fired.add(rule.name)
                return rule
        return None
