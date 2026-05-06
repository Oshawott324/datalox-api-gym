# Gemini Instructions

Use this pack with the loop:

`detect -> use -> record -> promote -> lint`

Product boundary:

- Datalox MCP is the product-facing instrumentation and control layer.
- `datalox-trajectory-mcp` is the repo-local implementation package.
- B2B approved session data plus derived trajectory/evals are the primary product focus.
- Do not keep legacy note/skill promotion as a second product loop in this repo.
- Existing skills/notes are legacy or internal agent-guidance surfaces until migrated.
- `agent_turn.v1` events are the simple capture primitive.
- Approved anonymized session bundles are the source B2B data asset.
- Lean, outcome-labeled `debugging_trajectory.v1` rows are compact training/eval derivatives.

Read:

1. `.datalox/manifest.json`
2. `.datalox/config.json`
3. `docs/product-definition.md`
4. `docs/agent-turn-schema.md` when touching session capture, session export, or data-sale fields
5. `docs/trajectory-dataset-schema.md` when touching trajectory export or data-sale fields
6. selected skill in `skills/` only when current host guidance requires it
7. linked notes in `agent-wiki/notes/` only when current host guidance requires it

Route new product behavior through `.datalox/events/` captured `agent_turn.v1` events first, assemble sessions, then derive trajectory rows when useful.
Read `agent-wiki/events/` only as the legacy event store.
Unapproved raw traces are not sellable data.
