# Agent Instructions

Read in this order:

1. `.datalox/manifest.json`
2. `.datalox/config.json`
3. `docs/product-definition.md`
4. `docs/tool-io-store-schema.md` when the task touches tool-call capture or replay
5. `docs/replay-bundle-schema.md` when the task touches replay bundles, approval, or export
6. `docs/agent-turn-schema.md` when the task touches turn review data
7. trajectory schema docs only when deriving optional trajectory/eval rows
8. the selected `skills/<name>/SKILL.md` only when the user explicitly asks for that local skill

Use Datalox Agent Replay with this model:

```text
agent run -> tool I/O records -> replay bundle -> approval/export -> optional derivatives
```

- source kinds: `trace`, `web`, `pdf`
- replay primitive: `tool_io_record.v1`
- review primitive: `agent_turn.v1`
- product replay stores: `.datalox/tool-io/records/`, `.datalox/events/agent-turns/`, `.datalox/replay-bundles/`
- turn event root: `.datalox/events/agent-turns/`
- tool I/O root: `.datalox/tool-io/records/`
- replay bundle root: `.datalox/replay-bundles/`
- source export target: approved anonymized `replay_bundle.v1`
- optional derivative root: `.datalox/derivatives/trajectories/`

Business rule:

- B2B approved replay bundle data plus derived trajectory/evals are the primary product focus.
- Do not keep note/skill promotion as a second product loop in this repo.
- New product data writes under `.datalox/tool-io/records/`, `.datalox/events/agent-turns/`, and `.datalox/replay-bundles/`.
- `tool_io_record.v1` records are the exact replay primitive.
- `agent_turn.v1` events are the simple turn review primitive.
- Approved anonymized replay bundles are the source B2B data asset.
- Lean, outcome-labeled trajectory rows are optional compact training/eval derivatives.
- Unapproved raw traces are not sellable data.

When deriving `debugging_trajectory.v1` or `agent_task_trajectory.v1` rows, keep
them downstream from replay evidence. For code-heavy derivatives, include exact
code evidence; source references alone are provenance, not proof.

Native Codex chat with MCP is guidance-only unless it explicitly calls the MCP
tools. Wrapper runs such as `datalox codex` are the enforceable path because
they inject guidance before the child run and record after it.

Fresh product adoption creates `.datalox/`, instruction surfaces, and shims. It
does not create a parallel wiki/note/event store.

If docs disagree on what Datalox is, `docs/product-definition.md` wins.
If docs disagree on tool I/O capture, `docs/tool-io-store-schema.md` wins.
If docs disagree on replay bundles, `docs/replay-bundle-schema.md` wins.
If docs disagree on turn review capture, `docs/agent-turn-schema.md` wins.
