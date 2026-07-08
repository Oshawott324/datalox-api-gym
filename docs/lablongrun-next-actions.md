# LabLongRun Strict Admission: Current State and Next Actions

Date: 2026-07-08
Branch: `codex/strict-admission`
Base: `origin/unitelabs-api-grounding-wz`

This note is for discussion with Zheng. It is intentionally about what the current branch proves, what it does not prove, and what we should build next if the goal is a serious scalable benchmark rather than a toy demo.

## Current State

Phase 0 now has a strict admission gate for a small but concrete lab slice.

The gate runs through the public world runtime surface:

```text
sample_episode -> dispatch_tool calls -> verify_run
```

It does not inspect hidden mutable state directly from the admission harness.

Current strict suite:

```text
7 scenarios
30 admission cases
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
```

Each strict scenario now includes at least:

```text
oracle pass
empty plan fail
known-bad or resource/provenance mutant fail
expected failure code match
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
```

The important shift is that the admission gate is now testing verifier validity, not only task sampling.

`scripts/package_benchmark.py --verify-all` now runs strict admission and fails the command if strict admission fails.

## What This Does Not Prove

This is not yet a scalable benchmark.

It does not prove:

```text
all STAR scenarios are admission-safe
all lab scenarios have oracle/mutant coverage
fault recovery is covered deeply
stochastic dynamics are covered deeply
task generation can scale to 1,000 tasks
mutants are generated systematically
verifier checks are grounded across many scenario families
biology-specific realism is enough for a paper
```

The current suite is still hand-written. That is acceptable for Phase 0 because the goal is to prove the verifier can reject known bad behavior. It is not acceptable as the long-term scaling strategy.

## Next Decision

We should not immediately expand by adding many more hand-written tasks.

The next question for Zheng is:

```text
Do we turn this into a scalable admission framework first, or add one more deep scenario family first?
```

My recommendation:

```text
Do one more deep family first, then abstract the mutant framework.
```

Reason: abstracting now risks building a generic framework around only resource-refusal examples. We need one non-resource long-horizon family to pressure-test the design.

## Recommended Next Slice

Build a strict admission slice for:

```text
instrument_busy_wait_or_reschedule
```

Why this one:

```text
It is not just resource refusal.
It forces temporal reasoning.
It tests fault handling.
It is easy to understand without deep biology.
It maps to real lab/instrument behavior.
It creates reusable mutant patterns for later scenarios.
```

Admission cases should include:

```text
oracle waits/retries and succeeds
empty plan fails
single busy error then gives up fails
submits without successful readout fails
uses stale pre-fault readout fails
retries too many times or ignores limit fails
wrong final decision after valid readout fails
```

Expected verifier codes should be explicit, for example:

```text
readout_after_busy_recovery
retry_count_within_policy
fresh_readout_used_for_submission
successful_readout_required
decision_matches_observed_data
```

## Then Build Mutant Families

After the instrument-busy slice passes, introduce a small reusable mutant-family layer.

Do not make it too generic yet. Start with a registry like:

```text
empty_plan
arbitrary_note
wrong_decision
stale_evidence
unsafe_resource_attempt
partial_action_before_refusal
failed_tool_then_false_success
give_up_after_recoverable_fault
skip_required_inspection
```

Each scenario declares which families apply:

```json
{
  "scenario": "low_reagent_qc",
  "mutants": [
    "empty_plan",
    "arbitrary_note",
    "unsafe_resource_attempt",
    "partial_action_before_refusal"
  ]
}
```

This avoids pretending every scenario has every failure mode.

## Zheng Review Questions

Ask Zheng to review these, not to write biological task generators.

1. Is the structured-refusal contract acceptable, or should refusal be a first-class tool instead of JSON in `add_workflow_note`?

2. Should strict admission live in API Gym for now, or should the generic admission harness move later to `datalox-gated-runtime` once it stops being world-specific?

3. Is `instrument_busy_wait_or_reschedule` the right next deep family, or should we choose `stale_evidence_detection` first?

4. Does the mutant-family registry design look like the right scaling path from 30 cases to hundreds?

5. What is the minimum report/table needed before showing this to external partners or posting a Hugging Face benchmark preview?

## Proposed Work Plan

Immediate:

```text
commit strict admission branch
write this note
Zheng reviews current proof and next-slice choice
```

Next implementation:

```text
add instrument_busy strict admission slice
add verifier checks for recovery/freshness/retry policy
add admission cases for busy/retry/stale/give-up mutants
wire into --verify-all
run final reviewer
```

After that:

```text
extract mutant-family declarations
apply to 3-5 scenario families
produce an admission matrix
write benchmark card / technical report outline
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

The next serious move is not more demo polish. It is one more deep long-horizon family, then a small mutant-family framework so the benchmark can scale beyond hand-coded examples.
