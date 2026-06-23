# Research Environment Factory

This playbook turns practical research workflows into API Gym worlds.

The goal is not to create another text benchmark. A research environment must
make an agent operate stateful scientific software through tools, receive
environment feedback, repair failures, and leave evidence that a verifier can
check from world state.

## Product Rule

Build research environments, not device-command demos.

Bad center of gravity:

```text
agent can aspirate and dispense
```

Good center of gravity:

```text
agent can complete a dose-response assay workflow with plate design,
dry-run execution, readout QC, curve result, repair, and evidence
```

The substrate can be PyLabRobot, a scheduler, SiLA-like drivers, fixture data,
or a deterministic simulator. The environment owns the task, state, action
surface, observations, verifier, and evidence export.

## Task-To-Environment Shape

Every candidate workflow must declare:

- practical research value
- target users
- non-toy signals
- source-backed substrates
- dry-run/live boundary
- state model
- agent-visible action surface
- observations and repairable errors
- hidden verifier checks
- evidence exports
- scenarios

Use:

```bash
api-gym world-blueprint validate blueprints/research/dose_response_assay_env_v0.json
```

Then scaffold a non-registered world package:

```bash
api-gym world-blueprint scaffold \
  blueprints/research/dose_response_assay_env_v0.json \
  --out-root .
```

The scaffold writes:

```text
worlds/<world>/
  spec.json
  README.md
  source_refs.json
  policies/environment-contract.md
  tasks/<scenario>.json

api_gym/worlds/<world>/
  __init__.py
  README.md
```

Do not register the world until sampler, state, tools, services, verifier, and
tests exist.

## Selection Bar

A workflow is worth turning into an environment when at least three are true:

- a real researcher would recognize the workflow as useful
- the workflow has a measurable scientific or operational endpoint
- mistakes are costly, slow, or risky to discover live
- the agent must inspect and mutate state, not only write an answer
- the verifier can check world state without reading the transcript
- failures can be repaired through structured tool feedback
- run evidence would be useful for audit, eval, or training

If the workflow is only a device primitive, keep it as a substrate test. Do not
market it as a flagship environment.

## PyLabRobot And Scheduler Rule

PyLabRobot is a useful open reference substrate. It supplies Python APIs,
resource serialization, tracker state, visualizer state, and dry-run/simulator
paths.

Schedulers are the commercial integration target when a lab already has device
orchestration. Do not force a universal lab action JSON shape. Each environment
can expose task-specific tools backed by the native scheduler or PyLabRobot
binding.

The stable API Gym loop is:

```text
reset -> observe -> act through tools -> mutate world state -> verify -> export evidence
```

The variable part is the domain tool payload.

## First Practical Family

Start with assay environments because they are more valuable than generic
liquid-handling environments:

- dose-response assay
- ELISA assay
- NGS library prep
- plate-based QC workflow

For each one, model the research workflow end to end:

- design intent
- samples and controls
- deck/labware state
- dry-run execution
- measurement fixture
- QC
- scientific result
- final report
- run evidence

## Implementation Rule

Each environment should be small enough to test locally and real enough to
matter.

Prefer deterministic, file-system or SQLite state first. Add a real scheduler
binding only when a concrete partner workflow exists and the live boundary is
explicit.
