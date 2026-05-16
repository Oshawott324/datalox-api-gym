# Claude Instructions

Claude Code can see Datalox through separate surfaces:

- `datalox claude` / Claude shim wrapper: enforceable pre-run prompt injection when the active run is inside the Datalox wrapper.
- Claude Stop hook: post-turn sidecar automation; it cannot force pre-turn behavior.
- Claude MCP tools: guidance-only unless Claude Code actually calls them.

Product boundary:

- Datalox MCP is the product-facing instrumentation and control layer for desktop agents.
- B2B approved replay bundles plus derived trajectory/evals are the primary product focus.
- `tool_io_record.v1` records are the exact replay primitive.
- `agent_turn.v1` events are the simple turn review primitive.
- Approved anonymized replay bundles are the source B2B data asset.
- Lean, outcome-labeled trajectory rows are optional compact training/eval derivatives.

Primary product loop:

```text
agent run -> tool I/O records -> replay bundle -> approval/export -> optional derivatives
```

On each loop:

1. read `docs/product-definition.md`, `docs/tool-io-store-schema.md`, `docs/replay-bundle-schema.md`, and `docs/agent-turn-schema.md` when export/data fields are involved
2. record replay source evidence under `.datalox/tool-io/records/`, `.datalox/events/agent-turns/`, and `.datalox/replay-bundles/`
3. route new product behavior through tool I/O records first, assemble replay bundles, then derive trajectory rows when useful
4. do not create a parallel wiki/note/event store

Useful commands:

- current trajectory commands are derivative-only until replay MCP tools land
