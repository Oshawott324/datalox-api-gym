"""SQLite episode state for automata_linq_workflow_planning_v0."""

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
    """Create the Automata LINQ dry-run state schema."""
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
  external_id TEXT NOT NULL,
  name TEXT NOT NULL,
  slug TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  logo_url TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS scheduler_versions (
  scheduler TEXT NOT NULL,
  version TEXT NOT NULL,
  is_default INTEGER NOT NULL DEFAULT 0,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY (scheduler, version)
);

CREATE TABLE IF NOT EXISTS drivers (
  id TEXT PRIMARY KEY,
  scheduler TEXT NOT NULL,
  scheduler_version TEXT NOT NULL,
  name TEXT NOT NULL,
  version TEXT NOT NULL,
  configuration_json TEXT NOT NULL DEFAULT '{}',
  actions_json TEXT NOT NULL DEFAULT '{}',
  protocols_json TEXT NOT NULL DEFAULT '{}',
  metadata_json TEXT NOT NULL DEFAULT '{}',
  FOREIGN KEY (scheduler, scheduler_version) REFERENCES scheduler_versions(scheduler, version)
);

CREATE TABLE IF NOT EXISTS workcells (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL,
  hub_id TEXT NOT NULL,
  hub_last_access TEXT NOT NULL,
  name TEXT NOT NULL,
  mode TEXT NOT NULL,
  status TEXT NOT NULL,
  transport_config_id TEXT,
  transport_config_type TEXT,
  transport_config_version INTEGER,
  metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS devices (
  id TEXT PRIMARY KEY,
  workcell_id TEXT NOT NULL REFERENCES workcells(id),
  name TEXT NOT NULL,
  serial TEXT NOT NULL,
  online INTEGER NOT NULL,
  state_status TEXT NOT NULL,
  state_details TEXT,
  error_json TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS workflows (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  author TEXT NOT NULL,
  creator_username TEXT NOT NULL,
  version TEXT NOT NULL,
  workflow_type TEXT,
  published INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  published_at TEXT,
  parameter_definitions_json TEXT NOT NULL DEFAULT '[]',
  valid_batch_data_json TEXT NOT NULL DEFAULT '{}',
  synced_plan_id TEXT,
  workflow_config_json TEXT NOT NULL DEFAULT '{}',
  metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS workflow_validations (
  id TEXT PRIMARY KEY,
  workflow_id TEXT NOT NULL REFERENCES workflows(id),
  validate_for_execution INTEGER NOT NULL DEFAULT 0,
  validate_for_infeasibility INTEGER NOT NULL DEFAULT 0,
  is_valid INTEGER NOT NULL,
  errors_json TEXT NOT NULL DEFAULT '[]',
  warnings_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS plans (
  id TEXT PRIMARY KEY,
  workflow_id TEXT NOT NULL REFERENCES workflows(id),
  workflow_checksum TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL,
  error TEXT NOT NULL DEFAULT '',
  stage TEXT,
  stage_detail TEXT,
  result_available INTEGER NOT NULL DEFAULT 0,
  status_poll_count INTEGER NOT NULL DEFAULT 0,
  scheduler TEXT NOT NULL,
  scheduler_version TEXT NOT NULL,
  parameter_values_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (scheduler, scheduler_version) REFERENCES scheduler_versions(scheduler, version)
);

CREATE TABLE IF NOT EXISTS plan_results (
  id TEXT PRIMARY KEY,
  plan_id TEXT NOT NULL REFERENCES plans(id),
  plan_json TEXT NOT NULL DEFAULT '{}',
  metrics_json TEXT NOT NULL DEFAULT '{}',
  locations_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_histories (
  id TEXT PRIMARY KEY,
  device_id TEXT NOT NULL REFERENCES devices(id),
  last_updated TEXT NOT NULL,
  owner_json TEXT NOT NULL DEFAULT '{}',
  outcome TEXT NOT NULL,
  outcome_details TEXT,
  start_time TEXT NOT NULL,
  stop_time TEXT,
  workflow_json TEXT,
  tags_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS log_exports (
  id TEXT PRIMARY KEY,
  run_history_id TEXT NOT NULL REFERENCES run_histories(id),
  download_url TEXT NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT,
  dereferenced INTEGER NOT NULL DEFAULT 0,
  metadata_json TEXT NOT NULL DEFAULT '{}'
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

CREATE INDEX IF NOT EXISTS idx_workflows_synced_plan ON workflows(synced_plan_id);
CREATE INDEX IF NOT EXISTS idx_validations_workflow ON workflow_validations(workflow_id);
CREATE INDEX IF NOT EXISTS idx_plans_workflow ON plans(workflow_id);
CREATE INDEX IF NOT EXISTS idx_events_type_object ON events(event_type, object_type, object_id);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action);
"""
