"""Deterministic normalization for PyLabRobot observations."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from typing import Any

_TIMESTAMP_KEYS = frozenset({"time", "timestamp", "created_at", "updated_at"})
NORMALIZED_TIMESTAMP = "<normalized-runtime-timestamp>"


def normalize_json(value: Any, *, key: str | None = None) -> Any:
    """Return strict, deterministic JSON without runtime timestamps or non-finite numbers."""
    if key in _TIMESTAMP_KEYS and isinstance(value, (int, float, str)):
        return NORMALIZED_TIMESTAMP
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if math.isnan(value):
            return {"kind": "normalized_non_finite_float", "value": "NaN"}
        if math.isinf(value):
            return {
                "kind": "normalized_non_finite_float",
                "value": "Infinity" if value > 0 else "-Infinity",
            }
        return value
    if isinstance(value, Mapping):
        return {
            str(child_key): normalize_json(child_value, key=str(child_key))
            for child_key, child_value in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [normalize_json(item) for item in value]
    raise TypeError(f"PyLabRobot observation is not JSON-normalizable: {type(value).__name__}")


def normalize_console_output(stdout: str, stderr: str) -> dict[str, Any]:
    """Omit unstructured Chatterbox text while retaining deterministic capture evidence."""

    def describe(stream: str) -> dict[str, Any]:
        lines = [" ".join(line.split()) for line in stream.splitlines() if line.strip()]
        normalized = "\n".join(lines)
        return {
            "policy": "omitted_unstructured_console",
            "nonempty_line_count": len(lines),
            "normalized_sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        }

    return {"stdout": describe(stdout), "stderr": describe(stderr)}
