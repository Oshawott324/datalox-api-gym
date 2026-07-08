# LabLongRun Strict Admission: Current State and Next Actions

Date: 2026-07-08
Branch: `codex/strict-admission`
Base: `origin/unitelabs-api-grounding-wz`

This note summarizes what the current branch proves, what it does not prove,
and what we should build next if the goal is a serious scalable benchmark rather
than a toy demo.

The useful review focus is benchmark and training depth: whether this
environment would produce credible evaluation or training signal for
long-horizon lab agents, and what evidence would make it comparable to recent
agent-environment papers.

## Current State

Phase 0 now has a strict admission gate for a small but concrete lab slice,
plus one deeper fault-recovery family.

The gate runs through the public world runtime surface:

```text
sample_episode -> dispatch_tool calls -> verify_run
```

It does not inspect hidden mutable state directly from the admission harness.

Current strict suite:

```text
8 scenarios
36 admission cases
```

Covered worlds:

```text
pylabrobot_lab_v0
pylabrobot_star_v0
```

Covered scenario types:

```text
plate transfer decision
stale/provenance read-before-transfer
limited tips refusal
low reagent refusal
STAR 96-head insufficient tips refusal
STAR instrument busy fault recovery
```

Each strict scenario now includes at least:

```text
oracle pass
empty plan fail
known-bad or resource/provenance mutant fail
exact expected failure-code set match
```

Resource-refusal scenarios now reject arbitrary notes. A valid refusal must include a structured JSON workflow note with:

```json
{
  "decision": "refuse",
  "reason_code": "...",
  "evidence": {}
}
```

The verifier also checks relevant visible evidence:

```text
inspection.labware
error.tip_not_available
error.insufficient_well_volume
tips96.picked_up
single-channel workaround events
successful transfer-before-refusal events
```

## What This Proves

This branch proves that the verifier is no longer accepting the most obvious fake completions for the current admission slice.

Examples now caught:

```text
do nothing
write arbitrary "done" note
read before transfer and submit stale evidence
attempt unavailable tip usage
attempt low-reagent overdraw
partially transfer low reagent before refusing
attempt 96-head pickup with fewer than 96 tips
attempt single-channel workaround in a 96-head refusal task
failed single-channel tip pickup workaround
busy instrument error then giving up
using a pre-transfer readout after recovery
wrong final decision after a valid recovered readout
extra successful readout after recovery
```

The important shift is that the admission gate is now testing verifier validity, not only task sampling.

`scripts/package_benchmark.py --verify-all` now runs strict admission and fails the command if strict admission fails.

## What This Does Not Prove

This is not yet a scalable benchmark.

It does not prove:

```text
all STAR scenarios are admission-safe
all lab scenarios have oracle/mutant coverage
fault recovery is covered across multiple families
stochastic dynamics are covered across multiple families
task generation can scale to 1,000 tasks
mutants can be generated rather than hand-authored
verifier checks are grounded across many scenario families
biology-specific realism is enough for a paper
```

The current suite still uses hand-written runners. That is acceptable for Phase 0
because the goal is to prove the verifier can reject known bad behavior. It is
not acceptable as the long-term scaling strategy.

## Bar From Recent Env/Gym Benchmarks

The standard we need to match is not "a demo with a verifier." Recent serious
agent environments have a recognizable shape:

- AppWorld: a controllable execution environment with 9 apps, 457 APIs, 750
  tasks, and state-based unit tests that also check unexpected collateral
  changes. Reference: https://arxiv.org/abs/2407.18901
- ToolSandbox: stateful tool execution, implicit state dependencies, user
  simulation, and dynamic evaluation over intermediate and final milestones.
  Reference: https://aclanthology.org/2025.findings-naacl.65/
- tau2-bench: shared dynamic environment where both the agent and user can use
  tools to observe, act, and verify state, formalized as a dual-control setting.
  Reference: https://arxiv.org/pdf/2506.07982
- BrowserGym: a gym-like standardized interface with defined observations,
  actions, reproducible experiment management, and multi-benchmark comparisons.
  Reference: https://arxiv.org/abs/2412.05467
- ScienceAgentBench: scientific authenticity through tasks extracted from
  peer-reviewed papers and expert validation, with explicit metrics and
  execution-based checks. Reference: https://arxiv.org/abs/2410.05080
- MLGym: gym-style training/evaluation environments for research agents, with
  reproducible task registration and evaluation across open-ended tasks.
  Reference: https://arxiv.org/abs/2502.14499

What this means for LabLongRun:

```text
Executable/resettable environment is table stakes.
State-based final verification is table stakes.
We need task-scale, task-source discipline, split discipline, dynamic/milestone checks, collateral-damage checks, reproducible run exports, and baseline/failure analysis.
```

The next checkpoint should therefore prove benchmark solidity, not just add more
lab scenarios.

## What Changed In This Checkpoint

We did the recommended next slice:

```text
instrument_fault_star_qc
```

In plain English: the agent transfers liquid, the plate reader first says it is
busy, the agent must retry, recover one valid OD600 reading, and make the
decision from that recovered evidence.

The strict suite now includes these cases for the family:

```text
oracle: transfer -> busy read -> successful retry -> correct submit
empty: no work
no_retry_after_busy: gives up after the recoverable busy error
read_before_transfer_then_retry: uses a recovered but stale pre-transfer reading
wrong_decision_after_recovery: reads correctly but chooses the wrong final action
extra_read_after_success: keeps reading after recovery instead of stopping cleanly
```

We also added a first mutant-declaration layer:

```text
StrictScenarioDecl(world, scenario, oracle, mutants, seed)
StrictMutantDecl(family, case_id, runner, expected_failure_codes)
```

This is intentionally not a full generic mutant generator yet. It gives every
scenario an explicit list of applicable mutant families and exact expected
failure-code sets, without pretending every scenario supports every failure
mode. The exact set matters: if a mutant is expected to fail one check but
actually fails three, strict admission now treats that as drift instead of a
pass.

Current declared mutant families:

```text
empty_plan
arbitrary_note
wrong_decision
stale_evidence
unsafe_resource_attempt
partial_action_before_refusal
non96_workaround_attempt
failed_tool_then_false_success
fault_recovery
extra_retry_after_success
```

## Review Questions

The questions below are intentionally about benchmark design, training signal,
and how AI-lab agents would actually be developed. The focus is on decisions
that affect scientific value.

1. For training/evaluation, what task distribution would actually teach a
long-horizon lab agent useful behavior rather than overfit a simulator?

2. What split design is credible: random task split, family-held-out split,
fault-held-out split, instrument-held-out split, or some combination?

3. Which intermediate milestones should be scored for training signal: inspect
before act, resource check before irreversible action, recovery after tool
fault, fresh evidence before submission, or collateral-damage avoidance?

4. How would an AI lab team actually use such an environment: pre-deployment
eval, RL training, regression testing after agent changes, protocol authoring
guardrails, or post-run audit? Which of these is real enough to optimize for?

5. What is the minimum credible release size for a Hugging Face preview:
100 tasks with strong provenance and baselines, or a smaller number with deeper
verifier/admission evidence?

6. Where is LLM generation acceptable, and where is it dangerous? For example:
LLM-written task text may be fine, but verifier logic and expected state
transitions need programmatic or source-grounded checks.

## Proposed Work Plan

Immediate discussion focus:

```text
Primary objective: training data, eval credibility, or AI-lab workflow realism.
Reward drift risk: how to keep tasks and verifiers aligned as the benchmark scales.
Release bar: what minimum evidence makes a Hugging Face preview credible.
```

Next implementation:

```text
produce an admission matrix: scenario x mutant family x exact expected failure-code set
add milestone-level verifier outputs, not only final pass/fail
add collateral-damage checks for unintended state changes
add one controlled generator experiment for a low-biology family, such as resource refusal or stale evidence
create a small held-out split by family or fault type, even before scaling task count
```

After that:

```text
decide D&B artifact paper vs method paper
write benchmark card / technical report outline
run baseline agents and publish failure taxonomy
only then decide whether domain researchers are needed
```

## Domain Researcher Input

Domain researcher input becomes most valuable if we decide to build a larger
scientifically grounded task set, for example:

```text
100+ biology-grounded tasks
domain-specific protocol realism review
real assay failure-mode taxonomy
external validation of wet-lab plausibility
```

For the next engineering step, this is mostly systems/verifier work, not biology.

## Bottom Line

The current branch is a good Phase 0 verifier-validity checkpoint.

The next serious move is not more demo polish. It is turning the new
declaration layer into an admission matrix, milestone verifier, collateral
damage checker, and one small generator experiment, so we can tell whether this
scales beyond hand-authored examples and reaches the solidity of recent
agent-environment papers.
