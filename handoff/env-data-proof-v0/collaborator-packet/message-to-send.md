Here is the cleaned v0 handoff. I removed the old parser/toy rows and preview lifecycle wrappers.

The active packet is 12 MCP-backed domain tasks: FlowCyto, Molecule Biology, and Protein MCP. It includes captured tool observations, mechanical verifier fixtures, tool-message SFT rows, and tool-env eval rows.

Main files to inspect:

1. collaborator-packet/one-page-context.md
2. collaborator-packet/task-cards.md
3. collaborator-packet/trajectory-guide.md
4. collaborator-packet/review-questions.md
5. exports/sft.tool_messages.seed.jsonl
6. exports/eval.tool_env.seed.jsonl

The main question is not whether our schema is perfect. The question is whether this world/task shape is useful enough for your SFT/rollout workflow, and what exact converter or harness boundary you would want before we scale toward 80/20/20.
