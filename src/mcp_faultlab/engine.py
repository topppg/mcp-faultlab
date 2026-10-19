"""Fault engine. Results keep MCP tool errors distinct from transport failures."""

from __future__ import annotations

import copy
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from .model import Call, Matcher, VirtualClock
from .scenario import Scenario


class TransportError(RuntimeError):
    """No reliable response was received; upstream work might have committed."""


class Backend(Protocol):
    def execute(self, call: Call) -> dict[str, Any]: ...


@dataclass(frozen=True)
class Outcome:
    result: dict[str, Any] | None = None
    failure: str | None = None
    uncertain: bool = False

    @property
    def ok(self) -> bool:
        return self.result is not None and not self.result.get("isError", False)


def tool_error(code: str, message: str, **data: Any) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": message}], "isError": True,
            "structuredContent": {"code": code, **data}}


class Harness:
    def __init__(self, scenario: Scenario, backend: Backend):
        self.scenario = scenario
        self.backend = backend
        self.matcher = Matcher(scenario)
        self.clock = VirtualClock()
        self.events: list[dict[str, Any]] = []
        self.ids: set[str] = set()

    def emit(self, kind: str, **data: Any) -> None:
        self.events.append({"seq": len(self.events), "time_ms": self.clock.now_ms,
                            "kind": kind, **copy.deepcopy(data)})

    def invoke(self, call: Call) -> Outcome:
        if call.id in self.ids:
            raise ValueError(f"duplicate call id: {call.id}")
        self.ids.add(call.id)
        self.emit("call", call=call.to_dict())
        rule = self.matcher.select(call)
        if rule:
            self.clock.advance(rule.delay_ms)
            self.emit("fault", call_id=call.id, rule=rule.name, fault=rule.fault)
        if rule and rule.fault in {"tool_error", "permission_denied", "rate_limit"}:
            outcome = Outcome(result=tool_error(rule.fault, f"Injected {rule.fault}",
                                                retry_after_ms=rule.delay_ms))
        elif rule and rule.fault == "timeout":
            outcome = Outcome(failure="timeout", uncertain=False)
        elif rule:
            raise NotImplementedError(f"fault not implemented: {rule.fault}")
        else:
            outcome = self._execute(call)
        self.emit("outcome", call_id=call.id, outcome=asdict(outcome))
        return outcome

    def _execute(self, call: Call) -> Outcome:
        self.emit("dispatch", call_id=call.id)
        try:
            result = self.backend.execute(call)
        except TransportError as exc:
            return Outcome(failure=str(exc), uncertain=True)
        if not isinstance(result, dict):
            return Outcome(failure="invalid_backend_result", uncertain=True)
        return Outcome(result=copy.deepcopy(result))
