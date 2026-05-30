# Project Definition

This is the canonical definition of what this repo is building.

If other docs drift, this document wins. For exact tool-call capture,
[tool-io-store-schema.md](./tool-io-store-schema.md) wins. For normalized
action/observation views, [action-observation-schema.md](./action-observation-schema.md)
wins. For replay bundles, [replay-bundle-schema.md](./replay-bundle-schema.md)
wins. For optional turn review context, [agent-turn-schema.md](./agent-turn-schema.md)
wins. [agentic-rl-layer-map.md](./agentic-rl-layer-map.md) defines the product
boundary inside the broader sandbox/env/reward stack. Trajectory schemas define
optional downstream adapters only.

## Definition

Datalox Agent Replay is the engine for versioned API/MCP snapshot
environments.

Users consume versioned fixture packs and fixture sets: frozen tool catalogs,
tool observations, task specs, verifier metadata, deterministic replay, and
training/eval exports. Recording is one authoring path for creating a private
snapshot from a live MCP/API/domain environment.

The broader Datalox product wedge is:

```text
traditional human-facing workflow
  -> agent-native domain environment
  -> replay evidence/data layer
  -> exportable training/eval data
```

For this repo, that means Agent Replay owns the replay evidence/data layer:
exact tool I/O records, replay bundles, fixture activation, deterministic
replay, verifier evidence, and training/eval exports. Sibling domain repos may
own live scientific environments that reconstruct traditional applications or
workflows as agent-native tools, structured state, validators, and constrained
UI/app surfaces. The current concrete proof target is
`flowcyto-gating-qc-basic@2026-06.0`: a versioned flow cytometry environment
pack that combines real domain tools, workspace state, validators, replay
bundles, and SFT export. See
[flowcyto-environment-pack-plan.html](./flowcyto-environment-pack-plan.html).

Primary consumption loop:

```text
versioned API/MCP snapshot -> fixture set -> replay runtime -> agent run -> training/eval exports
```

Snapshot authoring loop:

```text
live MCP/API/domain env -> agent rollout -> tool_io_record.v1 -> replay_bundle.v1 -> fixture pack/version
```

The environment ladder is:

```text
versioned snapshot environment
  versioned API/MCP snapshot + fixture set + replay bundles
  deterministic over observed scenarios

runtime-backed environment
  live tools, APIs, MCPs, or external runtimes generate new rollouts

generative environment
  reset/step world that samples many task instances and verifies them
```

## Project Boundary

This repo is not a data-recorder-only product, a trajectory-first dataset
builder, a wiki, a note promotion system, or a general memory layer.

The project boundary is:

- record exact tool I/O
- preserve MCP proxy tool catalogs when Datalox sits in front of an upstream MCP server
- preserve deterministic request hashes and sequence indexes
- pack tool I/O records and optional turn context into a replay bundle
- verify bundle integrity through checksums
- replay recorded observations without live tool fallback
- activate versioned fixture worlds from verified bundles and fixture sets
- derive compact training/eval rows only after replay evidence exists

Everything else is supporting infrastructure.

This boundary describes the Agent Replay repo. Sibling Datalox domain MCP repos
can provide constrained scientific environments, such as flow cytometry,
molecular biology, or protein visualization workspaces. Agent Replay should
snapshot and replay the tool I/O those environments emit; it should not absorb
their domain runtime, UI, or scientific algorithms.

The business front door should therefore not be "replay company" by itself.
Replay is the trust and data layer. The stronger product story is that Datalox
turns high-value traditional workflows into agent-native environments, and then
uses replay evidence to make those environments auditable, reusable, and useful
for training/eval teams.

Do not make training row format the core wedge. SFT, completion, preference,
reward, and transition rows are adapters derived from grounded environment
rollouts. Training teams may reshape those rows for verl, Hugging Face, or
internal trainers.

## Why This Exists

Agent training, eval, and regression teams hit the same failure mode: they
cannot reproduce the environment an agent actually experienced. Live APIs
change, search results move, databases mutate, model tool outputs vary, and
reward/debugging becomes guesswork.

Datalox solves the versioned snapshot environment layer first:

- provide published fixture packs for common task worlds
- provide domain environment packs when sibling Datalox domain repos own the
  live environment
- let teams author private fixture packs from their own live tools
- make that evidence content-addressed and portable
- package the evidence into pinned fixture worlds
- replay the same observations later with upstream off
- export SFT, preference, reward/eval, and later RL views from verified evidence

Teams can keep their existing agent runtime, sandbox, reward code, eval runner,
or training stack. Datalox sits underneath those systems as the versioned
snapshot environment and evidence layer.

## Agentic RL Layer Map

Datalox Agent Replay lives in the versioned snapshot environment and tool-I/O
record/replay layer:

```text
Layer 1    sandbox/runtime foundation
Layer 2a   constrained domain MCP environments       <- sibling Datalox domain repos can own this
Layer 2b   generic task environment construction      <- not this repo
Layer 1.5  versioned snapshot environment + tool-I/O replay <- Datalox Agent Replay
Layer 3    evaluation and reward rules
```

During replay, recorded observations can function like record-based mocks for
agent-visible tools or external APIs. The important boundary is that Datalox
does not invent behavior. It records a real observation first and later returns
that exact observation by `request_hash + sequence_index`.

Datalox Agent Replay is complementary to sandbox runtimes, generic environment
builders, behavioral mocks, judge agents, reward engines, and Datalox's own
domain MCP environments. It should provide versioned snapshots for those
systems when available, but not become those systems.

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

### `mcp_tool_catalog.v1`

Optional proxy metadata for the MCP VCR path.

When Datalox records through `datalox proxy --mode record`, it snapshots the
agent-visible upstream MCP `tools/list` result under:

```text
.datalox/mcp-tool-catalogs/
```

Replay bundles can include those catalog artifacts so replay mode can answer
`tools/list` without starting upstream.

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
  mcp-tool-catalogs/
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
- a stateful environment/mock construction platform
- a reward or judge-agent engine
- a replacement for existing RL or eval harnesses

## Stable Project Sentence

Use this sentence when describing the project:

> Datalox Agent Replay provides versioned API/MCP snapshot environments that teams can run, replay, and export into training/eval data without live upstream tools.
