# Gemini Instructions

Use this pack with the loop:

`detect -> use -> record -> promote -> lint`

Product boundary:

- Datalox MCP is the product-facing instrumentation and control layer.
- `datalox-trajectory-mcp` is the repo-local implementation package.
- B2B trajectory data/evals are the primary product focus.
- Do not keep legacy note/skill promotion as a second product loop in this repo.
- Existing skills/notes are legacy or internal agent-guidance surfaces until migrated.
- Lean, outcome-labeled `debugging_trajectory.v1` rows are the dataset/eval export product.

Read:

1. `.datalox/manifest.json`
2. `.datalox/config.json`
3. `docs/product-definition.md`
4. `docs/trajectory-dataset-schema.md` when touching trajectory export or data-sale fields
5. selected skill in `skills/` only when current host guidance requires it
6. linked notes in `agent-wiki/notes/` only when current host guidance requires it

Route new product behavior through structured events and trajectory rows.
Raw traces are not sellable data.
