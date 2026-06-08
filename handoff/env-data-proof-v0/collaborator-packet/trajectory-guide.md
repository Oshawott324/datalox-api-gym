# Trajectory Guide

The handoff uses captured tool observations, not hand-written final-answer records. Each active task has:

- `task.spec.json`: prompt, allowed tools, source reference, and success criteria.
- `tools/tool-observations.jsonl`: captured agent-visible tool outputs from the real sibling domain runtime.
- `verifier/verifier.spec.json`: mechanical evidence gate requiring captured `tool_io:*` ids and simple workspace metadata.
- `verifier/expected.pass.json` and `expected.fail.json`: positive/negative fixtures for loader and verifier checks.

Training-facing exports:

- `exports/sft.tool_messages.seed.jsonl`: standard system/user/assistant/tool messages for the train split.
- `exports/eval.tool_env.seed.jsonl`: tool-environment eval rows without preloaded observations.
- `exports/eval.seed.jsonl`: context-eval rows with observation context preloaded.

The split is `exports/split.mcp-seed-v0.json`: 8 train, 2 dev, 2 test. It validates the handoff shape; it is not enough to claim model lift.
