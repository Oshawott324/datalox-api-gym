# Action/Observation Schema

This document defines the normalized action/observation view over Datalox tool
I/O records. If other docs describe action schema normalization differently,
this document wins for `action_observation.v1`.

## Purpose

The accessible standardization gap is replayable action schema normalization:

```text
tool_io_record.v1 -> action_observation.v1 -> replay_bundle.v1
```

MCP standardizes how tools are called. Datalox standardizes the replayable
action/observation evidence that can be packed, verified, replayed, and later
converted into optional trajectory/eval derivatives.

`action_observation.v1` is a strict normalized view. It is not a second replay
store. The persisted replay primitive remains `tool_io_record.v1` under:

```text
.datalox/tool-io/records/
```

## Canonical View

```ts
type ActionObservationV1 = {
  schema_version: "action_observation.v1";
  action: {
    type: "tool_call";
    name: string;
    version?: string;
    arguments: unknown;
    argument_schema_ref?: string;
    request_hash: string;
    sequence_index: number;
  };
  observation: {
    status: "ok" | "error";
    content?: unknown;
    error_code?: string;
    error_message?: string;
    observation_schema_ref?: string;
  };
  provenance: {
    source_kind: "mcp" | "wrapper" | "raw_trace";
    source_path?: string;
    host?: string;
    session_id?: string;
    turn_id?: string;
    call_id: string;
  };
};
```

## Normalization Rules

- preserve exact `arguments` and `observation` values as agent-visible JSON
- derive `request_hash` from `sha256(canonical_json({ tool_name, arguments }))`
- preserve `sequence_index` from the source `tool_io_record.v1`
- use `sequence_index: 0` for a single raw trace event unless the source
  explicitly supplies the replay order
- do not infer missing observations from stdout prose or assistant summaries
- do not alias or fuzzy-match tool names
- do not infer `version`, `argument_schema_ref`, or
  `observation_schema_ref`; include them only when the source provides them
- reject non-canonical JSON values such as `undefined`, `NaN`, or infinities
- reject unknown fields with strict validation

## Raw Trace Input

Raw trace adapters may normalize a minimal trace event:

```ts
type RawActionObservationTraceInput = {
  source_kind: "raw_trace";
  source_path?: string;
  host?: string;
  session_id?: string;
  turn_id?: string;
  call_id: string;
  tool_name: string;
  tool_version?: string;
  arguments: unknown;
  argument_schema_ref?: string;
  observation: {
    status: "ok" | "error";
    content?: unknown;
    error_code?: string;
    error_message?: string;
  };
  observation_schema_ref?: string;
  sequence_index?: number;
};
```

This adapter is intentionally narrow. A raw trace that has only prose output,
missing observations, ambiguous tool names, or inferred reward details must
fail validation instead of producing replay evidence.

## Relationship To Tool I/O Records

`tool_io_record.v1` is the stored replay primitive. `action_observation.v1`
is a normalized view used by adapters, tests, and future export code.

The mapping is direct:

```text
tool_io_record.v1.tool_name        -> action.name
tool_io_record.v1.arguments        -> action.arguments
tool_io_record.v1.request_hash     -> action.request_hash
tool_io_record.v1.sequence_index   -> action.sequence_index
tool_io_record.v1.observation      -> observation
tool_io_record.v1.session_id       -> provenance.session_id
tool_io_record.v1.turn_id          -> provenance.turn_id
tool_io_record.v1.call_id          -> provenance.call_id
```

Do not create a separate `.datalox/action-observations/` store. Replay bundles
should continue to pack tool I/O records and agent turns.

## Non-Goals

This schema does not implement:

- a reward engine
- a sandbox runtime
- environment snapshot execution
- step-level credit assignment
- hidden chain-of-thought capture

Those can be referenced later through explicit replay-bundle provenance fields
after the core action/observation schema is stable.
