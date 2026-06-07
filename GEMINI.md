# Gemini Instructions

Use Datalox API Gym for resettable API-world practice and replay capture.

Primary API Gym loop:

```text
API world -> task scenario -> agent run -> verifier/replay evidence -> training/eval exports
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

Datalox owns API-world packaging, tool contracts, verifier metadata, replay
evidence, and export adapters. It does not own production API aggregation,
sandbox runtimes, model trainers, reward model research, or generic robot/lab
simulators.

Trajectory derivation code is derivative-only and is not exposed by the install-facing MCP surface.
