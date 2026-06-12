# Product Definition

This is the canonical product definition for `datalox-api-gym`.

## Definition

Datalox API Gym packages source-backed dry-run worlds: resettable, stateful
action systems that expose tools, preserve episode state, run dynamics, return
observations, hide verifier state, and export evidence for testing, evaluating,
training, and auditing agents before they touch real systems.

```text
source substrate
  -> world package
  -> world session
  -> MCP/action interface
  -> agent rollout
  -> verifier outcome
  -> run_export evidence
```

The core abstraction is:

```text
World = source substrate
      + mutable episode state
      + actions
      + dynamics
      + observations
      + verifier
      + evidence
```

API Gym is not an API aggregator. Aggregators connect agents to live services.
API Gym creates resettable dry-run, testing, evaluation, training, and audit
worlds around API-like, workflow-like, simulator-like, or physical-action
systems.

API Gym is also not the training dataset collector. It produces world sessions
and run evidence. `datalox-rollout-collector` packages that evidence into
training or eval datasets.

## Owned Here

- API source packs and source references
- world specs
- world session lifecycle
- per-episode state backends
- action contracts exposed through MCP or host adapters
- dynamics backends
- observation contracts
- hidden verifier execution
- tool traces
- session manifests
- run exports

## Not Owned Here

- dataset manifests
- train/dev/test split assignment
- dataset quality labels
- dataset validation reports
- frontier-lab dataset distribution
- model training recipes
- general-purpose live API aggregation

## Source Substrate Boundary

API source substrate lives under `source_packs/apis`. It contains raw and
normalized API evidence such as OpenAPI contracts, documentation captures,
test-mode probe outputs, observed errors, examples, operation catalogs, and
grounded response cases for dry-run API gating.

Source packs are not worlds. They do not expose MCP tools, hold resettable
episode state, run verifiers, or produce `run_export.json`. They are upstream
provider facts that can be selected into a world design.

Source packs should be usable before a world exists. The intended dry-run
pattern is:

```text
agent calls original-shaped API
  -> Datalox gate matches provider + operation + scenario
  -> gate returns a sampled response case
  -> optional world/session layer adds state, verifier, and export evidence
```

Source packs are a product primitive, not only documentation. Agents and CI can
validate one provider/version pack with:

```bash
api-gym source-pack validate source_packs/apis/<provider>/<version>
```

The source-pack pipeline is:

```text
source_packs/apis/<provider>/<version>
  -> normalized operation catalog
  -> world candidate design
  -> worlds/<world_id>
  -> MCP/session/runtime
  -> run_export
  -> datalox-rollout-collector
```

Once selected, a world cites source packs through
`worlds/<world_id>/source_refs.json`. Do not duplicate broad sampled provider
APIs under `worlds/<world_id>/evidence`; keep world-local evidence limited to
source records already selected for that concrete world.

## World Shell And Dynamics Backend

Every world has two separable parts:

```text
World shell:
  session lifecycle
  state path
  action contract
  observation contract
  reset policy
  verifier contract
  evidence export

Dynamics backend:
  deterministic business logic
  dry-run lab workflow logic
  replayed provider observation
  live-gated provider call
  simulator or oracle
```

The shell is what makes a source-backed system usable by agents. The dynamics
backend is how the world decides what changes after an action.

## Session Contract

External agent environments should integrate through the world session
manifest, not by hand-running setup commands.

```text
api-gym session create
  -> session_manifest.json
  -> agent_task.json
  -> MCP config
  -> expected_tools
  -> check-tools command
  -> finalize command
```

Before rollout, the host must prove the agent-visible tool layer contains every
tool listed in `expected_tools`. After rollout, the host must finalize the
session so API Gym can run the verifier and write `run_export.json`.

## Evidence Boundary

API Gym evidence is upstream evidence for dataset collectors:

```text
world_ref:
  world id, source substrate, state policy, action contract, verifier contract

task_ref:
  scenario, seed, and task package

rollout_ref:
  externally captured tool trace and observations

outcome_ref:
  verifier result and run export
```

The agent must not receive hidden verifier state or direct access to mutable
state files such as `state.sqlite`.

## Current Worlds

`billing_support_v0`

- deterministic business workflow world
- SQLite state
- billing, support, CRM, and email tool surface
- verifier checks final business state

`unitelabs_plate_qc_v0`

- deterministic dry-run lab workflow world
- SQLite state
- labware, transfer, readout, note, and protocol decision tools
- verifier checks dry-run workflow invariants
- API semantics should be grounded from an explicit UniteLabs OpenAPI contract
