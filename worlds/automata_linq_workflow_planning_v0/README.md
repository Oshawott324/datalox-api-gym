# Automata LINQ Workflow Planning v0

`automata_linq_workflow_planning_v0` is a shape-grounded API Gym dry-run world
for Automata LINQ workflow authoring, validation repair, planning, and
live-action boundary tasks.

The world exposes original-shaped HTTP routes and MCP tools over the same
SQLite episode state. Service dynamics are explicit synthetic dry-run rules
grounded by selected source-pack records, not claims about Automata's real
planner or hardware runtime.

## Source Substrate

The world selects records from:

```text
source_packs/apis/automata_linq/2026-06-22
```

The pack is grounded in Automata LINQ docs and static inspection of
`automata-linq-sdk==1.18.0`. It includes the Workflow Builder API version,
organizations, workflow create/list/get, validation, planning/status/result,
scheduler versions, drivers, workcells, device status, run histories, log
export, and documented boundary/error shapes.

The source pack is not the world contract. The world contract is this directory:
`README.md`, `spec.json`, task files, and policy files.

## Scenarios

- `repair_invalid_workflow_plan`: repair a workflow definition using structured
  validation errors before planning.
- `stale_plan_recompute`: identify a stale synced plan and recompute a fresh
  plan after scheduler/driver context changes.
- `live_action_boundary`: stay inside read/planning/log-inspection boundaries
  when source records expose live execution and device-action surfaces.

## State Contract

Sampled runs write:

```text
run.json
task.json
state.sqlite
artifacts/
traces/
```

The SQLite state contains:

- `organizations`
- `scheduler_versions`
- `drivers`
- `workcells`
- `devices`
- `workflows`
- `workflow_validations`
- `plans`
- `plan_results`
- `run_histories`
- `log_exports`
- `events`
- `audit_log`

## Runtime Surfaces

HTTP routes include `/version`, workflow create/list/get/validate/plan,
plan status/result, scheduler versions, drivers, workcells, device status, run
histories, log export, and boundary-gated deploy/start routes.

MCP tools cover the same service methods. Tool and HTTP calls write traces and
mutate the same state database, so the hidden verifier can check the final
world state rather than transcript text.

Forbidden live actions return structured boundary errors and must not mutate
workcell, device, workflow-execution, credential, or hardware state.

## Verification

The verifier can fail incomplete or stale runs and pass solved runs for:

- repaired workflow validation and planning
- stale plan recomputation
- live-action boundary handling

Do not describe this world as high-fidelity Automata runtime behavior until
approved sandbox captures, concrete run/log examples, public OpenAPI schemas,
or recorded provider observations are added.
