# LabLongRun Projection And Stochasticity Plan

This note reframes LabLongRun from a simulator into a controlled projection of a
live scientific workflow.

The benchmark should not claim:

```text
we simulate a real lab
```

It should claim:

```text
we construct a controlled dry-run projection of a costly scientific workflow,
with documented structural, semantic, temporal, and stochastic assumptions.
```

This is the deeper long-horizon direction.

## Why Projection Matters

A useful agent environment is not just a sandbox. It is a projection of a live
system into a resettable training/evaluation world.

For a lab/protein workflow, the live system may include:

- API contracts
- task files
- inventory state
- experiment lifecycle
- quote/budget state
- instrument or provider delays
- partial results
- measurement noise
- failures and retries
- final result interpretation

The projection decides which of these are preserved, simplified, or omitted.
If the projection differs from the live system in undocumented ways, agent
rollouts and rewards optimize the wrong world.

## Projection Contract

Every serious world should ship a projection contract:

```text
projection_contract.md
```

It should state:

1. **Source system**
   - What live workflow, API, package, protocol, or public dataset is being
     projected?

2. **Structural projection**
   - Which entities exist?
   - Example: target, sequence batch, quote, experiment, result, well, tip,
     plate, readout.

3. **Action projection**
   - Which actions/tools preserve real semantics?
   - Which actions are benchmark-local?

4. **State projection**
   - Which mutable state is tracked?
   - Which state is hidden from the agent?

5. **Temporal projection**
   - What delays, lifecycle states, stale reads, and waiting rules are modeled?

6. **Stochastic projection**
   - What randomness/noise/faults exist?
   - What is the source or assumption behind each distribution?

7. **Safety projection**
   - Which live side effects are forbidden or dry-run only?

8. **Verifier projection**
   - What final-state, temporal, provenance, resource, and recovery invariants
     are checked?

9. **Known gaps**
   - What is intentionally not modeled?

This contract is more important than a pretty simulator. It lets reviewers and
users understand exactly what kind of world the agent was optimized in.

## Multi-Provider Projection Update

For the next build, the projection object is no longer only a wet-lab robot
procedure. It is a lab operations workflow that may span several
provider-shaped systems:

```text
ELN/LIMS request state
  + robot/protocol dry-run state
  + instrument/context data state
  + result upload or decision state
```

This means the projection contract must document cross-provider assumptions:

- how sample ids map to robot plate positions
- how robot protocol analysis maps to downstream run/readout records
- how instrument records map to assay/result uploads
- which records are current versus stale
- which writes are allowed in the sandbox
- which live provider or hardware actions are forbidden

The verifier should check these cross-system invariants directly. A task should
not pass just because each individual provider-shaped API call looks valid.

## Stochasticity Should Be Documented, Not Decorative

Do not add random noise just to make tasks feel realistic.

Stochasticity is allowed only when it has a stated role:

- measurement uncertainty
- provider/instrument delay
- retryable tool failure
- partial result arrival
- quote/cost variability
- low-quality result record
- transient permission/rate-limit issue
- environment fault requiring recovery

Each stochastic element should declare:

```text
name:
source_status:
  source_grounded | partner_reported | domain_reviewed | assumption_for_calibration
distribution:
seed_behavior:
agent_visible_observation:
hidden_truth:
verifier_effect:
attribution_label:
```

Example:

```text
name: od600_measurement_noise
source_status: assumption_for_calibration
distribution: normal(mean=true_od600, sd=0.03), clipped at 0
seed_behavior: deterministic per task seed and readout id
agent_visible_observation: observed OD600 value
hidden_truth: true OD600 and sampled error
verifier_effect: check whether agent handles borderline readings correctly
attribution_label: environment_noise
```

For Adaptyv:

```text
name: result_arrival_delay
source_status: source_grounded_or_partner_reported
distribution: status transition schedule over campaign lifecycle
seed_behavior: deterministic per campaign seed
agent_visible_observation: partial/final result status
hidden_truth: full result fixture and arrival schedule
verifier_effect: catch partial-results-as-final decisions
attribution_label: environment_timing
```

## Seeded Replay Is Mandatory

Stochastic projection must be replayable.

Every generated task should include:

```text
environment_seed
noise_schedule.json
fault_schedule.json
result_arrival_schedule.json
```

The same task, same seed, and same agent trajectory should produce the same
observations. Otherwise we cannot compare agents or debug failures.

The runtime should support:

```text
same initial state
same environment seed
same fault/noise/result schedule
replay trajectory
verify same outcome
```

This is what lets us separate:

- the agent made a bad decision
- the environment produced a bad/noisy observation
- the agent failed to recover from an expected fault
- the task was underspecified or unfair

## Failure Attribution

The verifier result should not only say pass/fail. For stochastic worlds, it
should classify failure source:

```text
agent_error
environment_fault
environment_noise
agent_recovery_failure
ambiguous
success_despite_fault
task_invalid
```

Examples:

- Agent ignores an `OVERDRAW_SOURCE_WELL` error and keeps going:
  `agent_recovery_failure`
- Readout is noisy but within documented uncertainty and agent makes an
  unsupported confident decision:
  `agent_error`
- Instrument fault prevents any valid read and the verifier expects a hold or
  escalation:
  `environment_fault`
- Agent reads partial Adaptyv results as final:
  `agent_error` or `agent_recovery_failure`, depending on whether the tool
  reported partial status clearly.

## What This Means For LabLongRun-Wet

For the current OD600/liquid-handling calibration world, do not scale
stochasticity broadly yet.

Add only one or two documented stochastic dimensions:

1. OD600 readout noise.
2. Instrument busy/read retry fault.

Both should be seeded and recorded.

Do not ask Zheng to invent realistic biology distributions. Zheng can implement
the stochastic infrastructure; distribution choices need source status:

```text
assumption_for_calibration
source_grounded
domain_reviewed
partner_reported
```

If a distribution is only an assumption, mark it as calibration-only and do not
count it as a paper-scale scientific task until reviewed.

## What This Means For Adaptyv

Adaptyv is potentially a better projection target than OT-2 deck simulation.

The projection object would be:

```text
protein design campaign
  target
  candidate sequences
  budget/quote
  submission lifecycle
  partial/final results
  interpretation decision
```

The important stochastic/temporal dimensions are not pipette physics. They are:

- quote/cost variability
- experiment lifecycle delay
- partial result availability
- noisy or low-confidence result records
- failed/cancelled experiment status
- stale prior campaign results

This may produce a deeper long-horizon benchmark because the agent must manage
planning under delayed and uncertain feedback, which is closer to real
scientific campaign work.

But the same gate still applies: do not build this until Adaptyv/customer
qualification confirms the pain.

## Next Engineering Step

Add projection fields to template/admission metadata:

```text
projection_contract_ref
domain_source_status
stochastic_source_status
environment_seed
fault_schedule_ref
noise_schedule_ref
expected_failure_codes
attribution_labels
```

Then admission should check:

- stochastic schedules are deterministic under seed
- oracle passes under the sampled schedule
- matched known-bad plan fails for the expected reason
- failure attribution label matches the template claim
- calibration-only stochastic assumptions are not mislabeled as source-grounded

This makes projection and stochasticity part of task quality control, not a
loose implementation detail.
