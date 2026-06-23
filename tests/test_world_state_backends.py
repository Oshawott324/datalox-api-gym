from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from api_gym.worlds.state_backends import (
    connect_sqlite,
    ensure_run_subdirs,
    resolve_state_db_path_from_metadata,
)


def test_ensure_run_subdirs_creates_artifacts_and_traces(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"

    result = ensure_run_subdirs(run_dir)

    assert result == {
        "artifacts": run_dir / "artifacts",
        "traces": run_dir / "traces",
    }
    assert (run_dir / "artifacts").is_dir()
    assert (run_dir / "traces").is_dir()


def test_resolve_state_db_path_from_metadata(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "state.sqlite").write_bytes(b"")
    (run_dir / "run.json").write_text(json.dumps({"state_db": "state.sqlite"}), encoding="utf-8")

    assert resolve_state_db_path_from_metadata(run_dir, metadata_name="run.json") == run_dir / "state.sqlite"


def test_resolve_state_db_path_rejects_path_traversal(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "run.json").write_text(json.dumps({"state_db": "../state.sqlite"}), encoding="utf-8")

    with pytest.raises(ValueError) as exc_info:
        resolve_state_db_path_from_metadata(run_dir, metadata_name="run.json")

    assert str(exc_info.value) == "run.json state_db must be a file name inside the run directory."


def test_connect_sqlite_enables_foreign_keys(tmp_path: Path) -> None:
    db_path = tmp_path / "state.sqlite"

    with connect_sqlite(db_path) as conn:
        assert isinstance(conn, sqlite3.Connection)
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
