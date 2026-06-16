# Env Data Proof v0

This handoff is a small MCP-backed agent-world seed for post-training collaboration. It is intentionally scoped to high-value domain environments only: FlowCyto (4), Molecule Biology (5), Protein MCP (3).

It does not include the old parser/report-only tasks, toy sequence task, or preview lifecycle wrappers. Those were removed because they did not demonstrate the domain-environment advantage.

## What Is Ready

- 12 active task specs under `families/*/tasks/*/task.spec.json`.
- Captured tool observations from real sibling runtimes in `tools/tool-observations.jsonl`.
- Mechanical verifier fixtures in each task's `verifier/` directory.
- Standard tool-message SFT rows in `exports/sft.tool_messages.seed.jsonl`.
- Tool-environment eval rows in `exports/eval.tool_env.seed.jsonl`.
- Split metadata in `exports/split.mcp-seed-v0.json` with 8 train, 2 dev, and 2 test tasks.

## Boundary

The verifier is not a reward model and does not judge scientific correctness. It checks that final answers cite captured tool evidence and simple workspace metadata. The post-training objective, reward design, and rollout harness remain collaborator decisions.

## First Collaborator Ask

Ask Zheng to inspect whether `exports/sft.tool_messages.seed.jsonl` and `exports/eval.tool_env.seed.jsonl` are enough for his loader/harness planning, and whether the task/world shape is worth scaling toward 80 train / 20 dev / 20 test.
