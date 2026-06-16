# One-Page Context for Zheng

We changed the handoff after your feedback. The active artifact is no longer a schema-first or parser-task packet. It is a small set of domain MCP worlds with captured tool observations.

## What This Contains

- 12 MCP-backed tasks: FlowCyto (4), Molecule Biology (5), Protein MCP (3).
- 8/2/2 train/dev/test split for handoff validation.
- Real captured tool outputs from FlowCyto, Molecule Biology, and Protein MCP sibling runtimes.
- Standard `system/user/assistant/tool` SFT rows in `exports/sft.tool_messages.seed.jsonl`.
- Tool-env eval rows in `exports/eval.tool_env.seed.jsonl`.

## What It Does Not Claim

- It does not claim model lift. The split is too small.
- It does not assign reward for scientific correctness.
- It does not ask you to adopt a new schema as the main point.
- It does not include the old parser/report-only or toy sequence rows.

## Why It May Be Useful

The useful question is whether a model+harness can interact with resettable domain tools and produce trajectories dense enough for SFT/RL planning. This packet gives you the first runnable evidence shape without asking you to review code first.
