# Datalox Pack Rules

This repo is the repo-local implementation package for Datalox Trajectory MCP.

Product boundary:

- Datalox MCP is the product-facing instrumentation and control layer for desktop agents.
- `datalox-trajectory-mcp` provides repo-local CLI, skills, notes, events, and adoption assets.
- B2B trajectory data/evals are the primary product focus.
- Do not keep legacy note/skill promotion as a second product loop in this repo.
- Existing skills/notes are legacy or internal agent-guidance surfaces until migrated.
- Lean, outcome-labeled `debugging_trajectory.v1` rows are the dataset/eval export product.

Read:

1. `.datalox/manifest.json`
2. `.datalox/config.json`
3. `docs/product-definition.md`
4. `docs/trajectory-dataset-schema.md` when touching trajectory export or data-sale fields
5. `DATALOX.md`

Then use the loop:

`detect -> use -> record -> promote -> lint`

Keep these files current:

- `agent-wiki/index.md`
- `agent-wiki/log.md`
- `agent-wiki/lint.md`
- `agent-wiki/hot.md`

Raw traces are not sellable data. Trajectory dataset rows are export artifacts, not repo-local knowledge page types.

Do not replace native Windsurf or Cascade skills. Datalox is additive.
