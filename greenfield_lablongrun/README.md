# Greenfield LabLongRun-Wet Phase 2

This directory is a prototype for the `LabLongRun-Wet v0` architecture. It is
not integrated with the current `api-gym` CLI and does not try to preserve the
existing repo architecture.

The prototype demonstrates a small template-driven source-grounded dry-run
generator. It contains six OD600 calibration task families:

```text
od600_nominal
od600_low_source_volume
od600_contaminated_tip
od600_instrument_busy_wait
od600_stale_readout
od600_partial_dispense_recovery
```

The six original prompts are quarantined from model evaluation because they
disclose reference procedures or challenge-specific recovery behavior. Their
oracle and known-bad controls still run for world calibration, but admission now
fails until each public prompt is redesigned and an exact-digest disclosure
review is recorded in `templates/prompt_disclosure_reviews.json`.

For each template, generation creates a task bundle, clones a SQLite sandbox,
runs an oracle through the same tool path an agent would use, verifies the run,
runs one known-bad plan for the template's declared failure mode, and exports
traces plus verifier results. Admission checks the public schema, all
agent-visible files, the isolated agent-workspace export, the exact prompt-review
digest, projection metadata, deterministic fault/noise schedules, oracle pass,
and exact known-bad failure codes.

Run it from the repository root:

```bash
python -m greenfield_lablongrun.demo --clean
```

Expected outputs:

```text
runs/greenfield_lablongrun_phase2/
  summary.json
  generated/<template_id>/
    task.json
    agent_task.json
    admission.json
    initial_state.sqlite
    source_refs_snapshot.json
    visible_artifacts/
    hidden/
      task_metadata.json
      oracle_plan.json
      known_bad_plans.json
      verifier_expectations.json
      fault_schedule.json
      noise_schedule.json
  runs/<template_id>/oracle/
    tool_calls.jsonl
    state_diffs.jsonl
    verifier_result.json
    run_export.json
  runs/<template_id>/known_bad/
    tool_calls.jsonl
    state_diffs.jsonl
    verifier_result.json
    run_export.json
```

Grounding:

- Opentrons is the primary source for liquid-handling command semantics.
- PyLabRobot is the secondary source for hardware-agnostic lab concepts and the
  direct `read_absorbance` naming.
- API Gym-specific additions such as trace recording, state diffs, logical
  clock, stable JSON schemas, and hidden verifiers are marked benchmark-local in
  `worlds/lablongrun_wet_v0/source_refs.json`.
- Projection, stochastic, hidden-state, safety, verifier, and known-gap
  semantics are stated in
  `worlds/lablongrun_wet_v0/projection_contract.md`.

No live hardware, live provider, or production credential path exists in this
prototype. Internal task bundles and run directories contain evaluator state and
must never be used as an agent working directory. `export_agent_workspace(...)`
is the only supported filesystem package for an agent host; it refuses tasks
that have not passed admission. Its manifest records the SHA-256 digest and byte
size of every public file plus a digest of the complete file-record set.

Generator entry points:

```python
from pathlib import Path
from greenfield_lablongrun.worlds.lablongrun_wet_v0.task_generator import (
    export_agent_workspace,
    generate_suite,
    generate_task,
)

generate_task("od600_nominal", seed=1, difficulty="short", out=Path("runs/generated/nominal"))
generate_task("od600_low_source_volume", seed=1, difficulty="short", out=Path("runs/generated/low_source"))
generate_task("od600_contaminated_tip", seed=1, difficulty="short", out=Path("runs/generated/contaminated_tip"))
generate_task("od600_instrument_busy_wait", seed=1, difficulty="short", out=Path("runs/generated/instrument_busy"))
generate_task("od600_stale_readout", seed=1, difficulty="short", out=Path("runs/generated/stale_readout"))
generate_task("od600_partial_dispense_recovery", seed=1, difficulty="short", out=Path("runs/generated/partial_dispense"))
generate_suite(Path("suite_spec.json"), Path("runs/generated/suite"))
export_agent_workspace(Path("runs/generated/nominal"), Path("agent-workspaces/episode"))
```

Suite specs are JSON and contain a `tasks` list with `template_id`,
`difficulty`, and either `seed` or `seeds`.

The export call above succeeds only after the selected template has an approved
prompt-disclosure review bound to the exact public-template SHA-256 digest.
