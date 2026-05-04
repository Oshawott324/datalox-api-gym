# Wiki Instructions

This repo uses a trajectory-export product model:

- `agent-wiki/events/` for grounded evidence
- `docs/trajectory-dataset-schema.md` for exported row shape
- `skills/` and `agent-wiki/notes/` only as legacy/internal guidance surfaces during migration

For product work, route new behavior through structured events and trajectory rows.

Legacy folders may still exist in older repos, but do not add new product behavior to them.

Product boundary:

- Datalox MCP is the product-facing instrumentation and control layer.
- B2B trajectory data/evals are the primary product focus.
- Do not keep legacy note/skill promotion as a second product loop in this repo.
- Existing skills/notes are legacy or internal agent-guidance surfaces until migrated.
- Lean, outcome-labeled `debugging_trajectory.v1` rows are the dataset/eval export product.

For trajectory export fields, read `docs/trajectory-dataset-schema.md`. Raw traces are not sellable data.
