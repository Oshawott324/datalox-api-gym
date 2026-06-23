"""Shared state-backend helpers for API Gym worlds."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path


def connect_sqlite(db_path: Path) -> sqlite3.Connection:
    """Open a SQLite database with API Gym world defaults."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ensure_run_subdirs(run_dir: Path) -> dict[str, Path]:
    """Create standard run subdirectories used by adapters and exports."""
    run_dir.mkdir(parents=True, exist_ok=True)
    artifacts = run_dir / "artifacts"
    traces = run_dir / "traces"
    artifacts.mkdir(exist_ok=True)
    traces.mkdir(exist_ok=True)
    return {"artifacts": artifacts, "traces": traces}


def resolve_state_db_path_from_metadata(run_dir: Path, *, metadata_name: str) -> Path:
    """Resolve a run-local SQLite state path from run metadata."""
    run_dir = run_dir.resolve()
    metadata_path = run_dir / metadata_name
    if not metadata_path.exists():
        raise FileNotFoundError(f"Missing {metadata_name} in run directory: {run_dir}")

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if not isinstance(metadata, dict):
        raise ValueError(f"{metadata_name} must contain a JSON object.")

    state_db = metadata.get("state_db")
    if not isinstance(state_db, str) or not state_db:
        raise ValueError(f"{metadata_name} must contain a non-empty state_db string.")

    state_path = Path(state_db)
    if state_path.name != state_db:
        raise ValueError(f"{metadata_name} state_db must be a file name inside the run directory.")

    db_path = run_dir / state_path
    if not db_path.exists():
        raise FileNotFoundError(f"Missing state database at {db_path}")
    return db_path
