---
name: maintain-datalox-agent-replay
description: Use when changing the Datalox Agent Replay package, schemas, CLI/MCP surfaces, wrappers, docs, or product guidance in this repo.
metadata:
  datalox:
    id: repo-engineering.maintain-datalox-agent-replay
    workflow: repo_engineering
    trigger: Datalox Agent Replay package maintenance
---

# Maintain Datalox Agent Replay

Use this skill when changing this repo itself.

## Workflow

1. Read `AGENTS.md`, `DATALOX.md`, and the docs named by the task.
2. Keep product data under `.datalox/events/`.
3. Prefer the lean MCP tools for dataset work:
   - `record_trajectory`
   - `record_agent_task_trajectory`
   - `grade_trajectories`
   - `repair_trajectory`
   - export tools
4. Keep schema changes deterministic and covered by focused tests.
5. Make install/adoption behavior explicit in `README.md`, `DATALOX.md`, docs, or tests.
6. Run focused tests plus `npm run check` before finishing.

## Boundaries

- Do not add a second note/skill promotion product loop.
- Do not create a parallel wiki/note/event store.
- Do not infer training rows from prose when schema evidence is missing.
- Do not mark code-heavy `agent_task_trajectory.v1` rows as buyer-ready without exact `code_change` evidence.

## Good Commands

```bash
npm run check
npx vitest run tests/adoptionScripts.test.ts
npx vitest run tests/trajectoryExport.test.ts tests/agentTaskTrajectoryExport.test.ts
node dist/src/cli/main.js status --repo . --json
```
