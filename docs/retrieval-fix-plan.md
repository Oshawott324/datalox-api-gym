# Retrieval Fix Plan

This document turns the diagnosis in [retrieval-heuristics.md](./retrieval-heuristics.md) into a concrete implementation plan.

It is intentionally narrow:

- fix retrieval first
- do not add another knowledge layer
- keep the pack model skill-first, note-second
- keep agent adjudication for semantic promotion decisions

## Target

The target behavior is:

- retrieval produces a small set of plausible candidates
- downstream agents do not see raw heuristic scores
- candidate admission is based on explicit structural rules, not loose additive overlap
- note retrieval stays subordinate to skill retrieval
- usage counters remain analytics, not retrieval truth

In short:

- retrieval = candidate generation
- adjudication = semantic decision
- code = legality and write rules

## Non-Goals

This plan does not try to:

- redesign the whole pack
- replace the note or skill schemas
- move promotion back to repetition-only thresholds
- make PDF capture non-rule-based
- add a hidden runtime service layer

## Current Problem Summary

Today:

- `scoreSkill()` is still a hand-weighted lexical scorer
- `scoreNote()` is still a hand-weighted lexical scorer
- `candidateSkills[].score` and `matchedSkillScore` still leak downstream
- repo hints and usage counts still influence ranking
- weak lexical overlap can still surface unrelated candidates

Observed example:

- a repo-engineering query can still surface `github` as a candidate because of weak token overlap

That means retrieval is still too loose and too visible.

## Desired Contract

Downstream contract should expose:

- `matchedSkillId`
- `candidateSkills[]`
  - `skillId`
  - `displayName`
  - `workflow`
  - `supportingNotes`
- `whyMatched`
- `selectionBasis`

Downstream contract should not expose:

- `candidateSkills[].score`
- `matchedSkillScore`
- any raw backend score

If ranking still exists internally, it should stay internal.

## Implementation Order

## Phase 1: Remove Score Leakage

### Goal

Stop exposing heuristic ranking numbers to downstream agents and tools.

### Main files

- `src/adapters/shared.ts`
- `removed legacy pack script`
- `src/core/packCore.ts`
- tests covering wrapper, bridge, hook, and script outputs

### Changes

- remove `score` from emitted `candidateSkills`
- remove `matchedSkillScore` from recorded event payloads
- keep any internal score only as a local implementation detail if still needed
- update JSON-shape tests and snapshots

### Pass criteria

- wrapper outputs do not contain `candidateSkills[].score`
- recorded events do not contain `matchedSkillScore`
- MCP/CLI resolve outputs do not expose heuristic score fields

## Phase 2: Replace Additive Scoring With Candidate Admission Rules

### Goal

Stop using “sum enough overlap points and keep anything above zero” as the main retrieval boundary.

### Main files

- `removed legacy pack script`

### Changes

Replace `scoreSkill()` with a stricter candidate evaluation step, for example:

- `explicit`:
  - exact `skillId` or exact `name`
- `workflow_scoped`:
  - query workflow matches skill workflow
  - and query matches at least one strong skill field
- `generic`:
  - allowed only when no workflow is given
  - or when explicitly requested
- `reject`:
  - anything else

Strong skill fields should be limited to:

- skill id
- skill name
- display name
- trigger
- description

Do not use:

- loose body-wide substring matching as the main admission rule
- repo hints as admission

Repo hints may remain only as a tie-breaker between already-admitted candidates.

### Important rule

If `query.workflow` is present, a skill with no matching workflow should not become a candidate just because of token overlap, unless explicitly requested.

That is the cleanest fix for “repo-engineering question still surfaces github.”

### Pass criteria

- weak lexical overlap alone cannot surface an unrelated candidate
- workflow-bound queries do not admit generic/null-workflow skills by default
- explicit skill selection still works

## Phase 3: Tighten Direct Note Retrieval

### Goal

Make note retrieval more structural and less popularity-weighted.

### Main files

- `removed legacy pack script`

### Changes

Replace `scoreNote()` as the primary model with staged note admission:

1. eligibility:
   - note status is usable
   - workflow matches when query workflow is present
2. strong match:
   - exact skill-linked note
   - exact title match
   - strong section match in `whenToUse`, `signal`, or `action`
3. fallback:
   - only if no skill matched and no strong note match exists

Keep `explainNoteMatch()`, but make it describe structural reasons rather than score accumulation.

### Important rule

Usage counters must stop affecting retrieval rank:

- `read_count`
- `apply_count`
- `evidence_count`

These should stay analytics only.

They can remain visible in note metadata, but they should not steer retrieval.

### Pass criteria

- old popular notes do not outrank better-fitting notes just because of usage
- direct notes are still available when no skill matches
- note retrieval remains deterministic

## Phase 4: Make Candidate Output Reason-First

### Goal

Give downstream agents reasons, not numbers.

### Main files

- `src/adapters/shared.ts`
- `removed legacy pack script`

### Changes

Expose compact reason classes such as:

- `explicit_skill_match`
- `workflow_match`
- `title_match`
- `skill_linked_note`
- `source_kind_pdf`

Candidate summaries should surface:

- why this candidate is present
- what notes support it

Do not expose:

- raw ranking totals
- backend scores

### Pass criteria

- agent-facing outputs stay interpretable without exposing heuristic numbers
- candidate reasoning is still inspectable

## Phase 5: Separate Source Routing From Retrieval More Cleanly

### Goal

Keep source routing from polluting generic retrieval.

### Main files

- `src/adapters/sourceRoutes.ts`
- `src/core/pdfCapture.ts`

### Changes

- keep explicit file-path routing ahead of generic retrieval
- prefer explicit path parameters or concrete existing paths over loose prompt scanning whenever a wrapper/CLI surface can provide them
- keep PDF routing as a source-kind override, not a scored candidate

This is lower priority than Phases 1 to 4, but it reduces one more heuristic surface.

### Pass criteria

- concrete PDF inputs route to capture without involving generic skill ranking
- generic repo-engineering queries do not accidentally trigger source routing

## Phase 6: Delete Stale Heuristic Promotion Code

### Goal

Remove dead or misleading older heuristic logic so the repo reflects the actual model.

### Main files

- `removed legacy pack script`

### Changes

- remove `decidePromotionAction()` if it is no longer live
- make the repo reflect the current adjudicated promotion path only

### Pass criteria

- there is one visible promotion model in code, not two
- future contributors do not mistake the stale threshold ladder for the active design

## Tests

Required proof tests:

1. repo-engineering query does not surface `github` from weak overlap alone
2. workflow-bound query rejects null-workflow skills unless explicitly requested
3. `candidateSkills[].score` is absent in wrapper/CLI/MCP outputs
4. `matchedSkillScore` is absent in recorded event payloads
5. direct note fallback still works when no skill matches
6. note usage counters no longer affect retrieval order
7. explicit skill selection still wins deterministically
8. PDF path routing still works without score leakage

## Concrete File Touch Points

Primary:

- `removed legacy pack script`
- `src/adapters/shared.ts`
- `src/core/packCore.ts`
- `src/adapters/sourceRoutes.ts`

Likely tests:

- `tests/bridgeSurfaces.test.ts`
- `tests/agentScripts.test.ts`
- `tests/wrapperSurfaces.test.ts`
- `tests/hookIntegration.test.ts`
- `tests/retrievalBackends.test.ts`

## Recommended Sequence

Do this in order:

1. remove downstream score fields
2. tighten skill candidate admission
3. remove usage-based note ranking
4. make output reason-first
5. clean up source routing edges
6. delete stale heuristic promotion code

This order keeps the user-visible contract moving toward cleaner agent behavior before deeper algorithm changes.

## Success Condition

The plan is complete when:

- retrieval still returns useful candidates
- unrelated weak lexical candidates stop surfacing
- downstream agents no longer see raw heuristic scores
- skill-first / linked-note-second behavior remains intact
- promotion continues to rely on agent adjudication, not on retrieval scores
