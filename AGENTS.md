# Agent Instructions

Read in this order:

1. `.datalox/manifest.json`
2. `.datalox/config.json`
3. `docs/product-definition.md`
4. `docs/agent-turn-schema.md` when the task touches session capture, session export, or data sale
5. `docs/trajectory-dataset-schema.md` when the task touches trajectory recording, trajectory export, or data sale
6. `agent-wiki/hot.md` when it exists
7. the selected `skills/<name>/SKILL.md`
8. the linked notes in `metadata.datalox.note_paths`

If legacy full-pack MCP tools are available, call `resolve_loop` before internal Datalox maintenance work and use the matched skill plus linked notes before acting. For trajectory dataset work, prefer the lean `datalox-mcp` tools: `record_trajectory` and `export_trajectories`.

When building `debugging_trajectory.v1` rows, `context.relevant_files[].before` and `after` must be exact code snippets, not prose summaries or pointers to source paths. If a row claiming `curation.quality: "use"` fails deterministic grading, Datalox records it as `needs_review` with downgrade diagnostics so it can be repaired.

Native Codex chat with MCP is guidance-only unless it explicitly calls the MCP tools. Wrapper runs such as `datalox codex` are the enforceable path because they inject guidance before the child run and record after it.

Use the pack with this model:

- source kinds: `trace`, `web`, `pdf`
- capture primitive: `agent_turn.v1`
- product event store: `.datalox/events/`
- legacy event store: `agent-wiki/events/` is read-only for future product work
- source export target: approved anonymized session bundle
- trajectory derivative target: `debugging_trajectory.v1`
- trajectory dataset rows are compact export derivatives, not repo-local knowledge page types or the complete source session

Legacy promotion rule:

- repeated local knowledge -> note
- repeated reusable workflow -> skill

Business rule:

- B2B approved session data plus derived trajectory/evals are the primary product focus
- do not keep legacy note/skill promotion as a second product loop in this repo
- existing skills/notes are legacy or internal agent-guidance surfaces until migrated
- `agent_turn.v1` events are the simple capture primitive
- new product data writes under `.datalox/`, not `agent-wiki/events/`
- approved anonymized session bundles are the source B2B data asset
- lean, outcome-labeled `debugging_trajectory.v1` rows are compact training/eval derivatives
- unapproved raw traces are not sellable data

Generate new supporting knowledge into `agent-wiki/notes/`, not legacy wiki folders.

If docs disagree on what Datalox is, `docs/product-definition.md` wins.
If docs disagree on turn capture, `docs/agent-turn-schema.md` wins.
If docs disagree on exported trajectory rows, `docs/trajectory-dataset-schema.md` wins.
