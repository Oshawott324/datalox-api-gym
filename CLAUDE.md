# Claude Instructions

Claude Code can see Datalox through separate surfaces:

- `datalox claude` / Claude shim wrapper: enforceable pre-run prompt injection when the active run is inside the Datalox wrapper.
- Claude Stop hook: post-turn sidecar automation; it cannot force pre-turn behavior.
- Claude MCP tools: guidance-only unless Claude Code actually calls them.

Product boundary:

- Datalox MCP is the product-facing instrumentation and control layer for desktop agents.
- B2B approved replay/session data plus derived trajectory/evals are the primary product focus.
- `agent_turn.v1` events are the simple capture primitive.
- Approved anonymized replay/session bundles are the source B2B data asset.
- Lean, outcome-labeled trajectory rows are compact training/eval derivatives.

On each loop:

1. read `docs/product-definition.md`, `docs/agent-turn-schema.md`, and trajectory schema docs when export/data fields are involved
2. record new product events under `.datalox/events/`
3. route new product behavior through captured `agent_turn.v1` events first, assemble sessions, then derive trajectory rows when useful
4. do not create a parallel wiki/note/event store

Useful commands:

- `datalox record-trajectory --repo . --trajectory-row row.json --json`
- `datalox record-agent-task-trajectory --repo . --agent-task-trajectory row.json --json`
- `datalox grade-trajectories --repo . --json`
- `datalox export-trajectories --repo . --quality use --json`
