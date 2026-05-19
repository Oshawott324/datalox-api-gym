# Gemini Instructions

Use Datalox Agent Replay for replay capture.

Primary replay loop:

```text
agent tool call -> tool_io_record.v1 -> replay_bundle.v1 -> deterministic replay -> optional derivatives
```

Read:

1. `.datalox/manifest.json`
2. `.datalox/config.json`
3. `docs/project-definition.md`
4. `docs/agentic-rl-layer-map.md` when sandbox, environment, mock, reward, or agentic RL positioning is involved
5. `docs/action-observation-schema.md` when raw trace normalization or action schema is involved
6. `docs/tool-io-store-schema.md` when tool-call capture or replay is involved
7. `docs/replay-bundle-schema.md` when replay bundles, approval, or export are involved
8. `docs/agent-turn-schema.md` when turn review data is involved
9. trajectory schema docs only when deriving optional trajectory/eval rows

Replay data belongs under `.datalox/tool-io/records/`,
`.datalox/events/agent-turns/`, and `.datalox/replay-bundles/`. Do not create a
parallel wiki/note/event store.

Datalox owns tool-I/O record/replay, not sandbox runtimes, environment
construction, behavioral mocks, reward functions, or judge agents.

Trajectory derivation code is derivative-only and is not exposed by the install-facing MCP surface.
