# Task Orchestration

Use filesystem-backed task state so context can be passed by reference instead
of by transcript.

This protocol is for orchestrated Datalox work where one parent agent delegates
small assignments to planner, executor, reviewer, viewer, and summarizer
workers. It keeps the parent transcript out of worker prompts and gives each
worker file paths, contracts, and acceptance criteria.

## Task State

Create one task directory per orchestrated task:

```txt
.datalox/tasks/<task-id>/
  task.json
  plan.md
  context/
    selected-files.json
    notes.md
  workers/
    <worker-id>/
      assignment.json
      result.json
      changed-files.json
      notes.md
      artifacts/
  review/
    <review-id>/
      assignment.json
      result.json
  final.md
  events.jsonl
```

The orchestrator may summarize context into `context/notes.md`, but workers
should receive file paths, contracts, and acceptance criteria instead of the
full parent transcript.

## Roles

- `planner`: breaks the task into implementation steps, risks, and acceptance
  criteria.
- `executor`: performs the assigned implementation or documentation update.
- `reviewer`: checks correctness, boundary control, and test or lint evidence.
- `viewer`: inspects selected files and reports facts without changing files.
- `summarizer`: compacts the final state into `final.md` or a typed result.

Workers should stay inside `allowed_paths`. If they need a different path, they
should report it as a diagnostic instead of editing outside the assignment.

## Assignment Packet

Worker assignments should be typed and small.

```ts
type DataloxTaskAssignment = {
  schema: "datalox.task_assignment.v1";
  task_id: string;
  worker_id: string;
  role: "planner" | "executor" | "reviewer" | "viewer" | "summarizer";
  objective: string;
  cwd: string;
  allowed_paths: string[];
  relevant_files: string[];
  context_notes_path?: string;
  constraints: string[];
  acceptance_criteria: string[];
  output_contract: {
    result_path: string;
    changed_files_path?: string;
    artifact_dir?: string;
  };
};
```

## Result Packet

Worker results should also be typed.

```ts
type DataloxTaskResult = {
  schema: "datalox.task_result.v1";
  task_id: string;
  worker_id: string;
  ok: boolean;
  summary: string;
  changed_files: string[];
  artifact_paths: string[];
  diagnostics: Array<{
    code: string;
    message: string;
    detail?: Record<string, unknown>;
  }>;
};
```

## Changed Files Packet

When `changed_files_path` is present, workers should write a small mirror packet.

```ts
type DataloxChangedFiles = {
  schema: "datalox.changed_files.v1";
  task_id: string;
  worker_id: string;
  changed_files: string[];
};
```

`changed_files` must include worker output files the worker wrote. It may include
implementation files only when the assignment allowed those paths. If the worker
writes no files except its required outputs, the packet still lists those output
files. If no changed file packet is required, the result packet remains
authoritative.

`artifact_dir` is writable only when that path or a parent path appears in
`allowed_paths`. Workers may create the directory when it is listed in
`output_contract`.

## Event Log

`events.jsonl` is an append-only orchestration log, not a trajectory dataset
export. Each line should be one JSON object.

```ts
type DataloxTaskEvent = {
  schema?: "datalox.task_event.v1";
  ts: string;
  event:
    | "task_created"
    | "assignment_created"
    | "workers_spawned"
    | "worker_completed"
    | "worker_failed"
    | "integration_started"
    | "integration_completed"
    | "task_blocked";
  task_id: string;
  worker_id?: string;
  summary: string;
  detail?: Record<string, unknown>;
};
```

The orchestrator owns task-level events. Workers may write diagnostics in their
result packets; they should not append to `events.jsonl` unless the assignment
explicitly grants that path.

## Replay Recording

The agent that performs the real implementation must record replay source
evidence through `datalox-mcp`.

- If an executor worker edits product code, tests, docs, schemas, or runtime
  behavior, that executor must call replay capture tools through `datalox-mcp`
  before returning `ok: true`.
- If the orchestrator personally performs the implementation instead of
  delegating it, the orchestrator must record replay source evidence before
  marking the task completed.
- Planner, reviewer, viewer, and summarizer workers do not record implementation
  replay evidence unless they also perform implementation work.
- `events.jsonl` remains only the task coordination log. It is not a substitute
  for Datalox replay records.

## Lifecycle

Use these task states in `task.json`:

- `queued`: task state exists but no worker has started
- `in_progress`: at least one worker is running or integration is pending
- `blocked`: integration cannot proceed without a user decision or missing input
- `completed`: final integration is done and `final.md` is current
- `failed`: the task cannot be completed from available worker results

Use these worker result states through `result.json`:

- missing result file: worker is still pending or failed before writing output
- malformed result file: worker output is invalid and integration must stop
- `ok: false`: worker failed or could not satisfy the assignment
- `ok: true` with diagnostics: worker completed but integration must review the
  diagnostics
- `ok: true` with no diagnostics: worker completed cleanly

If a worker needs to edit outside `allowed_paths`, it should return `ok: false`
with a diagnostic instead of making the edit.

## Integration Gate

Before writing `final.md`, the orchestrator should:

1. Parse every required `assignment.json`.
2. Check worker write sets for overlapping non-output paths.
3. Parse every required `result.json`.
4. Parse `changed-files.json` when `changed_files_path` is present.
5. Treat malformed JSON, missing required result files, or `ok: false` as
   integration blockers.
6. Review diagnostics from `ok: true` results and either patch the task/doc or
   record the diagnostic in `final.md`.
7. Append `integration_started` and `integration_completed` events.
8. Update `task.json` to `completed` only after `final.md` reflects the worker
   results and any follow-up decisions.

## Orchestrator Rules

1. Create `.datalox/tasks/<task-id>/task.json` before delegation.
2. Put selected repository context in `context/selected-files.json`.
3. Put compact task context in `context/notes.md`.
4. Give each worker an `assignment.json`; do not paste the parent transcript.
5. Keep write sets disjoint when multiple workers may edit files.
6. Require each worker to write or return a typed `result.json`.
7. Record important orchestration events in `events.jsonl`.
8. Write `final.md` after the orchestrator integrates results.
9. Keep task orchestration events separate from `debugging_trajectory.v1` rows.

## Product Boundary

For this repo, orchestration is process infrastructure. It must not reintroduce
the legacy note/skill loop as a product model. Product work still flows through:

```txt
agent run -> tool I/O records -> replay bundle -> approval/export -> optional derivatives
```

Use task state for coordination. Use `tool_io_record.v1` records as the exact
replay primitive, `agent_turn.v1` events as the review primitive, replay bundles
as the source B2B data asset, and trajectory rows as compact dataset/eval
derivatives.

Fresh replay-product adoption keeps orchestration and product data under
`.datalox/`. This branch does not create a parallel wiki, note, or event store
for task state, session capture, or trajectory rows.
