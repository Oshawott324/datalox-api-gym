# Project Overview

The canonical product definition lives in [product-definition.md](./product-definition.md).
The canonical per-turn capture schema lives in [agent-turn-schema.md](./agent-turn-schema.md).
The canonical dataset export schema lives in [trajectory-dataset-schema.md](./trajectory-dataset-schema.md).
The filesystem-backed orchestration protocol lives in [task-orchestration.md](./task-orchestration.md).

Short version:

- Approved Datalox session bundles are the source B2B dataset product.
- `agent_turn.v1` events are the simple capture primitive.
- `debugging_trajectory.v1` rows are compact training/eval derivatives.
- Datalox MCP is the instrumentation, session capture, labeling, verification, and export-control layer.
- `datalox-pack` is the repo-local implementation package.
- Existing skills and notes are legacy or internal guidance surfaces, not a second product loop.

Primary product loop:

```text
agent run -> AgentTurnV1 events -> session/episode assembly -> export/redaction gate -> approved session dataset -> optional trajectory/eval rows
```

Do not model this repo around legacy note/skill promotion. New product work should route through captured turn events first, assemble sessions, then derive trajectory rows when useful.

The repo is centered on:

- `.datalox/events/agent-turns/`
- `.datalox/events/trajectory-rows/`
- `.datalox/session-candidates/`
- `.datalox/approvals/`
- `docs/agent-turn-schema.md`
- `docs/trajectory-dataset-schema.md`
- legacy/internal `skills/` and `agent-wiki/notes/` only where current host guidance still requires them

`agent-wiki/events/` remains a readable legacy event store. New product data should write to `.datalox/` paths.

Normal read path:

1. read the product definition
2. read the turn schema when session capture/export fields are involved
3. read the trajectory schema when trajectory export/data fields are involved
4. record meaningful grounded events
5. use existing skill/note guidance only where current host behavior still requires it

Current source kinds:

- `trace`
- `web`
- `pdf`

Current durable local outputs:

- `skill`
- `note`

Turn events are source capture units, not raw host transcripts. Trajectory dataset rows are export derivatives, not new repo-local knowledge page types and not the complete source session. Use `agent_turn.v1` from [agent-turn-schema.md](./agent-turn-schema.md) for capture and `debugging_trajectory.v1` from [trajectory-dataset-schema.md](./trajectory-dataset-schema.md) for compact derived rows. Do not add new product behavior to local note/skill promotion.

Avoid expanding taxonomy unless real usage proves another generated page type is necessary.
