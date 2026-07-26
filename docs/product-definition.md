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
- provider-specific fixture definitions, observations, normalization, bounded
  projections, transition atoms, and verifier facts
- world specs
- world-bundle state schemas and seed data
- action contracts exposed through MCP or host adapters
- dynamics backends
- observation contracts
- hidden verifier contracts and deterministic outcome signals
- world-local task families, mutations, and admission trajectories

## Not Owned Here

- generic gates and session lifecycle
- live capture, promotion, replay verification, and runtime audit/export
- generic call-path adapters
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

## Provider Component Boundary

Source evidence is not executable behavior. Reusable provider-specific
behavior lives under:

```text
api_gym/provider_components/<provider>/
```

A provider component may contain:

- a disposable local or authorized-sandbox fixture definition;
- a provider-shaped reference target and state observations;
- explicit normalization for generated IDs and timestamps;
- a bounded dry-run projection;
- transition atoms and provider-level verifier facts;
- conformance fixtures and known gaps.

Provider components are not generic CRUD adapters and they do not define
cross-provider scientific workflows. The generic offline conformance runner
belongs in `datalox-gated-runtime`; the target, observations, normalization,
and projected semantics belong here because they are provider-specific.

World bundles must remain self-contained. When a world uses a canonical
provider component, the builder vendors a generated, hash-checked copy into
the bundle. Do not maintain a second handwritten provider implementation under
the world.

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
  dry-run domain workflow logic
  replayed provider observation
  simulator or oracle
```

The shell is what makes a source-backed system usable by agents. The dynamics
backend is how the world decides what changes after an action.

## Runtime Contract

`datalox-gated-runtime` is the runtime authority. It loads API Gym world
bundles, creates isolated sessions, exposes the action channel, executes the
hidden verifier, and exports run evidence. Do not add new generic lifecycle or
call-path behavior to API Gym.

```text
datalox-gate session create
  -> session_manifest.json
  -> agent_task.json
  -> MCP config
  -> expected_tools
  -> check-tools command
  -> finalize command
```

Before rollout, the host must prove the agent-visible tool layer contains every
tool listed in `expected_tools`. After rollout, the host must finalize the
session so the runtime can run the world verifier and write `run_export.json`.

Existing API Gym worlds may still use the legacy `api-gym session` commands.
That compatibility path must not become the foundation for new worlds.

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
