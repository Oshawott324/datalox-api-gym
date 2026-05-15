# Gemini Instructions

Use this pack for product session and trajectory capture.

Read:

1. `.datalox/manifest.json`
2. `.datalox/config.json`
3. `docs/product-definition.md`
4. `docs/agent-turn-schema.md` when session capture or data sale is involved
5. `docs/trajectory-dataset-schema.md` and `docs/agent-task-trajectory-schema.md` when trajectory rows are involved

Product data belongs under `.datalox/events/`. Do not create a parallel
wiki/note/event store.

Use `record_trajectory`, `record_agent_task_trajectory`, `grade_trajectories`,
`repair_trajectory`, and export tools for dataset work.
