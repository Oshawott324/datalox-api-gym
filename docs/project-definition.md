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

Datalox API Gym provides resettable, verifiable API worlds where agents can
practice realistic tool use before touching production systems.

The product object is an API world: a stateful fake or replay-backed business
system with seeded scenarios, model-visible tools, side effects, async events,
permission boundaries, hidden verifier state, and exportable run evidence.

Replay is a feature of API Gym, not the center of the product. Replay freezes
exact observations from live APIs, MCP tools, domain tools, or prior world runs
so the same episode can be reused later without calling upstream systems.

Primary consumption loop:

```text
API world -> task scenario -> agent run -> verifier/replay evidence -> training/eval exports
```

World authoring loop:

```text
API state distribution -> scenario sampler -> tool contract -> verifier -> world package
```

Replay authoring loop:

```text
live API/MCP/domain env -> agent rollout -> tool_io_record.v1 -> replay_bundle.v1 -> replay-backed world version
```

The near-term wedge is API-specific. Do not lead with generic "worlds" until
other families prove themselves. The first useful target is not a catalog of
endpoint mocks; it is a small set of stateful API worlds with many realistic
task scenarios:

```text
billing-support-miniworld@2026-06
  fake_billing_api
  fake_support_api
  fake_crm_api
  fake_email_api
```

The durable distinction:

```text
API aggregators connect agents to real APIs.
Datalox API Gym gives agents resettable practice worlds for API workflows.
```

For broader positioning and prior domain exploration, see
[buyer-pilot-playbook.html](./buyer-pilot-playbook.html),
[physical-lab-replay-sim-ladder.html](./physical-lab-replay-sim-ladder.html),
[budget-agent-rl-proof-demo-guide.html](./budget-agent-rl-proof-demo-guide.html),
and [flowcyto-environment-pack-plan.html](./flowcyto-environment-pack-plan.html).

## Project Boundary

This repo is not a data-recorder-only product, a trajectory-first dataset
builder, a wiki, a note promotion system, or a general memory layer.

The project boundary is:

- package runnable API worlds
- define task scenarios and state distributions
- expose model-visible tool contracts
- execute local CLI/HTTP/MCP world adapters
- record exact tool I/O during runs
- preserve deterministic request hashes and sequence indexes
- verify task outcomes against hidden state and verifier specs
- replay recorded observations without live tool fallback
- export compact training/eval rows from verified run evidence

This repo does not own production API aggregation, sandbox engines, model
trainers, reward model research, or generic robot/lab simulators. Those systems
can host or consume API Gym worlds, but they are not the product center here.

Sibling Datalox domain repos can still provide scientific or physical-lab
worlds later. Treat them as separate families. This repo should stay centered
on API Gym unless a non-API world reaches the same level of buyer pull.

Do not make training row format the core wedge. SFT, completion, preference,
reward, and transition rows are adapters derived from grounded environment
rollouts. Training teams may reshape those rows for verl, Hugging Face, or
internal trainers.

## Why This Exists

Agent teams do not mainly need another connector catalog. They need realistic
practice worlds where API state changes, permissions, async events, edge cases,
and hidden verifier state behave consistently across thousands of rollouts.

Official provider sandboxes help developers test integrations, but they are not
designed as agent training environments. They usually do not provide seeded task
distributions, per-episode reset, hidden verifiers, isolated rollouts at scale,
or cross-service workflows.

Datalox API Gym solves that gap:

- provide resettable stateful API worlds
- sample many scenarios inside a few high-value API families
- make side effects, async events, permissions, and errors part of the world
- verify outcomes against hidden state
- replay exact observations when a world is backed by real or prior runs
- export SFT, preference, eval, and later RL views from verified run evidence

Teams can keep their existing agent runtime, sandbox, reward code, eval runner,
or trainer. API Gym supplies the runnable practice world and evidence layer.

## Agentic RL Layer Map

Datalox API Gym lives above raw connectors and below trainers/eval harnesses:

```text
Layer 1    host sandbox / container / cluster
Layer 2    stateful API world runtime                 <- Datalox API Gym
Layer 2.5  replay evidence mode                       <- Datalox API Gym feature
Layer 3    verifier / reward / eval adapters
Layer 4    trainer / rollout worker / model provider
```

During replay, recorded observations function like high-trust fixtures for
agent-visible tools or external APIs. The important boundary is that replay
does not invent behavior. A generative simulator may predict new outcomes only
when explicitly declared as a simulator-backed world.

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

The install-facing MCP surface is API-world-first:

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

> Datalox API Gym provides resettable, verifiable API worlds that teams can run, replay, and export into training/eval data without live upstream tools.
