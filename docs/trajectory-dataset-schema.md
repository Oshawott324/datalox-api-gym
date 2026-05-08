# Trajectory Dataset Schema

This document is the canonical schema contract for the B2B debugging trajectory
data/eval product.

If other docs describe exported dataset rows differently, this document wins.

This document intentionally covers only `debugging_trajectory.v1`. For mixed
task episodes where evidence crosses code, documents, spreadsheets, analysis,
lab workflow, or source review, use
[agent-task-trajectory-schema.md](./agent-task-trajectory-schema.md) and
`agent_task_trajectory.v1` instead.

## Design Goal

The schema must be adopted by agents and buyers, so it stays small.

The row is a compact training/eval derivative, not the complete source session
or audit log. `agent_turn.v1` events are the simple capture primitive. The
captured session remains the source asset after turns are assembled with prompts,
tool actions, file edits, verification results, and export/redaction evidence.
Agents should be able to emit the row from a normal debugging run without
inventing fields, doing manual classification, or filling compliance-heavy
objects.

## Product Meaning

The trajectory row product is not raw traces.

The source product can be an approved anonymized session bundle. The trajectory
row product is:

```text
high-signal debugging trajectories with labeled outcomes
```

A valid exported row should preserve the learning unit:

```text
problem -> context -> trajectory -> final fix -> verification -> outcome
```

Use JSONL for bulk export: one `DebuggingTrajectoryV1` object per line.

## Standalone Export Contract

An exported trajectory row must be usable without access to the original repo,
source event, or audit bundle. The JSONL line itself is the training/eval
payload.

Paths are provenance labels only:

- `context.relevant_files[].path` identifies where an inline snippet came from.
- `final.changed_files` identifies changed files.
- `export.source_event_paths` links audit evidence and repair lineage.
- artifact paths in `metadata` can point to optional review material.

Those paths must not be required to understand the bug, edit, or verification.
Put the minimal before/after code evidence inline in
`context.relevant_files[].before` and `after`. Put compact diff hunks in
`final.patch` when available, or use a concrete `final.explanation` grounded in
the embedded snippets when no patch is available.

Builder rule: `before` and `after` are code-evidence fields, not summary fields.
If an agent only has prose, it should put that prose in `context.notes`,
`trajectory.content`, or `final.explanation` and leave the row as
`curation.quality: "needs_review"` until repaired.

Optional source/audit bundles can be packaged separately for reproducibility,
but the default `debugging_trajectory.v1` export contract is standalone JSONL.

## Required Row

Only fields without `?` are required.

```ts
type DebuggingTrajectoryV1 = {
  schema_version: "debugging_trajectory.v1";
  id: string;
  created_at: string;

  task: {
    domain: "coding_debugging";
    prompt: string;
    language?: string;
    environment?: string;
  };

  context: {
    error?: string;
    relevant_files?: Array<{
      path: string;
      before?: string;
      after?: string;
    }>;
    notes?: string[];
  };

  trajectory: Array<{
    role: "user" | "agent" | "tool";
    content: string;
    tool?: string;
    command?: string;
    exit_code?: number;
    files_changed?: string[];
  }>;

  final: {
    fix_summary: string;
    patch?: string;
    changed_files?: string[];
    explanation?: string;
  };

  outcome: {
    label: "success" | "failure" | "partial";
    verification: "passed" | "failed" | "not_run" | "reviewed";
    command?: string;
    evidence?: string;
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

## Field Rules

### `schema_version`

Use exactly `debugging_trajectory.v1`.

Do not silently change field meaning under the same version. Add a new version
when the contract changes.

### `id`

Use a stable unique id. It must not expose a private repo name or user identity.

### `task.prompt`

Use the user's task or a concise problem statement. This is the instruction side
of the training example.

### `context`

Keep only the context needed to understand the fix:

- the error or failing behavior
- relevant file snippets
- short setup notes when needed

Do not require complete repository state, dependency inventories, or exhaustive
environment descriptions.

### `trajectory`

Store concise, agent-visible steps. Good rows usually need 3-20 steps.

Each step should be one of:

- what the user asked
- what the agent inspected or concluded
- what command or tool ran
- what edit was made
- what result was observed

Do not include hidden chain-of-thought. Use short summaries that another model
can learn from.

### `final`

Prefer a unified diff in `patch` when available. If a patch is unavailable, use
`fix_summary` and `changed_files`.

### `outcome`

`label` says whether the debugging episode succeeded.

`verification` says how much confidence the row has:

- `passed`: a command, test, or runtime check passed
- `failed`: verification ran and failed
- `reviewed`: no command proof, but the result was reviewed
- `not_run`: no verification happened

Rows with `failed`, `reviewed`, or `not_run` can still be useful for evals and
failure-mode data, but the label must be explicit.

### `export`

Keep the export gate small:

- `allowed: false` means the row must not be sold or published
- `redaction: "blocked"` means the row must not be exported
- `source_event_paths` links back to Datalox evidence when available

Detailed consent records, licenses, full provenance, and audit trails should
live in source events or curation systems, not in every training row.

### `curation`

Use `curation` for buyer-facing packaging decisions. Do not make agents fill it
during normal work unless the value is already known.

Pattern labels, failure categories, knowledge ids, and dataset split decisions
belong here as optional tags, not required row structure.

## Minimal Valid Example

```json
{
  "schema_version": "debugging_trajectory.v1",
  "id": "traj_01hxyz",
  "created_at": "2026-05-03T00:00:00.000Z",
  "task": {
    "domain": "coding_debugging",
    "prompt": "Fix the TypeError when reading an async API response.",
    "language": "typescript",
    "environment": "nodejs"
  },
  "context": {
    "error": "TypeError: Cannot read properties of undefined",
    "relevant_files": [
      {
        "path": "src/api.ts",
        "before": "const data = fetchUser(id); return data.name;",
        "after": "const data = await fetchUser(id); return data.name;"
      }
    ]
  },
  "trajectory": [
    {
      "role": "agent",
      "content": "Observed that the failing line reads a property from the API response."
    },
    {
      "role": "agent",
      "content": "Identified that fetchUser returns a Promise and the call was not awaited."
    },
    {
      "role": "agent",
      "content": "Added await before fetchUser(id).",
      "files_changed": ["src/api.ts"]
    },
    {
      "role": "tool",
      "content": "tests/api.test.ts passed: 8 tests, 0 failed.",
      "tool": "shell",
      "command": "npm test -- tests/api.test.ts",
      "exit_code": 0
    }
  ],
  "final": {
    "fix_summary": "Await the async API call before reading the response.",
    "changed_files": ["src/api.ts"],
    "explanation": "The resolved object is available before property access."
  },
  "outcome": {
    "label": "success",
    "verification": "passed",
    "command": "npm test -- tests/api.test.ts",
    "evidence": "tests/api.test.ts passed: 8 tests, 0 failed."
  },
  "export": {
    "allowed": true,
    "redaction": "none_needed",
    "source_event_paths": [".datalox/events/trajectory-rows/example.json"]
  },
  "curation": {
    "quality": "use",
    "tags": ["async", "missing-await"]
  }
}
```

## Non-Goals

Do not add required top-level fields for:

- detailed reproduction setup
- full dependency inventories
- detailed data-rights objects
- local skill/note feedback loops
- confidence updates
- pattern taxonomies
- every failed attempt as a separate object

Those can be derived later from source events or added as optional curation
metadata. The base row should stay easy for agents to produce and easy for
training pipelines to consume.

## Versioning Rule

Changes that add optional fields may stay in `debugging_trajectory.v1`.

Changes that rename fields, change enum meaning, remove required fields, or
alter validity rules require a new schema version.
