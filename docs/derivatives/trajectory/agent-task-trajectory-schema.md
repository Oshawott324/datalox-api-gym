# Agent Task Trajectory Schema

This document defines `agent_task_trajectory.v1`, the generic mixed-domain task
episode row. Use it when a real agent task crosses domains or when the evidence
is not purely coding/debugging.

Use [trajectory-dataset-schema.md](trajectory-dataset-schema.md) for the
narrow `debugging_trajectory.v1` coding/debugging row.

## Design Goal

`agent_task_trajectory.v1` is still a compact training/eval derivative. It is
not a raw session log and not a compliance record. The row should be usable as a
standalone JSONL line after export approval.

The schema keeps the shared task episode shape generic:

```text
task -> context -> trajectory -> evidence_blocks -> final -> outcome -> export gate
```

Domain-specific proof lives in `evidence_blocks`. This keeps mixed work such as
code plus documents, spreadsheet analysis plus source review, or lab workflow
planning plus literature evidence in one row without inventing a new top-level
schema per domain.

`context.code_snippets` is not part of this schema and is not part of
`debugging_trajectory.v1`. Put code proof in a `code_change` evidence block for
mixed-domain rows, or in `debugging_trajectory.v1.context.relevant_files[]` for
pure coding/debugging rows.

## Storage And Export

Recorded candidate events are written under:

```text
.datalox/derivatives/trajectories/agent-task/
```

Buyer-facing JSONL defaults to:

```text
exports/trajectories/agent_task_trajectory.v1.jsonl
```

New `agent_task_trajectory.v1` rows are recorded under
`.datalox/derivatives/trajectories/agent-task/`.

## Required Row

Only fields without `?` are required.

```ts
type AgentTaskTrajectoryV1 = {
  schema_version: "agent_task_trajectory.v1";
  id: string;
  created_at: string;

  task: {
    prompt: string;
    domains: string[];
    workflows?: string[];
    environment?: string;
    constraints?: string[];
  };

  context?: {
    problem?: string;
    background?: string;
    source_paths?: string[];
    notes?: string[];
  };

  trajectory: Array<{
    role: "user" | "agent" | "tool" | "reviewer";
    content: string;
    tool?: string;
    command?: string;
    exit_code?: number;
    artifacts?: string[];
    files_changed?: string[];
  }>;

  evidence_blocks: AgentTaskEvidenceBlockV1[];

  final: {
    summary: string;
    changed_artifacts?: string[];
    explanation?: string;
  };

  outcome: {
    label: "success" | "failure" | "partial";
    verification: "passed" | "failed" | "not_run" | "reviewed";
    command?: string;
    evidence?: string;
  };

  trajectory_type?: "success" | "failure" | "recovery";

  first_wrong_step?: number;

  replay_bundle_ref?: {
    bundle_id: string;
    bundle_path?: string;
  };

  export: {
    allowed: boolean;
    redaction: "none_needed" | "applied" | "blocked";
    source_event_paths?: string[];
  };

  curation?: {
    split?: "train" | "validation" | "test" | "eval";
    quality?: "use" | "needs_review" | "discard";
    tags?: string[];
    notes?: string;
  };

  metadata?: Record<string, unknown>;
};
```

## Evidence Blocks

Every evidence block is strict. Unknown fields are rejected.

### `code_change`

Use for exact code edits. Provide either exact `before` and `after` snippets, or
a compact exact `patch`.

`patch` is a first-class schema field. It may be a compact unified diff hunk, or
an exact addition/removal snippet with `+`/`-` prefixes when that is the smallest
self-contained evidence. For newly added code, addition-only `+...` patches are
valid when they show real code, not a summary. For edits to existing code, prefer
exact `before` and `after` snippets or a compact unified diff with enough context
to understand what changed. Do not use prose such as "the code now validates
inputs" as `patch` evidence.

```ts
{
  type: "code_change";
  path: string;
  language?: string;
  symbol?: string;
  before?: string;
  after?: string;
  patch?: string;
  reason?: string;
}
```

### `command_result`

Use for shell, test, smoke, notebook, or tool-run results.

```ts
{
  type: "command_result";
  command: string;
  exit_code: number;
  result_summary: string;
  evidence?: string;
  artifact_paths?: string[];
}
```

### `document_change`

Use for docs, reports, slide text, contracts, protocols, or other text artifacts.

```ts
{
  type: "document_change";
  artifact: string;
  format?: string;
  before: string;
  after: string;
  section?: string;
  reason?: string;
}
```

### `spreadsheet_change`

Use for spreadsheet edits, model logic, formulas, validation ranges, or tabular
artifact changes.

```ts
{
  type: "spreadsheet_change";
  artifact: string;
  sheet?: string;
  range?: string;
  before: string;
  after: string;
  formula?: string;
  validation?: string;
}
```

### `data_analysis`

Use for analysis work where the important proof is question, method, and result.

```ts
{
  type: "data_analysis";
  artifact: string;
  question: string;
  method: string;
  result: string;
  input_summary?: string;
  code_ref?: string;
  validation?: string;
}
```

### `lab_workflow`

Use for biotech, lab, assay, protocol, or measurement planning work.

```ts
{
  type: "lab_workflow";
  workflow: string;
  assay?: string;
  measurement_context: string;
  before: string;
  after: string;
  criteria?: string;
  validation?: string;
}
```

### `source_reference`

Use for web, PDF, or local-file grounding. `excerpt` and `relevance` are optional
at schema validation time so weak captures can be saved as `needs_review`, but
use-quality `quality: "use"` export requires both.

```ts
{
  type: "source_reference";
  source_kind: "web" | "pdf" | "local_file";
  title: string;
  source_path?: string;
  url?: string;
  excerpt?: string;
  relevance?: string;
}
```

## Optional Derivative Annotations

`trajectory_type`, `first_wrong_step`, and `replay_bundle_ref` follow the same
semantics as in [trajectory-dataset-schema.md](trajectory-dataset-schema.md):

- `trajectory_type` is a learning-role label (`success` / `failure` /
  `recovery`) separate from `outcome.label`. A recoverable failure that
  ultimately succeeded can be tagged `trajectory_type: "recovery"` with
  `outcome.label: "success"`.
- `first_wrong_step` is a zero-based index into `trajectory[]` for the first
  step where the agent went off the correct path. Most valuable for
  failure/recovery rows as a credit-assignment signal.
- `replay_bundle_ref` points to the source `replay_bundle.v1` this row was
  packaged from. When present, downstream consumers can recompute rewards,
  replay tool I/O, or compare model behavior against the same recorded
  environment.

All three fields are optional and additive; rows without them remain valid
`agent_task_trajectory.v1` records.

## Readiness Rules

Schema-valid does not mean use-quality. `export-agent-task-trajectories --quality
use` applies deterministic readiness checks:

- `evidence_blocks` must be non-empty.
- Unknown evidence block types and unknown fields are rejected by schema.
- `code_change` evidence must carry exact code or patch evidence, not prose.
- Code-heavy rows must include at least one concrete `code_change` block before
  use-quality `quality: "use"` export. A row is code-heavy when task domains or
  artifact paths indicate code, tests, package metadata, runtime behavior, or
  implementation work.
- `source_reference` entries for local code files are provenance/context only.
  They do not replace `code_change`, even when the excerpt describes the edit.
- Document, spreadsheet, and lab before/after evidence must be concrete excerpts,
  not placeholder summaries or path-only references.
- `source_reference` must include a concrete excerpt and relevance, not only a
  URL or file path.
- `command_result` must include the command, exit code, and observed result.
- `export.source_event_paths` must contain `.datalox/events/...` provenance
  event paths only. Put source files in `context.source_paths` and
  `final.changed_artifacts`.
- `export.allowed: false` and `export.redaction: "blocked"` are excluded.
- Oversized rows, patches, evidence fields, and metadata are blocked from
  `quality: "use"` export.

Recording also runs the deterministic readiness grader. If a row claims
`curation.quality: "use"` but fails these checks, Datalox records the event with
`curation.quality: "needs_review"` and adds downgrade metadata:

- `datalox_quality_downgraded_from`
- `datalox_quality_downgrade_issue_codes`
- `datalox_quality_downgraded_at`

Bad code-heavy evidence:

```json
{
  "type": "source_reference",
  "source_kind": "local_file",
  "title": "Preview implementation",
  "source_path": "src/core/preview.ts",
  "excerpt": "getEventPreview now caches previews and delegates work to a worker.",
  "relevance": "Explains the implementation."
}
```

Good code-heavy evidence:

```json
{
  "type": "code_change",
  "path": "src/core/preview.ts",
  "language": "typescript",
  "before": "const preview = buildPreview(events, options);",
  "after": "const preview = await runPreviewWorker(events, options);",
  "reason": "Move preview generation off the main process for large workspaces."
}
```

## Module Boundary

This schema is derivative-only. The install-facing CLI and MCP surfaces do not
expose agent-task trajectory recording or export tools. Derivative builders may
use the source modules under `src/core/derivatives/trajectory/` after a replay
bundle is verified.

## Examples

### Mixed Code And Command

```json
{
  "schema_version": "agent_task_trajectory.v1",
  "id": "traj-runtime-key-save-ui-state",
  "created_at": "2026-05-07T00:00:00.000Z",
  "task": {
    "prompt": "Fix the runtime API-key save UI state and verify the focused test.",
    "domains": ["coding", "ui"],
    "workflows": ["runtime_settings"],
    "environment": "React, TypeScript, Vitest"
  },
  "trajectory": [
    {
      "role": "user",
      "content": "Asked to pick up a runtime API-key save UI-state sync fix."
    },
    {
      "role": "agent",
      "content": "Inspected the runtime setup card and settings section state flow."
    },
    {
      "role": "tool",
      "content": "Focused runtime setup card tests passed.",
      "tool": "exec_command",
      "command": "npx vitest run src/components/runtime/agent-runtime-setup-card.test.tsx",
      "exit_code": 0
    }
  ],
  "evidence_blocks": [
    {
      "type": "code_change",
      "path": "src/components/runtime/runtime-settings-section.tsx",
      "language": "tsx",
      "before": "setFormState(agentRuntimeSetupFormFromView(updatedSetup));",
      "after": "setFormState(agentRuntimeSetupStateAfterSave(updatedSetup, submittedApiKey));",
      "reason": "Keep the submitted key in memory for the successful save round."
    },
    {
      "type": "command_result",
      "command": "npx vitest run src/components/runtime/agent-runtime-setup-card.test.tsx",
      "exit_code": 0,
      "result_summary": "Runtime setup card test file passed: 9 tests, 0 failed."
    }
  ],
  "final": {
    "summary": "Saved runtime API keys now remain visually saved after successful submit.",
    "changed_artifacts": [
      "src/components/runtime/runtime-settings-section.tsx",
      "src/components/runtime/agent-runtime-setup-card.test.tsx"
    ]
  },
  "outcome": {
    "label": "success",
    "verification": "passed",
    "command": "npx vitest run src/components/runtime/agent-runtime-setup-card.test.tsx",
    "evidence": "Runtime setup card test file passed: 9 tests, 0 failed."
  },
  "export": {
    "allowed": true,
    "redaction": "none_needed"
  },
  "curation": {
    "quality": "use",
    "tags": ["runtime-settings", "ui-state"]
  }
}
```

### Non-Code Lab Workflow

```json
{
  "schema_version": "agent_task_trajectory.v1",
  "id": "traj-viability-gate-review",
  "created_at": "2026-05-07T00:00:00.000Z",
  "task": {
    "prompt": "Update a viability assay workflow using a cited local source.",
    "domains": ["biotech", "source_review"],
    "workflows": ["lab_workflow_review"],
    "environment": "protocol planning"
  },
  "trajectory": [
    {
      "role": "user",
      "content": "Asked to tighten a viability gate."
    },
    {
      "role": "agent",
      "content": "Compared the gate wording against the local protocol note."
    }
  ],
  "evidence_blocks": [
    {
      "type": "lab_workflow",
      "workflow": "viability gate review",
      "assay": "cell viability",
      "measurement_context": "Triplicate plate-read measurements after compound exposure.",
      "before": "Accept gate when a single viability measurement is above 70%.",
      "after": "Accept gate when all triplicate wells remain above 70% viability and CV is below 15%.",
      "criteria": "Triplicate wells, viability threshold, and coefficient of variation must all pass."
    },
    {
      "type": "source_reference",
      "source_kind": "local_file",
      "title": "Viability gate protocol note",
      "source_path": "docs/viability-gate.md",
      "excerpt": "Triplicate measurements reduce false acceptance when one well is an outlier.",
      "relevance": "Grounds the added replicate and CV criteria."
    }
  ],
  "final": {
    "summary": "The viability workflow now requires triplicate threshold and CV criteria.",
    "changed_artifacts": ["docs/viability-gate.md"]
  },
  "outcome": {
    "label": "success",
    "verification": "reviewed",
    "evidence": "Reviewed against local protocol note."
  },
  "export": {
    "allowed": true,
    "redaction": "none_needed"
  },
  "curation": {
    "quality": "use",
    "tags": ["biotech", "lab-workflow"]
  }
}
```
