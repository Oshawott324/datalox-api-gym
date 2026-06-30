"""SQLite state for the LabLongRun-Wet v0 prototype."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


STATE_DB_NAME = "state.sqlite"
LOGICAL_TIME_PREFIX = "2026-06-29T12:00:"


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        conn.executescript(SCHEMA_SQL)


def seed_initial_state(
    db_path: Path,
    *,
    source_volume_ul: float = 1000.0,
    diluent_volume_ul: float = 10000.0,
    stock_corrected_od600: float = 1.18,
    acceptance_band: dict[str, float] | None = None,
    fault_schedule: dict[str, Any] | None = None,
) -> None:
    initialize_db(db_path)
    acceptance_band = acceptance_band or {"min": 1.0, "max": 1.3}
    with connect(db_path) as conn:
        set_metadata(conn, "dry_run", True)
        set_metadata(conn, "logical_clock", 0)
        set_metadata(conn, "pipette_max_volume_ul", 200.0)
        set_metadata(conn, "stock_corrected_od600", stock_corrected_od600)
        set_metadata(conn, "raw_od600_linear_range", {"min": 0.02, "max": 0.2})
        set_metadata(conn, "corrected_od600_acceptance_band", acceptance_band)
        conn.executemany(
            """
            INSERT INTO labware (id, kind, display_name, slot, visible_to_agent, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                ("culture_tube", "tube", "Overnight culture tube", "A1", 1, dumps_json({"role": "source_culture"})),
                ("diluent_reservoir", "reservoir", "Sterile diluent reservoir", "A2", 1, dumps_json({"role": "diluent"})),
                ("dilution_plate", "96_well_plate", "Serial dilution plate", "B1", 1, dumps_json({"role": "dilution"})),
                ("qc_plate", "96_well_plate", "QC readout plate", "C1", 1, dumps_json({"role": "readout"})),
                ("tiprack_1", "tiprack_200ul", "200 uL tip rack", "D1", 1, dumps_json({"role": "tips"})),
                ("trash", "trash", "Tip trash", "D2", 1, dumps_json({"role": "waste"})),
            ],
        )
        stock_od = stock_corrected_od600
        conn.executemany(
            """
            INSERT INTO wells (
              labware_id, well_id, volume_ul, cell_signal, mixed, touched_by_tip_json, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "culture_tube",
                    "S1",
                    source_volume_ul,
                    stock_od * source_volume_ul,
                    1,
                    "[]",
                    dumps_json({"contents": "culture"}),
                ),
                (
                    "diluent_reservoir",
                    "R1",
                    diluent_volume_ul,
                    0.0,
                    1,
                    "[]",
                    dumps_json({"contents": "sterile_diluent"}),
                ),
                ("dilution_plate", "A1", 0.0, 0.0, 0, "[]", dumps_json({"contents": "empty"})),
                ("qc_plate", "B1", 0.0, 0.0, 0, "[]", dumps_json({"contents": "empty"})),
            ],
        )
        conn.executemany(
            "INSERT INTO tips (tip_ref, status, touched_wells_json, metadata_json) VALUES (?, ?, ?, ?)",
            [
                ("tiprack_1:A1", "clean", "[]", "{}"),
                ("tiprack_1:A2", "clean", "[]", "{}"),
                ("tiprack_1:A3", "clean", "[]", "{}"),
                ("tiprack_1:A4", "clean", "[]", "{}"),
            ],
        )
        conn.execute(
            """
            INSERT INTO pipette_state (
              id, current_tip, held_volume_ul, held_cell_signal, held_source_ref, touched_wells_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("p300_single", None, 0.0, 0.0, None, "[]"),
        )
        _apply_fault_schedule(conn, fault_schedule or {})


def dumps_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def loads_json(value: str | None) -> Any:
    return json.loads(value) if value else None


def set_metadata(conn: sqlite3.Connection, key: str, value: Any) -> None:
    conn.execute(
        """
        INSERT INTO metadata (key, value_json)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json
        """,
        (key, dumps_json(value)),
    )


def get_metadata(conn: sqlite3.Connection, key: str, default: Any = None) -> Any:
    row = conn.execute("SELECT value_json FROM metadata WHERE key = ?", (key,)).fetchone()
    if row is None:
        return default
    return loads_json(row["value_json"])


def next_timestamp(conn: sqlite3.Connection) -> str:
    clock = int(get_metadata(conn, "logical_clock", 0)) + 1
    set_metadata(conn, "logical_clock", clock)
    return f"{LOGICAL_TIME_PREFIX}{clock:02d}Z"


def next_id(conn: sqlite3.Connection, prefix: str) -> str:
    key = f"counter.{prefix}"
    value = int(get_metadata(conn, key, 0)) + 1
    set_metadata(conn, key, value)
    return f"{prefix}_{value:03d}"


def parse_well_ref(ref: str) -> tuple[str, str]:
    if ":" not in ref:
        raise ValueError(f"Well reference must be '<labware_id>:<well_id>', got {ref!r}")
    labware_id, well_id = ref.split(":", 1)
    if not labware_id or not well_id:
        raise ValueError(f"Well reference must be '<labware_id>:<well_id>', got {ref!r}")
    return labware_id, well_id


def well_ref(labware_id: str, well_id: str) -> str:
    return f"{labware_id}:{well_id}"


def raw_od600(volume_ul: float, cell_signal: float) -> float | None:
    if volume_ul <= 0:
        return None
    return round(cell_signal / volume_ul, 6)


def row_to_well(row: sqlite3.Row) -> dict[str, Any]:
    volume = float(row["volume_ul"])
    cell_signal = float(row["cell_signal"])
    return {
        "labware_id": row["labware_id"],
        "well_id": row["well_id"],
        "well_ref": well_ref(row["labware_id"], row["well_id"]),
        "volume_ul": round(volume, 6),
        "raw_od600": raw_od600(volume, cell_signal),
        "mixed": bool(row["mixed"]),
        "metadata": loads_json(row["metadata_json"]) or {},
        "touched_by_tip": loads_json(row["touched_by_tip_json"]) or [],
    }


def _apply_fault_schedule(conn: sqlite3.Connection, fault_schedule: dict[str, Any]) -> None:
    for event in fault_schedule.get("events", []):
        event_type = event.get("event_type")
        if event_type == "reader_busy_until_wait_seconds":
            set_metadata(conn, "reader_busy_until_wait_seconds", float(event["wait_seconds"]))
            set_metadata(conn, "accumulated_wait_seconds", 0.0)
        elif event_type == "partial_dispense_once":
            requested = float(event["requested_volume_ul"])
            delivered = float(event["delivered_volume_ul"])
            set_metadata(
                conn,
                "partial_dispense_once",
                {
                    "target_well_ref": event["target_well_ref"],
                    "requested_volume_ul": requested,
                    "delivered_volume_ul": delivered,
                    "remaining_volume_ul": round(requested - delivered, 6),
                    "applied": False,
                },
            )
        elif event_type == "stale_prior_readout":
            labware_id, well_id = parse_well_ref(event["well_ref"])
            conn.execute(
                """
                INSERT INTO od_readouts (
                  id, plate_id, well_id, wavelength_nm, raw_od600, corrected_od600,
                  dilution_factor, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event["readout_id"],
                    labware_id,
                    well_id,
                    int(event["wavelength_nm"]),
                    float(event["raw_od600"]),
                    float(event["corrected_od600"]),
                    float(event["dilution_factor"]),
                    event["created_at"],
                ),
            )


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS metadata (
  key TEXT PRIMARY KEY,
  value_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS labware (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  display_name TEXT NOT NULL,
  slot TEXT NOT NULL,
  visible_to_agent INTEGER NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS wells (
  labware_id TEXT NOT NULL REFERENCES labware(id),
  well_id TEXT NOT NULL,
  volume_ul REAL NOT NULL,
  cell_signal REAL NOT NULL,
  mixed INTEGER NOT NULL,
  touched_by_tip_json TEXT NOT NULL DEFAULT '[]',
  metadata_json TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY (labware_id, well_id)
);

CREATE TABLE IF NOT EXISTS tips (
  tip_ref TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  touched_wells_json TEXT NOT NULL DEFAULT '[]',
  metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS pipette_state (
  id TEXT PRIMARY KEY,
  current_tip TEXT,
  held_volume_ul REAL NOT NULL,
  held_cell_signal REAL NOT NULL,
  held_source_ref TEXT,
  touched_wells_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS liquid_actions (
  id TEXT PRIMARY KEY,
  action TEXT NOT NULL,
  source_ref TEXT,
  target_ref TEXT,
  volume_ul REAL,
  tip_ref TEXT,
  created_at TEXT NOT NULL,
  payload_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS mixes (
  id TEXT PRIMARY KEY,
  well_ref TEXT NOT NULL,
  repetitions INTEGER NOT NULL,
  volume_ul REAL NOT NULL,
  tip_ref TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS delays (
  id TEXT PRIMARY KEY,
  seconds REAL NOT NULL,
  reason TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS od_readouts (
  id TEXT PRIMARY KEY,
  plate_id TEXT NOT NULL,
  well_id TEXT NOT NULL,
  wavelength_nm INTEGER NOT NULL,
  raw_od600 REAL NOT NULL,
  corrected_od600 REAL NOT NULL,
  dilution_factor REAL NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lab_notes (
  id TEXT PRIMARY KEY,
  note TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS qc_submissions (
  id TEXT PRIMARY KEY,
  decision TEXT NOT NULL,
  evidence_readout_id TEXT NOT NULL,
  target_well_ref TEXT NOT NULL,
  rationale TEXT NOT NULL,
  evidence_status TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS contamination_events (
  id TEXT PRIMARY KEY,
  tip_ref TEXT NOT NULL,
  source_ref TEXT,
  target_ref TEXT,
  risk_code TEXT NOT NULL,
  details_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_liquid_actions_action ON liquid_actions(action);
CREATE INDEX IF NOT EXISTS idx_liquid_actions_created ON liquid_actions(created_at);
CREATE INDEX IF NOT EXISTS idx_readouts_target ON od_readouts(plate_id, well_id, wavelength_nm);
CREATE INDEX IF NOT EXISTS idx_submissions_created ON qc_submissions(created_at);
"""
