# Source Pack To Environment Framework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the generic runtime framework that turns a validated source pack and registered world into a stateful, verifiable environment exposed through original-shaped HTTP and optional MCP adapters.

**Architecture:** Extend the current API Gym world runtime instead of adding a parallel platform. Registered worlds get an optional HTTP app factory, session manifests advertise both MCP and HTTP surfaces, source refs can be validated, and run exports include the selected source/evidence surfaces. Provider-specific behavior remains inside `api_gym/worlds/<world_id>/`; generic code only handles dispatch, manifests, traces, and validation.

**Tech Stack:** Python 3.12, Typer CLI, FastAPI/TestClient, SQLite, pytest, JSON/JSONL source-pack records.

---

## Source Spec

Primary design doc:

- `docs/playbooks/source-pack-to-environment-framework.md`

This plan implements the generic framework pieces only. It does not implement
`automata_linq_workflow_planning_v0`; that world should use the framework after
these tasks land.

## File Structure

Create:

- `api_gym/worlds/http.py` - shared HTTP adapter utilities for request JSON, query params, JSONL trace writes, and structured JSON errors.
- `api_gym/worlds/state_backends.py` - shared run-directory and SQLite helper functions used by worlds without forcing a class hierarchy.
- `api_gym/worlds/source_refs.py` - validator for `worlds/<world_id>/source_refs.json` selected source-pack records and world evidence paths.
- `tests/test_world_http_runtime.py` - tests for generic HTTP app dispatch through `api_gym.server.app`.
- `tests/test_world_http_cli.py` - tests for generic `api-gym serve` behavior.
- `tests/test_session_http_manifest.py` - tests for HTTP metadata in session manifests.
- `tests/test_world_source_refs.py` - tests for source-ref validation.

Modify:

- `api_gym/worlds/registry.py` - add optional HTTP app factory to `WorldRuntime`.
- `api_gym/server/app.py` - dispatch HTTP app creation through `WorldRuntime`.
- `api_gym/cli.py` - remove billing-only guard from `serve`; add `world-source-refs validate`.
- `api_gym/session.py` - add HTTP surface metadata to session manifests.
- `api_gym/exports/run_export.py` - include source refs and HTTP trace artifacts.
- `api_gym/source_pack_gate_server.py` - reuse shared HTTP utilities without changing behavior.
- `api_gym/worlds/billing_support_v0/state.py` - reuse shared SQLite/run helpers.
- `api_gym/worlds/unitelabs_plate_qc_v0/state.py` - reuse shared SQLite/run helpers.

Do not modify provider source packs in this plan.

---

### Task 1: Add Optional HTTP App Contract To World Runtime

**Files:**
- Modify: `api_gym/worlds/registry.py`
- Modify: `api_gym/server/app.py`
- Test: `tests/test_world_http_runtime.py`

- [ ] **Step 1: Write failing tests for runtime HTTP dispatch**

Create `tests/test_world_http_runtime.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api_gym.server.app import create_app
from api_gym.worlds.billing_support_v0.sampler import sample_episode as sample_billing_episode
from api_gym.worlds.registry import get_world_runtime
from api_gym.worlds.unitelabs_plate_qc_v0.sampler import sample_episode as sample_unitelabs_episode


def test_billing_runtime_exposes_http_app_factory() -> None:
    runtime = get_world_runtime("billing_support_v0")

    assert runtime.create_http_app is not None
    assert runtime.http_surface == "available"


def test_unitelabs_runtime_has_no_http_app_factory() -> None:
    runtime = get_world_runtime("unitelabs_plate_qc_v0")

    assert runtime.create_http_app is None
    assert runtime.http_surface == "not_available"


def test_create_app_dispatches_to_registered_world_http(tmp_path: Path) -> None:
    episode = sample_billing_episode(
        scenario="duplicate_payment_refund",
        seed=41,
        out_dir=tmp_path / "billing-run",
    )

    app = create_app(episode.run_dir)

    assert isinstance(app, FastAPI)
    assert app.title == "Datalox API Gym billing_support_v0"
    response = TestClient(app).get("/support/tickets/not-real")
    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert response.json()["error"]["code"] == "ticket_not_found"


def test_create_app_fails_clearly_for_world_without_http(tmp_path: Path) -> None:
    episode = sample_unitelabs_episode(
        scenario="plate_transfer_qc",
        seed=42,
        out_dir=tmp_path / "unitelabs-run",
    )

    with pytest.raises(ValueError) as exc_info:
        create_app(episode.run_dir)

    assert str(exc_info.value) == "World 'unitelabs_plate_qc_v0' does not expose an HTTP app."
```

- [ ] **Step 2: Run the tests and verify they fail for missing fields**

Run:

```bash
python -m pytest tests/test_world_http_runtime.py -q
```

Expected: failure mentioning `WorldRuntime` has no attribute `create_http_app`
or `http_surface`.

- [ ] **Step 3: Extend `WorldRuntime` and package loading**

Modify `api_gym/worlds/registry.py`:

```python
from importlib import import_module, util
```

Add fields to `WorldRuntime`:

```python
    create_http_app: Callable[[Path], Any] | None
    http_surface: str
```

In `_runtime_from_package`, add optional HTTP module loading before the return:

```python
    http_spec = util.find_spec(f"{package}.http")
    http_module = import_module(f"{package}.http") if http_spec is not None else None
    create_http_app = getattr(http_module, "create_app", None) if http_module is not None else None
    if create_http_app is not None and not callable(create_http_app):
        raise ValueError(f"{package}.http.create_app must be callable when defined.")
```

Add these values to the returned `WorldRuntime`:

```python
        create_http_app=create_http_app,
        http_surface="available" if create_http_app is not None else "not_available",
```

- [ ] **Step 4: Make `api_gym.server.app.create_app` generic**

Replace `api_gym/server/app.py` with:

```python
"""HTTP app factory for API Gym run directories."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from api_gym.worlds.registry import get_runtime_for_run


def create_app(run_dir: Path) -> FastAPI:
    """Create the FastAPI app for the run's world."""
    runtime = get_runtime_for_run(run_dir)
    if runtime.create_http_app is None:
        raise ValueError(f"World '{runtime.world}' does not expose an HTTP app.")
    return runtime.create_http_app(run_dir)
```

- [ ] **Step 5: Run the focused tests**

Run:

```bash
python -m pytest tests/test_world_http_runtime.py -q
```

Expected: all tests in `tests/test_world_http_runtime.py` pass.

- [ ] **Step 6: Commit this task**

```bash
git add api_gym/worlds/registry.py api_gym/server/app.py tests/test_world_http_runtime.py
git commit -m "feat: add optional world HTTP runtime contract"
```

---

### Task 2: Make `api-gym serve` World-Generic

**Files:**
- Modify: `api_gym/cli.py`
- Test: `tests/test_world_http_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Create `tests/test_world_http_cli.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from api_gym.cli import app
from api_gym.worlds.billing_support_v0.sampler import sample_episode as sample_billing_episode
from api_gym.worlds.unitelabs_plate_qc_v0.sampler import sample_episode as sample_unitelabs_episode


def test_serve_cli_uses_generic_world_http_app(tmp_path: Path, monkeypatch) -> None:
    episode = sample_billing_episode(
        scenario="duplicate_payment_refund",
        seed=51,
        out_dir=tmp_path / "billing-run",
    )
    called: dict[str, object] = {}

    def fake_run(fastapi_app, *, host: str, port: int) -> None:
        called["title"] = fastapi_app.title
        called["host"] = host
        called["port"] = port

    monkeypatch.setattr("uvicorn.run", fake_run)

    result = CliRunner().invoke(
        app,
        ["serve", "--run", str(episode.run_dir), "--host", "127.0.0.1", "--port", "9099"],
    )

    assert result.exit_code == 0, result.output
    assert called == {
        "title": "Datalox API Gym billing_support_v0",
        "host": "127.0.0.1",
        "port": 9099,
    }


def test_serve_cli_reports_world_without_http_surface(tmp_path: Path) -> None:
    episode = sample_unitelabs_episode(
        scenario="plate_transfer_qc",
        seed=52,
        out_dir=tmp_path / "unitelabs-run",
    )

    result = CliRunner().invoke(app, ["serve", "--run", str(episode.run_dir)])

    assert result.exit_code == 2
    payload = json.loads(result.stderr)
    assert payload == {
        "ok": False,
        "error": {
            "code": "invalid_run",
            "message": "World 'unitelabs_plate_qc_v0' does not expose an HTTP app.",
            "details": {"run": str(episode.run_dir)},
        },
    }
```

- [ ] **Step 2: Run the tests and verify the billing guard fails the second case**

Run:

```bash
python -m pytest tests/test_world_http_cli.py -q
```

Expected: at least one failure because `api-gym serve` still uses the
billing-only guard.

- [ ] **Step 3: Remove the billing-only guard from `serve`**

In `api_gym/cli.py`, change `serve` to:

```python
@app.command()
def serve(
    run: Annotated[Path, typer.Option(help="Run directory created by api-gym sample.")],
    host: Annotated[str, typer.Option(help="Host interface for the HTTP server.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Port for the HTTP server.")] = 8080,
) -> None:
    """Serve one sampled run through the registered world's FastAPI HTTP surface."""
    try:
        fastapi_app = create_app(run)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        _exit_error("invalid_run", str(exc), {"run": str(run)})

    import uvicorn

    uvicorn.run(fastapi_app, host=host, port=port)
```

Do not remove `_ensure_billing_run_surface` yet because `resolve`, `run`, and
`eval` still intentionally use billing-only surfaces.

- [ ] **Step 4: Run focused CLI tests**

Run:

```bash
python -m pytest tests/test_world_http_cli.py -q
```

Expected: both tests pass.

- [ ] **Step 5: Run existing source-pack gate CLI tests**

Run:

```bash
python -m pytest tests/test_source_pack_gate_cli.py -q
```

Expected: existing gate CLI tests still pass.

- [ ] **Step 6: Commit this task**

```bash
git add api_gym/cli.py tests/test_world_http_cli.py
git commit -m "feat: make run HTTP serving world-generic"
```

---

### Task 3: Add HTTP Surface Metadata To Session Manifests

**Files:**
- Modify: `api_gym/session.py`
- Test: `tests/test_session_http_manifest.py`

- [ ] **Step 1: Write failing manifest tests**

Create `tests/test_session_http_manifest.py`:

```python
from __future__ import annotations

from pathlib import Path

from api_gym.session import create_world_session


def test_session_manifest_advertises_http_when_available(tmp_path: Path) -> None:
    manifest = create_world_session(
        world="billing_support_v0",
        scenario="duplicate_payment_refund",
        seed=61,
        out_dir=tmp_path / "billing-session",
    )

    assert manifest["http"] == {
        "available": True,
        "recommended_command": ["api-gym", "serve", "--run", manifest["run_dir"]],
        "recommended_base_url": "http://127.0.0.1:8080",
        "trace_path": str(Path(manifest["run_dir"]) / "traces" / "http_requests.jsonl"),
    }
    assert "Start the HTTP server only when the task or host needs provider-shaped HTTP." in manifest[
        "integration_instructions"
    ]


def test_session_manifest_marks_http_unavailable_for_mcp_only_world(tmp_path: Path) -> None:
    manifest = create_world_session(
        world="unitelabs_plate_qc_v0",
        scenario="plate_transfer_qc",
        seed=62,
        out_dir=tmp_path / "unitelabs-session",
    )

    assert manifest["http"] == {
        "available": False,
        "reason": "World 'unitelabs_plate_qc_v0' does not expose an HTTP app.",
    }
```

- [ ] **Step 2: Run the tests and verify missing `http` metadata**

Run:

```bash
python -m pytest tests/test_session_http_manifest.py -q
```

Expected: failure because `manifest["http"]` is missing.

- [ ] **Step 3: Add HTTP metadata builder**

In `api_gym/session.py`, add:

```python
def _http_manifest(runtime: Any, run_dir: Path) -> dict[str, Any]:
    if runtime.create_http_app is None:
        return {
            "available": False,
            "reason": f"World '{runtime.world}' does not expose an HTTP app.",
        }
    return {
        "available": True,
        "recommended_command": ["api-gym", "serve", "--run", str(run_dir)],
        "recommended_base_url": "http://127.0.0.1:8080",
        "trace_path": str(run_dir / "traces" / "http_requests.jsonl"),
    }
```

In `build_session_manifest`, add this key at the top level:

```python
        "http": _http_manifest(runtime, run_dir),
```

Add this exact instruction to `integration_instructions`:

```python
            "Start the HTTP server only when the task or host needs provider-shaped HTTP.",
```

- [ ] **Step 4: Run manifest tests**

Run:

```bash
python -m pytest tests/test_session_http_manifest.py -q
```

Expected: both tests pass.

- [ ] **Step 5: Run session lifecycle tests**

Run:

```bash
python -m pytest tests/test_phase4_agent_harness.py -q
```

Expected: existing session and MCP packaging tests still pass.

- [ ] **Step 6: Commit this task**

```bash
git add api_gym/session.py tests/test_session_http_manifest.py
git commit -m "feat: advertise HTTP surface in session manifests"
```

---

### Task 4: Add Shared Run-State Helpers Without Forcing A Backend Class

**Files:**
- Create: `api_gym/worlds/state_backends.py`
- Modify: `api_gym/worlds/billing_support_v0/state.py`
- Modify: `api_gym/worlds/unitelabs_plate_qc_v0/state.py`
- Test: `tests/test_world_state_backends.py`

- [ ] **Step 1: Write failing tests for shared state helpers**

Create `tests/test_world_state_backends.py`:

```python
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
```

- [ ] **Step 2: Run tests and verify module missing**

Run:

```bash
python -m pytest tests/test_world_state_backends.py -q
```

Expected: import failure for `api_gym.worlds.state_backends`.

- [ ] **Step 3: Create shared state helper module**

Create `api_gym/worlds/state_backends.py`:

```python
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
```

- [ ] **Step 4: Reuse helpers in existing worlds**

In both `api_gym/worlds/billing_support_v0/state.py` and
`api_gym/worlds/unitelabs_plate_qc_v0/state.py`:

Replace the local `connect` implementation body with:

```python
def connect(db_path: Path) -> sqlite3.Connection:
    """Open an episode SQLite database with API Gym defaults."""
    return connect_sqlite(db_path)
```

Replace `resolve_state_db_path` body with:

```python
def resolve_state_db_path(run_dir: Path) -> Path:
    """Resolve the SQLite state database for a sampled run directory."""
    return resolve_state_db_path_from_metadata(run_dir, metadata_name=RUN_METADATA_NAME)
```

Add imports:

```python
from api_gym.worlds.state_backends import connect_sqlite, resolve_state_db_path_from_metadata
```

Remove direct `json` imports from those files only if nothing else in the file
uses `json`.

- [ ] **Step 5: Ensure samplers create standard subdirectories**

In both `api_gym/worlds/billing_support_v0/sampler.py` and
`api_gym/worlds/unitelabs_plate_qc_v0/sampler.py`, import:

```python
from api_gym.worlds.state_backends import ensure_run_subdirs
```

Call this immediately after the existing `db_path.exists() or task_path.exists()
or run_metadata_path.exists()` guard and before `initialize_db(db_path)`:

```python
    ensure_run_subdirs(out_dir)
```

Keep the existing file-exists guard before creating the standard subdirectories
or initializing state files.

- [ ] **Step 6: Run state and world tests**

Run:

```bash
python -m pytest tests/test_world_state_backends.py tests/test_billing_support_v0.py tests/test_unitelabs_plate_qc_v0.py -q
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit this task**

```bash
git add api_gym/worlds/state_backends.py api_gym/worlds/billing_support_v0/state.py api_gym/worlds/unitelabs_plate_qc_v0/state.py api_gym/worlds/billing_support_v0/sampler.py api_gym/worlds/unitelabs_plate_qc_v0/sampler.py tests/test_world_state_backends.py
git commit -m "feat: add shared run state helpers"
```

---

### Task 5: Add Shared HTTP Adapter Utilities And Reuse Them In Source-Pack Gate

**Files:**
- Create: `api_gym/worlds/http.py`
- Modify: `api_gym/source_pack_gate_server.py`
- Test: `tests/test_world_http_helpers.py`
- Test: `tests/test_source_pack_gate_server.py`

- [ ] **Step 1: Write failing helper tests**

Create `tests/test_world_http_helpers.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from api_gym.worlds.http import append_jsonl, query_params, structured_error_response


def test_append_jsonl_writes_compact_sorted_rows(tmp_path: Path) -> None:
    path = tmp_path / "traces" / "http.jsonl"

    append_jsonl(path, {"b": 2, "a": 1})
    append_jsonl(path, {"ok": True})

    assert path.read_text(encoding="utf-8").splitlines() == [
        '{"a":1,"b":2}',
        '{"ok":true}',
    ]


def test_query_params_preserves_repeated_values() -> None:
    app = FastAPI()

    @app.get("/probe")
    async def probe(request: Request) -> JSONResponse:
        return JSONResponse(query_params(request))

    response = TestClient(app).get("/probe?expand[]=charge&expand[]=customer&limit=10")

    assert response.status_code == 200
    assert response.json() == {"expand[]": ["charge", "customer"], "limit": "10"}


def test_structured_error_response() -> None:
    response = structured_error_response(
        status_code=409,
        code="world_conflict",
        message="The world state rejected this transition.",
        details={"object_id": "obj_123"},
    )

    assert response.status_code == 409
    assert json.loads(response.body) == {
        "ok": False,
        "error": {
            "code": "world_conflict",
            "message": "The world state rejected this transition.",
            "details": {"object_id": "obj_123"},
        },
    }
```

- [ ] **Step 2: Run helper tests and verify import failure**

Run:

```bash
python -m pytest tests/test_world_http_helpers.py -q
```

Expected: import failure for `api_gym.worlds.http`.

- [ ] **Step 3: Create shared HTTP helper module**

Create `api_gym/worlds/http.py`:

```python
"""Shared HTTP adapter helpers for API Gym worlds."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

COMMON_HTTP_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]


async def request_json_or_none(request: Request) -> object:
    """Return a request JSON body, or None for non-JSON/empty bodies."""
    try:
        return await request.json()
    except json.JSONDecodeError:
        return None


def query_params(request: Request) -> dict[str, object]:
    """Return query parameters with repeated keys preserved as lists."""
    return {
        key: values[0] if len(values) == 1 else values
        for key in sorted(set(request.query_params.keys()))
        if (values := request.query_params.getlist(key))
    }


def append_jsonl(path: Path, row: dict[str, object]) -> None:
    """Append one compact JSON object row to a JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")


def structured_error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any],
) -> JSONResponse:
    """Build a stable agent-readable JSON error response."""
    return JSONResponse(
        content={
            "ok": False,
            "error": {
                "code": code,
                "message": message,
                "details": details,
            },
        },
        status_code=status_code,
    )
```

- [ ] **Step 4: Refactor source-pack gate server to use shared helpers**

In `api_gym/source_pack_gate_server.py`:

Replace local `COMMON_HTTP_METHODS` with import:

```python
from api_gym.worlds.http import (
    COMMON_HTTP_METHODS,
    append_jsonl,
    query_params,
    request_json_or_none,
    structured_error_response,
)
```

Change calls:

```python
        request_json = await request_json_or_none(request)
        evidence_row = _base_evidence_row(
            provider=provider,
            version=version,
            method=request.method,
            path=provider_path,
            query_params=query_params(request),
            request_json=request_json,
            selected_case=requested_case,
        )
```

Replace `_record_evidence` body:

```python
def _record_evidence(evidence_path: Path | None, row: dict[str, object]) -> None:
    if evidence_path is None:
        return
    append_jsonl(evidence_path, row)
```

Replace `_source_pack_error_response` body:

```python
def _source_pack_error_response(exc: SourcePackGateError) -> JSONResponse:
    status_code = 404 if "not_found" in exc.code else 400
    return structured_error_response(
        status_code=status_code,
        code=exc.code,
        message=exc.message,
        details=exc.details,
    )
```

Remove the now-unused local `_request_json_or_none`, `_query_params`, and
direct `json` import.

- [ ] **Step 5: Run HTTP helper and gate server tests**

Run:

```bash
python -m pytest tests/test_world_http_helpers.py tests/test_source_pack_gate_server.py -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit this task**

```bash
git add api_gym/worlds/http.py api_gym/source_pack_gate_server.py tests/test_world_http_helpers.py
git commit -m "feat: add shared HTTP adapter helpers"
```

---

### Task 6: Validate World Source References Against Checked-In Source Packs

**Files:**
- Create: `api_gym/worlds/source_refs.py`
- Modify: `api_gym/cli.py`
- Test: `tests/test_world_source_refs.py`

- [ ] **Step 1: Write failing source-ref validator tests**

Create `tests/test_world_source_refs.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from api_gym.cli import app
from api_gym.worlds.source_refs import validate_world_source_refs


def test_validate_billing_world_source_refs() -> None:
    result = validate_world_source_refs("billing_support_v0")

    assert result["ok"] is True
    assert result["world"] == "billing_support_v0"
    assert result["source_pack_count"] == 3
    assert result["world_evidence_count"] == 2


def test_validate_unitelabs_world_source_refs_without_source_packs() -> None:
    result = validate_world_source_refs("unitelabs_plate_qc_v0")

    assert result["ok"] is True
    assert result["world"] == "unitelabs_plate_qc_v0"
    assert result["source_pack_count"] == 0
    assert result["world_evidence_count"] == 2


def test_validate_world_source_refs_reports_missing_record(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    world_dir = repo_root / "worlds" / "example_world"
    pack_dir = repo_root / "source_packs" / "apis" / "example" / "2026-06-22"
    world_dir.mkdir(parents=True)
    pack_dir.mkdir(parents=True)
    (pack_dir / "source_pack.json").write_text(
        json.dumps(
            {
                "records": {
                    "operations": "operations.jsonl",
                    "response_cases": "response_cases.jsonl",
                }
            }
        ),
        encoding="utf-8",
    )
    (pack_dir / "operations.jsonl").write_text(
        json.dumps({"id": "operation:known"}) + "\n",
        encoding="utf-8",
    )
    (pack_dir / "response_cases.jsonl").write_text("", encoding="utf-8")
    (world_dir / "source_refs.json").write_text(
        json.dumps(
            {
                "schema_version": "api_gym.world_source_refs.v0",
                "world": "example_world",
                "source_packs": [
                    {
                        "source_pack_id": "api.example.2026-06-22",
                        "path": "../../source_packs/apis/example/2026-06-22/source_pack.json",
                        "records": ["operation:missing"],
                        "role": "test",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = validate_world_source_refs("example_world", repo_root=repo_root)

    assert result["ok"] is False
    assert result["missing_records"] == [
        {
            "source_pack_id": "api.example.2026-06-22",
            "record_id": "operation:missing",
        }
    ]


def test_world_source_refs_validate_cli() -> None:
    result = CliRunner().invoke(app, ["world-source-refs", "validate", "--world", "billing_support_v0"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["world"] == "billing_support_v0"
```

- [ ] **Step 2: Run tests and verify module/CLI missing**

Run:

```bash
python -m pytest tests/test_world_source_refs.py -q
```

Expected: import failure for `api_gym.worlds.source_refs`.

- [ ] **Step 3: Implement source-ref validator**

Create `api_gym/worlds/source_refs.py`:

```python
"""Validation for world source_refs.json files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def validate_world_source_refs(world: str, *, repo_root: Path | None = None) -> dict[str, Any]:
    """Validate selected source refs for one world."""
    root = (repo_root or PROJECT_ROOT).resolve()
    world_dir = root / "worlds" / world
    source_refs_path = world_dir / "source_refs.json"
    if not source_refs_path.exists():
        return {
            "ok": False,
            "world": world,
            "missing_source_refs": str(source_refs_path),
            "missing_records": [],
            "missing_world_evidence": [],
            "source_pack_count": 0,
            "world_evidence_count": 0,
        }

    payload = _read_json(source_refs_path)
    source_packs = payload.get("source_packs", [])
    world_evidence = payload.get("world_evidence", [])
    missing_records: list[dict[str, str]] = []
    missing_world_evidence: list[str] = []

    if not isinstance(source_packs, list):
        raise ValueError("source_refs.json source_packs must be a list when present.")
    if not isinstance(world_evidence, list):
        raise ValueError("source_refs.json world_evidence must be a list when present.")

    for source_pack_ref in source_packs:
        if not isinstance(source_pack_ref, dict):
            raise ValueError("Each source_packs entry must be an object.")
        source_pack_id = str(source_pack_ref.get("source_pack_id", ""))
        source_pack_path = _resolve_child(world_dir, str(source_pack_ref.get("path", "")))
        available_record_ids = _source_pack_record_ids(source_pack_path)
        for record_id in source_pack_ref.get("records", []):
            if record_id not in available_record_ids:
                missing_records.append({"source_pack_id": source_pack_id, "record_id": str(record_id)})

    for evidence_ref in world_evidence:
        if not isinstance(evidence_ref, dict):
            raise ValueError("Each world_evidence entry must be an object.")
        evidence_path = _resolve_child(world_dir, str(evidence_ref.get("path", "")))
        if not evidence_path.exists():
            missing_world_evidence.append(str(evidence_path))

    return {
        "ok": not missing_records and not missing_world_evidence,
        "world": world,
        "source_pack_count": len(source_packs),
        "world_evidence_count": len(world_evidence),
        "missing_records": missing_records,
        "missing_world_evidence": missing_world_evidence,
    }


def _source_pack_record_ids(source_pack_path: Path) -> set[str]:
    source_pack = _read_json(source_pack_path)
    records = source_pack.get("records")
    if not isinstance(records, dict):
        raise ValueError(f"{source_pack_path} records must be an object.")

    record_ids: set[str] = set()
    for rel_path in records.values():
        if not isinstance(rel_path, str):
            continue
        record_path = _resolve_child(source_pack_path.parent, rel_path)
        if record_path.suffix == ".jsonl" and record_path.exists():
            record_ids.update(_jsonl_ids(record_path))
    return record_ids


def _jsonl_ids(path: Path) -> set[str]:
    ids: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if isinstance(row, dict) and isinstance(row.get("id"), str):
            ids.add(row["id"])
    return ids


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return data


def _resolve_child(parent: Path, rel_path: str) -> Path:
    if not rel_path:
        raise ValueError("source_refs path entries must be non-empty strings.")
    resolved = (parent / rel_path).resolve()
    return resolved
```

- [ ] **Step 4: Add CLI command**

In `api_gym/cli.py`, import:

```python
from api_gym.worlds.source_refs import validate_world_source_refs
```

Add Typer app near the other sub-apps:

```python
world_source_refs_app = typer.Typer(help="World source reference commands.")
app.add_typer(world_source_refs_app, name="world-source-refs")
```

Add command:

```python
@world_source_refs_app.command("validate")
def world_source_refs_validate(
    world: Annotated[str, typer.Option(help="World directory id.")],
) -> None:
    """Validate a world's selected source-pack and evidence references."""
    try:
        result = validate_world_source_refs(world)
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        _exit_error("world_source_refs_validate_failed", str(exc), {"world": world})
    _echo_json(result)
    if not result["ok"]:
        raise typer.Exit(1)
```

- [ ] **Step 5: Run source-ref tests**

Run:

```bash
python -m pytest tests/test_world_source_refs.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Run the CLI manually against current worlds**

Run:

```bash
api-gym world-source-refs validate --world billing_support_v0
api-gym world-source-refs validate --world unitelabs_plate_qc_v0
```

Expected: both commands emit `"ok": true`.

- [ ] **Step 7: Commit this task**

```bash
git add api_gym/worlds/source_refs.py api_gym/cli.py tests/test_world_source_refs.py
git commit -m "feat: validate world source references"
```

---

### Task 7: Include Source Refs And HTTP Traces In Run Exports

**Files:**
- Modify: `api_gym/exports/run_export.py`
- Test: `tests/test_run_export_framework_evidence.py`

- [ ] **Step 1: Write failing export tests**

Create `tests/test_run_export_framework_evidence.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from api_gym.exports.run_export import build_run_export
from api_gym.worlds.billing_support_v0.sampler import sample_episode


def test_run_export_includes_world_source_refs_and_http_trace(tmp_path: Path) -> None:
    episode = sample_episode(
        scenario="duplicate_payment_refund",
        seed=71,
        out_dir=tmp_path / "run",
    )
    trace_path = episode.run_dir / "traces" / "http_requests.jsonl"
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    trace_path.write_text(
        json.dumps(
            {
                "schema_version": "api_gym.world_http_call.v0",
                "method": "GET",
                "path": "/support/tickets/example",
                "status_code": 200,
                "ok": True,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    payload = build_run_export(episode.run_dir)

    assert payload["source_refs"]["path"].endswith("worlds/billing_support_v0/source_refs.json")
    assert payload["source_refs"]["world"] == "billing_support_v0"
    assert len(payload["source_refs"]["source_packs"]) == 3
    assert payload["http_trace"] == [
        {
            "schema_version": "api_gym.world_http_call.v0",
            "method": "GET",
            "path": "/support/tickets/example",
            "status_code": 200,
            "ok": True,
        }
    ]
    assert payload["artifacts"]["http_trace"] == str(trace_path)
```

- [ ] **Step 2: Run test and verify missing export keys**

Run:

```bash
python -m pytest tests/test_run_export_framework_evidence.py -q
```

Expected: failure for missing `source_refs` or `http_trace`.

- [ ] **Step 3: Add source refs and HTTP trace to exports**

In `api_gym/exports/run_export.py`, add:

```python
PROJECT_ROOT = Path(__file__).resolve().parents[2]
```

Add helper:

```python
def _read_world_source_refs(world: str) -> dict[str, Any] | None:
    path = PROJECT_ROOT / "worlds" / world / "source_refs.json"
    if not path.exists():
        return None
    payload = _read_json(path)
    payload["path"] = str(path)
    return payload
```

In `build_run_export`, after `tool_trace`:

```python
    http_trace_path = run_dir / "traces" / "http_requests.jsonl"
    http_trace = _read_jsonl(http_trace_path) if http_trace_path.exists() else []
    source_refs = _read_world_source_refs(str(metadata["world"]))
```

Add top-level fields:

```python
        "source_refs": source_refs,
        "http_trace": http_trace,
```

Add artifact field:

```python
            "http_trace": str(http_trace_path) if http_trace_path.exists() else None,
```

- [ ] **Step 4: Run export tests**

Run:

```bash
python -m pytest tests/test_run_export_framework_evidence.py tests/test_billing_support_phase5_evidence.py -q
```

Expected: selected export/evidence tests pass.

- [ ] **Step 5: Commit this task**

```bash
git add api_gym/exports/run_export.py tests/test_run_export_framework_evidence.py
git commit -m "feat: export source refs and HTTP traces"
```

---

### Task 8: Add Framework Acceptance Smoke Test

**Files:**
- Create: `tests/test_source_pack_to_environment_framework.py`

- [ ] **Step 1: Write end-to-end framework smoke test**

Create `tests/test_source_pack_to_environment_framework.py`:

```python
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from api_gym.exports.run_export import build_run_export
from api_gym.server.app import create_app
from api_gym.session import check_session_tools, create_world_session, finalize_world_session


def test_registered_world_framework_surfaces_work_together(tmp_path: Path) -> None:
    run_dir = tmp_path / "framework-run"

    manifest = create_world_session(
        world="billing_support_v0",
        scenario="duplicate_payment_refund",
        seed=81,
        out_dir=run_dir,
    )
    assert manifest["http"]["available"] is True

    app = create_app(run_dir)
    response = TestClient(app).get("/support/tickets/not-real")
    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert response.json()["error"]["code"] == "ticket_not_found"

    tools = check_session_tools(run_dir)
    assert tools["ok"] is True
    assert "support_get_ticket" in tools["listed_tools"]

    finalization = finalize_world_session(run_dir)
    assert finalization["ok"] is False
    assert finalization["export"]["source_refs"]["world"] == "billing_support_v0"

    export = build_run_export(run_dir)
    assert export["world"] == "billing_support_v0"
    assert export["source_refs"]["world"] == "billing_support_v0"
```

- [ ] **Step 2: Run the smoke test**

Run:

```bash
python -m pytest tests/test_source_pack_to_environment_framework.py -q
```

Expected: the smoke test passes after Tasks 1-7.

- [ ] **Step 3: Commit this task**

```bash
git add tests/test_source_pack_to_environment_framework.py
git commit -m "test: cover source-pack environment framework surfaces"
```

---

### Task 9: Update Documentation For Implemented Framework Surface

**Files:**
- Modify: `docs/playbooks/source-pack-to-environment-framework.md`
- Modify: `README.md`

- [ ] **Step 1: Update the framework doc with concrete commands**

In `docs/playbooks/source-pack-to-environment-framework.md`, add this section
after "First Generic Milestone":

````markdown
## Implemented Generic Surfaces

The generic framework surface is:

```bash
api-gym source-pack validate source_packs/apis/<provider>/<version>
api-gym world-source-refs validate --world <world_id>
api-gym session create --world <world_id> --scenario <scenario> --seed 1 --out runs/<run_id> --json
api-gym serve --run runs/<run_id>
api-gym mcp --run runs/<run_id>
api-gym session check-tools --run runs/<run_id>
api-gym session finalize --run runs/<run_id> --json
```

`api-gym gate serve` remains the stateless source-pack response-case gate.
`api-gym serve` is the stateful world HTTP surface.
```
````

- [ ] **Step 2: Update README integration contract**

In `README.md`, in "Integration Contract", add this short paragraph after the
TypeScript adapter block:

```markdown
For provider-shaped environments, the session manifest may also include an
`http` surface. Use `api-gym serve --run <run_dir>` when the agent or SDK needs
original-shaped HTTP calls. MCP remains available for hosts that prefer tool
calls; both adapters must share the same world state and verifier.
```

- [ ] **Step 3: Run documentation grep checks**

Run:

```bash
rg -n "api-gym gate serve|api-gym serve --run|world-source-refs" README.md docs/playbooks/source-pack-to-environment-framework.md
```

Expected: output includes all three command surfaces.

- [ ] **Step 4: Commit this task**

```bash
git add README.md docs/playbooks/source-pack-to-environment-framework.md
git commit -m "docs: document source-pack environment framework commands"
```

---

### Task 10: Final Verification

**Files:**
- No new files.

- [ ] **Step 1: Validate current source packs used by framework smoke tests**

Run:

```bash
api-gym source-pack validate source_packs/apis/stripe/2026-06-12
api-gym source-pack validate source_packs/apis/zendesk/2026-06-12
api-gym source-pack validate source_packs/apis/hubspot/2026-06-12
```

Expected: all commands emit `"ok": true`.

- [ ] **Step 2: Validate world source refs**

Run:

```bash
api-gym world-source-refs validate --world billing_support_v0
api-gym world-source-refs validate --world unitelabs_plate_qc_v0
```

Expected: both commands emit `"ok": true`.

- [ ] **Step 3: Run focused framework tests**

Run:

```bash
python -m pytest \
  tests/test_world_http_runtime.py \
  tests/test_world_http_cli.py \
  tests/test_session_http_manifest.py \
  tests/test_world_state_backends.py \
  tests/test_world_http_helpers.py \
  tests/test_world_source_refs.py \
  tests/test_run_export_framework_evidence.py \
  tests/test_source_pack_to_environment_framework.py \
  -q
```

Expected: all selected tests pass.

- [ ] **Step 4: Run full test suite**

Run:

```bash
python -m pytest -q
```

Expected: full test suite passes.

- [ ] **Step 5: Inspect git diff**

Run:

```bash
git status --short
git diff --stat
```

Expected: changed files are limited to framework runtime, tests, and docs from
this plan. Existing unrelated dirty worktree files should not be reverted.

---

## Execution Handoff

Recommended execution mode: subagent-driven, one task per worker. Each worker
should own only the files listed in its task and should not edit provider
source packs.

Task dependency order:

```text
Task 1 -> Task 2 -> Task 3
Task 4 -> Task 5
Task 6 -> Task 7
Task 8 -> Task 9 -> Task 10
```

Tasks 4 and 5 can run after Task 1 in parallel with Task 2 if workers keep
their file scopes separate. Task 7 depends on Task 6 only for source-ref export
shape, not for HTTP traces.
