# Datalox Pack Copilot Instructions

This repository is the repo-local implementation package for Datalox MCP.

Product boundary:

- Datalox MCP is the product-facing instrumentation and control layer for desktop agents.
- `datalox-trajectory-mcp` provides the repo-local protocol, CLI, event capture, export, and adoption assets.
- B2B approved session data plus derived trajectory/evals are the primary product focus.
- Do not keep legacy note/skill promotion as a second product loop in this repo.
- Existing skills/notes are legacy or internal agent-guidance surfaces until migrated.
- `agent_turn.v1` events are the simple capture primitive.
- Approved anonymized session bundles are the source B2B data asset.
- Lean, outcome-labeled `debugging_trajectory.v1` rows are compact training/eval derivatives.

## Core Model

- `.datalox/events/*.json`: new product event evidence
- `.datalox/session-candidates/`: future session review candidates
- `.datalox/approvals/`: future approval/block records
- `docs/agent-turn-schema.md`: per-turn capture contract
- `docs/trajectory-dataset-schema.md`: coding/debugging row contract
- `docs/agent-task-trajectory-schema.md`: mixed-domain task row contract
- `skills/<name>/SKILL.md`: legacy optional workflow skills when present
- `agent-wiki/events/*.json`: legacy event evidence only when present
- `agent-wiki/notes/*.md`: legacy optional supporting notes when present

## Loop

1. read `docs/product-definition.md`
2. read `docs/agent-turn-schema.md` when session capture/export fields are involved
3. read `docs/trajectory-dataset-schema.md` when trajectory export/data fields are involved
4. record meaningful grounded events
5. use skills and linked notes only when this repo has explicit legacy guidance
6. route new product behavior through captured `agent_turn.v1` events first, assemble sessions, then derive trajectory rows when useful
7. lint the pack

When touching session capture, trajectory recording, export gates, redaction states, or dataset fields, read `docs/agent-turn-schema.md` or `docs/trajectory-dataset-schema.md` as appropriate before changing shape.

## Editing Rules

- keep legacy skills in markdown `SKILL.md`, not JSON
- keep new product behavior in `.datalox/events/`, assembled session bundles, and derived trajectory rows
- treat `agent-wiki/notes/` as legacy/internal guidance during migration
- keep Datalox additive to native agent skills
- prefer updating the existing skill over creating duplicates
- unapproved raw traces are not sellable data
- trajectory dataset rows are export derivatives, not repo-local knowledge page types or the complete source session
- refresh legacy `agent-wiki` indexes only when explicitly maintaining a repo that already has that legacy wiki
