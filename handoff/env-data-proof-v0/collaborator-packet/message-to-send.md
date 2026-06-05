# Message To Send

```text
我整理了一个 Datalox Env Data Proof v0 collaborator packet。这个不是让你看
Datalox 代码，也不是 model lift claim。主要想让你判断这个 World API / MCP
adapter / trajectory shape 是否贴近你们正常的 post-training workflow。

请优先看：

1. README.md
2. one-page-context.md
3. task-cards.md
4. world-api-contract.md
5. trajectory-guide.md
6. examples/runs/*/trajectory.jsonl 和 verifier_result.json
7. exports/sft.messages.examples.jsonl
8. review-questions.md

核心问题是：

Can this kind of runnable domain world generate trajectories that are usable for
your SFT / eval / RL workflow?

我不希望你先 review 代码。appendix 里的 runnable-world/world-api 只是为了可复现和之后
对接 agent harness。最需要你判断的是：

- World API 的 reset/tools/step/finalize/export lifecycle 是否够；
- MCP adapter 是否适合你们现在的 harness；
- trajectory 里信息是否够；
- SFT messages 是否接近你们 loader；
- 如果要跑第一个 LoRA，最小需要改什么；
- dataset size 至少要多大才值得跑。
```
