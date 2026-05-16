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
name: maintain-datalox-agent-replay
description: Use when changing the Datalox Agent Replay package, schemas, CLI/MCP surfaces, wrappers, docs, or product guidance in this repo.
metadata:
  datalox:
    id: repo-engineering.maintain-datalox-agent-replay
    workflow: repo_engineering
    trigger: Datalox Agent Replay package maintenance
---
```

The body should contain the usable workflow. Durable product evidence belongs
under `.datalox/events/`, not in skill frontmatter.
