# Post-Training Collaborator Handoff

## Current Position

This handoff is an MCP-backed domain-world seed. Datalox owns task packaging, captured tool evidence, mechanical verifier fixtures, and export adapters. The training stack owns model choice, rollout harness, SFT/RL objective, and reward design.

## Active Data

- Tasks: 12 total.
- Families: FlowCyto (4), Molecule Biology (5), Protein MCP (3).
- Split: 8 train, 2 dev, 2 test.
- Captures: every task has `tools/tool-observations.jsonl` from a real sibling runtime.
- Verifier: every task has pass/fail fixtures; local verifier check passes for 24 fixtures.
- Exports: 12 eval rows, 8 tool-message SFT rows.

## Important Non-Claims

This is not lift-grade data. It is a handoff-validation set. A serious first training run should target at least 80 train / 20 dev / 20 test after Zheng confirms the loader/harness boundary.

The verifier is not assigning scientific reward. It only checks captured evidence references and simple workspace metadata.

## Recommended Next Step

Give Zheng the packet and ask him to run a loader dry-run on `exports/sft.tool_messages.seed.jsonl`, then decide whether the rollout harness should consume `exports/eval.tool_env.seed.jsonl` or task specs directly.
