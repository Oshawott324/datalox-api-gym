# LabLongRun Strict Admission: Current State and Next Actions

Date: 2026-07-08
Branch: `codex/strict-admission`
Base: `origin/unitelabs-api-grounding-wz`

This note is for discussion with Zheng. It is intentionally about what the current branch proves, what it does not prove, and what we should build next if the goal is a serious scalable benchmark rather than a toy demo.

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

## Zheng Review Questions

Ask Zheng to review the scaling path, not to write biological task generators.

1. Is the structured-refusal contract acceptable, or should refusal be a first-class tool instead of JSON in `add_workflow_note`?

2. Should strict admission live in API Gym for now, or should the generic admission harness move later to `datalox-gated-runtime` once it stops being world-specific?

3. Is the declaration layer enough for the next checkpoint, or do we need a real mutant generator before adding more families?

4. For training/evaluation, what is the minimum abstraction needed to scale from 36 hand-authored admission cases to hundreds without creating reward drift?

5. What is the minimum report/table needed before showing this to external partners or posting a Hugging Face benchmark preview?

## Proposed Work Plan

Immediate discussion:

```text
Zheng reviews current proof
Zheng reviews whether the mutant-declaration layer is the right scaling surface
Do not ask Zheng biological realism questions unless we translate them into plain workflow terms
```

Next implementation:

```text
apply declarations to 3-5 more scenario families
produce an admission matrix: scenario x mutant family x expected failure code
separate reusable mutant families from one-off scenario runners
add one generator experiment for a low-biology family, such as resource refusal or stale evidence
```

After that:

```text
decide D&B artifact paper vs method paper
write benchmark card / technical report outline
only then decide whether domain researchers are needed
```

## When To Use Domain Researchers

Do not use the Ann Arbor researcher network yet.

Use them only if we decide to build a larger scientifically valuable task set, for example:

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
declaration layer into an admission matrix and one small generator experiment,
so we can tell whether this scales beyond hand-authored examples.
