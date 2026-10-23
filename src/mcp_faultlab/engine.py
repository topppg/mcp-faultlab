"""Fault engine. Results keep MCP tool errors distinct from transport failures."""

from __future__ import annotations

import copy
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from .model import Call, Matcher, VirtualClock
from .scenario import Scenario


class TransportError(RuntimeError):
    """No reliable response was received; upstream work might have committed."""


class ProtocolError(TransportError):
    def __init__(self, error: dict[str, Any]):
        super().__init__("upstream_protocol_error")
        self.error = error


class Backend(Protocol):
    def execute(self, call: Call) -> dict[str, Any]: ...


@dataclass(frozen=True)
class Outcome:
    result: dict[str, Any] | None = None
    failure: str | None = None
    uncertain: bool = False
    protocol_error: dict[str, Any] | None = None

    @property
    def ok(self) -> bool:
        return self.result is not None and not self.result.get("isError", False)


def tool_error(code: str, message: str, **data: Any) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": message}],
        "isError": True,
        "structuredContent": {"code": code, **data},
    }


class Harness:
    def __init__(self, scenario: Scenario, backend: Backend):
        self.scenario = scenario
        self.backend = backend
        self.matcher = Matcher(scenario)
        self.clock = VirtualClock()
        self.events: list[dict[str, Any]] = []
        self.ids: set[str] = set()
        self.previous: dict[str, dict[str, Any]] = {}
        self.crashed = False

    def emit(self, kind: str, **data: Any) -> None:
        self.events.append(
            {
                "seq": len(self.events),
                "time_ms": self.clock.now_ms,
                "kind": kind,
                **copy.deepcopy(data),
            }
        )

    def approve(self, call: Call) -> None:
        """Record an approval from the trusted test driver, bound to exact arguments."""
        self.emit("approval", call=call.to_dict())

    def invoke(self, call: Call) -> Outcome:
        if call.id in self.ids:
            raise ValueError(f"duplicate call id: {call.id}")
        self.ids.add(call.id)
        self.emit("call", call=call.to_dict())
        rule = self.matcher.select(call)
        if rule:
            self.clock.advance(rule.delay_ms)
            self.emit("fault", call_id=call.id, rule=rule.name, fault=rule.fault)
        if self.crashed:
            outcome = Outcome(failure="transport_closed", uncertain=False)
        elif rule and rule.fault == "crash":
            self.crashed = True
            outcome = Outcome(failure="transport_closed", uncertain=False)
        elif rule and rule.fault in {"tool_error", "permission_denied", "rate_limit"}:
            outcome = Outcome(
                result=tool_error(
                    rule.fault, f"Injected {rule.fault}", retry_after_ms=rule.delay_ms
                )
            )
        elif rule and rule.fault == "timeout":
            outcome = Outcome(failure="timeout", uncertain=False)
        elif rule and rule.fault in {"malformed", "stale"}:
            old = copy.deepcopy(self.previous.get(call.tool))
            outcome = self._execute(call)
            if outcome.result is not None:
                result = copy.deepcopy(outcome.result)
                if rule.fault == "malformed":
                    result["structuredContent"] = ["invalid: expected a JSON object"]
                    outcome = Outcome(result=result)
                elif isinstance(rule.value, dict):
                    outcome = Outcome(result=copy.deepcopy(rule.value))
                elif old is not None:
                    outcome = Outcome(result=old)
                else:
                    outcome = Outcome(failure="no_stale_result_available", uncertain=True)
        elif rule and rule.fault == "response_loss":
            actual = self._execute(call)
            self.emit("response_discarded", call_id=call.id, upstream_ok=actual.ok)
            outcome = Outcome(failure="response_lost", uncertain=True)
        elif rule and rule.fault == "duplicate_execution":
            first = self._execute(call)
            if first.failure is None:
                outcome = self._execute(call)
            else:
                outcome = first
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
        except ProtocolError as exc:
            return Outcome(failure="upstream_protocol_error", protocol_error=exc.error)
        except TransportError as exc:
            return Outcome(failure=str(exc), uncertain=True)
        if not isinstance(result, dict):
            return Outcome(failure="invalid_backend_result", uncertain=True)
        if not result.get("isError", False):
            self.previous[call.tool] = copy.deepcopy(result)
        return Outcome(result=copy.deepcopy(result))
