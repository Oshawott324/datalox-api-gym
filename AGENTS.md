# Agent Instructions

Read in this order:

1. `.datalox/manifest.json`
2. `.datalox/config.json`
3. `docs/product-definition.md`
4. `docs/agent-turn-schema.md` when the task touches session capture, session export, or data sale
5. `docs/trajectory-dataset-schema.md` when the task touches debugging trajectory recording, trajectory export, or data sale
6. `docs/agent-task-trajectory-schema.md` when the task touches mixed-domain agent episodes
7. the selected `skills/<name>/SKILL.md` only when the user explicitly asks for that local skill

Use the pack with this model:

- source kinds: `trace`, `web`, `pdf`
- capture primitive: `agent_turn.v1`
- product event store: `.datalox/events/`
- turn event root: `.datalox/events/agent-turns/`
- debugging trajectory root: `.datalox/events/trajectory-rows/`
- mixed-domain trajectory root: `.datalox/events/agent-task-trajectories/`
- source export target: approved anonymized session bundle
- trajectory derivative targets: `debugging_trajectory.v1`, `agent_task_trajectory.v1`

Business rule:

- B2B approved session data plus derived trajectory/evals are the primary product focus.
- Do not keep note/skill promotion as a second product loop in this repo.
- New product data writes under `.datalox/`.
- `agent_turn.v1` events are the simple capture primitive.
- Approved anonymized session bundles are the source B2B data asset.
- Lean, outcome-labeled trajectory rows are compact training/eval derivatives.
- Unapproved raw traces are not sellable data.

When building `debugging_trajectory.v1` rows, `context.relevant_files[].before`
and `after` must be exact code snippets, not prose summaries or pointers to
source paths. If a row claiming `curation.quality: "use"` fails deterministic
grading, Datalox records it as `needs_review` with downgrade diagnostics so it
can be repaired.

When building `agent_task_trajectory.v1` rows for code-heavy work, include at
least one exact `code_change` evidence block for buyer-facing `quality: "use"`.
Use source references as provenance, not as a substitute for snippets or patch
hunks.

Native Codex chat with MCP is guidance-only unless it explicitly calls the MCP
tools. Wrapper runs such as `datalox codex` are the enforceable path because
they inject guidance before the child run and record after it.

Fresh product adoption creates `.datalox/`, instruction surfaces, and shims. It
does not create a parallel wiki/note/event store.

If docs disagree on what Datalox is, `docs/product-definition.md` wins.
If docs disagree on turn capture, `docs/agent-turn-schema.md` wins.
If docs disagree on exported trajectory rows, `docs/trajectory-dataset-schema.md` wins.
