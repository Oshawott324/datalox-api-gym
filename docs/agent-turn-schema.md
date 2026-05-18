# Agent Turn Capture Schema

This document defines the small per-turn review primitive for Datalox replay
data.

If other docs describe turn capture differently, this document wins for
`agent_turn.v1`. Exact tool-call capture belongs to
[tool-io-store-schema.md](./tool-io-store-schema.md). Normalized action schema
belongs to [action-observation-schema.md](./action-observation-schema.md).
Replay bundle assembly belongs to [replay-bundle-schema.md](./replay-bundle-schema.md).
Trajectory schemas define optional derivatives only.

## Design Goal

`AgentTurnV1` captures one completed agent turn with enough structure to review,
redact, bundle, or derive compact training rows later.

It should stay simple enough for MCP tools, wrappers, and hooks to record after a
turn without replaying the whole raw Codex or Claude session log.

The boundary is:

```text
agent tool call -> tool_io_record.v1 -> replay_bundle.v1 -> deterministic replay -> optional derivatives
```

The normalized action view is `action_observation.v1`, the exact persisted
replay unit is `tool_io_record.v1`, and the review unit is one completed turn.
The portable replay artifact is a verified replay bundle assembled from tool
I/O records and optional turn review events.

## Required Shape

Only fields without `?` are required.

```ts
type AgentTurnV1 = {
  schema_version: "agent_turn.v1";
  id: string;
  session_id: string;
  turn_index: number;
  created_at: string;

  user_prompt?: string;
  assistant_summary?: string;

  tool_calls: Array<{
    tool: string;
    call_id?: string;
    tool_io_ref?: {
      record_id: string;
      request_hash: string;
      sequence_index: number;
    };
    command?: string;
    args_summary?: string;
    exit_code?: number;
    output_summary?: string;
  }>;

  file_changes?: Array<{
    path: string;
    action: "created" | "modified" | "deleted";
    diff_summary?: string;
  }>;

  verification?: {
    command?: string;
    status: "passed" | "failed" | "not_run";
    evidence?: string;
  };

  export: {
    allowed: boolean;
    redaction: "none_needed" | "applied" | "blocked";
  };
};
```

## Capture Rules

Capture the agent-visible facts, not the whole host transcript.

Include:

- the user request when it is safe to store
- a short assistant summary of what the agent did
- meaningful tool calls with command, exit code, compact output summary, and
  `tool_io_ref` when exact replay evidence exists
- file paths and edit summaries
- verification commands and result evidence
- export/redaction status

Do not inline by default:

- full raw session JSONL
- base, system, or developer instructions
- hidden reasoning or encrypted reasoning blobs
- auth tokens, API keys, credentials, or environment dumps
- long command output
- full files or long diffs
- screenshots or binary artifacts

Use path links for long artifacts when the implementation needs to preserve them.
The turn object should stay reviewable without becoming a raw log dump.

## Replay Bundle Assembly

Approved replay bundles are assembled from tool I/O records and turn events.

```ts
type ReplayBundleTurnIndexV1 = {
  schema_version: "replay_bundle_turn_index.v1";
  replay_bundle_id: string;
  created_at: string;
  turn_ids: string[];
  tool_io_record_ids: string[];
};
```

Replay bundles are the direct replay artifacts. `debugging_trajectory.v1` and
`agent_task_trajectory.v1` rows are optional compact derivatives for teams that
want training or eval examples instead of full replay bundles.

## Readiness Rule

An `AgentTurnV1` event is useful when it can answer three questions:

- What did the user ask the agent to do?
- What did the agent actually do through tools and edits?
- What evidence shows whether the turn helped?

If those answers are missing, the turn can still be stored as private source
evidence, but it should not be exported as approved replay data.
