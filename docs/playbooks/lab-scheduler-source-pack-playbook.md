# Lab Scheduler Source-Pack Playbook

This playbook is for turning lab scheduler, orchestration, automation, and
instrument APIs into source-backed API Gym substrate.

The goal is not to build an MCP wrapper first. The goal is:

```text
agent calls an original-shaped API
  -> Datalox gate intercepts it
  -> source-pack records select a sampled/source-grounded response
  -> a world mutates resettable dry-run state
  -> verifier checks final state and evidence
```

MCP is only one agent access channel over the same source-backed world.

## Non-Negotiables

- Do not invent endpoint paths for real vendors.
- Do not mark marketing claims as source-pack-ready API shape.
- Do not imply live scheduler, instrument, robot, run, protocol, or hardware
  execution.
- Do not give agents hidden verifier state or direct mutable world state.
- Do not call live endpoints unless the user has explicitly approved the probe,
  the endpoint is safe/test-mode/read-only, and the probe output is stored as
  source substrate.
- Prefer original-shaped HTTP/gRPC/API calls over agent-only abstractions.

## Evidence Levels

Use these levels when triaging a scheduler/API provider.

| Level | Name | Counts as source-pack operations? | Counts as concrete response cases? | Use |
| --- | --- | --- | --- | --- |
| L0 | Marketing/positioning only | No | No | Research note, outreach target |
| L1 | Public docs describe concepts but not request/response shape | Usually no | No | Boundary notes, world-candidate idea |
| L2 | Official API docs, OpenAPI, SDK schema, protobuf/FDL, or typed examples | Yes | Shape cases; concrete only if bodies are shown |
| L3 | Approved sandbox/test-mode/read-only probes | Yes | Yes, if captured body is checked in |
| L4 | Partner/customer recorded captures with export approval | Yes | Yes | Strongest runtime-world substrate |

Do not build runtime worlds from L0/L1 alone.

## Provider Triage

Current public triage as of 2026-06-22:

| Provider/system | Public signal | Immediate status | First Datalox action |
| --- | --- | --- | --- |
| Opentrons HTTP API | Public HTTP API reference covers protocols, analyses, runs, and commands. | Source-packable now; existing candidate pack already exists. | Strengthen `source_packs/apis/opentrons` with concrete protocol-analysis examples and safe read-only probe captures if approved. |
| Benchling automation / HighRes handoff | Public Benchling API and Benchling/HighRes posts describe structured experiment handoff to Cellario OS via API, including sample information, plate barcodes, and plate layout. | Source-packable for Benchling-side handoff objects; Cellario side likely needs private docs/probes. | Build Benchling automation handoff pack from public API docs; keep Cellario execution boundary separate. |
| SiLA 2 | Public standard defines servers, features, commands, properties, and parameters. | Source-packable as a gRPC/FDL reference substrate, not a scheduler vendor pack. | Build `sila2_reference` pack around feature discovery, property read, command call, and error/status boundaries. |
| HighRes Cellario | Public Q1 2026 update says Cellario Scheduler has RESTful API endpoints for protocol creation/modification/optimization through automated agents. Public lab-orchestration pages describe workflow/data/device orchestration. | L0/L1 until API docs, OpenAPI, SDK, examples, or captures are obtained. | Create discovery dossier and outreach ask for OpenAPI, example requests, safe sandbox, or recorded captures. |
| Biosero Green Button Go | Public product page says RESTful API/database hooks and driver library; scheduler executes processes on integrated platforms. | L0/L1 until endpoint docs/examples are obtained. | Create discovery dossier and ask for REST/database hook docs and safe sample workflow export. |
| Retisoft Genera | Public pages describe device-agnostic scheduling, simulation, runtime decisions, drivers, and error recovery. | L0/L1 until endpoint or export shape is obtained. | Create discovery dossier and ask for simulation API/export/log examples. |
| Automata LINQ | Public docs and `automata-linq-sdk==1.18.0` expose SDK client routes, generated models, planning semantics, workcell/status reads, run histories, and log-export URL shape. | Source-packable now as L2 shape-grounded SDK/API substrate; no concrete sampled bodies or MCP schema. | Maintain `source_packs/apis/automata_linq/2026-06-22`; pursue sandbox validation/planning captures, OpenAPI/MCP schemas, and run/log examples before world promotion. |
| PyLabRobot | Public Python SDK with resource/state serialization, trackers, simulator/Chatterbox, and visualizer. | Source-packable for Python operation semantics; not an original REST scheduler. | Use as open reference substrate for state/physics components, not as a fake vendor scheduler. |

Public sources:

- HighRes Cellario RESTful API statement: https://www.highres.com/highres-blog/innovation-update-q1-2026
- HighRes Cellario orchestration: https://www.highres.com/lab-orchestration
- Biosero Green Button Go Scheduler: https://biosero.com/products/green-button-go-scheduler/
- Retisoft Genera: https://retisoft.com/genera-automatic-scheduling-software/
- Automata LINQ: https://www.automata.tech/
- Automata LINQ SDK docs: https://docs.automata.tech/
- Automata LINQ SDK package: https://pypi.org/project/automata-linq-sdk/
- Opentrons HTTP API: https://docs.opentrons.com/http/api_reference.html
- SiLA 2 standards: https://sila-standard.com/standards/
- Benchling API reference: https://benchling.com/api/reference
- Benchling/HighRes handoff post: https://www.benchling.com/blog/benchling-and-highres-lab-automation

## Deliverables

For each provider, the first useful deliverable is not a world. It is a
provider source pack or a clear no-pack-yet dossier.

### Source-Pack Deliverable

Use when evidence is L2 or stronger:

```text
source_packs/apis/<provider>/<version>/
  source_pack.json
  docs_index.jsonl
  operations.jsonl
  response_cases.jsonl
  observed_errors.jsonl
  world_candidates.jsonl
  raw/                       # optional approved docs/probe/capture evidence
```

Validate with:

```bash
api-gym source-pack validate source_packs/apis/<provider>/<version>
```

### Discovery Dossier Deliverable

Use when evidence is L0/L1:

```text
docs/research/lab-scheduler-intake/<provider>.md
```

Required sections:

```text
# <Provider> Intake

## Public Claims
## API Evidence Found
## Missing Shape
## Safe Probe Possibilities
## Outreach Ask
## Datalox Boundary
## Decision
```

Decision must be one of:

- `source_pack_now`
- `needs_docs_or_probe`
- `reference_only`
- `skip`

## Operation Selection

For scheduler/orchestration systems, prefer operations in this order:

1. `capability/list` or equivalent discovery
2. `workflow/protocol/template read`
3. `workflow/protocol create or modify`
4. `validate`, `simulate`, `analyze`, or `dry-run`
5. `run create` only if dry-run/test-mode is explicit
6. `run status`
7. `run events/logs`
8. `run artifacts/results`
9. `error/recovery/resume/cancel` boundaries

Do not select live hardware action endpoints into a dry-run world unless there
is a separate live-gate policy.

## Response-Case Requirements

Every selected operation needs at least one response case.

Preferred cases:

- success
- validation failure
- permission/scope failure
- conflict/stale revision
- unavailable device/resource
- unsafe live execution boundary
- run/event/artifact not found

Label response evidence precisely:

```json
{
  "response_mode": "body_shape | body_excerpt | body | error_shape",
  "evidence_kind": "official_docs | openapi_example | sandbox_probe | recorded_capture | boundary"
}
```

Shape-only cases are acceptable for source grounding, but they are not concrete
sample evidence.

## Safe Probe Rules

Use probes only when approved.

Allowed without additional live-risk review after user approval:

- public OpenAPI fetch
- docs fetch
- SDK schema inspection
- unauthenticated read-only public metadata
- local simulator
- provider sandbox/test-mode read/list
- provider sandbox/test-mode validation/analyze endpoint that does not enqueue
  live work

Requires explicit live-gate review:

- creating a real scheduler run
- starting, pausing, resuming, canceling, or modifying a real run
- connecting to a robot, instrument, device driver, or hardware host
- issuing commands that move gantries, pipettes, grippers, pumps, readers, or
  other devices
- writing to a production LIMS/ELN/scheduler tenant

Record every approved probe under `raw/` or `probes.jsonl` with:

```json
{
  "id": "probe:<provider>:<operation>:<case>",
  "provider": "<provider>",
  "version": "<version>",
  "operation_ref": "operation:<name>",
  "mode": "docs_fetch | sandbox_read | sandbox_validate | recorded_capture",
  "command_or_request": {},
  "response_excerpt": {},
  "live_execution": false,
  "approved_by": "<approval id or user note>",
  "captured_at": "<ISO timestamp>"
}
```

## Original-Shaped Gate Rule

The gate must preserve the provider's original request shape.

Good:

```http
POST /protocols/{protocolId}/analyses
```

if that path is from Opentrons docs.

Bad:

```http
POST /datalox/run_protocol_analysis
```

for a provider pack.

The gate response should cite:

- provider
- operation id
- selected response case id
- source refs
- scenario state or synthetic dynamics boundary when used

## World-Promotion Gate

A source pack can become a world only when selected records cover:

- read/list context
- protocol/workflow creation, mutation, validation, or dry-run transition
- run/event/artifact inspection
- at least one meaningful failure path
- dry-run/live boundary
- verifier-relevant evidence

The world must then define:

- resettable episode state
- agent-visible tools or original-shaped gate URL
- hidden verifier checks
- evidence export
- scenario task package

## Recommended Work Order

### Sprint 1: Two Parallel Lanes

Sprint 1 has two lanes because the strongest commercial targets are not the
same as the easiest public source packs.

Lane A strengthens source-packable public APIs. Lane B creates commercial
scheduler intake dossiers for the systems buyers actually care about.

#### Lane A: Strengthen Open/Public Packs

1. Opentrons:
   - expand existing pack from protocol-analysis candidate to concrete
     protocol-analysis source pack
   - add official example bodies or approved local/sandbox read-only captures
   - keep run command execution out of scope

2. Benchling automation handoff:
   - capture public API docs for plates, inventory, workflow tasks, automation,
     webhooks/events, and file/result handoff
   - model Benchling-side handoff only
   - explicitly boundary-gate Cellario execution

3. SiLA 2 reference:
   - source-pack the standard concepts as gRPC/FDL-shaped operation records:
     feature discovery, property read, command call, command status/error
   - do not claim a specific vendor scheduler

#### Lane B: Commercial Scheduler Intake

Create dossiers for the commercial scheduler/orchestration systems in the same
sprint:

- `cellario`
- `green_button_go`
- `genera`
- `automata_linq`

These do not become operation records from public marketing pages alone. They
are still first-sprint work because they define the commercial integration
surface and outreach ask.

Each dossier must answer:

- What public claims are source-worthy?
- What concrete API shape is still missing?
- Is there a public SDK, OpenAPI, plugin API, database hook contract, export
  format, or simulator interface?
- What safe probe would not touch live hardware or production workflow state?
- What exact artifact should we ask the vendor/user/community for?

Each dossier must end with an outreach ask for:

- OpenAPI/Swagger, protobuf, SDK, or plugin docs
- example protocol/workflow create request
- example validation/simulation response
- example run event log
- example artifact/result response
- safe sandbox/test-mode access or recorded captures

### Sprint 2: Convert Discovered Shape Into Source Packs

Promote a commercial scheduler from dossier to source pack only when the
dossier reaches L2 or stronger evidence:

- official endpoint docs
- OpenAPI/Swagger
- protobuf/gRPC schema
- plugin/database hook contract
- SDK schema
- safe simulator/test-mode probe
- exportable recorded capture

Expected promotion targets:

- `source_packs/apis/cellario/<version>` if Cellario REST/API shape is obtained
- `source_packs/apis/green_button_go/<version>` if GBG REST/database hook shape is obtained
- `source_packs/apis/genera/<version>` if Genera API/export/simulation shape is obtained
- `source_packs/apis/automata_linq/<version>` if LINQ API/MCP/run-event shape is obtained or the public SDK exposes route/model shape by static inspection

If none of the commercial targets reach L2, do not fabricate operation records.
Keep improving Opentrons, Benchling handoff, and SiLA 2 while using the
dossiers for outreach.

### Sprint 1 Status: 2026-06-22

Completed public-lane source packs:

- `source_packs/apis/opentrons/2026-06-16`
  - Existing protocol-analysis/run-inspection pack strengthened with one
    concrete docs-derived upload response excerpt.
  - Boundary: protocol execution, robot run start, command execution, movement,
    pipetting, modules, lights, homing, and hardware control remain out of
    scope.
- `source_packs/apis/benchling/2026-06-22`
  - Benchling-side automation handoff substrate: plates, workflow tasks,
    workflow outputs, blobs, automation input generation, automation output
    processing, and events.
  - Boundary: Cellario endpoint shape, scheduler run creation, workcell
    execution, robot motion, and instrument control remain out of scope.
- `source_packs/apis/sila2_reference/2026-06-22`
  - Reference SiLA 2 substrate for discovery, implemented features, feature
    definitions, properties, commands, command status, typed data, and
    validation boundaries.
  - Boundary: vendor-specific features, instruments, and scheduler processes
    still require their own FDL/protobuf/docs or safe captures.

Completed commercial intake dossiers:

- `docs/research/lab-scheduler-intake/cellario.md`
- `docs/research/lab-scheduler-intake/green_button_go.md`
- `docs/research/lab-scheduler-intake/genera.md`
- `docs/research/lab-scheduler-intake/automata_linq.md`

At Sprint 1 close, all four commercial dossiers decided `needs_docs_or_probe`.
Promote them only when endpoint contracts, SDK/wire schemas, sandbox probes,
simulator captures, or approved recorded captures are obtained. Automata LINQ
was promoted in Sprint 2 after public SDK route/model inspection; Cellario,
Green Button Go, and Genera remain dossier-only.

### Sprint 2 Status: 2026-06-22

Completed commercial source-pack promotion:

- `source_packs/apis/automata_linq/2026-06-22`
  - Shape-grounded from public Automata SDK docs plus static inspection of the
    pinned public wheel `automata-linq-sdk==1.18.0`.
  - Covers workflow creation/list/read, validation, planning, plan
    status/result, scheduler versions, drivers, workcells, device status, run
    histories, and log-export URL shape.
  - Boundary: publish, deploy, start, pause, resume, stop, reset,
    respond-to-error, hub restart, credential management, and live
    workcell/hardware execution remain out of scope.
  - Quality: structurally valid source pack only. It has no live probes,
    sandbox captures, recorded run logs, concrete tenant bodies, OpenAPI
    examples, or public MCP schemas.

Still blocked at dossier level:

- `docs/research/lab-scheduler-intake/cellario.md`
- `docs/research/lab-scheduler-intake/green_button_go.md`
- `docs/research/lab-scheduler-intake/genera.md`

Do not promote Cellario, Green Button Go, or Genera until endpoint contracts,
SDK/protobuf/plugin schemas, simulator captures, or approved recorded captures
are obtained.

Implementation docs for the next step:

- Generic source-pack-to-environment framework:
  `docs/playbooks/source-pack-to-environment-framework.md`
- Automata LINQ environment implementation:
  `docs/playbooks/automata-linq-environment-implementation.md`

### Sprint 3: First Runtime World

Only after selected records are strong enough, compose a world from them.
Prefer:

```text
opentrons_protocol_analysis_v0
```

or:

```text
benchling_to_scheduler_handoff_v0
```

Do not start with `cellario_v0`, `gbg_v0`, or `genera_v0` unless real endpoint
contracts or captures are available. Automata LINQ can start as
`automata_linq_workflow_planning_v0` only if it is explicitly labeled as a
shape-grounded dry-run planning environment; do not market it as high-fidelity
LINQ runtime behavior until sandbox captures, recorded responses, OpenAPI
examples, or public MCP schemas exist.

## Provider-Specific Notes

### Opentrons

Public docs are strong enough to keep working now. Existing source pack already
covers protocol upload, analysis, analysis read, and run-command inspection.
Next value is concrete official examples or approved simulator/test captures.

Boundary:

- no run start
- no command execution
- no robot motion
- no module/device commands

### Benchling

Public API docs and Benchling/HighRes posts make Benchling a good handoff-side
candidate. It can model experiment parameters, plates, barcodes, layouts,
tasks, events, and result objects.

Boundary:

- Benchling handoff does not prove Cellario execution shape
- keep scheduler-side run execution out until Cellario docs/captures exist

### SiLA 2

Treat as a standard/reference pack. It is useful for driver-like semantics:
servers expose features; features expose commands and properties.

Boundary:

- SiLA 2 does not by itself define a lab scheduler workflow
- vendor-specific SiLA features still need their own source refs

### Cellario

Public pages strongly validate the market direction, especially programmatic
protocol creation/modification through automated agents. They do not provide
enough endpoint detail for operation records unless more docs are found.

Decision before pack:

- find public API docs/OpenAPI/SDK, or
- get private docs/probe/capture approval

### Green Button Go

Public pages mention RESTful API/database hooks and driver libraries. That is
not enough to create endpoint records.

Decision before pack:

- obtain REST/database hook docs or sample exported workflow/run logs

### Genera

Public pages are useful for scheduler semantics: simulation, dynamic decisions,
error recovery, driver scheduling, and instrument pooling. They are not enough
for original-shaped API records.

Decision before pack:

- obtain API/export/log shape or safe simulator captures

### Automata LINQ

Public MCP-enabled positioning is important, but the current source pack is
grounded by the Python SDK/API shape, not by a public MCP schema. Static
inspection of `automata-linq-sdk==1.18.0` exposed request routes, domain
routing, accepted statuses, generated Pydantic models, and structured error
envelopes for a shape-grounded source pack.

Current pack:

- `source_packs/apis/automata_linq/2026-06-22`

Decision before world promotion:

- obtain sandbox validation/planning captures, concrete workflow/run/log
  examples, OpenAPI/MCP schema docs, or approved recorded captures

## Definition Of Done

A lab scheduler/API source pack is done when:

- `api-gym source-pack validate` passes
- every operation has source refs
- every selected operation has response cases
- live execution is explicitly disallowed
- hardware-control endpoints are boundary-gated
- shape-only vs concrete cases are labeled
- world candidates declare what is still missing

A runtime world is done only when:

- it cites selected source-pack records in `worlds/<world>/source_refs.json`
- it has resettable state
- the agent can act through original-shaped gate calls or MCP tools backed by
  the same state
- hidden verifier checks final world state
- `api-gym session create`, `check-tools`, and `finalize` work
- `run_export.json` contains task, trace, verifier outcome, and evidence paths
