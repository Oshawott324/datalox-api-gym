# Message To Send

```text
我整理了一个 Datalox Env Data Proof v0 collaborator packet。这个不是让你看
Datalox 代码，也不是 model lift claim。主要想让你判断这个 runnable world /
trajectory shape 是否贴近你们正常的 post-training workflow。

请优先看：

1. README.md
2. one-page-context.md
3. task-cards.md
4. trajectory-guide.md
5. examples/runs/*/trajectory.jsonl 和 verifier_result.json
6. exports/sft.messages.examples.jsonl
7. review-questions.md

核心问题是：

Can this kind of runnable domain world generate trajectories that are usable for
your SFT / eval / RL workflow?

我不希望你先 review 代码。appendix/runnable-world 只是为了可复现和之后对接 agent
harness。最需要你判断的是：

- world interface 应该是 local workspace / Python reset-step / HTTP / MCP 哪种；
- trajectory 里信息是否够；
- SFT messages 是否接近你们 loader；
- 如果要跑第一个 LoRA，最小需要改什么；
- dataset size 至少要多大才值得跑。
```

