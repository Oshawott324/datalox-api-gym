# Review Questions

1. Are the tool-message rows in `exports/sft.tool_messages.seed.jsonl` close enough to your normal SFT loader shape? If not, what exact fields should the converter add or remove?
2. For rollout/eval, do you want `exports/eval.tool_env.seed.jsonl` plus the task specs, or would you rather consume task specs directly and let your harness build prompts/tools?
3. Is this task/world mix worth scaling, or should we change the domain mix before collecting 80/20/20?
4. Which open-weight model under 3B would you use first, and what is the cheapest run you would trust as a loader/harness check?
5. Which artifacts should we recapture from public pinned sources before any public Hugging Face release claim?
