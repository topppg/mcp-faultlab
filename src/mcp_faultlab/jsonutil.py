"""Strict JSON boundaries: finite numbers, unique object keys, and JSON-native values."""

from __future__ import annotations

import json
import math
from typing import Any


def _constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number: {value}")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def loads(value: str | bytes) -> Any:
    try:
        decoded = json.loads(value, parse_constant=_constant, object_pairs_hook=_pairs)
        validate_value(decoded)
        return decoded
    except RecursionError as exc:
        raise ValueError("JSON exceeds supported nesting depth") from exc


def validate_value(value: Any, depth: int = 0) -> None:
    if depth > 100:
        raise ValueError("JSON exceeds supported nesting depth")
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    if isinstance(value, list):
        for item in value:
            validate_value(item, depth + 1)
        return
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        for item in value.values():
            validate_value(item, depth + 1)
        return
    raise ValueError("expected JSON-native values with finite numbers and string object keys")
