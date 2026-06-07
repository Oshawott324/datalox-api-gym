# Claude Instructions

Claude Code can see Datalox through separate surfaces:

- `datalox claude` / Claude shim wrapper: enforceable pre-run prompt injection when the active run is inside the Datalox wrapper.
- Claude Stop hook: post-turn sidecar automation; it cannot force pre-turn behavior.
- Claude MCP tools: guidance-only unless Claude Code actually calls them.

Project boundary:

- Datalox MCP is the install-facing instrumentation and control layer for desktop agents.
- Resettable, verifiable API worlds are the primary project focus; replay is the evidence mode.
- Datalox owns API-world packaging, tool contracts, verifier metadata, replay evidence, and export adapters.
- Datalox does not own production API aggregation, sandbox runtimes, model trainers, reward model research, or generic robot/lab simulators.
- `action_observation.v1` is the strict normalized view over replay records and imported traces.
- `tool_io_record.v1` records are the exact replay primitive.
- `agent_turn.v1` events are optional turn review context.
- `replay_bundle.v1` is the portable artifact that can be verified and replayed.
- Lean, outcome-labeled trajectory rows are optional compact training/eval adapters.

Primary API Gym loop:

```text
API world -> task scenario -> agent run -> verifier/replay evidence -> training/eval exports
```

On each loop:

1. read `docs/project-definition.md`, `docs/agentic-rl-layer-map.md`, `docs/action-observation-schema.md`, `docs/tool-io-store-schema.md`, `docs/replay-bundle-schema.md`, and `docs/agent-turn-schema.md` when export/data fields, sandbox, environment, mock, reward, or agentic RL positioning are involved
2. record replay source evidence under `.datalox/tool-io/records/`, `.datalox/events/agent-turns/`, and `.datalox/replay-bundles/`
3. record exact tool I/O first, assemble replay bundles, and derive trajectory rows only when useful
4. do not create a parallel wiki/note/event store

Useful commands:

- trajectory derivation code is derivative-only and is not exposed by the install-facing MCP surface
