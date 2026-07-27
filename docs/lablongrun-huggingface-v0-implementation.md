# LabLongRun Hugging Face v0 Implementation

Date: 2026-07-26
Status: active implementation contract

## Current Status

Implemented and admitted on 2026-07-26:

- pinned PyLabRobot 0.2.1 provider component and sanitized reference captures;
- actual OT-2 simulator calls for every transfer;
- actual incubator and plate-reader Chatterbox calls at their declared fidelity;
- one cross-service world with eLabFTW-shaped records and PyLabRobot mechanisms;
- 12 deterministic episodes across nominal, resource-recovery, and
  asynchronous freshness/recovery families;
- 17 admitted reference, negative, recovery, and parity trajectories;
- obligation-level verifier output with stable codes and evidence references;
- deterministic source-pack and world rebuild checks;
- a bounded domain-review packet for the scientific workflow and recovery
  assumptions;
- isolated multi-session Streamable HTTP MCP with opaque bearer tokens, TTL
  cleanup, capacity limits, and no live-provider mode;
- serialized worker execution so blocking provider calls do not block the ASGI
  event loop or race finalization;
- a fail-closed public run-export contract with immutable bundle identity,
  actual world IDs, named verifier outcomes, and resolvable public evidence
  capsules;
- a complete remote reference replay: 22 tool calls, 22 public ledger events,
  and all 11 world obligations passing;
- an isolated exact-pinned Docker Space package under
  `deployments/huggingface/science_growth_kinetics_v0`, with a JSON service
  manifest, automatic Hugging Face host/origin binding, and both local-source
  and private runtime installation paths;
- a container smoke replay executing all 22 calls over Streamable HTTP MCP,
  passing all 11 checks, and proving OT-2, incubator, and plate-reader provider
  execution. The locked dependency set also resolves as binary wheels on
  Linux/x86-64;
- one controlled Codex `gpt-5.4-mini` MCP baseline passing all 11 obligations.
  Bounding kinetic readback reduced non-cached input from about 57.7k to 33.3k
  tokens and total reported input from about 796k to 463k.

Not yet complete:

- Codex and Claude baseline rollouts through the final deployed remote URL;
- trace replay UI and dataset export;
- independent scientific review;
- Hugging Face Space deployment and dataset publication;
- a public or otherwise reproducibly installable gated-runtime release. The
  current runtime repository is private.

## Objective

Release a small but complete public science-agent environment that an outside
user can run locally or through a Hugging Face Docker Space.

The release is successful when an outside agent can:

1. create an isolated episode;
2. read the task and provider-shaped tool contracts;
3. execute a scientific workflow through MCP;
4. cause real PyLabRobot simulator or Chatterbox methods to run;
5. recover from a realistic workflow failure;
6. finalize the episode;
7. inspect obligation-level verifier evidence and a visual trace replay.

Task count is not the release criterion. The initial target is 12 to 30
scientifically reviewed and strictly admitted episodes.

## Repository Boundaries

`datalox-api-gym` owns:

- PyLabRobot source evidence and reference executions;
- reusable PyLabRobot provider components;
- scientific workflow bundles;
- task-family contracts, dynamics, facts, and deterministic verification;
- world reference, negative, recovery, and parity trajectories.

`datalox-gated-runtime` owns:

- world sessions and authoritative episode state;
- HTTP and MCP transport;
- isolation, ledgers, scheduled events, handoffs, finalization, and exports;
- generic deterministic verifier assertions;
- world-bundle validation and admission.

`datalox-rollout-collector` owns:

- model rollout aggregation;
- dataset manifests and split assignment;
- Hugging Face dataset generation and validation.

The Hugging Face deployment package owns only deployment:

- one public FastAPI port;
- session creation and expiration policy;
- browser UI and trace replay;
- routing to the installed gated runtime;
- no world logic and no copied provider implementation.

Agent planning, memory, retries, model routing, and tool-selection strategy
remain outside all four layers.

## Canonical Source Layout

```text
source_packs/apis/pylabrobot/<capture-date>/
  source_pack.json
  operations.jsonl
  response_cases.jsonl
  observed_errors.jsonl
  known_gaps.jsonl
  raw/reference_sequences/

api_gym/provider_components/pylabrobot/
  __init__.py
  executor.py
  grounding.py
  errors.py
  snapshots.py
  liquid_handling.py
  plate_reading.py
  incubation.py

scripts/providers/pylabrobot/
  capture_reference.py
  check_reference.py

worlds/science_growth_kinetics_v0/
  README.md
  projection_contract.md
  source_refs.json
  evidence/
  tests/trajectories/
  world/
    manifest.json
    v1/
      implementation.py
      dynamics.py
      verifier.py
      provider_pylabrobot.py
      episodes.jsonl
      roles.json
      tools.json
      verifier.json
      sources.json

scripts/worlds/
  build_science_growth_kinetics.py
```

Do not add a second provider-pack tree for PyLabRobot. Source evidence lives in
`source_packs/apis`; executable provider behavior lives in
`api_gym/provider_components`.

## Grounding Levels

Every operation and observation must use one of these labels:

```text
simulator_executed
chatterbox_executed
provider_interface_only
captured_projection
benchmark_defined
unsupported
```

The initial pinned package is PyLabRobot 0.2.1. The local package contains an
OT-2 simulator and Chatterbox backends for liquid handling, plate reading,
incubation, thermocycling, centrifugation, heating and shaking, pumping,
weighing, temperature control, tilting, and powder dispensing.

The first world uses only:

- OT-2 simulator liquid handling;
- incubator Chatterbox operations;
- plate-reader Chatterbox operations;
- the admitted eLabFTW create, patch, and get projection;
- explicitly labeled benchmark time, biological dynamics, and handoff rules.

No physical hardware behavior, pipetting accuracy, sterility, biological
prediction, or production provider behavior is implied.

## Authoritative State Rule

The gated runtime `WorldSession` is the only authoritative episode state.
Provider components execute PyLabRobot operations and return normalized JSON
observations and state snapshots. The world commits those results to the
session.

The verifier reads only exported state, events, artifacts, scheduled events,
and handoffs. It does not invoke PyLabRobot, call a provider, or reconstruct a
simulator.

Visual replay is derived from the accepted tool trace after execution. The
visualizer is not part of world state and cannot affect verifier results.

## First World

`science_growth_kinetics_v0` composes:

```text
eLabFTW experiment record
  -> OT-2 microplate preparation
  -> explicit operator or workcell handoff
  -> incubation and logical-time progression
  -> plate-reader observations
  -> result-validity decision
  -> eLabFTW result record
```

The scientific protocol and measurement fixture must be grounded in a public
protocol or reviewed by one domain researcher before public release.

Initial task families:

1. `growth_nominal_v1`;
2. `growth_resource_recovery_v1`;
3. `growth_async_freshness_recovery_v1`.

Each family must include:

- one reference trajectory that passes;
- an empty trajectory that fails;
- relevant procedural, resource, fault, stale, and provenance mutants;
- one valid recovery trajectory;
- exact expected failure-code matching.

## Verification

World verification has three layers:

1. generic runtime assertions for ordering, freshness, deadlines, artifacts,
   mutation scopes, and handoffs;
2. provider facts for liquid volumes, tips, plate identity, location, and
   instrument state;
3. world predicates for required controls, contamination lineage, incubation
   exposure, measurement completeness, and supported conclusions.

The verifier reads state once, indexes the relevant operation events once, and
evaluates named predicates over those facts. It does not repeatedly scan the
complete trajectory. If multiple worlds reuse the same fact extraction, that
extraction becomes a reusable provider or runtime assertion rather than a
world-specific framework. Verification emits a boolean and obligation outcomes
with stable failure codes and evidence references. It emits no scalar reward,
weights, or credit assignment.

Remote publication adds a separate typed projection. The raw run export and
authoritative world state remain private. Each world verifier may publish a
minimal evidence capsule containing only the facts needed to audit its named
outcomes. Every published evidence reference must resolve inside that capsule.
For the growth world this includes protocol and plate identity, preparation
lineage and counts, incubation conditions, kinetic-run metadata and a series
digest, result-record metadata, operation order, and provider-execution counts.
It excludes raw world state, fault schedules, full kinetic values, simulator
context, and shadow mutations.

## Public Deployment

The Hugging Face Docker Space installs pinned releases of API Gym and gated
runtime. The implemented runtime service exposes one public port with:

```text
GET    /health
POST   /sessions
POST   /sessions/{id}/mcp
GET    /sessions/{id}/mcp
DELETE /sessions/{id}/mcp
POST   /sessions/{id}/finalize
GET    /sessions/{id}/export
DELETE /sessions/{id}
```

Session creation returns the selected task and bearer token. The MCP catalog
also exposes `get_task` but not the local session-manifest tool. A deployment UI
may add same-origin browser routes and trace replay without changing these
runtime contracts.

Sessions use opaque tokens, isolated run directories, expiration, fixed
resource limits, no arbitrary code execution, no user-supplied provider
credentials, and no live hardware access.

## Work Order

1. Pin PyLabRobot and execute sanitized local reference sequences.
2. Implement reusable liquid-handler, incubator, and plate-reader components.
3. Build and admit the nominal world vertical slice.
4. Add recovery and stale/partial-result families.
5. Profile reset, action, verifier, and model-context cost. Completed for the
   first Codex baseline; broader sampling remains.
6. Run Codex and Claude baselines through the deployed Streamable HTTP MCP
   surface.
7. Build and locally verify the deployment-isolated Docker Space package.
   Completed with a full provider-executing reference replay.
8. Authenticate to Hugging Face and publish the Space.
9. Add trace replay without placing world logic in the Space repository.
10. Extend `datalox-rollout-collector` to import the typed public run export,
    join host trajectory records, and publish the accompanying dataset.

## Release Gate

- one complete PyLabRobot-backed scientific workflow;
- three admitted task families and 12 to 30 admitted episodes;
- remote MCP access from outside the Docker Space;
- Codex and Claude baseline evidence;
- trace-derived visual replay;
- one scientific review;
- reproducible local and Docker execution;
- explicit source, version, grounding, and limitation records.

The review packet is
[`docs/reviews/science-growth-kinetics-v0-review.md`](reviews/science-growth-kinetics-v0-review.md).
