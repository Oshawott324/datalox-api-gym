# Product Definition

This is the canonical definition of what this repo is building.

If other docs drift, this document wins. For the per-turn capture shape,
[agent-turn-schema.md](./agent-turn-schema.md) wins. For the exported trajectory
row shape, [trajectory-dataset-schema.md](./trajectory-dataset-schema.md) wins
for coding/debugging rows and
[agent-task-trajectory-schema.md](./agent-task-trajectory-schema.md) wins for
mixed-domain task episode rows.

## One-Sentence Definition

Datalox captures export-gated agent debugging sessions for B2B data/eval use and derives lean trajectory rows from those sessions when buyers need compact training examples.

## Product Focus

The repo should optimize for the B2B session data and trajectory eval product.

The repo product pipeline is:

```text
agent run -> AgentTurnV1 events -> session/episode assembly -> export/redaction gate -> approved session dataset -> optional trajectory/eval rows
```

Do not preserve legacy note/skill promotion as a second product loop in this repo. Existing skills and notes are legacy or internal agent-guidance surfaces until they are migrated or isolated behind the session/trajectory data pipeline.

## Business Goal

The commercial goal is to sell approved, anonymized agent debugging session datasets and derived trajectory/eval corpora to AI companies.

The operating model is:

1. Users run an agent with Datalox MCP instrumentation enabled.
2. Datalox records `agent_turn.v1` events from completed turns: prompts, tool actions, file edits, verification commands, and outcome evidence.
3. Turn events are assembled into a session or task episode.
4. A small export/redaction gate and outcome label are applied.
5. Approved anonymized sessions can be packaged directly as source data.
6. Compact `debugging_trajectory.v1` or `agent_task_trajectory.v1` rows are derived for buyers who need training/eval examples instead of full session replay.

The desktop or host agent is the source of agent runs. `AgentTurnV1` is the capture primitive. The approved session bundle is the source-of-truth asset; trajectory rows are a buyer-facing derivative.

## Why This Exists

AI companies need more than final answers. For coding agents and debugging agents, the source asset is the real agent session with enough structure to inspect:

- user prompts
- agent-visible actions
- tool calls and command results
- file edits and diffs
- verification commands and outcomes

The compact learning unit derived from that session is:

```text
problem -> context -> trajectory -> final fix -> verification -> outcome
```

That unit is useful for:

- coding-agent evals
- debugging-agent regression suites
- post-training data
- tool-use analysis
- failure-mode analysis

Datalox exists to capture each turn simply, assemble approved sessions, keep them export-gated, and derive the compact unit only when useful. Agents should not have to fill an audit-heavy schema during normal work.

## What We Are Building

This repo builds one product pipeline with supporting infrastructure:

1. **Datalox MCP**
   Agent instrumentation, session/event capture, host adapters, outcome labeling, verification status, and export control.
2. **Datalox Session Data**
   The source B2B data product: approved anonymized agent sessions with prompts, tool actions, file edits, and verification evidence.
3. **Datalox Trajectory Data**
   The derived B2B dataset/eval product: lean, outcome-labeled `debugging_trajectory.v1` and `agent_task_trajectory.v1` records and curated corpora.

Legacy repo-local skill and note surfaces may remain while the pack is being migrated, but they are not the product architecture for this repo.

The commercial source export structure is:

- one `.datalox/events/agent-turns/` `agent_turn.v1` event per meaningful completed turn
- one approved session bundle per meaningful agent work episode
- prompts, tool actions, file edits, diffs or changed snippets, verification commands, and outcome evidence
- export/redaction status and source provenance

The derived trajectory export structure is:

- one `.datalox/events/trajectory-rows/` lean trajectory row per meaningful debugging episode
- one `.datalox/events/agent-task-trajectories/` lean trajectory row per mixed-domain task episode
- coding/debugging schema defined in [trajectory-dataset-schema.md](./trajectory-dataset-schema.md)
- mixed-domain schema defined in [agent-task-trajectory-schema.md](./agent-task-trajectory-schema.md)
- records include the problem, context, agent trajectory, final fix, outcome label, verification state, and a small export gate

The agent capture structure is:

- agents or host adapters produce `.datalox/events/` structured events
- events preserve enough context, action, evidence, and verification material for export
- approved events can be sold as anonymized sessions or used to derive trajectory rows after labels and export-blocking issues are handled

The first-class capture surface is Datalox MCP:

- `record_agent_turn` should record one explicit `agent_turn.v1` event as `payload.agentTurn`
- `record_trajectory` records one explicit `debugging_trajectory.v1` row as a `.datalox/events/trajectory-rows/` event with `trajectoryRow`
- `record_agent_task_trajectory` records one explicit `agent_task_trajectory.v1` row as a `.datalox/events/agent-task-trajectories/` event with `agentTaskTrajectory`
- `grade_trajectories` grades recorded rows for training readiness without mutating source events
- `repair_trajectory` records corrected rows as new linked events instead of mutating evidence events
- `export_trajectories` exports sellable row candidates from recorded events into JSONL
- `export_agent_task_trajectories` exports sellable mixed-domain task rows into JSONL
- `record_turn_result` may carry an explicit trajectory row candidate, but it must not infer one from prose fields

## Data Capture Rule

Datalox should capture data only when it can preserve trust.

User-facing capture copy should stay plain:

> Datalox captured this agent session. It includes prompts, tool actions, file edits, and verification results. You can keep it private, review it, or share approved anonymized sessions with your organization/data program.

Every exportable session bundle must include:

- source `agent_turn.v1` turn ids or event paths
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

Unapproved raw logs are not sellable data. An approved anonymized session can be a product by itself; a trajectory row is the compact training/eval derivative.

## Source Rules

The event capture and dataset export should stay direct:

- `trace` inputs record what happened during an agent run and should be normalized into `agent_turn.v1` events for session export
- `web` and `pdf` inputs provide source evidence
- verified debugging episodes can become derived trajectory dataset rows
- verified mixed-domain episodes can become `agent_task_trajectory.v1` rows when a task combines code, documents, spreadsheets, analysis, lab workflow, or source-review evidence
- new product capture data writes under `.datalox/events/`
- legacy `agent-wiki/events/` traces remain readable but are not the future product store

An exported trajectory can link:

- source event paths
- changed files or patches
- matched internal guidance ids when available
- verification artifacts

## Product Boundary

- `Datalox Session Data` = primary B2B source dataset product.
- `Datalox Trajectory Data` = derived B2B dataset/eval product.
- `Datalox MCP` = instrumentation, session capture, labeling, verification status, and export-control surface.
- `Datalox Desktop` or a desktop agent = a capture client, not a separate product loop for this repo.
- `datalox-trajectory-mcp` = repo-local implementation package, protocol, CLI, event capture, export, and remaining legacy guidance assets.
- `adapter` = host-specific enforcement and automation.

MCP availability alone is not enforcement. Enforced host wrappers still matter because they inject guidance before the child run and can record after it.

## How Knowledge And Data Should Emerge

Datalox should not be a raw log dump and should not be generic vector memory.

The export progression is primary:

```text
agent run -> AgentTurnV1 events -> session/episode assembly -> export/redaction gate -> approved session dataset -> optional trajectory/eval rows
```

Legacy note/skill promotion should be treated as internal behavior in this repo. New product work should route through structured turn events first, assemble sessions, then derive trajectory rows when useful.

The system should prefer:

- provenance-aware capture
- explicit export blocking when data cannot be sold
- approved anonymized session bundles
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

## Stable Product Sentence

Use this sentence when describing the project:

> Datalox captures approved agent debugging sessions and derives lean, outcome-labeled trajectories for coding-agent training and evaluation.

## Repo Rule

When repo docs talk about Datalox, they should stay consistent with this definition:

- B2B approved session data plus derived trajectory/evals are the primary product focus
- `AgentTurnV1` events are the simple capture primitive
- approved session bundles are the source B2B data asset
- trajectory rows are compact training/eval derivatives
- Datalox MCP is the instrumentation, capture, labeling, verification, and export-control layer
- `datalox-trajectory-mcp` is the repo-local implementation package
- legacy note/skill promotion is not a product loop for this repo
- unapproved raw traces are not sellable data
- exported coding/debugging rows must follow [trajectory-dataset-schema.md](./trajectory-dataset-schema.md)
- exported mixed-domain rows must follow [agent-task-trajectory-schema.md](./agent-task-trajectory-schema.md)
- agent-first operation and setup
