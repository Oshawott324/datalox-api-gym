# Wiki Instructions

This repo uses a session-first data product model:

- `.datalox/events/` for new product capture evidence
- `agent-wiki/events/` for legacy event evidence only
- `docs/agent-turn-schema.md` for simple per-turn capture shape
- `docs/trajectory-dataset-schema.md` for compact derived row shape
- `skills/` and `agent-wiki/notes/` only as legacy/internal guidance surfaces during migration

For product work, route new behavior through captured `agent_turn.v1` events first, assemble approved sessions, then derive trajectory rows when useful.

Legacy folders may still exist in older repos, but do not add new product behavior to them.

Product boundary:

- Datalox MCP is the product-facing instrumentation, session capture, and control layer.
- B2B approved session data plus derived trajectory/evals are the primary product focus.
- Do not keep legacy note/skill promotion as a second product loop in this repo.
- Existing skills/notes are legacy or internal agent-guidance surfaces until migrated.
- `agent_turn.v1` events are the simple capture primitive.
- Approved anonymized session bundles are the source B2B data asset.
- Lean, outcome-labeled `debugging_trajectory.v1` rows are compact training/eval derivatives.

For session capture fields, read `docs/agent-turn-schema.md`. For trajectory export fields, read `docs/trajectory-dataset-schema.md`. Unapproved raw traces are not sellable data.
