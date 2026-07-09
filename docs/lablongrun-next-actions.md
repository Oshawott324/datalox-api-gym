# LabLongRun Strict Admission: Current State and Next Actions

Date: 2026-07-09
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
9 scenarios
44 admission cases
14 mutant families
3 explicit split labels: dev, test_family_heldout, test_fault_heldout
```

Covered worlds:

```text
pylabrobot_lab_v0
pylabrobot_star_v0
```

Covered scenario types:

```text
plate transfer decision
OD600 serial dilution workflow
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
flat fake OD600 dilution readout
missing mix_after during serial dilution
post-dilution liquid handling that mutates dilution wells before readout
submitted readout that does not cover the full dilution series
```

The important shift is that the admission gate is now testing verifier validity, not only task sampling.

`scripts/package_benchmark.py --verify-all` now runs strict admission and fails the command if strict admission fails.

The branch also now exposes the strict-suite quality contract as data:

```text
api_gym.lab_benchmark_quality.build_admission_matrix()
api_gym.lab_strict_admission.run_strict_admission_suite(...).quality_summary
scripts/package_benchmark.py --output .../admission_matrix.json
```

The admission matrix records one row per case:

```text
world
scenario
case_id
case_kind
mutant_family
expected_failure_codes
milestones
split
```

This is not a final benchmark split strategy. It is a first enforceable split
discipline gate: every strict case has an explicit split and every admission
run reports pass counts by split and milestone.

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

These are translated quality dimensions, not exact feature names copied from
each paper. For example, AppWorld's "unexpected changes" motivates our
collateral-damage checks; ToolSandbox's intermediate/final milestones motivates
our milestone verifier; tau2-bench's compositional generation motivates our
family/split discipline. The goal is to match their level of evidence in a lab
agent setting, not to imitate their implementation shape.

The next checkpoint should therefore prove benchmark solidity, not just add more
lab scenarios.

## What Changed In This Checkpoint

We added the first biology-grounded composite family:

```text
pylabrobot_lab_v0::serial_dilution_qc
```

In plain English: the agent performs a 5-step OD600 serial dilution. It must
transfer 50 uL through the chain A1 -> B1 -> B2 -> B3 -> B4 -> B5, use and
discard a fresh tip at each step, request mixing after each dispense, read B1-B5
after the completed dilution, and submit the final decision from that submitted
readout.

This replaces a weak prompt-shaped version of serial dilution. The old readout
model returned 0.82 for every filled dilution well, so a dilution curve could
look valid without any real dilution semantics. The new model propagates OD600
through volume-weighted mixing:

```text
B1 = 0.5
B2 = 0.25
B3 = 0.125
B4 = 0.0625
B5 = 0.0312
```

The same semantics are mirrored into the OT-2 visualizer service path, so the
visual demo and benchmark verifier no longer tell different stories for this
family.

The strict suite now includes these cases for the serial dilution family:

```text
oracle: correct dilution chain -> submitted OD600 readout -> correct continue
empty: no work
read_before_dilution: submits a pre-dilution readout
tip_reuse_between_steps: omits required discard discipline between steps
missing_mix_after_dispense: omits mix_after during dilution dispenses
post_dilution_mutation: mutates a dilution well after the chain before readout
missing_terminal_readout: completes the chain but never reads/submits evidence
wrong_decision: reads a valid curve but chooses hold
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
tip_reuse_between_steps
missing_mix_after_dispense
post_dilution_mutation
missing_terminal_readout
```

This checkpoint also keeps the benchmark-quality layer on top of that
declaration layer:

```text
admission matrix
milestone labels
collateral-damage labels
split labels
quality summary over strict admission results
packaged admission_matrix.json
```

That gives Zheng something concrete to review: whether the current biological
family, split, milestone taxonomy, and failure-code discipline are the right
ones, not just whether the runner happens to pass today.

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
abstract this OD600 serial dilution family into a small family template
generate controlled variants over stock OD, dilution length, target wells, and held-out mutants
make the generator emit the same admission-matrix fields as hand-authored cases
measure whether generated variants preserve exact expected failure-code sets
add baseline-agent runs against the strict suite and summarize failure modes
```

The immediate engineering slice now covers one real composite biological family
plus the admission matrix, milestone labels, collateral labels, package export,
and a small split assignment. The generator experiment comes next because those
gates now exist; generation without these checks would only multiply unmeasured
drift.

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

The current branch is a stronger Phase 0 verifier-validity checkpoint than the
previous instrument-only slice.

The next serious move is not more demo polish. It is abstracting the OD600
serial dilution family into generated but admission-checked variants, so we can
tell whether this scales beyond hand-authored examples while preserving the
solidity expected from recent agent-environment papers.
