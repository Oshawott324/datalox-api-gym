---
name: maintain-datalox-api-gym
description: Use when changing the Datalox API Gym package, schemas, CLI/MCP surfaces, wrappers, docs, or project guidance in this repo.
metadata:
  datalox:
    id: repo-engineering.maintain-datalox-api-gym
    workflow: repo_engineering
    trigger: Datalox API Gym package maintenance
---

# Maintain Datalox API Gym

Use this skill when changing this repo itself.

## Workflow

1. Read `AGENTS.md`, `DATALOX.md`, and the docs named by the task.
2. Keep replay data under `.datalox/tool-io/records/`, `.datalox/events/agent-turns/`, and `.datalox/replay-bundles/`.
3. Treat trajectory rows as derivative-only until replay MCP tools land.
4. Keep schema changes deterministic and covered by focused tests.
5. Make install/adoption behavior explicit in `README.md`, `DATALOX.md`, docs, or tests.
6. Run focused tests plus `npm run check` before finishing.

## Boundaries

- Do not add a second note/skill promotion loop.
- Do not create a parallel wiki/note/event store.
- Do not infer training rows from prose when schema evidence is missing.
- Do not mark code-heavy `agent_task_trajectory.v1` rows as use-quality derivatives without exact `code_change` evidence.
- Do not present trajectory commands as the normal replay capture path.

## Good Commands

```bash
npm run check
npx vitest run tests/replayCanonicalDocs.test.ts
npx vitest run tests/adoptionScripts.test.ts
npx vitest run tests/trajectoryExport.test.ts tests/agentTaskTrajectoryExport.test.ts
node dist/src/cli/main.js status --repo . --json
```
