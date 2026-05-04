# Datalox Pack Copilot Instructions

This repository is the repo-local implementation package for Datalox MCP.

Product boundary:

- Datalox MCP is the product-facing instrumentation and control layer for desktop agents.
- `datalox-trajectory-mcp` provides the repo-local protocol, CLI, skills, notes, events, and adoption assets.
- B2B trajectory data/evals are the primary product focus.
- Do not keep legacy note/skill promotion as a second product loop in this repo.
- Existing skills/notes are legacy or internal agent-guidance surfaces until migrated.
- Lean, outcome-labeled `debugging_trajectory.v1` rows are the dataset/eval export product.

## Core Model

- `skills/<name>/SKILL.md`: canonical workflow skills
- `agent-wiki/notes/*.md`: grounded supporting notes
- `agent-wiki/events/*.json`: grounded event evidence
- `agent-wiki/index.md`: generated map of current knowledge
- `agent-wiki/log.md`: generated change trail
- `agent-wiki/lint.md`: generated lint snapshot
- `agent-wiki/hot.md`: recent context cache

## Loop

1. read `docs/product-definition.md`
2. read `docs/trajectory-dataset-schema.md` when export/data fields are involved
3. record meaningful grounded events
4. use skills and linked notes only where current host guidance still requires them
5. route new product behavior through structured events and trajectory rows
6. lint the pack

When touching trajectory recording, export gates, redaction states, or dataset fields, read `docs/trajectory-dataset-schema.md` first.

## Editing Rules

- keep skills in markdown `SKILL.md`, not JSON
- keep new product behavior in structured events and trajectory rows
- treat `agent-wiki/notes/` as legacy/internal guidance during migration
- keep Datalox additive to native agent skills
- prefer updating the existing skill over creating duplicates
- raw traces are not sellable data
- trajectory dataset rows are export artifacts, not repo-local knowledge page types
- refresh `index.md`, `log.md`, `lint.md`, and `hot.md` when patching or linting
