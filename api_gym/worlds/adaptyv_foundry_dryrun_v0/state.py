"""SQLite episode state for adaptyv_foundry_dryrun_v0."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from api_gym.worlds.state_backends import connect_sqlite, resolve_state_db_path_from_metadata

STATE_DB_NAME = "state.sqlite"
RUN_METADATA_NAME = "run.json"
TASK_NAME = "task.json"


def connect(db_path: Path) -> sqlite3.Connection:
    """Open an episode SQLite database with API Gym defaults."""
    return connect_sqlite(db_path)


def resolve_state_db_path(run_dir: Path) -> Path:
    """Resolve the SQLite state database for a sampled run directory."""
    return resolve_state_db_path_from_metadata(run_dir, metadata_name=RUN_METADATA_NAME)


def initialize_db(db_path: Path) -> None:
    """Create the Adaptyv Foundry dry-run state schema."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        conn.executescript(SCHEMA_SQL)


def dumps_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def loads_json(value: str | None) -> Any:
    if not value:
        return None
    return json.loads(value)


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
CREATE TABLE IF NOT EXISTS organizations (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS token_scopes (
  token_id TEXT PRIMARY KEY,
  can_read INTEGER NOT NULL,
  can_create_experiment INTEGER NOT NULL,
  can_confirm_quote INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS targets (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  antigen_ref TEXT NOT NULL,
  available INTEGER NOT NULL,
  pricing_tier TEXT NOT NULL,
  source_ref TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sequences (
  id TEXT PRIMARY KEY,
  alias TEXT NOT NULL,
  amino_acids TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  source_ref TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS experiments (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  target_id TEXT NOT NULL REFERENCES targets(id),
  experiment_type TEXT NOT NULL,
  method TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  submitted_at TEXT
);

CREATE TABLE IF NOT EXISTS experiment_sequences (
  experiment_id TEXT NOT NULL REFERENCES experiments(id),
  sequence_id TEXT NOT NULL REFERENCES sequences(id),
  alias TEXT NOT NULL,
  PRIMARY KEY (experiment_id, sequence_id)
);

CREATE TABLE IF NOT EXISTS cost_estimates (
  id TEXT PRIMARY KEY,
  experiment_id TEXT NOT NULL REFERENCES experiments(id),
  amount_cents INTEGER NOT NULL,
  currency TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quotes (
  id TEXT PRIMARY KEY,
  experiment_id TEXT NOT NULL REFERENCES experiments(id),
  amount_cents INTEGER NOT NULL,
  currency TEXT NOT NULL,
  status TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  confirmed_at TEXT,
  rejected_at TEXT
);

CREATE TABLE IF NOT EXISTS invoices (
  id TEXT PRIMARY KEY,
  quote_id TEXT NOT NULL REFERENCES quotes(id),
  status TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS experiment_updates (
  id TEXT PRIMARY KEY,
  experiment_id TEXT NOT NULL REFERENCES experiments(id),
  status TEXT NOT NULL,
  visible_at TEXT NOT NULL,
  message TEXT NOT NULL,
  source_ref TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS results (
  id TEXT PRIMARY KEY,
  experiment_id TEXT NOT NULL,
  sequence_id TEXT NOT NULL REFERENCES sequences(id),
  status TEXT NOT NULL,
  metric_type TEXT NOT NULL,
  value_json TEXT NOT NULL DEFAULT '{}',
  quality_label TEXT NOT NULL,
  visible_at TEXT NOT NULL,
  source_ref TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS campaign_decisions (
  id TEXT PRIMARY KEY,
  experiment_id TEXT NOT NULL REFERENCES experiments(id),
  decision TEXT NOT NULL,
  cited_result_ids_json TEXT NOT NULL DEFAULT '[]',
  rationale TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS live_boundary_events (
  id TEXT PRIMARY KEY,
  attempted_operation TEXT NOT NULL,
  blocked_at TEXT NOT NULL,
  reason TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS logical_clock (
  id TEXT PRIMARY KEY,
  current_time TEXT NOT NULL,
  source TEXT NOT NULL
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

CREATE INDEX IF NOT EXISTS idx_experiment_sequences_experiment ON experiment_sequences(experiment_id);
CREATE INDEX IF NOT EXISTS idx_cost_estimates_experiment ON cost_estimates(experiment_id);
CREATE INDEX IF NOT EXISTS idx_quotes_experiment ON quotes(experiment_id);
CREATE INDEX IF NOT EXISTS idx_updates_experiment ON experiment_updates(experiment_id);
CREATE INDEX IF NOT EXISTS idx_results_experiment ON results(experiment_id);
CREATE INDEX IF NOT EXISTS idx_events_type_object ON events(event_type, object_type, object_id);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action);
"""
