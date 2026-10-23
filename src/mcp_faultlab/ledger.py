"""Synthetic, in-memory payment ledger. No money, network, or customer data."""

from __future__ import annotations

import copy
import json
from collections import Counter
from typing import Any

from .engine import tool_error
from .model import Call


def result(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": json.dumps(data, sort_keys=True)}],
        "structuredContent": copy.deepcopy(data),
        "isError": False,
    }


TOOLS = [
    {
        "name": "ledger.charge",
        "description": "Commit a synthetic charge in an in-memory ledger",
        "inputSchema": {
            "type": "object",
            "required": ["operation", "amount"],
            "properties": {
                "operation": {"type": "string", "minLength": 1},
                "amount": {"type": "integer", "minimum": 1},
                "idempotency_key": {"type": "string", "minLength": 1},
            },
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": True},
    },
    {
        "name": "ledger.lookup",
        "description": "Reconcile charges by operation",
        "inputSchema": {
            "type": "object",
            "required": ["operation"],
            "properties": {"operation": {"type": "string", "minLength": 1}},
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "ledger.read",
        "description": "Read the synthetic ledger snapshot",
        "inputSchema": {"type": "object", "additionalProperties": False},
        "annotations": {"readOnlyHint": True},
    },
]


class Ledger:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []
        self.keys: dict[str, dict[str, Any]] = {}

    def execute(self, call: Call) -> dict[str, Any]:
        args = call.arguments
        if call.tool == "ledger.read" and not args:
            return result(self.snapshot())
        if call.tool == "ledger.lookup":
            if set(args) != {"operation"} or not self._text(args["operation"]):
                return tool_error("invalid_arguments", "operation must be a nonempty string")
            return result(
                {
                    "entries": [
                        copy.deepcopy(e)
                        for e in self.entries
                        if e["operation"] == args["operation"]
                    ]
                }
            )
        if call.tool != "ledger.charge":
            return tool_error("unknown_tool", f"Unknown synthetic tool: {call.tool}")
        if (
            set(args) - {"operation", "amount", "idempotency_key"}
            or not self._text(args.get("operation"))
            or type(args.get("amount")) is not int
            or args["amount"] <= 0
            or ("idempotency_key" in args and not self._text(args["idempotency_key"]))
        ):
            return tool_error(
                "invalid_arguments", "charge requires operation and positive integer amount"
            )
        key = args.get("idempotency_key")
        if key in self.keys:
            previous = self.keys[key]
            if (previous["operation"], previous["amount"]) != (args["operation"], args["amount"]):
                return tool_error("idempotency_conflict", "Key already belongs to another request")
            return result({"entry": previous, "deduplicated": True})
        entry = {
            "id": f"charge-{len(self.entries) + 1}",
            "operation": args["operation"],
            "amount": args["amount"],
        }
        self.entries.append(entry)
        if key is not None:
            self.keys[key] = entry
        return result({"entry": entry, "deduplicated": False})

    @staticmethod
    def _text(value: Any) -> bool:
        return isinstance(value, str) and bool(value.strip())

    def snapshot(self) -> dict[str, Any]:
        counts = Counter(e["operation"] for e in self.entries)
        return {
            "entries": copy.deepcopy(self.entries),
            "side_effects": len(self.entries),
            "duplicate_effects": sum(max(0, count - 1) for count in counts.values()),
            "total_amount": sum(e["amount"] for e in self.entries),
        }
