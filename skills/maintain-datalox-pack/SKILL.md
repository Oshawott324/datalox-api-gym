---
name: maintain-datalox-pack
description: Use when changing the Datalox pack or agent guidance in this repo. Keep Datalox additive to the agent's native skills and keep the pack loop minimal.
metadata:
  datalox:
    id: repo-engineering.maintain-datalox-pack
    workflow: repo_engineering
    trigger: Use when changing the Datalox pack or agent guidance in this repo.
    note_paths:
      - agent-wiki/notes/maintain-datalox-pack.md
      - agent-wiki/notes/repo-engineering-multi-agent-bootstrap-surfaces.md
    tags:
      - repo_engineering
      - portable_pack
      - agent_experience
      - knowledge_runtime
    status: approved
    author: yifanjin
    updated_at: 2026-04-12T10:31:16.869Z
    repo_hints:
      files:
        - AGENTS.md
        - CLAUDE.md
        - README.md
        - package.json
      path_prefixes:
        - skills/
        - .datalox/
        - scripts/
        - docs/
      package_signals:
        - vitest
        - datalox-pack
---

# Maintain Datalox Pack

Use this skill when changing the Datalox pack itself, its instruction surfaces, or its adoption flow.

## When to Use

- Editing `DATALOX.md`, `README.md`, `AGENTS.md`, `CLAUDE.md`, or `docs/agent-configuration.md`
- Changing how skills, notes, or control artifacts are written
- Changing bootstrap, adoption, or multi-agent discovery behavior
- Changing scripts under `scripts/` that implement detect, use, patch, or lint

## When Not to Use

- Backend/runtime service work that belongs in `datalox-knowledge-service`
- Generic coding tasks that do not change pack behavior
- Pure content edits to unrelated example files

## Workflow

1. Confirm the change is really about the Datalox pack and not the backend service.
2. Read linked notes before editing behavior or instructions when those note files exist.
3. Preserve the minimal loop: detect -> use -> patch -> lint.
4. Keep Datalox additive to the agent's native skills. Do not replace or shadow built-in skill behavior.
5. Keep writes in the host repo. Seed knowledge can be read from the pack, but generated skills and notes belong in the host repo.
6. When changing adoption or control behavior, update the visible artifacts and instruction surfaces together.

## Checks Before Editing

- Keep skill bodies operational, not metadata-heavy.
- Prefer plain markdown skills and notes over extra configuration layers.
- Make the benefit visible in `DATALOX.md`, `AGENTS.md`, `README.md`, docs, or tests. Use `agent-wiki/` only for explicit legacy compatibility work.
- Avoid pack-only abstractions that another agent cannot discover from the repo.

## Expected Output

- Explain why this skill matched.
- State the concrete pack behavior you are changing.
- State which instruction files, skill files, or notes were updated.
- State whether detect, use, patch, and lint still form a coherent loop.

## Notes

- agent-wiki/notes/maintain-datalox-pack.md
- agent-wiki/notes/repo-engineering-multi-agent-bootstrap-surfaces.md
