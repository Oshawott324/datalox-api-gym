# Skill Schema

Skills in this branch are local agent guidance only. They are not a second
product data store and they do not link to a wiki or note promotion loop.

Each skill lives at:

```text
skills/<skill-name>/SKILL.md
```

Keep frontmatter minimal:

```yaml
---
name: maintain-datalox-api-gym
description: Use when changing the Datalox API Gym package, schemas, CLI/MCP surfaces, wrappers, docs, or product guidance in this repo.
metadata:
  datalox:
    id: repo-engineering.maintain-datalox-api-gym
    workflow: repo_engineering
    trigger: Datalox API Gym package maintenance
---
```

The body should contain the usable workflow. Durable replay evidence belongs
under `.datalox/tool-io/records/`, `.datalox/events/agent-turns/`, and
`.datalox/replay-bundles/`, not in skill frontmatter.
