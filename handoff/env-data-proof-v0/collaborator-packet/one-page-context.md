# One-Page Context

## Position

Datalox is testing whether scientific workflow environments can be packaged as
agent-native runnable worlds that produce trusted trajectories.

The core value is not that Datalox invents a trainer. The value is that a
training or eval team can plug an agent into a domain world, get tool
observations, submit an answer, receive deterministic verifier evidence, and
export the result into the team's existing post-training stack.

## World Contract

Conceptually, the world exposes this lifecycle:

```text
init_task(task_id) -> task workspace
agent reads README.md / task.json / artifacts
agent calls domain tools -> tool observations
agent submits answer.json
verifier returns pass/fail + reward + check evidence
trajectory can export to system/user/assistant/tool messages
```

The implementation exposes this lifecycle as a small World API:

```text
reset(task_id) -> initial prompt, tool schemas, workspace refs
step(tool_call) -> observation
finalize(answer) -> verifier result, reward
export_messages() -> system/user/assistant/tool transcript
```

MCP is the first adapter because your current stack mainly uses MCP. The
important distinction is:

```text
MCP = tool transport
World API = episode lifecycle for rollout / eval / training extraction
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
workflow to justify an 80/20/20 dataset build.

The most useful feedback is:

- preferred environment API shape;
- whether the trajectory has enough information for SFT and eval;
- whether the SFT messages match your loader expectations;
- whether the World API + MCP adapter fits your current harness;
- minimum dataset size before training;
- blockers before you would run the first trainable open-weight model.
