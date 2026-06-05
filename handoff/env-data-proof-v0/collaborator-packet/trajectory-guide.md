# Trajectory Guide

## Example Runs

| Run directory | Task | Expected verifier result | Reward | Trajectory events |
| --- | --- | ---: | ---: | ---: |
| `examples/runs/fastq-pass/` | FASTQ QC | pass | 1 | 6 |
| `examples/runs/fastq-fail/` | FASTQ QC | fail | 0 | 6 |
| `examples/runs/molecule-pass/` | Molecule primer | pass | 1 | 6 |
| `examples/runs/molecule-fail/` | Molecule primer | fail | 0 | 6 |

Each run directory contains:

- `run.json`: task id, world id, and output paths.
- `trajectory.jsonl`: initialized task, tool calls, observations, and final
  submission.
- `answer.json`: the submitted structured answer.
- `verifier_result.json`: deterministic checks, pass/fail, and reward.
- `workspace/`: the task workspace used during the run.

## What To Inspect

For SFT shape, start with:

```text
exports/sft.messages.examples.jsonl
```

It contains two passing rows, one per task, in a standard
system/user/assistant/tool message shape.

The system prompt now includes the environment tool catalog and a
task-relevant tool subset with JSON input schemas. This follows the feedback
that the MCP service is environment-level and task relevance should be carried
by the prompt.

For environment or RL shape, inspect:

```text
examples/runs/fastq-pass/trajectory.jsonl
examples/runs/molecule-pass/trajectory.jsonl
```

The important question is whether this trajectory has enough information for
your rollout/debug/eval loop:

- task prompt;
- tool call names and arguments;
- tool observations;
- evidence ids;
- final answer;
- verifier checks;
- reward.

## Known Limitation

The example trajectories are oracle-driven for packet review. They are not yet
fresh model rollouts. The next phase should plug a real agent harness into the
same world contract and collect model-generated successes and failures.
