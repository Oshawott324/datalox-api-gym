"""File-system helpers for world specs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORLD_SPECS_ROOT = PROJECT_ROOT / "worlds"


def world_spec_path(world_dir: str) -> Path:
    """Return the spec path for a root-level world directory."""
    return WORLD_SPECS_ROOT / world_dir / "spec.json"


def load_world_spec(world_dir: str) -> dict[str, Any]:
    """Load a root-level world spec by directory name."""
    return json.loads(world_spec_path(world_dir).read_text(encoding="utf-8"))
