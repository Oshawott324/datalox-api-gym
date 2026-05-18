# Enforcement Fix Plan

This document turns the grounded drift in [enforcement-live-drift-2026-04-22.md](./enforcement-live-drift-2026-04-22.md) into a concrete implementation plan.

It is intentionally narrow:

- fix the enforced wrapper loop first
- keep the agent as the semantic decision-maker
- keep code responsible for legality, provenance, and bounded context
- do not add a second runtime layer or a fallback-heavy stabilization path

## Target

The target behavior is:

- fresh enforced runs record events with the correct workflow or `unknown`
- weak retrieval candidates do not assign workflow during post-run recording
- the same real run does not bounce between `record_trace` and `create_operational_note`
- promoted notes have correct semantics before nicer rendering
- transcript noise does not pollute stored evidence

In short:

- enforcement should be mechanically real
- promotion should be semantically stable
- note output should be compact and grounded

## Non-Goals

This plan does not try to:

- redesign retrieval again from scratch
- make a single run create a skill
- move durable truth out of repo files
- turn transcript capture into a full log-cleaning product
- add heuristic post-processing to “repair” bad notes after the fact

## Current Problem Summary

Live enforced runs now behave better than before, but four concrete drifts remain:

1. post-run trace recording can still adopt an unrelated workflow from weak retrieval
2. repeated identical runs can bounce between `create_operational_note` and `record_trace`
3. promoted notes can have wrong semantics:
   - wrong `kind`
   - wrong `workflow`
   - weak `When to Use`
   - noisy evidence
4. stored `stderr` / transcript sections can still contain large transport-warning or HTML dumps

These are no longer the old default-workflow or summary-extraction bugs. They are now:

- retrieval/admission drift during recording
- adjudication stability drift
- note semantic/rendering drift
- transcript hygiene drift

## Fix Order

Do these in this order:

1. stop weak retrieval from assigning workflow in post-run recording
2. stabilize repeated adjudication
3. fix promoted note semantics
4. tighten promoted note rendering
5. tighten transcript hygiene

That order matters:

- workflow correctness and adjudication stability are core logic
- note rendering is downstream quality
- transcript cleanup is useful but not the first blocker

## Phase 1: Stop Weak Workflow Adoption In Post-Run Recording

### Goal

If a run is unscoped and only weak candidates exist, keep the recorded workflow as `unknown`.

### Main files

- `removed legacy pack script`
- `src/core/packCore.ts`
- `src/adapters/shared.ts`

### Changes

- separate `candidateSkills` from `authoritativeSkill`
- only let post-run recording inherit workflow from:
  - explicit workflow
  - explicit skill
  - structurally strong matched skill
- if retrieval only returned weak candidates, record:
  - `workflow: "unknown"`
  - no authoritative matched skill
- keep weak candidates visible as suggestions only

### Important rule

Candidate presence must not be treated as workflow truth.

### Pass criteria

- fresh unscoped repo-description runs record `workflow: "unknown"`
- literal `__DATALOX_PROMPT__` runs record `workflow: "unknown"` unless a strong match exists
- weak candidates can still appear in candidate lists, but do not set recorded workflow

## Phase 2: Stabilize Repeated Adjudication

### Goal

The same real run on the same repo should not bounce between `record_trace` and `create_operational_note`.

### Main files

- `removed legacy pack script`
- `src/core/packCore.ts`
- wrapper/hook proof tests

### Changes

- make adjudication inputs deterministic:
  - same trace summary shape
  - same bounded candidate packet
  - same prior note/event evidence window
- separate:
  - `trace worth recording`
  - `pattern worth promoting to note`
- if a strong single-run note was already justified, the repeated identical run must not regress to `record_trace`
- add a stable promotion memory check:
  - if an existing recent candidate/note already covers the same gap, choose the next mature action instead of re-deciding from scratch

### Important rule

Repetition is only a debounce, not the semantic brain, but identical repeated evidence must still lead to stable decisions.

### Pass criteria

- two identical strong runs on the same repo do not split across `create_operational_note` then `record_trace`
- repeated identical strong runs are directionally monotonic:
  - `record_trace -> create_operational_note`
  - or `create_operational_note -> patch_existing_skill`
  - but not backward

## Phase 3: Fix Promoted Note Semantics

### Goal

Promoted notes should be semantically correct before they are made prettier.

### Main files

- `removed legacy pack script`
- note rendering path in `src/core/packCore.ts`

### Changes

- emitted note kind must match the promotion outcome:
  - promoted operational note must not render as `kind: trace`
- promoted note workflow must come from:
  - explicit workflow
  - authoritative matched skill
  - or `unknown`
  - never from weak candidate leakage
- note title/slug basis must come from the grounded reusable gap, not transport residue

### Important rule

Semantic correctness comes before note polish.

### Pass criteria

- promoted operational notes are not written with `kind: trace`
- note workflow is correct or `unknown`, never unrelated
- note slug/title is grounded in the actual reusable gap

## Phase 4: Tighten Promoted Note Rendering

### Goal

Make promoted notes agent-usable without carrying noisy dumps.

### Main files

- note rendering path in `src/core/packCore.ts`
- any helper shaping functions in `removed legacy pack script`

### Changes

- generate a better `When to Use` from:
  - reusable signal
  - scope
  - action boundary
- compress `Evidence` into:
  - small grounded bullet points
  - short compact excerpts
  - explicit file/path references when relevant
- do not dump whole repo root listings or long stderr blocks into note bodies

### Important rule

The note is for the next agent loop, not for human prose elegance.

### Pass criteria

- `When to Use` is not just a lowercased echo of the original prompt
- evidence is compact and grounded
- promoted note body is small enough to inject without blowing context

## Phase 5: Tighten Transcript Hygiene

### Goal

Keep stored transcript/evidence sections useful without letting transport dumps dominate.

### Main files

- `src/adapters/shared.ts`
- any transcript sanitizers used before recording

### Changes

- strip known transport boilerplate from stored stderr/transcript payloads
- drop large HTML warning bodies and analytics/plugin noise from evidence sections
- preserve real child error text when it is part of the grounded failure

### Important rule

This is hygiene, not evidence rewriting. Keep real failure evidence; drop host transport noise.

### Pass criteria

- stored transcript/evidence sections no longer contain large Codex warning / HTML dumps
- real child error content still survives when it is the actual failure evidence

## Required Live Proof

Use a fresh adopted temp repo and a cheap model through real `datalox codex`.

Minimum live proof set:

1. unscoped repo-description control run
2. literal `__DATALOX_PROMPT__` run
3. single strong reusable-gap run
4. repeated identical reusable-gap run on the same repo

Expected:

- control run records `workflow: "unknown"`
- literal placeholder run records `workflow: "unknown"` unless a strong match exists
- strong single run can still create the first operational note
- repeated identical strong run does not regress to `record_trace`
- promoted note has:
  - correct `kind`
  - correct `workflow`
  - compact evidence
- transcript sections stay bounded and clean

## Recommended Implementation Order

1. phase 1
2. phase 2
3. phase 3
4. phase 4
5. phase 5
6. rerun the live proof set
7. update the live drift note from diagnosis to residual gaps only
