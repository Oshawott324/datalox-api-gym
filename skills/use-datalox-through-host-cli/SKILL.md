---
name: use-datalox-through-host-cli
description: Use when an agent host has no enforced Datalox wrapper path, or when MCP/native tool surfaces are available but still model-chosen.
metadata:
  datalox:
    id: repo-engineering.use-datalox-through-host-cli
    workflow: agent_integration
    trigger: Host cannot enforce Datalox MCP calls automatically
---

# Use Datalox Through Host CLI

Use this skill when you need to record Datalox replay data from a host that did
not expose MCP tools directly.

## Workflow

1. Prefer MCP tools when they are callable:
   - `record_trajectory`
   - `record_agent_task_trajectory`
   - `grade_trajectories`
   - `repair_trajectory`
   - export tools
2. If MCP is not callable, use the host CLI:
   - `datalox record-trajectory --repo . --trajectory-row row.json --json`
   - `datalox record-agent-task-trajectory --repo . --agent-task-trajectory row.json --json`
   - `datalox grade-trajectories --repo . --json`
3. For Codex/Claude wrapper flows, prefer:
   - `datalox codex ...`
   - `datalox claude ...`
   - `datalox wrap command ... __DATALOX_PROMPT__`
4. The default wrapper post-run mode is `trajectory`; it records only explicit row markers:

```text
DATALOX_TRAJECTORY_ROW_FILE: .datalox/trajectory-rows/<stable-id>.json
```

## Boundaries

- Do not record replay data through removed legacy write commands.
- Do not create a parallel wiki/note/event store.
- Do not mark a trajectory row `quality: "use"` unless the row has enough concrete evidence for deterministic grading.
- For code-heavy mixed-domain rows, include exact `code_change` evidence blocks.

## Final Response

State whether capture used MCP, CLI, or wrapper recording. Mention the event path
under `.datalox/events/...` when one was created.
