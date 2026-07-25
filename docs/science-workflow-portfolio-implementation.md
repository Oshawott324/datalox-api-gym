# Science Workflow Portfolio: Concrete Implementation Plan

Date: 2026-07-25
Status: implementation-ready plan
Companion: `docs/science-long-horizon-workflow-portfolio.md`

## Objective

Build four resettable, source-grounded science worlds that preserve the native
shape of several independent services and can be run by Claude, Codex, and
other agent systems:

1. `science_amr_campaign_v0`
2. `science_growth_kinetics_v0`
3. `science_rnaseq_campaign_v0`
4. `science_metabolomics_qc_v0`

The first executable milestone is not four incomplete worlds. It is one deep
AMR vertical slice:

```text
eLabFTW experiment and sample map
  -> Opentrons protocol upload, analysis, and simulated run
  -> pinned sequence artifact arrival
  -> Galaxy AMR workflow invocation and outputs
  -> eLabFTW result attachment and research decision
```

The slice must pass the existing `datalox_world_bundle_v1` admission path and
must run through the existing gated-runtime session lifecycle. Do not add
another session runtime to API Gym.

## Non-Negotiable Architecture

### Repository ownership

`datalox-gated-runtime` owns:

- authorized local or sandbox probes;
- capture, redaction, promotion, and replay;
- the generic `datalox_world_bundle_v1` loader;
- session lifecycle, HTTP/MCP transport, ledgers, and exports;
- domain-neutral deterministic assertion implementations.

`datalox-api-gym` owns:

- canonical provider/API source packs;
- source-grounded transition, verifier, and reward atoms;
- science world bundle source;
- world-specific state, dynamics, fact adapters, and task families;
- deterministic world builders and mutation suites.

`datalox-rollout-collector` owns:

- benchmark manifests;
- train/dev/test and public/private splits;
- leakage groups;
- rollout quality labels and dataset packaging.

Do not put model planning, retry policy, memory, context management, or model
routing into any of the worlds. Those remain properties of the evaluated agent
host.

### Runtime format

New science worlds should be canonical world bundles directly under API Gym:

```text
worlds/science_amr_campaign_v0/
  README.md
  task.json
  gate_config.json
  source_refs.json
  grounding_matrix.json
  family_contracts/
  tests/trajectories/
  world/
    manifest.json
    v1/
      implementation.py
      providers.py
      facts.py
      verifier.py
      episodes.jsonl
      roles.json
      tools.json
      verifier.json
      sources.json
```

The existing gated runtime can load this without copying the world into its
repository:

```bash
export DATALOX_GATE_EXAMPLES_DIR=/Users/yifanjin/datalox-api-gym/worlds

datalox-gate session create \
  --example science_amr_campaign_v0 \
  --out /tmp/science-amr-run \
  --port 8765 \
  --seed 0 \
  --json
```

The bundle remains self-contained. Every executable Python file and every
contract, episode, source, and trajectory artifact must be covered by
`world/manifest.json` content hashes.

### Provider interface rule

Do not normalize eLabFTW, Opentrons, Galaxy, Seqera, or scientific databases
into a generic science API.

The agent should see provider-shaped operations such as:

```text
elabftw.get_experiment
elabftw.patch_experiment
opentrons.upload_protocol
opentrons.create_analysis
opentrons.create_run
galaxy.create_history
galaxy.upload_dataset
galaxy.invoke_workflow
galaxy.get_invocation
```

MCP is a thin projection over the same provider-shaped request and state. HTTP
and MCP calls must have parity where both surfaces exist.

### Cross-provider join rule

Do not invent a universal entity model. Each world declares only the join keys
needed for its scientific workflow:

```json
{
  "sample_id": "sample-001",
  "barcode": "BC001",
  "plate_id": "plate-amr-01",
  "well": "A1",
  "elabftw_experiment_id": 101,
  "opentrons_run_id": "run-001",
  "sequence_artifact_id": "fastq-001",
  "galaxy_history_id": "history-001"
}
```

Provider responses retain native identifiers. The world stores explicit link
records so the verifier can prove identity across systems.

## Step 0: Preserve The Current Repositories

Before changing any repository:

```bash
git status --short --branch
git fetch --all --prune
```

Use separate branches and worktrees:

```text
datalox-gated-runtime:
  codex/science-provider-captures

datalox-api-gym:
  codex/science-workflow-portfolio

datalox-rollout-collector:
  codex/science-benchmark-packaging
```

Do not mix the provider capture, world composition, and dataset packaging work
into one commit or pull request.

## Step 1: Add Construction-Ready Source-Pack Records

The current API Gym source-pack validator supports arbitrary record files, but
it only has typed validation for operations, schemas, examples, response
cases, probes, errors, and world candidates.

Add four optional construction records without changing existing packs:

```text
transition_atoms.jsonl
verifier_atoms.jsonl
reward_atoms.jsonl
known_gaps.jsonl
```

### Files to change

```text
source_packs/apis/schema.md
api_gym/source_packs.py
tests/test_source_packs.py
tests/fixtures/source_packs/
```

### Minimal record contracts

`transition_atoms.jsonl`:

```json
{
  "id": "transition:opentrons.create_analysis",
  "source_pack_id": "api.opentrons.<version>",
  "operation_ref": "operation:createAnalysis",
  "grounding_level": "G2_LOCAL_PROBE",
  "preconditions": [
    {"fact": "protocol.exists", "value": true}
  ],
  "effects": [
    {"fact": "analysis.status", "value": "pending"},
    {"fact": "analysis.protocol_id", "from_request": "/protocolId"}
  ],
  "source_refs": [
    {"kind": "probe", "path": "raw/probes/create_analysis_success.json"}
  ]
}
```

`verifier_atoms.jsonl`:

```json
{
  "id": "verifier:opentrons.analysis_succeeded",
  "source_pack_id": "api.opentrons.<version>",
  "requires_facts": [
    "analysis.status",
    "analysis.errors",
    "analysis.protocol_id"
  ],
  "clause_type": "state_equals",
  "default_failure_code": "opentrons.analysis_not_successful",
  "source_refs": [
    {"kind": "probe", "path": "raw/probes/analysis_terminal_success.json"}
  ]
}
```

`reward_atoms.jsonl`:

```json
{
  "id": "reward:opentrons.valid_analysis",
  "source_pack_id": "api.opentrons.<version>",
  "verifier_atom_refs": ["verifier:opentrons.analysis_succeeded"],
  "value": 1.0,
  "aggregation": "all_required",
  "source_refs": [
    {"kind": "contract", "path": "verifier_atoms.jsonl"}
  ]
}
```

`known_gaps.jsonl`:

```json
{
  "id": "gap:opentrons.hardware_motion",
  "source_pack_id": "api.opentrons.<version>",
  "scope": "hardware execution",
  "status": "unsupported",
  "reason": "Only the official local simulator was executed.",
  "forbidden_claims": [
    "physical gantry motion",
    "physical pipetting accuracy",
    "real module timing"
  ],
  "source_refs": [
    {"kind": "probe_policy", "path": "raw/probe_manifest.json"}
  ]
}
```

### Validation requirements

Extend `validate_source_pack()` so it fails when:

- an atom references an absent operation or verifier atom;
- `grounding_level` is absent or not G0-G4;
- `source_refs` are missing;
- a transition atom has no declared effects;
- a verifier atom has no required facts or failure code;
- a reward atom references a missing verifier atom;
- a known gap has no `forbidden_claims`.

Do not make these four files mandatory for legacy packs. A new pack is called
construction-ready only when all four exist and pass.

### Acceptance command

```bash
python -m pytest \
  tests/test_source_packs.py \
  tests/test_source_pack_to_environment_framework.py \
  -q
```

## Step 2: Capture eLabFTW As G2

This work belongs in `datalox-gated-runtime` because it executes and records a
local provider.

### 2.1 Pin and start a disposable local service

Add:

```text
scripts/providers/elabftw-local.sh
scripts/providers/fixtures/elabftw/
  docker-compose.yml
  seed.json
  sample-attachment.txt
```

The shell helper must:

1. use a pinned eLabFTW image digest, not `latest`;
2. create a disposable database volume;
3. create one admin and one restricted user;
4. seed two experiments, three samples/items, tags, metadata, and one upload;
5. print the loopback base URL and container identifiers;
6. provide `start`, `seed`, `probe`, and `destroy` subcommands.

The probe must refuse to run unless:

- the base URL resolves to loopback;
- the expected disposable deployment marker exists;
- the deployment image digest matches the pin;
- no production credential environment variable is present.

### 2.2 Capture a connected operation surface

Add:

```text
scripts/providers/capture-elabftw-local.py
probes/elabftw_local.json
```

Capture concrete request and response bodies for:

```text
authentication/self inspection
experiments list/get/create/patch
experiment revision or timestamp change
items/resources list/get
uploads create/get/delete
tags and links
metadata update and read-back
soft delete and restore, if supported by the pinned version
restricted-user permission denial
validation failure
missing-id failure
stale update or conflict, if the service exposes one
```

Every capture record must contain:

```json
{
  "provider": "elabftw",
  "provider_version": "<pinned version>",
  "captured_at": "<UTC timestamp>",
  "request": {
    "method": "PATCH",
    "path": "/api/v2/experiments/101",
    "headers": {"content-type": "application/json"},
    "body": {}
  },
  "response": {
    "status": 200,
    "headers": {"content-type": "application/json"},
    "body": {}
  },
  "pre_state_digest": "sha256:...",
  "post_state_digest": "sha256:...",
  "grounding_level": "G2_LOCAL_PROBE"
}
```

Strip tokens, cookies, container paths, host usernames, and private network
information before the capture can be committed.

### 2.3 Build the runtime provider component

Add:

```text
envs/probed_elabftw_local_v0/
  task.json
  gate_config.json
  replay_script.json
  provider_core_coverage.json
  evidence/
  world/
```

The world should shadow writes in run-private state and preserve eLabFTW body
and error shapes. It should include at least these operation families:

```text
experiments
items/resources
uploads
tags/links
metadata
permissions
deletion/restoration
```

### 2.4 Export the canonical API Gym pack

Copy only sanitized, durable evidence into:

```text
source_packs/apis/elabftw/<capture-date>/
  raw/openapi.json
  raw/probes/
  source_pack.json
  docs_index.jsonl
  operations.jsonl
  schemas.jsonl
  response_cases.jsonl
  probes.jsonl
  observed_errors.jsonl
  transition_atoms.jsonl
  verifier_atoms.jsonl
  reward_atoms.jsonl
  known_gaps.jsonl
  world_candidates.jsonl
```

The source pack must cite the runtime capture record and its SHA-256 digest.
Do not cite the local shadow as evidence of physical or production behavior.

### eLabFTW exit gate

```bash
python -m datalox_gated_runtime.cli env verify-replay \
  --env envs/probed_elabftw_local_v0 \
  --json

api-gym source-pack validate \
  source_packs/apis/elabftw/<capture-date>
```

Required result:

- zero replay misses;
- success and negative bodies captured;
- read-after-write behavior admitted;
- reset produces the same initial fingerprint;
- no credential material in the committed artifacts.

## Step 3: Execute The Opentrons Non-GET Lifecycle

The existing `probed_opentrons_local_v0` has 66 concrete GET captures, but the
65 non-GET operations were not executed. Extend it. Do not create a second
Opentrons source pack with overlapping identity.

### 3.1 Add simulator-only protocol fixtures

In `datalox-gated-runtime`, add:

```text
scripts/providers/fixtures/opentrons/
  amr_library_prep_smoke.py
  invalid_labware.py
  missing_module.py
  invalid_parameter.py
  flex_absorbance_smoke.py
```

`amr_library_prep_smoke.py` should be a bounded, published-protocol-derived
simulation fixture that exercises labware loading, pipette selection, transfer
commands, and protocol analysis. It is not a claim of a complete clinical NGS
library-preparation protocol.

`flex_absorbance_smoke.py` is a feasibility fixture. It enters the growth world
only if the official simulator executes its complete module lifecycle.

### 3.2 Add a fail-closed simulator probe

Add:

```text
scripts/providers/capture-opentrons-simulator-writes.py
```

Before any POST, PATCH, or DELETE, the script must prove:

```text
base URL is loopback
health.robot_serial == "simulator"
health.fw_version indicates the virtual backend
no USB or real robot target is configured
the persistence directory is disposable
```

Then capture:

```text
protocol upload/read/delete
analysis create/poll/read
analysis errors and commands
run create/read/delete
run actions needed for the simulator lifecycle
run current state
run commands list/read
protocol parameter validation
missing labware/module errors
invalid run-state transition
duplicate action or idempotency behavior
```

Never weaken these checks to make a probe pass. If the official simulator does
not support an operation, record the gap.

### 3.3 Refresh the existing provider component and pack

Update:

```text
datalox-gated-runtime/envs/probed_opentrons_local_v0/
datalox-api-gym/source_packs/apis/opentrons/<new-capture-date>/
```

The new source pack supersedes the 2026-06-16 pack for new worlds. Keep the old
pack immutable.

### Opentrons exit gate

The AMR world requires these G2 transitions:

```text
upload protocol
create and poll analysis
create simulated run
observe terminal simulated run or terminal analysis result
read command and error evidence
delete or reset run-private lifecycle state
```

The growth world additionally requires:

```text
load Absorbance Plate Reader module
initialize module
load plate
read
retrieve result
```

If the second list does not work in the official simulator, mark the Flex
topology blocked and use the separately named Synergy H1 topology. Do not join
the two devices into one fictional workcell.

## Step 4: Define The AMR Family Contract Before World Code

Add:

```text
worlds/science_amr_campaign_v0/grounding_matrix.json
worlds/science_amr_campaign_v0/source_refs.json
worlds/science_amr_campaign_v0/family_contracts/amr_nominal_v1.json
worlds/science_amr_campaign_v0/family_contracts/amr_identity_recovery_v1.json
worlds/science_amr_campaign_v0/family_contracts/amr_analysis_recovery_v1.json
```

Start with three families, not ten.

### Family contract schema

Each contract declares:

```json
{
  "schema_version": "api_gym.science_family_contract.v1",
  "family_id": "amr_identity_recovery_v1",
  "scientific_scope": "research-use AMR workflow",
  "source_refs": [],
  "parameter_space": {},
  "initial_state_contract": {},
  "fault_schedule_contract": {},
  "obligations": [],
  "valid_alternatives": [],
  "mutant_families": [],
  "stop_conditions": []
}
```

An obligation is a typed clause, not Python:

```json
{
  "id": "current_amr_artifact_matches_isolate",
  "type": "artifact_lineage_current",
  "artifact_ref": "galaxy.amr_result",
  "entity_ref": "sample.isolate",
  "required_version_ref": "elabftw.sample_map_version",
  "failure_code": "amr.result_wrong_isolate_or_version"
}
```

### Three initial families

`amr_nominal_v1`:

- 2-4 isolates;
- valid sample map and barcodes;
- valid Opentrons analysis;
- complete sequence artifacts;
- successful Galaxy invocation;
- current result attached to the matching eLabFTW experiment.

`amr_identity_recovery_v1`:

- one barcode or plate-well mapping changes;
- old sequence or Galaxy output remains present;
- agent must invalidate the stale result and use current lineage;
- final eLabFTW attachment must cite the corrected isolate.

`amr_analysis_recovery_v1`:

- one incomplete input or failed Galaxy job;
- agent may rerun only the affected item or invocation;
- partial output cannot support the final decision;
- current successful output and complete provenance are required.

### Domain review gate

Before generating episodes, ask one domain reviewer to check:

- whether the workflow order is scientifically recognizable;
- whether the identity and QC obligations are meaningful;
- whether the recovery choices are valid;
- whether any accepted near-miss is actually unsafe or scientifically invalid.

Do not ask the reviewer to inspect generated JSON or all future episodes.

## Step 5: Build One Self-Contained AMR World Bundle

Add:

```text
scripts/worlds/build_science_amr_campaign.py
worlds/science_amr_campaign_v0/
tests/test_science_amr_campaign.py
```

### 5.1 Provider state views

Use one run-private world session, with separate provider state views:

```text
state.elabftw
state.opentrons
state.artifact_arrival
state.galaxy
state.joins
state.fact_index
```

Each provider handler reads and writes only its own state view, except that
world-owned join and fact-index updates occur in the same runtime transaction.

### 5.2 Provider-shaped operations

Initial agent-visible tool surface:

eLabFTW:

```text
list_experiments
get_experiment
patch_experiment
list_items
get_item
list_uploads
create_upload
get_upload
```

Opentrons:

```text
list_protocols
upload_protocol
get_protocol
create_analysis
get_analysis
list_analysis_commands
create_run
get_run
post_run_action
get_run_commands
```

Artifact arrival:

```text
list_sequence_deliveries
get_sequence_delivery
accept_sequence_delivery
```

Galaxy:

```text
create_history
upload_dataset
create_collection
get_workflow
invoke_workflow
get_invocation
get_invocation_jobs_summary
get_dataset
get_provenance
```

Use the exact admitted AMR workflow and pinned tool versions. Do not expose
arbitrary Galaxy workflows in v0.

### 5.3 Asynchronous dynamics

Use the gated runtime clock and scheduled events:

```text
Opentrons analysis pending -> succeeded or failed
sequence delivery pending -> available
Galaxy invocation new -> scheduled -> running -> terminal
```

The seed selects a declared deterministic fault schedule. The agent cannot see
the hidden schedule, but it can inspect provider status and recover.

Do not claim the event delays or fault frequency match production. They are
benchmark-defined schedules over provider-grounded state transitions.

### 5.4 Materialized fact index

Do not make every verifier clause rescan the complete ledger.

Whenever a provider transition commits, update these facts transactionally:

```text
entity.current_version
entity.current_barcode
entity.current_plate_well
artifact.checksum
artifact.source_entity
artifact.source_version
artifact.complete
execution.input_versions
execution.workflow_revision
execution.terminal_status
decision.cited_artifacts
resource.active_owner
```

Retain the raw ledger for audit. Verification should load the materialized
facts once and evaluate all clauses against one immutable workspace.

### 5.5 Verifier structure

`world/v1/facts.py`:

- projects provider state and runtime artifacts into typed facts;
- performs one pass over relevant records;
- contains no task-specific pass/fail policy.

`world/v1/verifier.py`:

- loads the selected family contract;
- compiles typed obligations to existing gated-runtime deterministic
  assertions;
- evaluates each obligation once;
- returns stable failure codes and evidence references.

`world/v1/implementation.py`:

- owns provider routes and transitions;
- calls the fact-index updater transactionally;
- delegates final verification to `verifier.py`.

Use existing runtime assertions first:

```text
StateEquals
CrossStateEquals
OperationPresent
OperationAbsent
OperationsOrdered
RequestValueEquals
MutationScopeEquals
MutationScopeContains
ArtifactExists
ArtifactSchemaMatches
ArtifactStatusEquals
ArtifactLineageContains
EvidenceFresh
ScheduledEventDeliveryEquals
ForbiddenActorToolAttemptAbsent
```

Add a new generic assertion to `datalox-gated-runtime` only when:

1. two independent science worlds need the same semantics;
2. the semantics are domain-neutral;
3. the assertion cannot be expressed as a composition of existing assertions;
4. it has direct unit tests and stable failure behavior.

### 5.6 Mutant generation

The builder generates trajectories from the family contract. It should mutate
state or tool arguments, not verifier output.

Required AMR mutation operators:

```text
replace_entity_link
replace_artifact_version
drop_required_artifact
truncate_artifact
duplicate_artifact
change_checksum
use_superseded_execution
stop_job_before_terminal
attach_result_to_wrong_experiment
submit_before_qc_complete
repeat_non_idempotent_action
```

Each generated episode must include:

- one reference trajectory that passes;
- one empty trajectory that fails;
- one wrong-entity negative;
- one stale/provenance negative;
- one partial-result negative;
- one fault/recovery negative;
- one duplicate-action negative where applicable;
- one valid near-miss or alternative recovery.

Negative trajectories declare exact expected failure codes.

### 5.7 Deterministic build

The build script:

1. reads family contracts and source refs;
2. generates episodes from explicit seeds;
3. generates reference, negative, and parity trajectories;
4. writes bundle documents;
5. computes all content hashes;
6. refuses an undocumented provider operation;
7. supports `--check` to prove committed output is reproducible.

Commands:

```bash
python scripts/worlds/build_science_amr_campaign.py
python scripts/worlds/build_science_amr_campaign.py --check
```

## Step 6: Admit And Profile The AMR World

### Structural and runtime admission

```bash
export DATALOX_GATE_EXAMPLES_DIR=/Users/yifanjin/datalox-api-gym/worlds

datalox-gate env admit-world \
  --env /Users/yifanjin/datalox-api-gym/worlds/science_amr_campaign_v0 \
  --json
```

Admission must prove:

- bundle hashes;
- source and grounding references;
- reset determinism;
- HTTP/MCP parity;
- reference and negative trajectory outcomes;
- no hidden-state leakage;
- no credentials;
- no live writes;
- final session export.

### Direct session smoke

```bash
rm -rf /tmp/science-amr-run

datalox-gate session create \
  --example science_amr_campaign_v0 \
  --out /tmp/science-amr-run \
  --port 8765 \
  --seed 0 \
  --json

datalox-gate session check \
  --run /tmp/science-amr-run \
  --json

datalox-gate session finalize \
  --run /tmp/science-amr-run \
  --json
```

The empty session should fail the verifier with expected missing-obligation
codes. Execute the reference trajectory separately and require a pass.

### Performance gates

Measure these separately:

```text
session initialization
one provider read
one provider write
one scheduled-event delivery
fact projection
full verification
full reference trajectory
all admission trajectories
```

Initial limits on a development laptop:

```text
single verification, p95:       <= 100 ms
single provider operation, p95: <= 50 ms
session reset:                  <= 250 ms
30-trajectory admission:        <= 15 s
```

These are engineering budgets, not paper claims. Record the actual machine and
software versions.

If verification exceeds the budget:

1. profile before changing semantics;
2. remove repeated event/state scans;
3. use materialized facts and indexed lookups;
4. batch clause evaluation over one workspace;
5. cache immutable family contracts;
6. never cache a verdict across mutable state.

Do not replace deterministic checks with an LLM to hide verifier latency.

## Step 7: Build Growth As The Transfer Test

Do not extract a generic science verifier before this step. Growth is the
second world that proves which AMR abstractions actually transfer.

### Required files

```text
scripts/worlds/build_science_growth_kinetics.py
worlds/science_growth_kinetics_v0/
tests/test_science_growth_kinetics.py
```

### World boundaries

```text
eLabFTW plate map, controls, and protocol revision
  -> one selected reader topology
  -> scheduled read jobs over logical time
  -> pinned public OD600 observations
  -> eLabFTW QC decision and deviation record
```

Use exactly one reader topology:

- Opentrons Flex Absorbance Plate Reader if the official simulation probe
  passes the required lifecycle; or
- a separately named PyLabRobot/Synergy H1 projection with explicit
  assumptions and no Opentrons claim.

### First three families

```text
growth_nominal_v1
growth_cadence_recovery_v1
growth_plate_revision_freshness_v1
```

Required negative operators:

```text
temperature_set_without_stabilization
insufficient_incubation_exposure
measurement_outside_cadence_window
reader_busy_without_reschedule
partial_read_treated_as_complete
wrong_plate_or_barcode
stale_series_after_plate_change
overlapping_reader_jobs
missing_blank_or_replicate
decision_from_incomplete_series
```

These operators are grounded only when the family contract defines:

- the required temperature and stabilization criterion;
- the required exposure interval;
- the observation cadence and tolerance;
- reader exclusivity;
- expected wells, blanks, controls, and replicates;
- the plate and protocol version that makes a series current.

### Transfer measurement

After growth admission, classify every clause implementation:

```text
reused unchanged from AMR
reused with new parameters
new domain adapter over an existing primitive
new primitive
world-specific scientific check
```

Report:

```text
primitive implementation reuse
clause reuse
mutant catch rate
near-miss pass rate
verification latency
authoring time
```

Do not estimate a reuse percentage before both worlds pass.

## Step 8: Extract The Small Verifier Compiler

Only after AMR and growth pass, extract repeated construction logic into:

```text
api_gym/verification/
  contracts.py
  clauses.py
  compile.py
  results.py
  mutation_contracts.py
```

This is a compiler from typed obligations to deterministic assertions:

```text
family contract
  -> validated typed clauses
  -> provider/world fact requirements
  -> deterministic assertion instances
  -> diagnostic vector
```

It is not:

- a universal scientific ontology;
- a transcript judge;
- an LLM-authored verifier at rollout time;
- one custom verifier per MCP call;
- a replacement for provider state.

### Compiler contract

Input:

```json
{
  "clauses": [
    {
      "id": "result_is_current",
      "type": "artifact_lineage_current",
      "parameters": {},
      "failure_code": "workflow.result_stale"
    }
  ]
}
```

Output:

```json
{
  "required_facts": [],
  "assertions": [],
  "failure_codes": [],
  "source_refs": []
}
```

The compiler must fail when:

- a clause type is unknown;
- a required fact has no provider or world adapter;
- a failure code is duplicated ambiguously;
- a grounding source is absent;
- a clause requests hidden answer text;
- a provider operation is outside the declared pack.

### LLM role

An LLM may:

- propose a draft family contract;
- suggest candidate mutations;
- explain an already computed failure;
- identify missing source evidence during authoring.

An LLM may not:

- decide the rollout verdict;
- infer hidden state from transcript text;
- generate a verifier during a scored rollout;
- silently repair a missing provider fact;
- define unreviewed scientific thresholds.

## Step 9: Add RNA-seq Only After Seqera Qualifies

### Seqera acquisition gate

In `datalox-gated-runtime`, capture one authorized test workflow:

```text
workspace inspection
pipeline and revision inspection
launch configuration
workflow launch
status polling
task and log inspection
cancel
resume
invalid parameter
permission denial
terminal failure
```

Use one pinned `nf-core/rnaseq` test profile and record the exact revision and
container or software references.

If no authorized workspace is available, stop. Do not implement provider
behavior from documentation alone and call it a headline world.

### World implementation

Add:

```text
source_packs/apis/seqera/<capture-date>/
scripts/worlds/build_science_rnaseq_campaign.py
worlds/science_rnaseq_campaign_v0/
tests/test_science_rnaseq_campaign.py
```

The first three families:

```text
rnaseq_nominal_v1
rnaseq_partial_cohort_recovery_v1
rnaseq_reference_revision_v1
```

This world is the first held-out workflow used to test whether AMR/growth
verification primitives transfer without redesign.

## Step 10: Add Metabolomics With One Exact Galaxy Workflow

Do not generalize the current Galaxy AMR world into arbitrary workflow support.

### Pin an exact workflow

Record:

```text
workflow file digest
workflow revision
Galaxy tool ids and versions
input artifact digests
expected output artifact schemas
public training source
license and redistribution status
```

Add a separately admitted exact W4M component or exact workflow template to the
Galaxy provider implementation. The AMR template and W4M template must remain
independently pinned and testable.

### World implementation

Add:

```text
scripts/worlds/build_science_metabolomics_qc.py
worlds/science_metabolomics_qc_v0/
tests/test_science_metabolomics_qc.py
```

First three families:

```text
metabolomics_nominal_v1
metabolomics_batch_qc_recovery_v1
metabolomics_workflow_revision_v1
```

The instrument boundary remains pinned artifact arrival. Do not claim LC-MS
instrument control until an authorized provider capture replaces it.

## Step 11: Controlled Agent Runs

Do not hard-code Claude or Codex logic into a world. Use each host's normal MCP
attachment path and the session manifest.

### Per-run procedure

```bash
export DATALOX_GATE_EXAMPLES_DIR=/Users/yifanjin/datalox-api-gym/worlds

datalox-gate session create \
  --example science_amr_campaign_v0 \
  --out "$RUN_DIR" \
  --port "$PORT" \
  --seed "$SEED" \
  --json

datalox-gate session check --run "$RUN_DIR" --json
```

Give the agent:

- `task.json`;
- the manifest-declared MCP server;
- declared visible scientific input artifacts;
- the same turn, tool-call, wall-time, and cost budget.

Do not give the agent:

- world source;
- family contracts;
- verifier configuration;
- negative trajectories;
- expected failure codes;
- state database;
- hidden fault schedule.

After the agent stops:

```bash
datalox-gate session finalize --run "$RUN_DIR" --json
```

### Pilot matrix

Start with:

```text
2 admitted worlds
x 15 held-out tasks
x 3 agent systems
x 5 attempts
= 450 runs
```

Configurations:

```text
Claude controlled MCP
Codex controlled MCP
one additional controlled agent host
```

Run Claude Science as a separate native-scaffold study. Do not mix its scores
with the controlled track unless tool exposure and budgets are equivalent.

### Agent-CI report

Create `agent_ci.json` beside each `run_export.json`, then aggregate with the
existing runtime script:

```bash
python /Users/yifanjin/datalox-gated-runtime/scripts/evaluate_world_runs.py \
  runs/science-pilot \
  --json-out reports/science-pilot.json \
  --markdown-out reports/science-pilot.md \
  -k 1 \
  -k 3 \
  -k 5
```

Separate:

```text
passed
agent_failure
infrastructure_failure
```

Do not count infrastructure failures as model failures.

## Step 12: Package The Benchmark Downstream

The rollout collector is currently boundary-first and does not yet expose a
complete packaging CLI. Implement dataset packaging there only after stable
run exports exist.

Add to `datalox-rollout-collector`:

```text
src/scienceBenchmark.ts
tests/scienceBenchmark.test.ts
docs/science-benchmark-contract.md
```

Each dataset row must reference immutable upstream evidence:

```text
world_ref
task_ref
rollout_ref
outcome_ref
label_ref
```

Split by leakage group, not random row:

```text
family id
protocol/workflow revision
public input dataset
mutation combination
parameter-region bucket
```

Hold out at least:

- one configuration region per family;
- one workflow revision where possible;
- compound mutation combinations;
- the RNA-seq and metabolomics transfer worlds during early method
  development.

Do not copy world truth or verifier internals into model-visible training rows.

## Pull Request Sequence

Keep reviewable boundaries.

### Runtime PR 1: eLabFTW G2

Contents:

- pinned disposable service;
- safe local capture;
- sanitized evidence;
- provider replay/shadow world;
- replay and reset tests.

### Runtime PR 2: Opentrons write lifecycle

Contents:

- simulator-only protocol fixtures;
- non-GET captures;
- refreshed provider world;
- fail-closed hardware boundary tests.

### API Gym PR 1: construction-ready source-pack records

Contents:

- optional atom schemas;
- validator and tests;
- no provider data yet.

### API Gym PR 2: refreshed provider packs

Contents:

- eLabFTW G2 pack;
- refreshed Opentrons G2 pack;
- exact citations to runtime capture digests.

### API Gym PR 3: AMR vertical slice

Contents:

- three reviewed families;
- world bundle;
- oracle, negative, near-miss, and parity trajectories;
- deterministic build;
- admission and performance report.

### API Gym PR 4: growth transfer world

Contents:

- grounded reader topology decision;
- public OD600 artifact;
- three reviewed families;
- transfer and performance measurements.

### API Gym PR 5: verifier compiler extraction

Contents:

- only abstractions demonstrated by AMR and growth;
- clause validation;
- mutation contract validation;
- no scientific thresholds in generic code.

### Later PRs

- Seqera acquisition and RNA-seq world;
- exact Galaxy W4M component and metabolomics world;
- rollout collector packaging;
- controlled agent pilot reports.

## Ownership

Product and scientific owner:

- choose the exact public protocols and datasets;
- obtain provider access where required;
- coordinate one high-leverage domain review per family group;
- approve public provider claims and stop decisions.

Runtime and evaluation engineering:

- provider capture safety;
- world-bundle admission;
- verifier profiling and domain-neutral assertion performance;
- controlled agent-host parity;
- infrastructure-failure accounting.

World construction:

- compile reviewed contracts and grounded provider packs into bundles;
- implement provider-shaped local state and transitions;
- generate deterministic episodes and mutation trajectories;
- keep source, state, verifier, and agent-visible boundaries separate.

No biology knowledge is required to implement the generic runtime and
performance work. Scientific obligations and thresholds must come from pinned
sources or focused domain review before they become contracts.

## First Ten Working Days

### Days 1-2

- add construction-ready source-pack records and validation;
- start pinned eLabFTW locally;
- capture one experiment create/read/update cycle and one permission failure.

Exit: one concrete G2 eLabFTW state transition with sanitized request and
response bodies.

### Days 3-4

- finish the selected eLabFTW operation surface;
- build and replay its local provider component;
- refresh the canonical API Gym source pack.

Exit: eLabFTW pack validates and reset/replay pass.

### Days 5-6

- start the official Opentrons simulator;
- upload the AMR smoke protocol;
- create and poll analysis;
- create and complete one simulated run lifecycle;
- capture commands and negative cases.

Exit: the required AMR Opentrons transitions are G2 or the AMR topology is
stopped.

### Day 7

- write and review three AMR family contracts;
- freeze exact Galaxy AMR workflow and input artifact digests;
- complete `grounding_matrix.json`.

Exit: no consequential AMR transition is G0/G1.

### Days 8-10

- build one AMR episode end to end;
- add reference, wrong-identity, stale-result, and partial-result trajectories;
- run world admission;
- profile verification;
- fix correctness before adding task count.

Exit: one admitted cross-provider AMR world with at least one deep family.

## Definition Of Done For The First Milestone

The AMR vertical slice is done only when:

- eLabFTW and Opentrons consequential writes have G2 evidence;
- the exact Galaxy AMR workflow is pinned;
- the agent acts through provider-shaped HTTP/MCP operations;
- at least two independent stateful providers are involved;
- one world reset reproduces the initial fingerprint;
- HTTP and MCP parity passes for representative operations;
- oracle trajectories pass;
- empty, wrong-identity, stale, partial, fault, and duplicate mutants fail with
  exact codes;
- valid alternative recovery passes;
- the verifier uses one fact projection and does not repeatedly rescan the
  ledger per clause;
- verification and admission are profiled;
- finalization produces `run_export.json`;
- source, hidden state, verifier contracts, and expected codes are not exposed
  to the agent;
- no live provider or physical hardware write is possible;
- a domain reviewer accepts the family-level scientific contract;
- the build is reproducible with `--check`.

Only after this milestone should the project expand task count or begin the
growth world.
