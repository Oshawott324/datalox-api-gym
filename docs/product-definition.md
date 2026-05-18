# Product Definition

This is the canonical definition of what this repo is building.

If other docs drift, this document wins. For exact tool-call capture,
[tool-io-store-schema.md](./tool-io-store-schema.md) wins. For replay bundles,
[replay-bundle-schema.md](./replay-bundle-schema.md) wins. For the per-turn
capture shape, [agent-turn-schema.md](./agent-turn-schema.md) wins. Trajectory
schemas define optional derivatives only.

## One-Sentence Definition

Datalox Agent Replay records agent-visible tool I/O and session evidence into export-gated replay bundles, then derives lean trajectory/eval rows for AI teams doing agent training, evaluation, and agentic reinforcement learning.

## Product Focus

The repo should optimize for reproducible agent replay as the source product,
with B2B replay bundle data and trajectory/eval rows as export derivatives.

The repo product pipeline is:

```text
agent run -> tool I/O records -> replay bundle -> approval/export -> optional derivatives
```

Do not preserve legacy note/skill promotion as a second product loop in this repo. Existing skills and notes are legacy or internal agent-guidance surfaces until they are migrated or isolated behind the replay data pipeline.

## Business Goal

The commercial goal is to give agent teams reproducible records of what their
agents saw and did, then sell approved anonymized replay bundle datasets and
derived trajectory/eval corpora to AI teams doing agent training, evaluation,
and agentic reinforcement learning.

The operating model is:

1. Users run an agent with Datalox MCP instrumentation enabled.
2. Datalox records `tool_io_record.v1` records for agent-visible tool calls and observations.
3. Datalox records `agent_turn.v1` events from completed turns: prompts, tool actions, file edits, verification commands, and outcome evidence.
4. Tool I/O records and turn events are assembled into a replay bundle.
5. A small export/redaction gate and outcome label are applied.
6. Approved anonymized replay bundles can be packaged directly as source data.
7. Compact `debugging_trajectory.v1` or `agent_task_trajectory.v1` rows are derived for buyers who need training/eval examples instead of full replay.

The desktop or host agent is the source of agent runs. `tool_io_record.v1` is
the replay primitive, `agent_turn.v1` is the review primitive, and the approved
replay bundle is the source-of-truth asset. Trajectory rows are optional
buyer-facing derivatives.

## Why This Exists

AI teams doing agent training, evaluation, and reinforcement learning need
more than final answers and more than static logs. They need replayable
trajectories: enough structure to reproduce an agent episode later against a
new model, a new rubric, or a new tool stack, and get a comparable score.

For coding agents, debugging agents, browser agents, and tool-using agents,
the source asset is the real agent episode with enough structure to inspect
and replay:

- user prompts
- agent-visible actions
- exact tool I/O with deterministic request hashes
- file edits and diffs
- verification commands and outcomes

The replay value is operational, not just historical:

- replay an episode against a new model version to compare behavior
- replay against a new rubric to recompute reward without re-running
  inference
- regression-test that previously-passing trajectories still pass
- generate preference pairs from success vs failure variants of the same
  task
- assemble agentic RL training sets where rewards can be recomputed
  deterministically

Frontier labs have built internal sandbox and trajectory replay systems for
this exact reason. Most AI teams cannot afford to build that platform.
Datalox exists to be the small, open replay layer for the teams that need
replayable trajectories but cannot build a hyperscale sandbox themselves.

The compact derivative unit packaged from a replay bundle is:

```text
problem -> context -> trajectory -> final outcome -> verification -> outcome label
```

That unit is useful for:

- coding-agent evals
- debugging-agent regression suites
- post-training data
- agentic RL training data
- preference pairs and reward modeling
- tool-use analysis
- failure-mode analysis

Datalox exists to capture each tool call and turn simply, assemble approved
replay bundles, keep them export-gated, and derive compact derivative rows
only when packaging is useful. Agents should not have to fill an audit-heavy
schema during normal work.

## What We Are Building

This repo builds one product pipeline with supporting infrastructure:

1. **Datalox MCP**
   Agent instrumentation, session/event capture, tool I/O evidence capture, host adapters, outcome labeling, verification status, and export control.
2. **Datalox Replay Data**
   The source B2B data product: approved anonymized replay bundles with prompts, tool actions, tool observations, file edits, and verification evidence.
3. **Datalox Trajectory Data**
   The derived B2B dataset/eval product: lean, outcome-labeled `debugging_trajectory.v1` and `agent_task_trajectory.v1` records and curated corpora.

Local skills may remain as agent guidance, but they are not a product data
store and they do not create a second note/promotion loop.

The commercial source export structure is:

- one `.datalox/tool-io/records/` `tool_io_record.v1` event per replayable tool call
- one `.datalox/events/agent-turns/` `agent_turn.v1` event per meaningful completed turn
- one `.datalox/replay-bundles/` `replay_bundle.v1` artifact per meaningful agent work episode
- prompts, tool actions, file edits, diffs or changed snippets, verification commands, and outcome evidence
- export/redaction status and source provenance

The derived trajectory export structure is:

- optional trajectory rows under `.datalox/derivatives/trajectories/`
- coding/debugging schema defined in [trajectory-dataset-schema.md](./trajectory-dataset-schema.md)
- mixed-domain schema defined in [agent-task-trajectory-schema.md](./agent-task-trajectory-schema.md)
- records include the problem, context, agent trajectory, final fix, outcome label, verification state, and a small export gate

The agent capture structure is:

- host adapters produce `.datalox/tool-io/records/` replay records
- agents or host adapters produce `.datalox/events/agent-turns/` review events
- replay bundles preserve enough context, action, evidence, and verification material for export
- approved replay bundles can be sold as anonymized source data or used to derive trajectory rows after labels and export-blocking issues are handled

The first-class capture surface is Datalox MCP:

- `record_tool_io` should record one explicit `tool_io_record.v1` record
- `record_agent_turn` should record one explicit `agent_turn.v1` event as `payload.agentTurn`
- `pack_replay_bundle` should assemble turn events and tool I/O records into `replay_bundle.v1`
- `verify_replay_bundle` should verify bundle checksums and replay readiness
- derivative trajectory tools may exist only under the derivative boundary and must not be the normal capture path

## Data Capture Rule

Datalox should capture data only when it can preserve trust.

User-facing capture copy should stay plain:

> Datalox captured this agent session. It includes prompts, tool actions, file edits, and verification results. You can keep it private, review it, or share approved anonymized sessions with your organization/data program.

Every exportable replay bundle must include:

- source `agent_turn.v1` turn ids or event paths
- source `tool_io_record.v1` ids or record paths
- source prompt or problem statement
- agent-visible actions
- meaningful tool calls with command results
- file edits, diffs, or changed snippets
- verification status and evidence
- export/redaction gate

Every derived trajectory record must include:

- explicit schema version
- task prompt or problem statement
- minimal context needed to understand the fix
- concise agent-visible trajectory steps
- final fix summary
- outcome label
- verification status
- small export gate

Unapproved raw logs are not sellable data. An approved anonymized replay bundle
can be a product by itself; a trajectory row is the compact training/eval
derivative.

## Source Rules

The event capture and dataset export should stay direct:

- `trace` inputs record what happened during an agent run and should be normalized into `tool_io_record.v1` records plus `agent_turn.v1` events for replay export
- `web` and `pdf` inputs provide source evidence
- verified debugging episodes can become derived trajectory dataset rows
- verified mixed-domain episodes can become `agent_task_trajectory.v1` rows when a task combines code, documents, spreadsheets, analysis, lab workflow, or source-review evidence
- new replay product capture data writes under `.datalox/tool-io/records/`, `.datalox/events/agent-turns/`, and `.datalox/replay-bundles/`
- fresh product adoption creates `.datalox/`, instruction surfaces, and host shims only
- no wiki/note/event store is shipped as a parallel product path in this branch

An exported trajectory can link:

- source event paths
- changed files or patches
- matched internal guidance ids when available
- verification artifacts

## Product Boundary

- `Datalox Replay Data` = primary B2B source dataset product.
- `Datalox Trajectory Data` = derived B2B dataset/eval product.
- `Datalox MCP` = instrumentation, session capture, tool I/O capture, labeling, verification status, and export-control surface.
- `Datalox Desktop` or a desktop agent = a capture client, not a separate product loop for this repo.
- `datalox-agent-replay` = repo-local implementation package, protocol, CLI, event capture, and export.
- `adapter` = host-specific enforcement and automation.

MCP availability alone is not enforcement. Enforced host wrappers still matter because they inject guidance before the child run and can record after it.

## How Knowledge And Data Should Emerge

Datalox should not be a raw log dump and should not be generic vector memory.

The export progression is primary:

```text
agent run -> tool I/O records -> replay bundle -> approval/export -> optional derivatives
```

New product work should route through tool I/O records first, assemble replay
bundles, then derive trajectory or eval rows when useful.

The system should prefer:

- provenance-aware capture
- explicit export blocking when data cannot be sold
- approved anonymized replay bundles
- outcome-labeled rows
- exportable structured derivatives
- simple agent-readable capture outputs
- low-human-setup operation

## What We Are Not Building

We are not building:

- a generic chat memory blob
- a raw desktop surveillance stream
- a hidden server-only memory layer that agents cannot inspect
- a human-first wiki with agent support added later
- a consumer data marketplace sold directly to end users
- an unapproved collection of traces with no outcome or export gate
- a parallel local skill/note product loop inside this trajectory export repo
- a hyperscale sandbox execution platform (the layer below Datalox; teams bring their own Docker, k8s, Modal, e2b, Daytona, or equivalent)

## Stable Product Sentence

Use this sentence when describing the project:

> Datalox records agent tool I/O into reproducible replay bundles and derives lean, outcome-labeled trajectories for agent training and evaluation.

## Repo Rule

When repo docs talk about Datalox, they should stay consistent with this definition:

- B2B approved replay bundle data plus derived trajectory/evals are the primary product focus
- `tool_io_record.v1` records are the exact replay primitive
- `agent_turn.v1` events are the simple turn review primitive
- approved replay bundles are the source B2B data asset
- trajectory rows are optional compact training/eval derivatives that reference their source replay bundle
- Datalox MCP is the instrumentation, tool I/O capture, labeling, verification, and export-control layer
- `datalox-agent-replay` is the repo-local implementation package
- legacy note/skill promotion is not a product loop for this repo
- unapproved raw traces are not sellable data
- exported coding/debugging rows must follow [trajectory-dataset-schema.md](./trajectory-dataset-schema.md)
- exported mixed-domain rows must follow [agent-task-trajectory-schema.md](./agent-task-trajectory-schema.md)
- agent-first operation and setup
