# Project Overview

The canonical project definition lives in [project-definition.md](./project-definition.md).
The canonical action/observation schema lives in [action-observation-schema.md](./action-observation-schema.md).
The canonical tool I/O schema lives in [tool-io-store-schema.md](./tool-io-store-schema.md).
The canonical replay bundle schema lives in [replay-bundle-schema.md](./replay-bundle-schema.md).
The canonical per-turn review schema lives in [agent-turn-schema.md](./agent-turn-schema.md).
The canonical derivative trajectory schema lives in [trajectory-dataset-schema.md](./derivatives/trajectory/trajectory-dataset-schema.md).
The filesystem-backed orchestration protocol lives in [task-orchestration.md](./task-orchestration.md).

Short version:

- Datalox Agent Replay is an MCP-compatible VCR for agent tools.
- `action_observation.v1` is the strict normalized view over replay records and imported traces.
- `tool_io_record.v1` records are the exact replay primitive.
- `agent_turn.v1` events are optional turn review context.
- `replay_bundle.v1` is the portable artifact that can be verified and replayed.
- `debugging_trajectory.v1` rows are optional compact training/eval adapters.
- Datalox MCP is the instrumentation, tool I/O capture, replay, verification, and export-control layer.
- `datalox-agent-replay` is the repo-local implementation package.
- Local skills are internal guidance surfaces, not a second replay loop.

Primary replay loop:

```text
agent tool call -> tool_io_record.v1 -> replay_bundle.v1 -> deterministic replay -> optional derivatives
```

Do not model this repo around legacy note/skill promotion. New replay work
should record exact tool I/O first, assemble replay bundles, and derive
trajectory rows only when useful.

The repo is centered on:

- `.datalox/events/agent-turns/`
- `.datalox/tool-io/records/`
- `.datalox/replay-bundles/`
- `.datalox/approvals/`
- `.datalox/derivatives/trajectories/`
- `docs/action-observation-schema.md`
- `docs/tool-io-store-schema.md`
- `docs/replay-bundle-schema.md`
- `docs/agent-turn-schema.md`
- `docs/derivatives/trajectory/trajectory-dataset-schema.md`
- local `skills/` only where current host guidance still requires them

New replay data writes to `.datalox/` paths.

Normal read path:

1. read the project definition
2. read the action/observation schema when normalizing raw traces or action fields
3. read the tool I/O schema when replay capture fields are involved
4. read the replay bundle schema when approval/export fields are involved
5. read the turn schema when turn review fields are involved
6. read the trajectory schema only for optional derivative rows
7. record meaningful grounded events
8. use local skill guidance only where current host behavior still requires it

Current durable local replay outputs:

- `.datalox/events/agent-turns/`
- `.datalox/tool-io/records/`
- `.datalox/replay-bundles/`
- `.datalox/derivatives/trajectories/`

Tool I/O records are the exact replay source units, not raw host transcripts.
Action/observation records are strict normalized views over tool I/O evidence.
Turn events are review units. Trajectory dataset rows are export derivatives,
not new repo-local knowledge page types and not the complete source replay
bundle. Use `action_observation.v1` from
[action-observation-schema.md](./action-observation-schema.md) for normalized
action evidence, `tool_io_record.v1` from [tool-io-store-schema.md](./tool-io-store-schema.md)
for replay capture, `replay_bundle.v1` from [replay-bundle-schema.md](./replay-bundle-schema.md)
for portable replay bundles, and trajectory schemas only for compact derived
rows. Do not add new project behavior to local note/skill promotion.

Avoid expanding taxonomy unless real usage proves another generated page type is necessary.
