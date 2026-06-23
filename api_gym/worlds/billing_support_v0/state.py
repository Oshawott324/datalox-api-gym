"""SQLite episode state for billing_support_v0."""

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
    for key in ("metadata_json", "tags_json", "body_json", "payload_json", "request_json", "response_json"):
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
CREATE TABLE IF NOT EXISTS accounts (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  support_plan TEXT NOT NULL,
  default_currency TEXT NOT NULL,
  created_at TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS customers (
  id TEXT PRIMARY KEY,
  account_id TEXT NOT NULL REFERENCES accounts(id),
  email TEXT NOT NULL,
  name TEXT NOT NULL,
  phone TEXT,
  default_payment_method TEXT,
  delinquent INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS subscriptions (
  id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL REFERENCES customers(id),
  status TEXT NOT NULL,
  plan_name TEXT NOT NULL,
  current_period_start TEXT NOT NULL,
  current_period_end TEXT NOT NULL,
  cancel_at_period_end INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS invoices (
  id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL REFERENCES customers(id),
  subscription_id TEXT REFERENCES subscriptions(id),
  number TEXT NOT NULL,
  status TEXT NOT NULL,
  collection_method TEXT NOT NULL,
  currency TEXT NOT NULL,
  amount_due INTEGER NOT NULL,
  amount_paid INTEGER NOT NULL,
  amount_remaining INTEGER NOT NULL,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  next_payment_attempt TEXT,
  latest_payment_id TEXT,
  due_date TEXT,
  paid_at TEXT,
  created_at TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS payments (
  id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL REFERENCES customers(id),
  invoice_id TEXT REFERENCES invoices(id),
  amount INTEGER NOT NULL,
  currency TEXT NOT NULL,
  status TEXT NOT NULL,
  payment_method TEXT NOT NULL,
  payment_intent_id TEXT NOT NULL,
  charge_id TEXT NOT NULL,
  decline_code TEXT,
  failure_message TEXT,
  refunded_amount INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS refunds (
  id TEXT PRIMARY KEY,
  payment_id TEXT NOT NULL REFERENCES payments(id),
  amount INTEGER NOT NULL,
  currency TEXT NOT NULL,
  status TEXT NOT NULL,
  reason TEXT NOT NULL,
  ticket_id TEXT REFERENCES tickets(id),
  created_at TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS tickets (
  id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL REFERENCES customers(id),
  requester_email TEXT NOT NULL,
  subject TEXT NOT NULL,
  status TEXT NOT NULL,
  priority TEXT NOT NULL,
  assignee_group TEXT NOT NULL,
  tags_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  closed_at TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS ticket_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ticket_id TEXT NOT NULL REFERENCES tickets(id),
  author_type TEXT NOT NULL,
  author_email TEXT NOT NULL,
  body TEXT NOT NULL,
  public INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS emails (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ticket_id TEXT REFERENCES tickets(id),
  customer_id TEXT REFERENCES customers(id),
  to_email TEXT NOT NULL,
  from_email TEXT NOT NULL,
  subject TEXT NOT NULL,
  body TEXT NOT NULL,
  status TEXT NOT NULL,
  provider_message_id TEXT,
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

CREATE TABLE IF NOT EXISTS policies (
  id TEXT PRIMARY KEY,
  policy_key TEXT NOT NULL,
  version TEXT NOT NULL,
  body_json TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
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

CREATE INDEX IF NOT EXISTS idx_invoices_customer_id ON invoices(customer_id);
CREATE INDEX IF NOT EXISTS idx_payments_invoice_id ON payments(invoice_id);
CREATE INDEX IF NOT EXISTS idx_refunds_payment_id ON refunds(payment_id);
CREATE INDEX IF NOT EXISTS idx_ticket_messages_ticket_id ON ticket_messages(ticket_id);
CREATE INDEX IF NOT EXISTS idx_events_type_object ON events(event_type, object_type, object_id);
"""
