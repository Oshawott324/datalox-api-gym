# Retrieval Heuristics

This note records the current heuristic boundary in `datalox-pack`.

It exists because the repo has already reduced heuristic behavior in promotion, but retrieval and some source-routing paths still rely on hand-written scoring and pattern matching.

For the concrete fix sequence, see [retrieval-fix-plan.md](./retrieval-fix-plan.md).

## Bottom Line

The main remaining heuristic core is still retrieval.

More specifically:

- skill retrieval is still heuristic
- direct note retrieval is still heuristic
- some source routing is still heuristic
- promotion is less heuristic than before, but retrieval scores still leak into downstream payloads

This is different from the skill-note contract drift described in [runtime-skill-note-alignment.md](./runtime-skill-note-alignment.md).

## What Is Still Heuristic

### 1. Skill Retrieval

Current code:

- [removed legacy pack script](../removed legacy pack script)
  - `tokenize()`
  - `scoreRepoHints()`
  - `scoreSkill()`
  - `resolveLocalKnowledge()`

Current behavior:

- split `task` and `step` into lowercase alphanumeric tokens
- add points for token overlap with skill text
- add points for exact workflow match
- add large weight for explicit skill id or name match
- add repo-hint weights from:
  - changed files
  - root files
  - package signals
- rank by total score
- keep the top `limit`

Why this is heuristic:

- the weights are hand-written
- lexical overlap is not semantic equivalence
- changed-file and package-hint boosts are useful but not principled
- `score > 0` is still the admission rule for non-explicit matches

### 2. Direct Note Retrieval

Current code:

- [removed legacy pack script](../removed legacy pack script)
  - `scoreNote()`
  - `explainNoteMatch()`
  - `compareRetrievedNotes()`
  - `retrieveDirectNotes()`
  - `searchNotesWithQmd()`

Current behavior:

- add points for:
  - workflow match
  - skill-linked note match
  - title match
  - `whenToUse`, `signal`, and `action` text matches
  - token overlap across note sections
- rerank by:
  - Datalox local score
  - backend score when using QMD
  - note usage counts
  - recency

Why this is heuristic:

- the weights are hand-written
- note usage counts are treated as ranking signal
- QMD backend scores are mixed with local rescoring
- this is still a best-effort lexical ranking system, not a principled retrieval contract

### 3. Source Routing

Current code:

- [src/adapters/sourceRoutes.ts](../src/adapters/sourceRoutes.ts)

Current behavior:

- scan the prompt for PDF-looking paths using regex
- expand `~/`
- test whether the path exists
- if any concrete PDF is found, route into PDF capture before generic repo-context retrieval

Why this is heuristic:

- detection depends on prompt surface form
- regex path extraction is not a full parser
- it can miss oddly formatted paths or overmatch prompt text that only looks like a path

### 4. PDF Capture

Current code:

- [src/core/pdfEvidence.ts](../src/core/pdfEvidence.ts)
- [src/core/pdfCapture.ts](../src/core/pdfCapture.ts)

Current behavior:

- strip boilerplate with regex
- drop lines using pattern lists
- infer sections from regex matchers over the early page window
- filter reference-like sentences
- choose snippets and section summaries with preference ordering
- choose a slug from a fallback candidate list

Why this is heuristic:

- section detection is regex-based
- boilerplate removal is rule-based
- snippet selection is rule-based
- slug choice is fallback ordering, not structured metadata

This is acceptable for now because PDF capture is explicitly a rule-based evidence path, but it should still be recognized as heuristic extraction rather than a ground-truth parse.

### 5. Wrapper Prompt Inference

Current code:

- [src/adapters/codex/run.ts](../src/adapters/codex/run.ts)
- [src/adapters/claude/run.ts](../src/adapters/claude/run.ts)

Current behavior:

- if no explicit Datalox prompt is given, infer the prompt position from raw host CLI args

Why this is heuristic:

- host CLI syntax is inferred from option patterns
- wrapper behavior depends on argument shape rather than an explicit host-side prompt API

This is lower-severity than retrieval heuristics, but still real.

## What Is No Longer The Main Heuristic Problem

Promotion is no longer primarily score-driven.

Current code:

- [removed legacy pack script](../removed legacy pack script)
  - `buildAdjudicationPacket()`
  - `decideAdjudicatedPromotion()`

Current behavior:

- the agent explicitly adjudicates:
  - `record_trace`
  - `create_operational_note`
  - `patch_existing_skill`
  - `create_new_skill`
  - `needs_more_evidence`
- code then enforces legality:
  - source-derived inputs cannot patch skills directly
  - single-run skill patches are blocked until the note stage exists
  - new skill creation requires the note stage first

There are still policy brakes such as `occurrenceCount` and `operationalNoteExists`, but the patch-vs-create decision is no longer just “highest score wins.”

## What Still Leaks Downstream

Even though promotion is less heuristic, retrieval scores still leak into emitted payloads.

Current examples:

- `candidateSkills[].score`
- `matchedSkillScore`

Current code:

- [src/adapters/shared.ts](../src/adapters/shared.ts)
- [removed legacy pack script](../removed legacy pack script)

This means downstream agents can still see and possibly overtrust heuristic ranking numbers, even though those numbers are not durable product truth.

## Dead Or Stale Heuristic Code

There is also stale heuristic promotion code still present:

- `decidePromotionAction()` in [removed legacy pack script](../removed legacy pack script)

It reflects the older repetition-threshold ladder and should not be treated as the live product model.

## Recommended Direction

Short term:

- treat retrieval output as candidate generation, not truth
- stop exposing `candidateSkills[].score` and `matchedSkillScore` in downstream contracts
- keep score only as an internal implementation detail if needed

Medium term:

- reduce reliance on lexical hand-weighting in `scoreSkill()` and `scoreNote()`
- move more semantic boundary decisions into agent adjudication
- keep code responsible for legality, provenance, and write rules

## Repo Rule

When describing current system quality, say this plainly:

- promotion is increasingly agent-adjudicated
- retrieval is still mostly heuristic
- any output field that exposes a raw retrieval score is diagnostic, not ground truth
