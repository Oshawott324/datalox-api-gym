# Agent Instructions

Read in this order:

1. `.datalox/manifest.json`
2. `.datalox/config.json`
3. `docs/project-definition.md`
4. `docs/agentic-rl-layer-map.md` when the task touches sandbox, environment, mock, reward, or agentic RL positioning
5. `docs/action-observation-schema.md` when the task touches raw trace normalization or action schema
6. `docs/tool-io-store-schema.md` when the task touches tool-call capture or replay
7. `docs/replay-bundle-schema.md` when the task touches replay bundles, approval, or export
8. `docs/agent-turn-schema.md` when the task touches turn review data
9. trajectory schema docs only when deriving optional trajectory/eval rows
10. the selected `skills/<name>/SKILL.md` only when the user explicitly asks for that local skill

Use Datalox Agent Replay with this model:

```text
agent tool call -> tool_io_record.v1 -> replay_bundle.v1 -> deterministic replay -> optional derivatives
```

- normalized view over replay records and imported traces: `action_observation.v1`
- layer boundary: Datalox owns tool-I/O record/replay; it does not own sandbox runtime, environment construction, behavioral mocks, reward functions, or judge agents
- exact replay primitive: `tool_io_record.v1`
- replay lookup key: `request_hash + sequence_index`
- optional turn review context: `agent_turn.v1`
- replay stores: `.datalox/tool-io/records/`, `.datalox/mcp-tool-catalogs/`, `.datalox/events/agent-turns/`, `.datalox/replay-bundles/`
- turn event root: `.datalox/events/agent-turns/`
- tool I/O root: `.datalox/tool-io/records/`
- MCP tool catalog root: `.datalox/mcp-tool-catalogs/`
- replay bundle root: `.datalox/replay-bundles/`
- portable replay artifact: `replay_bundle.v1`
- optional derivative root: `.datalox/derivatives/trajectories/`

Business rule:

- Reproducible tool-call replay is the primary project focus.
- Do not keep note/skill promotion as a second loop in this repo.
- New replay data writes under `.datalox/tool-io/records/`, `.datalox/mcp-tool-catalogs/`, `.datalox/events/agent-turns/`, and `.datalox/replay-bundles/`.
- `action_observation.v1` is the strict normalized action/observation view over raw traces and tool I/O records.
- `tool_io_record.v1` records are the exact replay primitive.
- `agent_turn.v1` events are the simple turn review primitive.
- `replay_bundle.v1` is the portable artifact that can be verified and replayed.
- Lean, outcome-labeled trajectory rows are optional compact training/eval adapters.
- Raw traces and prose summaries are not replay records.

When deriving `debugging_trajectory.v1` or `agent_task_trajectory.v1` rows, keep
them downstream from replay evidence. For code-heavy derivatives, include exact
code evidence; source references alone are provenance, not proof.

Native Codex chat with MCP is guidance-only unless it explicitly calls the MCP
tools. Wrapper runs such as `datalox codex` are the enforceable path because
they inject guidance before the child run and record after it.

Fresh replay adoption creates `.datalox/`, instruction surfaces, and shims. It
does not create a parallel wiki/note/event store.

If docs disagree on what Datalox is, `docs/project-definition.md` wins.
If docs disagree on Datalox's agentic RL layer boundary, `docs/agentic-rl-layer-map.md` wins.
If docs disagree on action/observation normalization, `docs/action-observation-schema.md` wins.
If docs disagree on tool I/O capture, `docs/tool-io-store-schema.md` wins.
If docs disagree on replay bundles, `docs/replay-bundle-schema.md` wins.
If docs disagree on turn review capture, `docs/agent-turn-schema.md` wins.
