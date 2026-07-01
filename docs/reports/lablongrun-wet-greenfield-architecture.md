# LabLongRun-Wet Greenfield Architecture

Status update, 2026-07-01:

This architecture remains useful as the calibration kernel for dry-run lab
tasks: sandboxing, traces, seeded faults, admission, oracle, and verifier. It
should not be treated as the current benchmark identity. The next serious build
is multi-provider `lab_campaign_ops_v0`, where Opentrons is one source pack
alongside ELN/LIMS and instrument-data source packs.

Current next-build doc:

```text
docs/reports/lab-campaign-ops-v0-next-build.md
```

This note describes how to build `LabLongRun-Wet v0` if we are free to reshape
the current codebase. The goal is not to build a generic benchmark framework
first. The goal is to build one serious long-horizon wet-lab benchmark, while
extracting only the runtime pieces that are obviously reusable.

The split should be:

```text
api_gym/core/
  reusable rollout, sandbox, trace, fault, verifier-result, and export runtime

worlds/lablongrun_wet_v0/
  wet-lab state, tool semantics, dynamics, task generator, oracle, verifier
```

Rule:

> If the code knows wet-lab meaning, keep it in the world. If the code only
> manages isolation, trace capture, replay, or export shape, keep it in core.

## Target Repository Shape

```text
api_gym/
  core/
    sessions/
      __init__.py
      manifest.py
      lifecycle.py
      registry.py
    sandboxes/
      __init__.py
      base.py
      sqlite.py
      filesystem.py
    traces/
      __init__.py
      schema.py
      recorder.py
    state_diffs/
      __init__.py
      schema.py
      sqlite_diff.py
      semantic.py
    faults/
      __init__.py
      schema.py
      injector.py
      scheduler.py
    verifier_results/
      __init__.py
      schema.py
      writer.py
    exports/
      __init__.py
      run_export.py
      hf_export.py
      dataset_card.py

worlds/
  lablongrun_wet_v0/
    __init__.py
    spec.json
    source_refs.json
    state.py
    tools.py
    dynamics.py
    task_generator.py
    oracle.py
    verifier.py
    templates/
      task_templates.yaml
      protocol_notes/
      plate_maps/
      reagent_inventories/
      prior_run_logs/
    artifacts/
      README.md
```

## Core Runtime Contracts

Core should be boring. It should not know what a tip, well, OD600 readout, or
refund means.

### `core/sessions`

Owns session creation and finalization.

Responsibilities:

- locate a world by id
- load a generated task bundle
- create a per-rollout sandbox
- write `session_manifest.json`
- expose expected tools and artifact paths
- finalize a run by invoking the world verifier
- write `session_finalization.json`

Important data types:

```python
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class SessionManifest:
    session_id: str
    world_id: str
    task_id: str
    seed: int
    run_dir: Path
    agent_task_path: Path
    visible_artifacts_dir: Path
    expected_tools: list[str]
    tool_surface: dict
    finalize_command: list[str]

@dataclass(frozen=True)
class SessionFinalization:
    session_id: str
    passed: bool
    verifier_result_path: Path
    run_export_path: Path
```

Public API:

```python
def create_session(
    world_id: str,
    task_id: str,
    seed: int,
    out: Path,
) -> SessionManifest: ...

def finalize_session(run_dir: Path) -> SessionFinalization: ...
```

### `core/sandboxes`

Owns isolated mutable state per rollout.

For v0, use SQLite plus a filesystem artifact directory. Do not start with
Postgres. SQLite file copies are enough to generate 1,000 tasks and run agent
rollouts locally or in CI.

Responsibilities:

- create a fresh sandbox from an immutable task snapshot
- provide paths to mutable DB and artifact dirs
- destroy or archive after finalization

Important data types:

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

@dataclass(frozen=True)
class SandboxHandle:
    sandbox_id: str
    root: Path
    state_db: Path
    visible_artifacts_dir: Path
    hidden_artifacts_dir: Path

class SandboxProvider(Protocol):
    def create(self, task_bundle: "TaskBundle", out: Path) -> SandboxHandle: ...
```

SQLite implementation:

```text
generated_tasks/<task_id>/initial_state.sqlite
  -> copy to runs/<session_id>/state.sqlite

generated_tasks/<task_id>/visible_artifacts/
  -> copy to runs/<session_id>/artifacts/visible/

generated_tasks/<task_id>/hidden/
  -> copy to runs/<session_id>/artifacts/hidden/
```

### `core/traces`

Owns the append-only record of what happened.

Every tool call should write:

- call id
- tool name
- input args
- observation or structured error
- started/completed timestamps
- logical lab time before/after
- state hash before/after
- semantic events emitted by the world
- fault injected, if any

Schema:

```python
@dataclass(frozen=True)
class ToolCallRecord:
    call_id: str
    step_index: int
    tool_name: str
    args: dict
    observation: dict | None
    error: dict | None
    logical_time_before_ms: int
    logical_time_after_ms: int
    state_hash_before: str
    state_hash_after: str
    semantic_events: list[dict]
    fault: dict | None
```

Files:

```text
runs/<session_id>/tool_calls.jsonl
runs/<session_id>/events.jsonl
```

### `core/state_diffs`

Owns generic diff containers and generic SQLite before/after snapshots.

Core can compute table/row/column changes. The world can add semantic labels
such as `well_volume_changed`, `tip_contaminated`, or `readout_created`.

Generic diff schema:

```python
@dataclass(frozen=True)
class StateDiff:
    call_id: str
    table_diffs: list[dict]
    semantic_diffs: list[dict]
    invariant_deltas: list[dict]
```

Output:

```text
runs/<session_id>/state_diffs.jsonl
```

### `core/faults`

Owns seeded, replayable fault schedules. It does not decide which lab faults
are realistic. The world defines its supported fault types.

Fault schedule:

```python
@dataclass(frozen=True)
class FaultSpec:
    fault_id: str
    tool_name: str
    trigger: dict
    fault_type: str
    params: dict

@dataclass(frozen=True)
class FaultSchedule:
    seed: int
    faults: list[FaultSpec]
```

Supported trigger examples:

```text
at_call_index=17
first_call_to_tool=read_absorbance
when_args_match={"well": "B7"}
after_logical_time_ms=120000
```

The world decides what a fault means:

```text
read_absorbance.timeout
read_absorbance.stale_value
dispense.partial_volume
instrument.busy
```

### `core/verifier_results`

Owns result shape only.

Verifier result schema:

```python
@dataclass(frozen=True)
class Violation:
    category: str
    code: str
    message: str
    severity: str
    tool_call_id: str | None
    evidence: dict

@dataclass(frozen=True)
class VerifierResult:
    passed: bool
    score: float
    violations: list[Violation]
    metrics: dict
```

Categories should be stable across worlds:

```text
terminal_state
resource
temporal
provenance
recovery
live_boundary
world_specific
```

The wet-lab world may add category-specific codes:

```text
TIP_REUSE_CONTAMINATION
OVERDRAW_SOURCE_WELL
STALE_OD600_USED_FOR_DECISION
READ_BEFORE_INCUBATION_COMPLETE
```

### `core/exports`

Owns public artifact assembly.

Run export:

```text
runs/<session_id>/run_export.json
  world_ref
  task_ref
  session_ref
  tool_trace_ref
  state_diff_ref
  verifier_result
  artifact_refs
```

HF export:

```text
LabLongRun-Wet-v0/
  README.md
  dataset_card.md
  tasks.jsonl
  source_refs.json
  verifier/violation_schema.json
  examples/*.json
  trajectories/*.jsonl
```

## Wet-Lab World Contracts

The world owns the scientific and operational meaning.

### `worlds/lablongrun_wet_v0/state.py`

Defines the hidden mutable state and initialization logic.

SQLite schema should be explicit, not a pile of JSON blobs.

Tables:

```sql
CREATE TABLE labware (
  labware_id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  deck_slot TEXT NOT NULL
);

CREATE TABLE wells (
  labware_id TEXT NOT NULL,
  well_name TEXT NOT NULL,
  volume_ul REAL NOT NULL,
  concentration_factor REAL,
  contents_label TEXT,
  PRIMARY KEY (labware_id, well_name)
);

CREATE TABLE tips (
  rack_id TEXT NOT NULL,
  tip_name TEXT NOT NULL,
  status TEXT NOT NULL,
  contaminated_with TEXT,
  PRIMARY KEY (rack_id, tip_name)
);

CREATE TABLE pipette_state (
  pipette_id TEXT PRIMARY KEY,
  current_tip_rack_id TEXT,
  current_tip_name TEXT,
  held_volume_ul REAL NOT NULL,
  held_contents_label TEXT
);

CREATE TABLE instruments (
  instrument_id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  status TEXT NOT NULL,
  busy_until_ms INTEGER NOT NULL
);

CREATE TABLE readouts (
  readout_id TEXT PRIMARY KEY,
  instrument_id TEXT NOT NULL,
  labware_id TEXT NOT NULL,
  well_name TEXT NOT NULL,
  wavelength_nm INTEGER NOT NULL,
  value REAL NOT NULL,
  created_at_ms INTEGER NOT NULL,
  source_event_id TEXT NOT NULL
);

CREATE TABLE protocol_decisions (
  decision_id TEXT PRIMARY KEY,
  decision TEXT NOT NULL,
  cited_readout_ids TEXT NOT NULL,
  rationale TEXT NOT NULL,
  created_at_ms INTEGER NOT NULL
);

CREATE TABLE logical_clock (
  singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
  now_ms INTEGER NOT NULL
);
```

Keep event logs outside or inside SQLite, but make them append-only.

### `worlds/lablongrun_wet_v0/tools.py`

Defines the agent-visible tools and Pydantic request/response schemas.

Tool set for v0:

```text
get_deck_state
get_labware_state
get_protocol_artifact
pick_up_tip
drop_tip
aspirate
dispense
mix
wait
read_absorbance
add_workflow_note
submit_protocol_decision
```

Each tool wrapper should follow one path:

```python
def tool(args, context):
    before_hash = context.state_hash()
    fault = context.faults.match(tool_name, args)
    result = dynamics.apply(tool_name, args, fault=fault)
    after_hash = context.state_hash()
    context.trace.record(...)
    context.diff.record(...)
    return result.observation
```

Do not let tools update SQLite directly. Tools call `dynamics.py`.

### `worlds/lablongrun_wet_v0/dynamics.py`

Defines the state transition semantics.

This is the most important file. It should be boring and strict.

Examples:

```python
def pick_up_tip(state, rack_id: str, tip_name: str) -> ToolResult: ...

def aspirate(
    state,
    labware_id: str,
    well_name: str,
    volume_ul: float,
) -> ToolResult: ...

def dispense(
    state,
    labware_id: str,
    well_name: str,
    volume_ul: float,
) -> ToolResult: ...

def read_absorbance(
    state,
    labware_id: str,
    well_name: str,
    wavelength_nm: int,
) -> ToolResult: ...
```

Dynamics checks:

- no aspirate without tip
- no aspirate over available volume minus dead volume
- no dispense over destination max volume
- no unsafe tip reuse
- no read while instrument busy
- no read before required logical time
- no decision with unknown readout id

Structured tool errors are part of the benchmark:

```json
{
  "error_code": "OVERDRAW_SOURCE_WELL",
  "message": "Requested 80 uL from source_plate:A1, but only 42 uL is available above dead volume.",
  "recoverable": true,
  "agent_hint": "Inspect labware state and replan transfer volume."
}
```

### `worlds/lablongrun_wet_v0/task_generator.py`

Generates tasks at paper scale.

The generator should follow the pattern used by recent serious agent
benchmarks: a generated task is an executable specification, not a prompt with
an answer key. For LabLongRun-Wet, each generated task should couple:

- rendered agent instruction
- initialized lab state
- visible protocol artifacts
- hidden verifier expectations
- oracle/reference plan
- known-bad plans
- validators/verifier predicates
- metadata for difficulty, failure mode, source refs, and admission checks

This is closer to ClawForge/AppWorld-style construction than to a hard-coded
task list. The templates are hand-calibrated; the task instances are generated.

Public API:

```python
def generate_task(
    template_id: str,
    seed: int,
    difficulty: str,
    out: Path,
) -> GeneratedTask: ...

def generate_suite(
    suite_spec: Path,
    out: Path,
) -> list[GeneratedTask]: ...

def validate_generated_task(task_dir: Path) -> AdmissionResult: ...
```

Generated task layout:

```text
generated_tasks/<task_id>/
  task.json
  agent_task.json
  initial_state.sqlite
  visible_artifacts/
    protocol_note.md
    plate_map.csv
    reagent_inventory.csv
    prior_run_log.jsonl
  hidden/
    verifier_expectations.json
    oracle_plan.json
    known_bad_plans.json
    fault_schedule.json
  admission.json
```

Scenario template schema:

```yaml
template_id: stale_od600_requires_reread
lab_failure_mode: stale_evidence
source_refs:
  - opentrons_python_protocol_api
  - pylabrobot_stable_docs
parameter_ranges:
  source_volume_ul: [300, 1200]
  corrected_od600_band: [[1.0, 1.3], [0.8, 1.1]]
initial_state_constraints:
  - source_has_enough_volume
  - prior_readout_exists_but_is_expired
visible_artifact_recipe:
  protocol_note: templates/protocol_notes/od600_qc.md
  plate_map: generated
fault_policy:
  type: none
oracle_strategy: reread_then_decide
known_bad_plan_strategy:
  - cite_stale_prior_readout
verifier_predicates:
  - final_decision_matches_expected
  - decision_cites_run_readout
  - no_stale_readout_used
difficulty_targets:
  expected_horizon: medium
  min_tool_calls: 40
  max_tool_calls: 80
ood_perturbations:
  - alternate_plate_layout
  - distractor_prior_log
```

Admission checks:

- initial state is physically possible
- goal is reachable
- oracle plan passes verifier
- at least one known bad plan fails verifier
- expected tool-call horizon matches difficulty
- no hidden verifier state leaks to visible artifacts
- generated task is not a duplicate
- generated visible artifacts are internally consistent
- task maps to exactly one template and failure mode
- verifier predicates are non-vacuous
- no trivial shortcut can satisfy the verifier while skipping the intended lab
  process

Admission output:

```json
{
  "task_id": "stale_od600_requires_reread__seed_0042",
  "template_id": "stale_od600_requires_reread",
  "seed": 42,
  "difficulty": "medium",
  "expected_horizon": {
    "min_tool_calls": 40,
    "max_tool_calls": 80,
    "oracle_tool_calls": 53
  },
  "admitted": true,
  "checks": [
    {"name": "oracle_passes", "ok": true},
    {"name": "known_bad_fails", "ok": true},
    {"name": "no_hidden_leakage", "ok": true}
  ]
}
```

Template taxonomy for 1,000 tasks:

```text
20 templates x 50 seeds = 1,000 tasks
```

Difficulty bins:

```text
short: 20-40 calls
medium: 40-80 calls
long: 80-150 calls
stress: 150-250 calls
```

### `worlds/lablongrun_wet_v0/oracle.py`

The oracle is not a model. It is a deterministic construction-time planner
that proves the generated task is solvable.

Responsibilities:

- produce an expected valid plan
- execute the plan through the same tools/dynamics as agents
- prove the verifier passes
- estimate expected horizon
- create one or more known bad plans for negative verifier tests

Important:

> The oracle plan is never visible to the agent. It is part of task validation.

Public API:

```python
def build_oracle_plan(task: GeneratedTask) -> OraclePlan: ...

def validate_oracle_plan(task: GeneratedTask, plan: OraclePlan) -> None: ...

def build_known_bad_plans(task: GeneratedTask) -> list[OraclePlan]: ...
```

### `worlds/lablongrun_wet_v0/verifier.py`

Reads hidden state, tool trace, state diffs, and hidden expectations. Produces a
`VerifierResult`.

Checks:

```text
terminal_state:
  target wells contain expected final volumes/concentration bands
  final decision is continue/hold as expected

resource:
  no negative volume
  no source overdraw
  no missing tip use

contamination:
  no unsafe tip reuse
  no carryover into incompatible wells

temporal:
  no read before incubation or wait requirement
  no decision from expired readout

provenance:
  decision cites readout ids generated in this run
  required protocol artifacts were inspected before action

recovery:
  injected fault was detected and handled
  agent did not skip required recovery step

live_boundary:
  no live provider or hardware execution attempted
```

Verifier output should be useful for a paper and for agent debugging:

```json
{
  "passed": false,
  "score": 0.62,
  "violations": [
    {
      "category": "temporal",
      "code": "STALE_OD600_USED_FOR_DECISION",
      "severity": "high",
      "tool_call_id": "call_071",
      "message": "Protocol decision cited readout r12, which was older than the allowed freshness window.",
      "evidence": {
        "readout_id": "r12",
        "readout_age_ms": 720000,
        "max_age_ms": 300000
      }
    }
  ],
  "metrics": {
    "tool_calls": 84,
    "logical_time_ms": 940000,
    "faults_injected": 1,
    "faults_recovered": 0
  }
}
```

## End-To-End Flow

### 1. Generate Benchmark Tasks

```bash
api-gym lablongrun generate-suite \
  --suite worlds/lablongrun_wet_v0/templates/suite_1000.yaml \
  --out generated/lablongrun_wet_v0
```

This writes 1,000 validated task bundles.

### 2. Create A Session

```bash
api-gym session create \
  --world lablongrun_wet_v0 \
  --task generated/lablongrun_wet_v0/tasks/task_000173 \
  --out runs/task_000173/model_x/seed_1
```

This copies `initial_state.sqlite` and visible artifacts into a new sandbox.

### 3. Run Agent

The host reads `session_manifest.json`, exposes the expected tools, gives the
agent `agent_task.json`, and captures tool calls through the core recorder.

### 4. Finalize

```bash
api-gym session finalize --run runs/task_000173/model_x/seed_1
```

This invokes `worlds.lablongrun_wet_v0.verifier.verify(run_dir)` and writes:

```text
verifier_result.json
session_finalization.json
run_export.json
```

### 5. Export HF Artifact

```bash
api-gym export hf \
  --world lablongrun_wet_v0 \
  --tasks generated/lablongrun_wet_v0 \
  --runs runs/lablongrun_wet_v0_baselines \
  --out releases/LabLongRun-Wet-v0
```

## Build Order

### Phase 1: One Valid Task, Full Stack

Build one nominal task end to end.

Deliverables:

- `state.py` schema
- tool wrappers
- deterministic dynamics
- one generated task bundle
- oracle plan
- verifier
- run export

Acceptance:

- oracle passes
- one known bad plan fails
- trace and state diff files are written

### Phase 2: Six Calibration Templates

Add:

- low source volume
- tip exhaustion/contamination
- instrument busy
- stale readout
- partial dispense/read failure

Acceptance:

- 30 generated tasks pass admission checks
- each violation category has at least one negative test

### Phase 3: Generator Scale

Add 20 templates and difficulty bins.

Acceptance:

- 1,000 generated tasks
- no duplicate task ids or equivalent initial states
- oracle pass rate is 100 percent
- known bad plans fail for every template

### Phase 4: Baselines

Run 2 to 3 agents.

Report:

- pass rate by difficulty
- violation rate by category
- recovery success rate
- stale evidence failure rate
- transcript-review false positives
- examples of seeded replay/failure attribution

## What Not To Generalize Yet

Do not build these as generic core abstractions in v0:

- generic physical-world simulator
- generic labware ontology
- generic temporal logic DSL
- generic scientific protocol compiler
- generic reward model
- generic multi-domain task generator

These are tempting, but they will slow the benchmark. Build them only after the
wet-lab world proves which abstractions are real.

## The Engineering Thesis

The product is not a mock environment. It is:

```text
copy-on-write sandboxing
  + semantic tool facade
  + event-sourced trace
  + state-diff trajectories
  + seeded fault injection
  + hidden temporal/provenance verifier
```

For `LabLongRun-Wet v0`, the benchmark contribution lives in the world-specific
state, dynamics, task generator, oracle, and verifier. The reusable API Gym
runtime is the chassis that makes the benchmark reproducible and publishable.
