# Trajectory Training Readiness

This guide defines the quality gate above
[debugging_trajectory.v1](trajectory-dataset-schema.md).

`tool_io_record.v1` records are the replay primitive. `agent_turn.v1` events
are optional review context after turns are assembled. A replay bundle can
include prompts, tool actions, file edits, diffs, verification commands, and
outcome evidence. The trajectory row is the compact training/eval derivative.

The schema answers: "Is this row shaped correctly?"

Training readiness answers: "Can an eval runner learn the debugging move
from this row without replaying a transcript?"

## Row States

`schema-valid`: the row passes `parseDebuggingTrajectoryV1`.

`exportable`: the row is schema-valid and has `export.allowed: true` plus
`export.redaction !== "blocked"`.

`training-grade`: the row is exportable, compact, grounded in code evidence,
and has `curation.quality: "use"` after deterministic checks and review.

A row can be `exportable: true` and still be `quality: "needs_review"`.

## Training-Grade Checklist

- Include the concrete failure signal in `context.error` or `context.notes`.
- Put minimal code snippets in `context.relevant_files.before/after`; do not use
  prose summaries as code evidence.
- Prefer `final.patch` with unified diff hunks. If no patch is available, include
  `final.changed_files` and a concrete `final.explanation`.
- Keep `trajectory` to 3-20 concise visible steps: inspection, conclusion, edit,
  and verification.
- Use `role: "tool"` steps for meaningful commands and include `tool`,
  `command`, `exit_code`, and a short result summary.
- Make `outcome.evidence` name the checks and result, not just `passed`.
- Start captured rows as `curation.quality: "needs_review"` unless a reviewer
  already accepted them.

## Builder Instructions

When building a `debugging_trajectory.v1` row, treat
`context.relevant_files[].before` and `after` as code fields.

- Use exact minimal code snippets copied from the relevant files.
- Do not put prose summaries in `before` or `after`.
- Do not write `see src/file.ts`, `open source_event_paths`, or similar path
  references as snippet content.
- Put prose interpretation in `context.notes`, `trajectory.content`, or
  `final.explanation`.
- If the row claims `curation.quality: "use"` but deterministic grading fails,
  Datalox records the row as `needs_review` and returns downgrade diagnostics so
  the agent can repair it.

## Self-Contained Row Checklist

Buyer-facing JSONL rows must be understandable without opening the source repo,
`.datalox/events`, or an audit artifact.

- Use paths only as labels for provenance.
- Include at least one meaningful `before`/`after` code snippet pair.
- Do not use snippets such as `see src/file.ts`, `open source event`, or
  `refer to source_event_paths`.
- Do not use placeholder patch lines such as `...`.
- If `final.patch` is unavailable, make `final.explanation` describe the edit
  using the embedded snippets.
- Keep source/audit bundles optional and separate from the default JSONL export.

## Token Budgets

The deterministic grader defaults are character budgets, not tokenizer-specific
counts:

- full row JSON: 24000 chars
- `final.patch`: 12000 chars
- each `context.relevant_files.*.before/after` snippet: 4000 chars
- `metadata`: 4000 chars

Store raw command output, long diffs, screenshots, and transcripts as source
artifacts by path. Keep only the few lines needed to prove the fix inline.

## Good Compact Row Shape

```json
{
  "context": {
    "error": "TypeError: Cannot read properties of undefined",
    "relevant_files": [
      {
        "path": "src/api.ts",
        "before": "const data = fetchUser(id);\nreturn data.name;",
        "after": "const data = await fetchUser(id);\nreturn data.name;"
      }
    ]
  },
  "trajectory": [
    { "role": "agent", "content": "Found fetchUser returns a Promise." },
    { "role": "agent", "content": "Added await before fetchUser(id).", "files_changed": ["src/api.ts"] },
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
    "patch": "@@\n-const data = fetchUser(id);\n+const data = await fetchUser(id);"
  },
  "outcome": {
    "label": "success",
    "verification": "passed",
    "command": "npm test -- tests/api.test.ts",
    "evidence": "tests/api.test.ts passed: 8 tests, 0 failed."
  },
  "curation": { "quality": "use" }
}
```

## Bad Receipt Shape

```json
{
  "context": {
    "relevant_files": [
      {
        "path": "src/api.ts",
        "before": "The code called the API incorrectly.",
        "after": "The code now handles the API correctly."
      }
    ]
  },
  "trajectory": [
    { "role": "agent", "content": "Fixed the issue." }
  ],
  "final": {
    "fix_summary": "Fixed the bug."
  },
  "outcome": {
    "label": "success",
    "verification": "passed",
    "evidence": "passed"
  },
  "curation": { "quality": "use" }
}
```

This is schema-shaped prose, not training data. The grader should keep it in
`needs_review` and return repair actions.

## Bad External-Reference Shape

```json
{
  "context": {
    "relevant_files": [
      {
        "path": "src/api.ts",
        "before": "See src/api.ts in the repo.",
        "after": "See src/api.ts in the repo."
      }
    ]
  },
  "final": {
    "fix_summary": "Await the async API response.",
    "changed_files": ["src/api.ts"],
    "explanation": "Open source_event_paths for the actual patch."
  },
  "export": {
    "source_event_paths": [".datalox/derivatives/trajectories/debugging/source.json"]
  }
}
```

This is useful provenance, but not a standalone training row. An eval runner
would need repo or source-event access to understand the edit.

## Good Standalone Shape

```json
{
  "context": {
    "relevant_files": [
      {
        "path": "src/api.ts",
        "before": "const data = fetchUser(id);\nreturn data.name;",
        "after": "const data = await fetchUser(id);\nreturn data.name;"
      }
    ]
  },
  "final": {
    "fix_summary": "Await the async API call before reading the response.",
    "changed_files": ["src/api.ts"],
    "explanation": "The before snippet reads from the Promise; the after snippet awaits fetchUser before property access."
  },
  "export": {
    "source_event_paths": [".datalox/derivatives/trajectories/debugging/source.json"]
  }
}
```

Here the paths remain useful for audit, but the learning signal is inline.

## Module Boundary

This is derivative-only guidance. The install-facing CLI and MCP surfaces do
not expose trajectory recording, grading, repair, or export commands. Use the
source modules under `src/core/derivatives/trajectory/` only when explicitly
building replay-bundle derivatives.

Deterministic grading never calls a model and never writes notes, skills, or
curation artifacts. Model-backed review is a separate explicit workflow.
