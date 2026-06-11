"""SQLite episode state for unitelabs_plate_qc_v0."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

STATE_DB_NAME = "state.sqlite"
RUN_METADATA_NAME = "run.json"
TASK_NAME = "task.json"


def connect(db_path: Path) -> sqlite3.Connection:
    """Open an episode SQLite database with API Gym defaults."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def resolve_state_db_path(run_dir: Path) -> Path:
    """Resolve the SQLite state database for a sampled run directory."""
    run_dir = run_dir.resolve()
    metadata_path = run_dir / RUN_METADATA_NAME
    if not metadata_path.exists():
        raise FileNotFoundError(f"Missing {RUN_METADATA_NAME} in run directory: {run_dir}")

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    state_db = metadata.get("state_db")
    if not isinstance(state_db, str) or not state_db:
        raise ValueError(f"{RUN_METADATA_NAME} must contain a non-empty state_db string.")

    db_path = run_dir / state_db
    if not db_path.exists():
        raise FileNotFoundError(f"Missing state database at {db_path}")
    return db_path


def initialize_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        conn.executescript(SCHEMA_SQL)


def dumps_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def loads_json(value: str | None) -> Any:
    if not value:
        return None
    return json.loads(value)


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    for key in ("metadata_json", "payload_json", "request_json", "response_json", "wells_json", "values_json"):
        if key in data:
            data[key.removesuffix("_json")] = loads_json(data.pop(key))
    return data


def insert_event(
    conn: sqlite3.Connection,
    *,
    event_type: str,
    object_type: str,
    object_id: str,
    payload: dict[str, Any],
    created_at: str,
    visible_to_agent: bool = True,
) -> None:
    conn.execute(
        """
        INSERT INTO events (
          event_type, object_type, object_id, visible_to_agent, payload_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (event_type, object_type, object_id, int(visible_to_agent), dumps_json(payload), created_at),
    )


def insert_audit(
    conn: sqlite3.Connection,
    *,
    actor: str,
    action: str,
    object_type: str,
    object_id: str,
    request: dict[str, Any],
    response: dict[str, Any],
    created_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO audit_log (
          actor, action, object_type, object_id, request_json, response_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (actor, action, object_type, object_id, dumps_json(request), dumps_json(response), created_at),
    )


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS deck (
  id TEXT PRIMARY KEY,
  mode TEXT NOT NULL,
  dry_run INTEGER NOT NULL,
  loaded_labware_json TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS labware (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  display_name TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS wells (
  labware_id TEXT NOT NULL REFERENCES labware(id),
  well_id TEXT NOT NULL,
  volume_ul REAL NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY (labware_id, well_id)
);

CREATE TABLE IF NOT EXISTS tips (
  rack_id TEXT NOT NULL REFERENCES labware(id),
  well_id TEXT NOT NULL,
  status TEXT NOT NULL,
  PRIMARY KEY (rack_id, well_id)
);

CREATE TABLE IF NOT EXISTS pipette_state (
  id TEXT PRIMARY KEY,
  tip TEXT,
  aspirated_volume_ul REAL NOT NULL DEFAULT 0,
  source_labware_id TEXT,
  source_well_id TEXT
);

CREATE TABLE IF NOT EXISTS control_bands (
  id TEXT PRIMARY KEY,
  plate_id TEXT NOT NULL REFERENCES labware(id),
  well_id TEXT NOT NULL,
  wavelength_nm INTEGER NOT NULL,
  min_value REAL NOT NULL,
  max_value REAL NOT NULL,
  expected_value REAL NOT NULL,
  required_dispense_ul REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS transfers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_labware_id TEXT NOT NULL,
  source_well_id TEXT NOT NULL,
  target_labware_id TEXT NOT NULL,
  target_well_id TEXT NOT NULL,
  volume_ul REAL NOT NULL,
  tip TEXT NOT NULL,
  mix_after INTEGER NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS readouts (
  id TEXT PRIMARY KEY,
  plate_id TEXT NOT NULL,
  wavelength_nm INTEGER NOT NULL,
  wells_json TEXT NOT NULL,
  values_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS workflow_notes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  note TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS submissions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  decision TEXT NOT NULL,
  evidence_readout_id TEXT NOT NULL,
  target_labware_id TEXT NOT NULL,
  target_well_id TEXT NOT NULL,
  rationale TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_type TEXT NOT NULL,
  object_type TEXT NOT NULL,
  object_id TEXT NOT NULL,
  visible_to_agent INTEGER NOT NULL DEFAULT 1,
  payload_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  object_type TEXT NOT NULL,
  object_id TEXT NOT NULL,
  request_json TEXT NOT NULL DEFAULT '{}',
  response_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action);
CREATE INDEX IF NOT EXISTS idx_transfers_target ON transfers(target_labware_id, target_well_id);
"""
