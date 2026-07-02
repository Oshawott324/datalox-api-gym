# Adaptyv Foundry Dry-Run v0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an MCP-only `adaptyv_foundry_dryrun_v0` world with a source-grounded Adaptyv Foundry source pack, deterministic dry-run state, stable agent-readable tools, hidden verifier checks, and session lifecycle support.

**Architecture:** Reuse the existing API Gym world package pattern: root-level `worlds/<world>/` contract files plus `api_gym/worlds/<world>/` runtime modules. The first release is intentionally narrow: one scenario, six task-family fixtures encoded in sampled state metadata, and MCP tools only. Scientific outcomes are replayed fixtures, not predictions.

**Tech Stack:** Python, SQLite, pytest, Typer CLI, existing API Gym MCP/session/export helpers, JSON/JSONL source-pack records.

---

## File Map

- Create `source_packs/apis/adaptyv_foundry/2026-07-01/*` for source substrate.
- Create `worlds/adaptyv_foundry_dryrun_v0/README.md`, `spec.json`, `source_refs.json`, `projection_contract.md`, and `tasks/*.json`.
- Create `api_gym/worlds/adaptyv_foundry_dryrun_v0/{__init__.py,state.py,sampler.py,services.py,tools.py,verifier.py}`.
- Modify `api_gym/worlds/registry.py` to register the world.
- Add tests:
  - `tests/test_adaptyv_foundry_source_pack.py`
  - `tests/test_adaptyv_foundry_world.py`
  - `tests/test_adaptyv_foundry_verifier.py`
  - `tests/test_adaptyv_foundry_session.py`

## Task 1: Source Pack

**Files:**
- Create: `tests/test_adaptyv_foundry_source_pack.py`
- Create: `source_packs/apis/adaptyv_foundry/2026-07-01/source_pack.json`
- Create: `source_packs/apis/adaptyv_foundry/2026-07-01/docs_index.jsonl`
- Create: `source_packs/apis/adaptyv_foundry/2026-07-01/operations.jsonl`
- Create: `source_packs/apis/adaptyv_foundry/2026-07-01/schemas.jsonl`
- Create: `source_packs/apis/adaptyv_foundry/2026-07-01/examples.jsonl`
- Create: `source_packs/apis/adaptyv_foundry/2026-07-01/observed_errors.jsonl`
- Create: `source_packs/apis/adaptyv_foundry/2026-07-01/response_cases.jsonl`
- Create: `source_packs/apis/adaptyv_foundry/2026-07-01/world_candidates.jsonl`

- [ ] **Step 1: Write failing source-pack test**

```python
from pathlib import Path

from api_gym.source_packs import validate_source_pack


REPO_ROOT = Path(__file__).resolve().parents[1]
PACK_ROOT = REPO_ROOT / "source_packs" / "apis" / "adaptyv_foundry" / "2026-07-01"


def test_adaptyv_foundry_source_pack_validates() -> None:
    result = validate_source_pack(PACK_ROOT)

    assert result["ok"] is True
    assert result["source_pack_id"] == "api.adaptyv_foundry.2026-07-01"
    assert result["provider"] == "adaptyv_foundry"
    assert result["record_counts"]["operations"] >= 20
    assert result["record_counts"]["response_cases"] >= result["record_counts"]["operations"]
```

- [ ] **Step 2: Verify red**

Run: `python -m pytest -q tests/test_adaptyv_foundry_source_pack.py`

Expected: FAIL because the source pack path does not exist.

- [ ] **Step 3: Create source-pack records**

Create the pack with the operation ids listed in `docs/reports/adaptyv-foundry-dryrun-v0-build-spec.md`. Use `response_mode: "body_shape"` for success shapes and `response_mode: "error_shape"` for documented/agent-readable errors. Every operation needs at least one response case. All rows need `source_refs` pointing to the official OpenAPI URL or docs URL.

- [ ] **Step 4: Verify green**

Run: `python -m pytest -q tests/test_adaptyv_foundry_source_pack.py tests/test_source_packs.py::test_checked_in_source_packs_validate`

Expected: PASS.

## Task 2: World Shell And Scenario Sampling

**Files:**
- Create: `tests/test_adaptyv_foundry_world.py`
- Create: `api_gym/worlds/adaptyv_foundry_dryrun_v0/__init__.py`
- Create: `api_gym/worlds/adaptyv_foundry_dryrun_v0/state.py`
- Create: `api_gym/worlds/adaptyv_foundry_dryrun_v0/sampler.py`
- Create: `worlds/adaptyv_foundry_dryrun_v0/README.md`
- Create: `worlds/adaptyv_foundry_dryrun_v0/spec.json`
- Create: `worlds/adaptyv_foundry_dryrun_v0/source_refs.json`
- Create: `worlds/adaptyv_foundry_dryrun_v0/projection_contract.md`
- Create: `worlds/adaptyv_foundry_dryrun_v0/tasks/*.json`
- Modify: `api_gym/worlds/registry.py`

- [ ] **Step 1: Write failing world registration and sampler tests**

Test desired behavior:
- `get_world_runtime("adaptyv_foundry_dryrun_v0")` returns a runtime.
- `sample_episode(scenario="partial_results_not_final", seed=1, out_dir=...)` writes `run.json`, `task.json`, and `state.sqlite`.
- The task hides `hidden/` file contents and includes projection metadata.
- `validate_world_source_refs(worlds/adaptyv_foundry_dryrun_v0/source_refs.json)` passes.

- [ ] **Step 2: Verify red**

Run: `python -m pytest -q tests/test_adaptyv_foundry_world.py`

Expected: FAIL because the world package and registry entry do not exist.

- [ ] **Step 3: Implement minimal shell**

Implement constants:

```python
WORLD = "adaptyv_foundry_dryrun_v0"
WORLD_ID = "adaptyv-foundry-dryrun-v0"
SCENARIOS = {
    "budget_cap_quote_reject": ...,
    "expired_quote_not_confirmed": ...,
    "partial_results_not_final": ...,
    "stale_prior_campaign_result": ...,
    "duplicate_submission_guard": ...,
    "measured_result_supported_decision": ...,
}
```

Use SQLite tables from the build spec. Seed state deterministically from the scenario and seed. Insert hidden expected-resolution data into an internal table or events table that is not exposed through tools.

- [ ] **Step 4: Verify green**

Run: `python -m pytest -q tests/test_adaptyv_foundry_world.py`

Expected: PASS.

## Task 3: MCP Tools And Services

**Files:**
- Modify: `tests/test_adaptyv_foundry_world.py`
- Create: `api_gym/worlds/adaptyv_foundry_dryrun_v0/services.py`
- Create: `api_gym/worlds/adaptyv_foundry_dryrun_v0/tools.py`

- [ ] **Step 1: Write failing tool tests**

Test at least:
- expected tool names match the build spec;
- `list_targets` returns selected target data;
- `create_experiment`, `add_sequences_to_experiment`, `estimate_experiment_cost`, `submit_experiment`, `get_experiment_quote`, `confirm_quote`, `list_experiment_updates`, `list_experiment_results`, and `submit_campaign_decision` mutate state as expected;
- errors are structured and stable, including `QUOTE_EXPIRED`, `QUOTE_OVER_BUDGET`, `RESULTS_NOT_READY`, and `LIVE_EXECUTION_FORBIDDEN` where applicable.

- [ ] **Step 2: Verify red**

Run: `python -m pytest -q tests/test_adaptyv_foundry_world.py`

Expected: FAIL because service/tool functions are missing.

- [ ] **Step 3: Implement services and tool definitions**

Follow existing `unitelabs_plate_qc_v0.tools` shape. Return:

```json
{"ok": true, "data": {}, "observation_id": "obs_..."}
```

or:

```json
{"ok": false, "error": {"code": "...", "message": "...", "details": {}}}
```

Keep writes in SQLite only. Do not make network calls.

- [ ] **Step 4: Verify green**

Run: `python -m pytest -q tests/test_adaptyv_foundry_world.py`

Expected: PASS.

## Task 4: Verifier And Known-Bad Coverage

**Files:**
- Create: `tests/test_adaptyv_foundry_verifier.py`
- Create/modify: `api_gym/worlds/adaptyv_foundry_dryrun_v0/verifier.py`
- Modify: `api_gym/worlds/adaptyv_foundry_dryrun_v0/sampler.py`
- Modify: `api_gym/worlds/adaptyv_foundry_dryrun_v0/services.py`

- [ ] **Step 1: Write failing verifier tests**

For each first task family, test one oracle path passes and one known-bad path fails with the exact expected failure code:
- `QUOTE_OVER_BUDGET_CONFIRMED`
- `EXPIRED_QUOTE_CONFIRMED`
- `FINAL_DECISION_USED_PARTIAL_RESULT`
- `STALE_RESULT_USED_FOR_CURRENT_DECISION`
- `DUPLICATE_PAID_SUBMISSION`
- `DECISION_UNSUPPORTED_BY_MEASURED_RESULT`

- [ ] **Step 2: Verify red**

Run: `python -m pytest -q tests/test_adaptyv_foundry_verifier.py`

Expected: FAIL because verifier checks are missing or incomplete.

- [ ] **Step 3: Implement verifier**

Return a result object with:

```python
{
    "ok": bool,
    "scenario": scenario,
    "failure_code": str | None,
    "failure_attribution": str | None,
    "checks": [...]
}
```

Verifier checks must inspect SQLite state and hidden expected data, not transcript text.

- [ ] **Step 4: Verify green**

Run: `python -m pytest -q tests/test_adaptyv_foundry_verifier.py tests/test_adaptyv_foundry_world.py`

Expected: PASS.

## Task 5: Session Lifecycle And Full Verification

**Files:**
- Create: `tests/test_adaptyv_foundry_session.py`
- Modify: `tests/test_session_http_manifest.py`
- Modify any runtime files only if needed to satisfy session lifecycle.

- [ ] **Step 1: Write failing session tests**

Test:
- `create_world_session` works for `partial_results_not_final`;
- HTTP is unavailable for the MCP-only world;
- `check_session_tools` lists all expected tools;
- `finalize_world_session` writes a run export and reflects verifier failure before agent action;
- after oracle tool calls, `finalize_world_session` returns ok.

- [ ] **Step 2: Verify red**

Run: `python -m pytest -q tests/test_adaptyv_foundry_session.py`

Expected: FAIL until lifecycle integration is complete.

- [ ] **Step 3: Implement any missing lifecycle integration**

Use registry/session conventions only. Do not add world-specific branches outside `api_gym/worlds/registry.py` unless an existing shared helper requires it.

- [ ] **Step 4: Verify green and full suite**

Run:

```bash
python -m pytest -q tests/test_adaptyv_foundry_source_pack.py tests/test_adaptyv_foundry_world.py tests/test_adaptyv_foundry_verifier.py tests/test_adaptyv_foundry_session.py tests/test_session_http_manifest.py
python -m pytest -q
api-gym source-pack validate source_packs/apis/adaptyv_foundry/2026-07-01
api-gym session create --world adaptyv_foundry_dryrun_v0 --scenario partial_results_not_final --seed 1 --out runs/adaptyv-demo --json
api-gym session check-tools --run runs/adaptyv-demo
api-gym session finalize --run runs/adaptyv-demo --json
```

Expected: targeted tests pass, full suite passes, source-pack validation passes, check-tools passes. Initial finalize may fail if no oracle actions were applied; the test suite must cover the oracle pass path.
