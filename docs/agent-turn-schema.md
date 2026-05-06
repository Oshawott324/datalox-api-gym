# Agent Turn Capture Schema

This document defines the small per-turn capture primitive for Datalox session data.

If other docs describe turn capture differently, this document wins for
`agent_turn.v1`. For exported compact trajectory rows,
[trajectory-dataset-schema.md](./trajectory-dataset-schema.md) still wins.

## Design Goal

`AgentTurnV1` captures one completed agent turn with enough structure to review,
redact, sell, or derive compact training rows later.

It should stay simple enough for MCP tools, wrappers, and hooks to record after a
turn without replaying the whole raw Codex or Claude session log.

The boundary is:

```text
agent run -> AgentTurnV1 events -> session/episode assembly -> export/redaction gate -> approved session dataset -> optional trajectory/eval rows
```

The capture unit is one completed turn. The commercial unit is usually a reviewed
session or task episode assembled from multiple turns.

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
- meaningful tool calls with command, exit code, and compact output summary
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

## Session Assembly

Approved session bundles are assembled from turn events.

```ts
type AgentSessionBundleV1 = {
  schema_version: "agent_session_bundle.v1";
  session_id: string;
  created_at: string;
  turn_ids: string[];
  episodes?: Array<{
    id: string;
    goal: string;
    turn_ids: string[];
    outcome: "success" | "partial" | "failure";
  }>;
  export: {
    allowed: boolean;
    redaction: "none_needed" | "applied" | "blocked";
  };
  source_event_paths?: string[];
};
```

Session bundles are the direct B2B source data product when approved and
anonymized. `debugging_trajectory.v1` rows are compact derivatives for buyers
who want training or eval examples instead of session replay.

## Readiness Rule

An `AgentTurnV1` event is useful when it can answer three questions:

- What did the user ask the agent to do?
- What did the agent actually do through tools and edits?
- What evidence shows whether the turn helped?

If those answers are missing, the turn can still be stored as private source
evidence, but it should not be exported as approved session data.
