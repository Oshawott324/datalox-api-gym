# One-Page Context

## Position

Datalox is testing whether scientific workflow environments can be packaged as
agent-native runnable worlds that produce trusted trajectories.

The core value is not that Datalox invents a trainer. The value is that a
training or eval team can plug an agent into a domain world, get tool
observations, submit an answer, receive deterministic verifier evidence, and
export the result into the team's existing post-training stack.

## World Contract

Conceptually, the world exposes this interface:

```text
init_task(task_id) -> task workspace
agent reads README.md / task.json / artifacts
agent calls domain tools -> tool observations
agent submits answer.json
verifier returns pass/fail + reward + check evidence
trajectory can export to system/user/assistant/tool messages
```

If your stack prefers a Gym-like or agent-runner API, the equivalent shape is:

```text
reset(task_id) -> initial prompt, tool schemas, workspace refs
step(tool_call) -> observation
finalize(answer) -> verifier result, reward
export_messages() -> system/user/assistant/tool transcript
```

## Current Scope

This packet has two preview tasks:

- FASTQ QC failure triage.
- Molecule primer validation.

Each task has one passing and one failing precomputed trajectory. The examples
are intentionally small. They prove interface shape and verifier behavior, not
model improvement.

## The Ask

Please decide whether this is close enough to your normal post-training
workflow to justify a larger 30/10/10 or 80/20/20 dataset build.

The most useful feedback is:

- preferred environment API shape;
- whether the trajectory has enough information for SFT and eval;
- whether the SFT messages match your loader expectations;
- minimum dataset size before training;
- blockers before you would run the first trainable open-weight model.

