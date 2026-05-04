# Agent Instructions

Read in this order:

1. `.datalox/manifest.json`
2. `.datalox/config.json`
3. `docs/product-definition.md`
4. `docs/trajectory-dataset-schema.md` when the task touches trajectory recording, export, or data sale
5. `agent-wiki/hot.md` when it exists
6. the selected `skills/<name>/SKILL.md`
7. the linked notes in `metadata.datalox.note_paths`

If legacy full-pack MCP tools are available, call `resolve_loop` before internal Datalox maintenance work and use the matched skill plus linked notes before acting. For trajectory dataset work, prefer the lean `datalox-mcp` tools: `record_trajectory` and `export_trajectories`.

Native Codex chat with MCP is guidance-only unless it explicitly calls the MCP tools. Wrapper runs such as `datalox codex` are the enforceable path because they inject guidance before the child run and record after it.

Use the pack with this model:

- source kinds: `trace`, `web`, `pdf`
- product export target: `debugging_trajectory.v1`
- trajectory dataset rows are export artifacts, not repo-local knowledge page types

Legacy promotion rule:

- repeated local knowledge -> note
- repeated reusable workflow -> skill

Business rule:

- B2B trajectory data/evals are the primary product focus
- do not keep legacy note/skill promotion as a second product loop in this repo
- existing skills/notes are legacy or internal agent-guidance surfaces until migrated
- lean, outcome-labeled `debugging_trajectory.v1` rows are the dataset/eval product
- raw traces are not sellable data

Generate new supporting knowledge into `agent-wiki/notes/`, not legacy wiki folders.

If docs disagree on what Datalox is, `docs/product-definition.md` wins.
If docs disagree on exported trajectory rows, `docs/trajectory-dataset-schema.md` wins.
