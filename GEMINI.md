# Gemini Instructions

Use Datalox Agent Replay for product replay capture.

Primary product loop:

```text
messy agent traces -> validated action/observation records -> replay bundle -> approval/export -> optional derivatives
```

Read:

1. `.datalox/manifest.json`
2. `.datalox/config.json`
3. `docs/product-definition.md`
4. `docs/action-observation-schema.md` when raw trace normalization or action schema is involved
5. `docs/tool-io-store-schema.md` when tool-call capture or replay is involved
6. `docs/replay-bundle-schema.md` when replay bundles, approval, or export are involved
7. `docs/agent-turn-schema.md` when turn review data is involved
8. trajectory schema docs only when deriving optional trajectory/eval rows

Product source data belongs under `.datalox/tool-io/records/`,
`.datalox/events/agent-turns/`, and `.datalox/replay-bundles/`. Do not create a
parallel wiki/note/event store.

Trajectory derivation code is derivative-only and is not exposed by the install-facing MCP surface.
