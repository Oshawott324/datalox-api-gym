# Tool I/O Store Schema

This document is the canonical schema contract for Datalox tool I/O records.
If other docs describe tool-call capture differently, this document wins for
`tool_io_record.v1`.

## Purpose

The tool I/O store is the source replay primitive and the persisted backing
store for normalized action/observation evidence.

It records what an agent-visible tool received and returned, in a deterministic
form that can later be packed into a replay bundle. It is not a summary layer,
a vector-memory layer, or a trajectory row.

Canonical path:

```text
.datalox/tool-io/records/
```

Canonical pipeline:

```text
messy agent traces -> validated action/observation records -> replay bundle -> approval/export -> optional derivatives
```

The related normalized view is defined in
[action-observation-schema.md](./action-observation-schema.md):

```text
messy agent traces -> validated action/observation records -> replay bundle
```

`action_observation.v1` is a strict view over tool I/O records. It is not a
second store.

## Record Shape

```ts
type ToolIoRecordV1 = {
  schema_version: "tool_io_record.v1";
  id: string;
  session_id?: string;
  turn_id?: string;
  call_id: string;
  tool_name: string;
  arguments: unknown;
  request_hash: string;
  sequence_index: number;
  observation: {
    status: "ok" | "error";
    content?: unknown;
    error_code?: string;
    error_message?: string;
  };
  created_at: string;
  source?: {
    host?: string;
    mcp_server?: string;
    command?: string;
  };
  export: {
    allowed: boolean;
    redaction: "none_needed" | "applied" | "blocked";
  };
};
```

## Hash Rule

The request hash is deterministic:

```text
request_hash = sha256(canonical_json({ tool_name, arguments }))
```

Rules:

- object keys are sorted before hashing
- insignificant JSON formatting does not affect the hash
- arrays remain ordered
- `undefined` is not a valid JSON value and must not appear in stored records
- the hash covers only the tool name and arguments, not the observation

## Sequence Rule

The replay key is:

```text
request_hash + sequence_index
```

`sequence_index` starts at `0` for the first matching request hash in a replay
scope and increments by one for repeated identical requests.

Replay must not use fuzzy matching, timestamp matching, or nearest-neighbor
matching. A missing replay key is a deterministic replay miss.

## Observation Rule

Store the agent-visible observation.

Allowed:

- structured JSON returned by an MCP tool
- command status and compact command output when the command is the tool
- structured error codes and messages visible to the agent

Do not store by default:

- hidden reasoning
- credentials or environment dumps
- full files when a bounded excerpt or file artifact reference is enough
- host-private metadata that was not visible to the agent

## Relationship To Turns

`agent_turn.v1` may summarize tool calls for review, but the exact replay source
is `tool_io_record.v1`.

Turn events can reference tool I/O records by id, request hash, and sequence
index. Replay bundles should include both the turn summaries and the exact tool
I/O records needed to reproduce the episode.

## Relationship To Action/Observation Normalization

`tool_io_record.v1` maps directly into `action_observation.v1`:

- `tool_name` becomes `action.name`
- `arguments` becomes `action.arguments`
- `request_hash` becomes `action.request_hash`
- `sequence_index` becomes `action.sequence_index`
- `observation` becomes `observation`
- `session_id`, `turn_id`, and `call_id` become provenance fields

Normalization must not alias tool names, infer missing observations from prose,
or add schema/version metadata that the source did not provide.

## Export Readiness

A tool I/O record is replay-ready when:

- it has a valid schema version
- it has a deterministic request hash
- repeated identical requests have stable sequence indexes
- the observation is exactly what the agent saw, after any approved redaction
- export status is explicit
