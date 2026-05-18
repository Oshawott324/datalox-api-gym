# Runtime Skill-Note Alignment

This note explains the recent runtime realignment from older flat `pattern` / `direct note` naming toward the intended Datalox model:

- `skill` = primary reusable workflow entrypoint
- `note` = grounded supporting knowledge linked from the skill
- normal read path = `detect_skill -> read_skill -> read_linked_notes -> act`

This is a runtime and machine-facing contract change, not a new product definition.

## What Changed

The following public or machine-facing surfaces were changed:

- `removed legacy pack script`
- `src/core/packCore.ts`
- `src/adapters/shared.ts`
- `src/mcp/loopPulse.ts`
- `scripts/agent-bootstrap.mjs`
- `scripts/agent-resolve.mjs`
- `scripts/agent-learn-from-interaction.mjs`
- `scripts/agent-learn-pattern.mjs`
- `scripts/agent-learn-skill.mjs`

The emitted contract now prefers these fields and terms:

- `knowledgeModel`
- `matches[].linkedNotes`
- `directNoteMatches`
- `note`
- `notePaths`
- `notes` counts

The emitted contract no longer uses these as the primary downstream surface:

- `patternDocs`
- `directNotes`
- `pattern`
- `patternPaths`
- `matchedPatternPaths`
- `patterns` counts

## Intentional Contract Drift

These are deliberate downstream changes.

### Resolve Output

Before:

- top skill match exposed `patternDocs`
- no explicit `knowledgeModel`
- direct note fallback exposed `directNotes`

After:

- top skill match exposes `linkedNotes`
- result includes `knowledgeModel`
- direct note fallback exposes `directNoteMatches`

This is a contract drift for JSON consumers.

### Learn / Promote Output

Before:

- learning and promotion responses exposed `pattern`

After:

- learning and promotion responses expose `note`

This is a contract drift for scripts parsing returned JSON.

### Bootstrap / Status-Like Script Output

Before:

- bootstrap exposed `patterns`, `hostPatterns`, `seedPatterns`
- plain text output said `Patterns`

After:

- bootstrap exposes `notes`
- plain text output says `Notes`

This is a contract drift for scripts parsing bootstrap JSON or stdout.

### CLI Wording

Before:

- script output said `Pattern doc written`
- resolve output said `Pattern doc: ...`

After:

- script output says `Note written`
- resolve output says `Linked note: ...`

This is a wording drift for text-parsing callers.

## What Did Not Intentionally Change

These behaviors were not meant to change:

- skill matching and ranking
- note retrieval ranking
- note usage tracking
- note write location: still `removed-wiki-store/notes/`
- skill write location: still `skills/<name>/SKILL.md`
- wrapper recording flow
- hook provenance flow
- promotion thresholds

So the main drift is contract naming, not core selection logic.

## Real Behavior Drift Analysis

### 1. Algorithmic Drift

Expected impact: low

Reason:

- the matching code still resolves skills first
- linked notes still come from `skill.notePaths`
- direct note fallback still uses the same retrieval path
- wrappers still summarize the same matched guidance

No intended ranking or routing drift was introduced.

### 2. Machine Contract Drift

Expected impact: medium to high

Reason:

- any downstream parser expecting `patternDocs`, `directNotes`, or `pattern` will break
- any script expecting `counts.patterns` or `payload.patternPaths` will break

This is the main risk created by the change.

### 3. Prompt / Agent-Behavior Drift

Expected impact: low to medium

Reason:

- wrapper prompts now group note-derived guidance under `What to do now` and `Watch for`
- they no longer present the older flatter `Signal:` / `Action:` pair in the same way

The semantic content is still there, but prompt shape changed. That can slightly change agent behavior even if the information is equivalent.

### 4. Compatibility Drift

Expected impact: low internally, medium externally

Reason:

- internal read compatibility is still present in some places
- legacy config/frontmatter fields like `patternPaths`, `seedPatternsDir`, and `hostPatternsDir` are still accepted for reading
- emitted results no longer prefer those names

So old repos are still readable, but old consumers of emitted results may not be.

## Current Compatibility Boundary

Still supported for reading:

- legacy skill frontmatter using `patternPaths`
- legacy config fields such as `seedPatternsDir` and `hostPatternsDir`

No longer primary for emitted runtime output:

- `patternDocs`
- `directNotes`
- `pattern`
- `patternPaths`
- `matchedPatternPaths`

This means:

- old stored content remains usable
- old result parsers should be updated

## Known Non-Repo Caveat

A long-lived MCP server process that loaded older code may still emit stale fields until restarted.

That is not a repo-code mismatch. It is a stale process mismatch.

## Recommendation

Treat this change as:

- acceptable semantic realignment
- intentional contract break for old downstream parsers

If strict compatibility is required later, the right fix is:

- add an explicit contract version
- or add temporary read-only alias fields during one transition window

The wrong fix would be:

- restoring flat `pattern*` fields as the primary model

That would reintroduce the same skill-note drift the repo was trying to remove.

## Bottom Line

Yes, there can be downstream behavior drift after this change, but mostly in machine contracts rather than core reasoning logic.

Most likely to drift:

- external JSON parsers
- tests or scripts scraping old field names
- prompt-sensitive agents relying on exact old prompt wording

For the remaining heuristic boundary in retrieval and source routing, see [retrieval-heuristics.md](./retrieval-heuristics.md).

Least likely to drift:

- skill selection
- linked note loading
- where knowledge is written
- the overall enforced loop structure
