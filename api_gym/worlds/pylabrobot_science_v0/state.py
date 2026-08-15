"""SQLite-backed episode state shared by the science workflow families."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


STATE_DB_NAME = "state.sqlite"
RUN_METADATA_NAME = "run.json"
TASK_NAME = "task.json"
CONTRACT_NAME = "contract.json"


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def resolve_state_db_path(run_dir: Path) -> Path:
    metadata_path = run_dir.resolve() / RUN_METADATA_NAME
    if not metadata_path.exists():
        raise FileNotFoundError(f"Missing {RUN_METADATA_NAME}: {metadata_path}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    state_path = run_dir.resolve() / str(metadata["state_db"])
    if not state_path.exists():
        raise FileNotFoundError(f"Missing state database: {state_path}")
    return state_path


def initialize_db(db_path: Path, initial_state: dict[str, Any]) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.execute(
            "INSERT INTO snapshot(singleton, state_json) VALUES (1, ?)",
            (dumps_json(initial_state),),
        )


def load_state(conn: sqlite3.Connection) -> dict[str, Any]:
    row = conn.execute("SELECT state_json FROM snapshot WHERE singleton = 1").fetchone()
    if row is None:
        raise ValueError("Episode snapshot is missing.")
    return loads_json(str(row[0]))


def save_state(conn: sqlite3.Connection, state: dict[str, Any]) -> None:
    conn.execute(
        "UPDATE snapshot SET state_json = ? WHERE singleton = 1",
        (dumps_json(state),),
    )


def insert_event(
    conn: sqlite3.Connection,
    *,
    operation: str,
    time_s: float,
    payload: dict[str, Any] | None = None,
) -> int:
    cursor = conn.execute(
        "INSERT INTO events(operation, time_s, payload_json) VALUES (?, ?, ?)",
        (operation, time_s, dumps_json(payload or {})),
    )
    return int(cursor.lastrowid)


def insert_artifact(
    conn: sqlite3.Connection,
    *,
    artifact_id: str,
    kind: str,
    time_s: float,
    payload: dict[str, Any],
) -> None:
    conn.execute(
        "INSERT INTO artifacts(artifact_id, kind, time_s, payload_json) VALUES (?, ?, ?, ?)",
        (artifact_id, kind, time_s, dumps_json(payload)),
    )


def insert_decision(
    conn: sqlite3.Connection,
    *,
    decision: str,
    evidence_id: str,
    rationale: str,
    time_s: float,
) -> None:
    conn.execute(
        "INSERT INTO decisions(decision, evidence_id, rationale, time_s) VALUES (?, ?, ?, ?)",
        (decision, evidence_id, rationale, time_s),
    )


def dumps_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def loads_json(value: str) -> Any:
    return json.loads(value)


SCHEMA_SQL = """
CREATE TABLE snapshot (
  singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
  state_json TEXT NOT NULL
);

CREATE TABLE events (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  operation TEXT NOT NULL,
  time_s REAL NOT NULL CHECK (time_s >= 0),
  payload_json TEXT NOT NULL
);

CREATE TABLE artifacts (
  artifact_id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  time_s REAL NOT NULL CHECK (time_s >= 0),
  payload_json TEXT NOT NULL
);

CREATE TABLE decisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  decision TEXT NOT NULL,
  evidence_id TEXT NOT NULL,
  rationale TEXT NOT NULL,
  time_s REAL NOT NULL CHECK (time_s >= 0)
);

CREATE INDEX idx_events_operation_time ON events(operation, time_s);
CREATE INDEX idx_artifacts_kind_time ON artifacts(kind, time_s);
"""

