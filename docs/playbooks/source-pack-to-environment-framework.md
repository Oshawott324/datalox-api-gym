# Source Pack To Environment Framework

This document defines the reusable implementation pattern for turning API
source packs into runnable, verifiable API Gym environments.

It is intentionally not an MCP-first design. MCP is one adapter over the same
world runtime. The product primitive is the environment:

```text
source pack
  -> provider-shaped contract
  -> world/service layer
  -> state backend
  -> verifier/export
  -> adapters
```

## Goal

Build a generic path from checked-in source substrate to resettable agent
environments that can be called through original-shaped HTTP, MCP, SDK shims,
or CLI tools while sharing the same state, dynamics, verifier, and evidence.

The framework should make this repeatable:

```text
api-gym session create
  -> stateful run directory
  -> original-shaped API surface and/or MCP tools
  -> agent acts
  -> verifier checks final state
  -> run_export.json
```

## Non-Goals

- Do not make API Gym a live API aggregator.
- Do not make MCP the source of truth.
- Do not invent provider semantics that are not in a source pack, explicit
  world contract, approved sandbox probe, or recorded capture.
- Do not require every world to use the same storage engine.
- Do not force a universal lab automation JSON shape across vendors.

## Layer Model

```text
source_packs/apis/<provider>/<version>
  normalized source facts:
  operations, schemas, response cases, observed errors, world candidates

worlds/<world_id>
  selected source refs, task specs, policies, environment contract

api_gym/worlds/<world_id>
  sampler, state, services, adapters, tools, verifier

runs/<session_id>
  run.json, task.json, state backend files, traces, verifier output, export
```

### 1. Source-Pack Registry

Existing code:

- `api_gym/source_packs.py`
- `api_gym/source_pack_gate.py`
- `api_gym/source_pack_gate_server.py`

Responsibilities:

- validate source packs
- match provider method/path to `operation:*`
- select sourced `response_case:*`
- expose stateless source-pack gate responses

This layer is fact lookup only. It does not own episode state or verifier
logic.

### 2. World Service Layer

The service layer is where stateful behavior lives. It should expose provider
operations as methods with stable request/response envelopes, then be called by
all adapters.

Recommended shape:

```text
api_gym/worlds/<world_id>/services.py
  create_workflow(...)
  validate_workflow(...)
  plan_workflow(...)
  get_plan_status(...)
  get_plan_result(...)
```

Rules:

- The service owns dynamics and state mutation.
- The service returns structured provider-shaped responses.
- The service records audit/evidence rows.
- The service never reads hidden verifier expectations.
- The service rejects out-of-scope live actions with stable agent-readable
  boundary errors.

### 3. State Backend Interface

The right abstraction is a state backend interface, not "always files".

Backends should provide these capabilities:

- initialize one episode from a deterministic scenario and seed
- read and mutate world state transactionally
- append visible audit/evidence events
- expose artifact paths for export
- reset by deleting or recreating the run directory

Recommended default for API Gym worlds:

```text
runs/<session_id>/
  run.json
  task.json
  state.sqlite
  artifacts/
  traces/
  run_export.json
```

Use SQLite as the default because it gives deterministic local state,
transactions, constraints, portable session directories, and easy debugging.
This is a default, not a law.

Backend selection:

| Backend | Use when | Avoid when |
| --- | --- | --- |
| In-memory | unit tests, tiny adapter tests | replay/export or multi-process serving matters |
| SQLite in run dir | normal API Gym dry-run worlds | hosted multi-user scale is required |
| JSON files | immutable fixtures or small artifacts | mutable workflow/run state exists |
| Postgres/Redis | hosted shared environments, concurrency, long-lived state | local deterministic episode packaging is the goal |

### 4. Original-Shaped HTTP Adapter

For provider API environments, original-shaped HTTP should be the first-class
adapter.

Example:

```http
POST /v3/workflow
POST /v3/workflow/validate
POST /v3/workflow/plan
GET /v3/workflow/{workflow_id}/plan/{plan_id}/status
```

This lets agents, SDKs, and integration tests exercise the environment in a
shape that resembles the real provider contract.

Implementation direction:

- keep `api-gym gate serve` for stateless source-pack response cases
- add stateful world HTTP serving for registered worlds
- route original provider paths to the world service
- preserve provider status codes and error envelopes when source-backed
- emit evidence rows for every request

### 5. MCP Adapter

MCP is a transport adapter over the same service layer. It is not the
environment.

MCP adapter means:

```text
MCP tools/list
MCP tools/call
  -> api_gym/worlds/<world_id>/tools.py
  -> api_gym/worlds/<world_id>/services.py
  -> same state backend
  -> same verifier/export
```

Use MCP when an agent host needs a native tool surface. Do not put unique
business logic in MCP handlers. If HTTP and MCP disagree, the service layer is
wrongly split.

### 6. SDK Shim Adapter

SDK shims are useful when a provider has a public SDK and the agent or tests
can point that SDK at a local base URL.

Use this only when the SDK supports configurable domains or can be cleanly
wrapped without monkeypatching private internals. The SDK shim should still hit
the same original-shaped HTTP adapter and state backend.

### 7. Verifier And Export

Existing code:

- `api_gym/session.py`
- `api_gym/exports/run_export.py`
- `api_gym/worlds/<world_id>/verifier.py`

Verifier rules:

- check final world state and audit evidence, not transcript text
- do not expose hidden verifier state to the agent
- fail when required state transitions or evidence are missing
- emit stable failure codes for debugging and training

Export rules:

- include task, trace, verifier result, and artifact paths
- cite selected source-pack records through `worlds/<world_id>/source_refs.json`
- keep dataset packaging outside this repo

## Recommended Implementation Units

For the generic framework, extend the current world pattern instead of adding a
parallel platform.

Add or evolve:

```text
api_gym/worlds/http.py
  generic stateful HTTP adapter helpers for world runtimes

api_gym/worlds/state_backends.py
  shared SQLite helpers or protocols only if duplication appears across worlds

api_gym/worlds/adapters.py
  adapter-neutral request/response helpers if HTTP and MCP start duplicating
  dispatch code

api_gym/cli.py
  add a world HTTP serve command that is not billing-only
```

Keep provider-specific behavior inside:

```text
api_gym/worlds/<world_id>/state.py
api_gym/worlds/<world_id>/services.py
api_gym/worlds/<world_id>/http.py
api_gym/worlds/<world_id>/tools.py
api_gym/worlds/<world_id>/verifier.py
```

Do not create generic abstractions until two worlds need the same logic.

## First Generic Milestone

The first framework milestone is not a big abstraction pass. It is one
provider-shaped world that proves the pattern.

Acceptance:

- `api-gym session create --world <world> ...` writes a run directory
- original-shaped HTTP server can serve that run
- optional MCP tools call the same service
- verifier checks state and evidence
- source refs cite selected source-pack records
- live side-effecting provider operations are boundary-gated
- `python -m pytest -q` passes

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

## Design Rule

Every environment should answer this before implementation:

```text
What source records are selected?
What state is mutable?
What actions can the agent take?
What dynamics are source-backed vs explicit dry-run contract?
What observations let the agent repair?
What verifier checks final state?
What adapter surfaces expose the same service?
```
