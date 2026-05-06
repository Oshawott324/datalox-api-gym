# Datalox Pack Copilot Instructions

This repository is the repo-local implementation package for Datalox MCP.

Product boundary:

- Datalox MCP is the product-facing instrumentation and control layer for desktop agents.
- `datalox-trajectory-mcp` provides the repo-local protocol, CLI, skills, notes, events, and adoption assets.
- B2B approved session data plus derived trajectory/evals are the primary product focus.
- Do not keep legacy note/skill promotion as a second product loop in this repo.
- Existing skills/notes are legacy or internal agent-guidance surfaces until migrated.
- `agent_turn.v1` events are the simple capture primitive.
- Approved anonymized session bundles are the source B2B data asset.
- Lean, outcome-labeled `debugging_trajectory.v1` rows are compact training/eval derivatives.

## Core Model

- `skills/<name>/SKILL.md`: canonical workflow skills
- `agent-wiki/notes/*.md`: grounded supporting notes
- `.datalox/events/*.json`: new product event evidence
- `agent-wiki/events/*.json`: legacy event evidence
- `agent-wiki/index.md`: generated map of current knowledge
- `agent-wiki/log.md`: generated change trail
- `agent-wiki/lint.md`: generated lint snapshot
- `agent-wiki/hot.md`: recent context cache

## Loop

1. read `docs/product-definition.md`
2. read `docs/agent-turn-schema.md` when session capture/export fields are involved
3. read `docs/trajectory-dataset-schema.md` when trajectory export/data fields are involved
4. record meaningful grounded events
5. use skills and linked notes only where current host guidance still requires them
6. route new product behavior through captured `agent_turn.v1` events first, assemble sessions, then derive trajectory rows when useful
7. lint the pack

When touching session capture, trajectory recording, export gates, redaction states, or dataset fields, read `docs/agent-turn-schema.md` or `docs/trajectory-dataset-schema.md` as appropriate before changing shape.

## Editing Rules

- keep skills in markdown `SKILL.md`, not JSON
- keep new product behavior in `.datalox/events/`, assembled session bundles, and derived trajectory rows
- treat `agent-wiki/notes/` as legacy/internal guidance during migration
- keep Datalox additive to native agent skills
- prefer updating the existing skill over creating duplicates
- unapproved raw traces are not sellable data
- trajectory dataset rows are export derivatives, not repo-local knowledge page types or the complete source session
- refresh `index.md`, `log.md`, `lint.md`, and `hot.md` when patching or linting
