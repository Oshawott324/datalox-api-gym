# Project Overview

The canonical product definition lives in [product-definition.md](./product-definition.md).
The canonical dataset export schema lives in [trajectory-dataset-schema.md](./trajectory-dataset-schema.md).
The filesystem-backed orchestration protocol lives in [task-orchestration.md](./task-orchestration.md).

Short version:

- Datalox Trajectory Data is the primary B2B dataset/eval product.
- Datalox MCP is the instrumentation, capture, labeling, verification, and export-control layer.
- `datalox-pack` is the repo-local implementation package.
- Existing skills and notes are legacy or internal guidance surfaces, not a second product loop.

Primary product loop:

```text
agent run -> structured event -> verified trajectory row -> curated dataset/eval corpus
```

Do not model this repo around legacy note/skill promotion. New product work should route through structured events and trajectory rows.

The repo is centered on:

- `agent-wiki/events/`
- `docs/trajectory-dataset-schema.md`
- legacy/internal `skills/` and `agent-wiki/notes/` only where current host guidance still requires them

Normal read path:

1. read the product definition
2. read the trajectory schema when export/data fields are involved
3. record meaningful grounded events
4. use existing skill/note guidance only where current host behavior still requires it

Current source kinds:

- `trace`
- `web`
- `pdf`

Current durable local outputs:

- `skill`
- `note`

Trajectory dataset rows are export artifacts, not new repo-local knowledge page types. Use `debugging_trajectory.v1` from [trajectory-dataset-schema.md](./trajectory-dataset-schema.md). Do not add new product behavior to local note/skill promotion.

Avoid expanding taxonomy unless real usage proves another generated page type is necessary.
