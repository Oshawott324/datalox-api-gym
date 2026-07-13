"""SQLite state for the Synergy H1 yeast-growth projection."""

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
    db_path = run_dir.resolve() / str(metadata["state_db"])
    if not db_path.exists():
        raise FileNotFoundError(f"Missing state database: {db_path}")
    return db_path


def initialize_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.execute(
            "INSERT INTO clock(singleton, time_s) VALUES (1, 0.0)"
        )
        conn.execute(
            """
            INSERT INTO reader(
              singleton, door_open, loaded_plate_id, target_temperature_c,
              current_temperature_c, temperature_set_at_s, temperature_start_c,
              shaking, shake_type, frequency_setting
            ) VALUES (1, 0, NULL, NULL, 22.0, NULL, 22.0, 0, NULL, NULL)
            """
        )
        conn.execute(
            """
            INSERT INTO plate(
              plate_id, version, sealed, volume_ul, replicate_wells_json
            ) VALUES (?, 1, 1, 200.0, ?)
            """,
            ("yeast_growth_plate", dumps_json([f"A{i}" for i in range(1, 9)])),
        )


def dumps_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def loads_json(value: str) -> Any:
    return json.loads(value)


def insert_event(
    conn: sqlite3.Connection,
    event_type: str,
    time_s: float,
    payload: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        "INSERT INTO events(event_type, time_s, payload_json) VALUES (?, ?, ?)",
        (event_type, time_s, dumps_json(payload or {})),
    )


SCHEMA_SQL = """
CREATE TABLE clock (
  singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
  time_s REAL NOT NULL CHECK (time_s >= 0)
);

CREATE TABLE reader (
  singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
  door_open INTEGER NOT NULL,
  loaded_plate_id TEXT,
  target_temperature_c REAL,
  current_temperature_c REAL NOT NULL,
  temperature_set_at_s REAL,
  temperature_start_c REAL NOT NULL,
  shaking INTEGER NOT NULL,
  shake_type TEXT,
  frequency_setting INTEGER
);

CREATE TABLE plate (
  plate_id TEXT PRIMARY KEY,
  version INTEGER NOT NULL,
  sealed INTEGER NOT NULL,
  volume_ul REAL NOT NULL,
  replicate_wells_json TEXT NOT NULL
);

CREATE TABLE measurements (
  measurement_id TEXT PRIMARY KEY,
  time_s REAL NOT NULL,
  plate_id TEXT NOT NULL,
  plate_version INTEGER NOT NULL,
  wavelength_nm INTEGER NOT NULL,
  wells_json TEXT NOT NULL,
  values_json TEXT NOT NULL,
  temperature_c REAL NOT NULL,
  shaking INTEGER NOT NULL
);

CREATE TABLE submissions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  decision TEXT NOT NULL,
  evidence_measurement_id TEXT NOT NULL,
  rationale TEXT NOT NULL,
  time_s REAL NOT NULL
);

CREATE TABLE events (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  event_type TEXT NOT NULL,
  time_s REAL NOT NULL,
  payload_json TEXT NOT NULL
);

CREATE INDEX idx_measurements_time ON measurements(time_s);
CREATE INDEX idx_events_type_time ON events(event_type, time_s);
"""
