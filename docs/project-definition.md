# Project Definition

This is the canonical definition of what this repo is building.

If other docs drift, this document wins. For exact tool-call capture,
[tool-io-store-schema.md](./tool-io-store-schema.md) wins. For normalized
action/observation views, [action-observation-schema.md](./action-observation-schema.md)
wins. For replay bundles, [replay-bundle-schema.md](./replay-bundle-schema.md)
wins. For optional turn review context, [agent-turn-schema.md](./agent-turn-schema.md)
wins. Trajectory schemas define optional downstream adapters only.

## Definition

Datalox Agent Replay is an MCP-compatible VCR for agent tools.

It records the exact request an agent made to a tool and the exact observation
the agent received back, stores that pair by deterministic request hash, packs
the records into a sealed replay bundle, and replays the same observations later
without calling live upstream tools.

Primary replay loop:

```text
agent tool call -> tool_io_record.v1 -> replay_bundle.v1 -> deterministic replay -> optional derivatives
```

## Project Boundary

This repo is not a trajectory-first dataset builder, a wiki, a note promotion
system, or a general memory layer.

The project boundary is:

- record exact tool I/O
- preserve deterministic request hashes and sequence indexes
- pack tool I/O records and optional turn context into a replay bundle
- verify bundle integrity through checksums
- replay recorded observations without live tool fallback
- derive compact training/eval rows only after replay evidence exists

Everything else is supporting infrastructure.

## Why This Exists

Agentic RL, eval, and regression teams hit the same failure mode: they cannot
reproduce what an agent saw from tools months later. Live APIs change, search
results move, databases mutate, model tool outputs vary, and reward debugging
becomes guesswork.

Datalox solves the lower layer only:

- capture what the agent-visible tool boundary received and returned
- make that evidence content-addressed and portable
- replay the same observations later
- let existing harnesses compute rewards, evals, or policy updates on top

Teams can keep their existing agent runtime, sandbox, reward code, eval runner,
or RL stack. Datalox sits underneath those systems as the reproducible tool I/O
layer.

## Core Schemas

### `tool_io_record.v1`

The exact persisted replay primitive.

One record represents one agent-visible tool request and one returned
observation. It belongs under:

```text
.datalox/tool-io/records/
```

Replay lookup uses:

```text
request_hash + sequence_index
```

### `replay_bundle.v1`

The portable replay artifact.

A bundle packages tool I/O records, optional turn review events, a manifest, and
checksums under:

```text
.datalox/replay-bundles/
```

Replay mode reads a verified bundle and returns recorded observations. It must
not silently call live tools when a record is missing.

### `action_observation.v1`

The strict normalized view over replay records and imported raw traces.

It is useful for analysis, adapters, and future eval rows, but it is not a
second store. The persisted evidence remains `tool_io_record.v1`.

### `agent_turn.v1`

Optional review context for one completed turn.

It can summarize the user request, tool calls, file edits, verification result,
and export/redaction status. It should point back to exact tool I/O records when
they exist.

### Derivative Rows

`debugging_trajectory.v1` and `agent_task_trajectory.v1` are optional compact
adapters derived from replay evidence.

They are useful when a downstream training or eval system wants a small row
instead of a full replay bundle. They are not the capture surface and must not
replace the replay records.

## Storage Layout

New replay data writes to:

```text
.datalox/
  tool-io/
    records/
  events/
    agent-turns/
  replay-bundles/
  approvals/
  derivatives/
    trajectories/
```

Fresh adoption creates `.datalox/`, instruction surfaces, and host shims. It
does not create a parallel wiki, note, or event store.

## MCP And CLI Surface

The install-facing MCP surface is replay-first:

- `record_tool_io`
- `replay_tool_io`
- `record_agent_turn`
- `pack_replay_bundle`
- `verify_replay_bundle`

The install-facing CLI should expose replay, bundle, status, proxy, and wrapper
operations. Trajectory commands may exist only behind the derivative boundary
and must not be the normal capture path.

## Capture Rules

Record exact replay evidence first.

Include:

- tool name
- exact agent-visible arguments
- deterministic request hash
- sequence index for repeated identical requests
- exact agent-visible observation
- source host metadata when known
- export/redaction status

Do not synthesize replay evidence from:

- assistant summaries
- final answers
- prose descriptions of commands
- file paths alone
- trajectory rows
- hidden reasoning

If no tool I/O was captured, the correct behavior is to say no replay evidence
exists. Do not create fake replay records.

## Replay Rules

Replay mode is deterministic by contract:

- resolve by `request_hash + sequence_index`
- return the recorded observation exactly as stored
- fail clearly when no matching record exists
- do not call live tools as a hidden fallback
- verify bundle checksums before treating a bundle as replay-ready

## Derivative Rules

Derivative rows are downstream adapters.

They may include:

- compact problem/context summaries
- selected agent-visible steps
- final outcome labels
- verification evidence
- domain-specific evidence blocks such as code changes, command results,
  document changes, spreadsheet changes, lab workflow evidence, or source
  references

They must remain grounded in replay evidence. For code-heavy rows, source file
references are provenance only; concrete code evidence belongs in exact
`code_change` snippets or patch hunks.

## What We Are Not Building

This repo is not:

- a generic chat memory store
- a raw desktop surveillance stream
- a hidden server-side memory layer agents cannot inspect
- a wiki or note promotion system
- a trajectory-first capture tool
- a hosted sandbox execution platform
- a replacement for existing RL or eval harnesses

## Stable Project Sentence

Use this sentence when describing the project:

> Datalox Agent Replay records exact agent tool I/O into verifiable replay bundles so teams can reproduce tool observations later without live upstream tools.
