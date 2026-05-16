# Completed TODO Items

This document records work that was completed and verified, so `TODO.md` can stay focused on open work.

## Skill Boundary

Completed:

- Replaced patch-vs-create heuristics with agent-side adjudication.
- Stopped treating auto-retrieved matches as authoritative skill matches.
- Fixed the bootstrap problem before relying on note-aware adjudication.
- Created a clean first-note path for repeated operational gaps.
- Stopped using repetition count as the main semantic test for note creation.
- Allowed a single strong run to create an operational note.
- Added the mature-phase adjudication path for patch-vs-create.
- Added proof tests for the real boundary.

Implemented shape:

- deterministic layer retrieves candidate skills and linked notes
- agent returns a structured decision:
  - `record_only`
  - `create_operational_note`
  - `patch_existing_skill`
  - `create_new_skill`
  - `needs_more_evidence`
- code still enforces hard product rules:
  - `pdf/web/source` cannot patch skills directly
  - only operational evidence can create or patch skills
  - patched skills must come from explicit or retrieved candidates

## Concrete Steps

Completed:

1. separated retrieved candidates from authoritative targets
2. added bootstrap adjudication for the first operational note
3. made note creation semantic instead of repetition-only
4. added the mature adjudication path for patch-vs-create
5. enforced hard write rules after adjudication
6. kept adjudication packets small
7. added end-to-end proof coverage

Main touched areas:

- `removed legacy pack script`
- `src/adapters/shared.ts`
- `src/core/packCore.ts`
- `src/mcp/loopPulse.ts`
- wrapper / hook / agent-script tests

## Pass Criteria

Passed:

1. an ordinary wrapped run with weak evidence can stay `trace` only
2. a single strong operational run can create the first operational note with zero existing notes
3. repeated ordinary wrapped failure can create the first operational note without manual MCP intervention
4. a genuine existing-skill match can patch that skill automatically after adjudication
5. weak lexical overlap does not patch an unrelated skill
6. a true no-match path creates a note before it creates a skill
7. a single run cannot create or patch a skill
8. source-derived inputs can create evidence notes but cannot patch skills directly
9. the adjudication packet stays within a small bounded context budget
10. the runtime contract stays skill-first:
    - detect skill
    - read linked notes
    - act

## Bootstrap Payload Shape

Completed:

- confirmed the problem was bootstrap/adoption payload shape, not MCP itself
- defined a smaller default bootstrap contract
- split bootstrap into core runtime surfaces versus optional seed knowledge
- inventoried the minimum files needed for loop behavior
- removed whole-tree adoption of unrelated seed knowledge
- reduced the default seed set to the core pack-maintenance / host-wrapper knowledge
- kept the live skill-generation proof working with the smaller bootstrap set
- added focused adopt/auto-bootstrap proofs
- updated docs to match the smaller bootstrap contract

Passed:

1. fresh `adopt` and `auto-bootstrap` repos no longer get unrelated skills like `github`, `ordercli`, or `review-ambiguous-viability-gate`
2. fresh generic repos no longer get unrelated `pdf/` and `web/` note corpora by default
3. enforced wrapper behavior still works
4. first-note bootstrap still works
5. the live skill-generation proof still passes on a fresh repo

Residual open item:

- optional seed knowledge still needs an explicit separate install path if the pack keeps shipping extra example/domain bundles

## Same-Repo Session And Agent Bootstrap

Completed:

- audited the current same-repo handoff surfaces
- added one canonical repo-local handoff instruction
- made the handoff machine-readable in `.datalox/manifest.json`
- fixed the real same-repo bootstrap bug where the installed Codex shim broke after the host binary path changed
- live-proved fresh same-repo pickup through the enforced Codex path

Implemented shape:

- supported enforced hosts can pick up the same repo pack automatically
- non-automatic paths have one explicit repo-local instruction:
  - `Use this repo's Datalox pack. Read AGENTS.md and DATALOX.md before acting.`
- the repo-local write target stays inside the same repo
- no global shared-memory mode was added

Grounded proof:

- [docs/same-repo-bootstrap-live-2026-04-24.md](/Users/yifanjin/datalox-agent-replay/docs/same-repo-bootstrap-live-2026-04-24.md)

## Setup And Partial Adoption Recovery

Completed:

- kept the safety block for partial Datalox-owned paths without an install stamp
- added explicit recovery guidance to blocked bootstrap probe output
- updated setup instructions to preserve the target repo path before changing into the source clone
- clarified that `datalox-agent-replay` is the source clone and the user's current project is the adoption target
- clarified that `bin/adopt-host-repo.sh` belongs to the source clone, while adopted host repos get host-local shims
- updated the public `datalox.ai` source copy and manifest to use the same setup shape
- added focused regression coverage for the reported partial-adoption state

Implemented shape:

- first-time setup from the target repo now uses:

```bash
TARGET_REPO="$(pwd)"
git clone https://github.com/Oshawott324/datalox-agent-replay.git
cd datalox-agent-replay
bash bin/setup-multi-agent.sh claude
bash bin/adopt-host-repo.sh "$TARGET_REPO"
node bin/datalox.js status --repo "$TARGET_REPO" --json
```

- `probe-bootstrap --json` still returns `status: "blocked"` and `canAutoBootstrap: false` for unrecognized partial repos
- the blocked partial-state probe now includes:
  - `recommendedAction: "explicit_adopt_from_source_pack"`
  - `recoveryCommands` that preserve the target repo path and adopt from a source clone
- explicit adoption from a real source clone repairs the repo by writing the core bundle and `.datalox/install.json`

Passed:

1. a git repo with `removed-wiki-store/` but no `.datalox/install.json` remains blocked for auto-bootstrap
2. the blocked probe output includes an explicit recovery action and command shape
3. explicit `bash bin/adopt-host-repo.sh "$TARGET_REPO"` from a real source clone repairs the repo and writes `.datalox/install.json`
4. the repaired repo reports `status: "ready"`
5. setup docs use `TARGET_REPO="$(pwd)"` before changing directories
6. focused adoption and wrapper suites pass
7. `datalox.ai` production is redeployed and the live page/manifest are checked

Focused verification:

- `npm run build`
- `npx vitest run tests/adoptionScripts.test.ts tests/wrapperSurfaces.test.ts`

Public deployment:

- deployed production `datalox.ai` to `https://datalox-land-hnws45vdb-oshawott1124s-projects.vercel.app`
- live page check confirmed `TARGET_REPO="$(pwd)"`, `bash bin/setup-multi-agent.sh claude`, and `bash bin/adopt-host-repo.sh "$TARGET_REPO"`
- live manifest check confirmed the same `agent_setup_prompt`

## Periodic Trace Maintenance And Skill Synthesis

Completed:

- added a real bounded maintenance pass over `removed-wiki-store/events/`
- grouped recent unresolved traces by `workflow + stabilityKey`
- compacted repeated traces into operational notes
- wrote explicit trace coverage back to the recorded event JSON
- exposed the maintenance loop through a manual command:
  - `datalox maintain`
- synthesized new skills only from note-backed evidence in an explicit later pass
- prevented notes created in the same maintenance pass from immediately creating a skill
- kept `unknown` wrapper-generated notes as note-only during new-skill synthesis
- added review/demotion for low-evidence or incident-shaped generated draft skills
- added focused tests and a fresh-agent live proof

Implemented shape:

- maintenance is explicit, bounded, and repo-local
- first pass:
  - scan recent unresolved traces
  - compact repeated traces into notes
  - mark those traces covered
- explicit later pass with `--synthesize-skills`:
  - scan existing note-backed evidence
  - keep note only, patch skill, create skill, or demote generated draft skill
- new skill synthesis requires note-backed evidence and a real workflow boundary

Passed:

1. recent traces in `removed-wiki-store/events/` can be compacted periodically instead of growing unbounded
2. maintenance explicitly marks covered traces with durable metadata
3. the first durable compaction boundary is `trace -> note`
4. no skill is created in the same pass that first creates the note
5. an explicit later maintenance pass can synthesize a new skill only from note-backed evidence
6. generated skill ids and names are reusable workflow names instead of incident-capture wording
7. low-quality generated draft skills can be demoted by the same maintenance path
8. wrapper-generated `unknown` notes stay note-only instead of creating a second unscoped skill

Grounded proof:

- [docs/periodic-trace-maintenance-live-2026-04-25.md](/Users/yifanjin/datalox-agent-replay/docs/periodic-trace-maintenance-live-2026-04-25.md)

## Claude Native Skill Installation

Completed:

- changed Claude skill link installation from one nested `~/.claude/skills/datalox-agent-replay` link to per-skill links at `~/.claude/skills/<skill-name>`
- disable removes only Datalox-managed per-skill links; user-owned skill directories are preserved
- disable handles old nested `datalox-agent-replay` links (removes if they target this pack's `skills/` directory)
- install status reports native Claude skill surfacing separately from hook/shim state
- `status --json` exposes `nativeSkillLinks.installed`, `canonical`, `linked`, `missing`, and `legacyPackLink`
- docs updated: README, DATALOX.md, docs/agent-configuration.md, START_HERE.md
- focused install/disable test coverage added in `adoptionScripts.test.ts`
- live proof written to `docs/claude-native-skill-install-live-2026-04-27.md`

Implemented shape:

- `datalox install claude` links each pack skill to `~/.claude/skills/<skill-name>` and removes the old nested `datalox-agent-replay` link if it targets the current pack
- `datalox disable claude` removes each managed per-skill link; leaves unrelated user skill directories untouched
- `status --json` exposes `nativeSkillLinks` under `adapters.claude`
- `CLAUDE.md` and hook/wrapper paths remain the robust fallback when native skill surfacing is unavailable

Passed:

1. install in temp HOME creates canonical per-skill symlinks at `~/.claude/skills/<skill-name>`
2. each linked directory contains a root `SKILL.md`
3. disable removes Datalox-managed per-skill links
4. disable preserves unrelated user-owned skill directories
5. old nested `datalox-agent-replay` symlink is removed during install when it targets the same pack
6. `status --json` correctly reports `nativeSkillLinks.canonical` after install
7. `npm run build` passes
8. bridge/wrapper regression passes (54/54)

Grounded proof:

- [docs/claude-native-skill-install-live-2026-04-27.md](/Users/yifanjin/datalox-agent-replay/docs/claude-native-skill-install-live-2026-04-27.md)

Live machine state (2026-04-27):

- `~/.claude/skills/` now contains direct per-skill symlinks for all 4 current pack skills
- `~/.claude/hooks/removed legacy hook` present
- `status.adapters.claude.nativeSkillLinks.canonical: true`
- host limitation recorded: `claude` CLI not in shell PATH (IDE extension mode); canonical skill links are installed and will surface in a CLI-launched session

## Online Retrieval And Note Capture

Completed:

- removed lexical workflow-overlap from authoritative skill matching
- kept weak lexical retrieval candidate-only
- stopped wrapper/shared surfaces from silently upgrading the top candidate into `matchedSkillId`
- added a bounded online match adjudicator for ambiguous Codex/Claude cases
- kept generic wrapper paths candidate-only when no adjudicator-backed host path exists
- prevented candidate-only wrapper guidance from leaking `matchedNotePaths` or workflow into durable event capture
- preserved the narrow compatibility path for online skill creation without making it the default product path
- added focused bridge/wrapper/agent-script proofs

Implemented shape:

- deterministic accept:
  - `explicit_skill_match`
  - `field_phrase_match`
- deterministic reject:
  - no candidate set
- ambiguous online case:
  - bounded agent adjudication over `2-5` compact skill cards
- candidate-only retrieval:
  - weak candidates still surface
  - `matchedSkillId` stays `null`
  - top-level supporting notes stay empty

Passed:

1. weak workflow-bound lexical overlap no longer sets `matchedSkillId`
2. weak candidates can still surface without being treated as authoritative
3. ambiguous same-workflow online cases use a cheap structured adjudicator instead of lexical authority
4. durable event capture no longer inherits workflow or matched notes from weak online candidates
5. online note-safe behavior remains intact while new-skill creation stays a narrow compatibility path

Grounded proof:

- [docs/online-retrieval-live-2026-04-26.md](/Users/yifanjin/datalox-agent-replay/docs/online-retrieval-live-2026-04-26.md)

## Maintenance Defaults And Skill Synthesis Boundary

Completed:

- lowered default maintenance scope from `50` events to `12`
- made default `datalox maintain` trace-to-note only
- kept trace coverage marking unchanged
- added explicit note-backed skill synthesis through `--synthesize-skills`
- exposed the same flag through the shared CLI/MCP command surface
- kept skill synthesis note-backed and excluded notes created in the same maintenance pass

Implemented shape:

- default command:
  - `datalox maintain --max-events 12 --json`
- default behavior:
  - scan bounded trace events
  - compact repeated trace groups into `removed-wiki-store/notes/`
  - mark covered events
  - do not create or patch skills
- explicit skill synthesis:
  - `datalox maintain --synthesize-skills`
  - can create, patch, keep-note-only, or demote generated draft skills from existing note-backed evidence

Passed:

1. default maintenance scans the smaller default window
2. explicit `--max-events` still overrides the scan window
3. repeated traces create or update a note without skill actions by default
4. existing note-backed evidence creates a skill only when `--synthesize-skills` is set
5. low-evidence generated draft skill review remains available only on explicit synthesis

## Event Backlog Visibility And Maintenance Nudges

Completed:

- added shared event backlog stats and policy evaluation
- added maintenance backlog data to `status --json`
- added Claude hook stderr warnings for hot backlogs
- added next-turn-readable backlog visibility in `removed-wiki-store/hot.md`
- added machine-readable Codex wrapper backlog warnings in wrapper JSON
- added a composite backlog policy in `.datalox/config.json` and `.datalox/config.schema.json`
- kept hook/wrapper warnings note-only; they recommend bounded maintenance and do not synthesize skills

Implemented shape:

- shared status fields include:
  - total event count
  - trace / non-trace count
  - uncovered trace count
  - covered trace count
  - unresolved trace group count
  - repeated unresolved trace group count
  - maintainable unresolved trace group count
  - oldest uncovered event timestamp/path
  - policy level: `none`, `warn`, or `urgent`
  - recommended command
- default backlog policy:
  - warn at `50` uncovered events, `7` days oldest age, or `1` maintainable group
  - urgent at `100` uncovered events, `14` days oldest age, or `5` maintainable groups
- policy uses OR semantics across:
  - uncovered event depth
  - oldest uncovered event age
  - maintainable unresolved group count

Passed:

1. synthetic repo with `135` uncovered events reports urgent by depth
2. covered events are excluded from urgent warnings
3. old uncovered events can warn even when raw count is low
4. one repeated maintainable group warns even when raw count is low
5. config can tune backlog policy
6. invalid empty warning policies fail clearly
7. Codex wrapper JSON includes machine-readable backlog warning data
8. Claude hook writes a compact stderr warning and updates `removed-wiki-store/hot.md`
9. `status --json` exposes the same shared backlog status
10. warnings do not trigger skill synthesis

Focused verification:

- `npm run build`
- `npx vitest run tests/bridgeSurfaces.test.ts tests/wrapperSurfaces.test.ts tests/agentScripts.test.ts tests/hookIntegration.test.ts`

## Singleton Trace Rollup And Non-Repeated Event Drainage

Completed:

- added `summarized` as a drained maintenance status for singleton trace rollups
- kept `covered` reserved for traces compacted into real operational notes
- updated backlog status so `covered` and `summarized` traces no longer keep depth/age warnings hot
- added bounded singleton rollup generation to default `datalox maintain`
- kept low-signal singleton traces out of operational-note promotion and skill synthesis
- kept summarized singleton traces available as prior evidence when the same stability key appears again
- allowed explicitly adjudicated singleton traces to become operational notes
- excluded `trace_rollup` notes from note-backed skill synthesis

Implemented shape:

- repeated trace groups:
  - compact into operational notes
  - events are marked `maintenanceStatus: "covered"`
  - events receive `coveredByNotePath`
- low-signal singleton traces:
  - compact into bounded `trace_rollup` notes under `removed-wiki-store/notes/`
  - events are marked `maintenanceStatus: "summarized"`
  - events receive `summarizedByNotePath`
- explicitly adjudicated singleton traces:
  - may become operational notes when the event carries a structured decision such as `create_operational_note`
  - still do not create skills during default maintenance
- skill synthesis:
  - remains explicit through `--synthesize-skills`
  - ignores `trace_rollup` notes

Passed:

1. `status --json` reports covered, summarized, drained, and uncovered trace counts separately
2. summarized traces are excluded from backlog warning depth and age
3. repeated traces still compact into operational notes and mark coverage
4. low-signal singleton traces produce rollup coverage, not operational guidance
5. explicitly adjudicated singleton traces can still become operational notes
6. a fresh trace with the same stability key can promote together with a previously summarized singleton
7. rollup notes do not synthesize skills on a later explicit synthesis pass
8. a synthetic repo with `135` old singleton traces drains through bounded `12` event maintenance passes
9. generated rollup notes stay bounded and agent-readable

Focused verification:

- `npm run build`
- `npx vitest run tests/bridgeSurfaces.test.ts -t "backlog|maintenance|singleton"`
- `npx vitest run tests/bridgeSurfaces.test.ts tests/hookIntegration.test.ts tests/agentScripts.test.ts`
- `npx vitest run tests/wrapperSurfaces.test.ts`

## Cross-Host Automatic Bounded Maintenance Trigger

Completed:

- added a shared automatic maintenance helper after event recording / compile / review
- kept automatic maintenance note-only with `synthesizeSkills: false`
- added config controls under `maintenance.automatic`
- added `DATALOX_AUTO_MAINTENANCE=off|warn_only|write` as an emergency override
- added a visible repo-local lock at `.datalox/maintenance.lock.json`
- wired Codex, generic wrapper, and Claude hook paths through the shared helper
- kept existing backlog output while adding a machine-readable `maintenance` object to wrapper post-run JSON

Implemented shape:

- automatic maintenance modes:
  - `write`: run bounded note-only maintenance when backlog policy is hot
  - `warn_only`: report the backlog and skip writes
  - `off`: skip automatic maintenance entirely
- default config:
  - `maintenance.automatic.enabled: true`
  - `maintenance.automatic.write: true`
  - `maintenance.automatic.lockStaleMs: 300000`
- automatic run behavior:
  - checks `getEventBacklogStatus`
  - skips when backlog policy is `none`
  - runs `maintainKnowledge` with configured `maxEvents`
  - forces `synthesizeSkills: false`
  - returns before/after backlog status plus maintenance result
- lock behavior:
  - active lock skips with `maintenance_lock_held`
  - stale lock is replaced deterministically

Passed:

1. core helper runs note-only maintenance for a hot backlog
2. core helper never produces automatic skill actions
3. config can disable automatic maintenance
4. env override can force warning-only behavior
5. active lock skips without failing the turn
6. stale lock is recovered deterministically
7. Codex wrapper drains a hot backlog without manual `datalox maintain`
8. generic wrapper drains a hot backlog when prompt injection is active
9. Claude hook drains a hot backlog after recording/compiling the current event
10. after-maintenance `removed-wiki-store/hot.md` no longer keeps a stale backlog warning

Focused verification:

- `npm run build`
- `npx vitest run tests/bridgeSurfaces.test.ts -t "automatic bounded maintenance|backlog|maintenance"`
- `npx vitest run tests/wrapperSurfaces.test.ts -t "automatic bounded maintenance|backlog"`
- `npx vitest run tests/hookIntegration.test.ts -t "automatic bounded maintenance"`

## Native Codex MCP Loop Enforcement

Completed as active-session provenance plus guidance-only MCP clarity.

The important boundary:

- installed Codex shim / adapter capability can be enforceable
- active wrapper enforcement must be proven by wrapper sentinels
- native Codex chat with MCP is guidance-only unless the agent explicitly calls MCP tools

Completed:

- updated `AGENTS.md` so Datalox MCP-capable agents call `resolve_loop` before Datalox-pack work and `record_turn_result` after meaningful grounded outcomes
- updated `skills/use-datalox-through-host-cli/SKILL.md` and its linked note to stop treating MCP availability as enforcement
- added wrapper sentinels to Codex, Claude, and generic child process environments:
  - `DATALOX_ACTIVE_WRAPPER`
  - `DATALOX_HOST_KIND`
  - `DATALOX_ENFORCEMENT=wrapper`
- added `currentSession` to `datalox status --json`
- kept adapter install status separate from active-session status
- documented live proof in [docs/native-codex-session-provenance-live-2026-04-30.md](/Users/yifanjin/datalox-agent-replay/docs/native-codex-session-provenance-live-2026-04-30.md)

Passed:

1. native Codex status reports `currentSession.enforcementLevel: "guidance_only"` when no wrapper sentinel is present
2. wrapper-sentinel status reports `currentSession.enforcementLevel: "enforced"`
3. installed Codex adapter status still reports the installed shim as enforceable
4. `datalox codex` child processes receive Codex wrapper sentinels
5. agent-facing guidance points native Codex to MCP calls without claiming automatic enforcement

Focused verification:

- `npm run build`
- `npx vitest run tests/adoptionScripts.test.ts tests/wrapperSurfaces.test.ts -t "reports enforced host adapters as automatic in status output|Codex wrapper"`

## Claude Code Surface Provenance And Status Clarity

Completed as explicit four-surface status plus active-session provenance.

The important boundary:

- Claude shim wrapper / `datalox claude` is the enforceable pre-run guidance injection path
- Claude Stop hook is post-turn sidecar automation
- Claude native skills are model-chosen and restart-sensitive
- Claude MCP tools are guidance-only unless Claude Code actually calls them

Completed:

- added `adapters.claude.surfaces.wrapper`, `stopHook`, `nativeSkills`, and `mcp` to `datalox status --json`
- kept existing raw `adapters.claude` fields for compatibility
- added Claude-specific active-session notes so wrapper enforcement only counts when `currentSession.activeWrapper` is `"claude"` and `currentSession.wrapperEnforced` is `true`
- documented the boundary in `CLAUDE.md`, `skills/use-datalox-through-host-cli/SKILL.md`, and `removed-wiki-store/notes/use-datalox-through-host-cli.md`
- documented live proof in [docs/claude-code-surface-provenance-live-2026-05-02.md](/Users/yifanjin/datalox-agent-replay/docs/claude-code-surface-provenance-live-2026-05-02.md)

Passed:

1. status reports Claude wrapper, Stop hook, native skills, and MCP separately
2. hook/native-skill availability does not imply pre-run wrapper enforcement
3. simulated Claude wrapper sentinels report active wrapper enforcement
4. `datalox claude` child processes receive wrapper sentinels
5. Claude hook recording/maintenance stays post-turn and does not pretend to be pre-run enforcement

Focused verification:

- `npm run build`
- `npx vitest run tests/adoptionScripts.test.ts tests/wrapperSurfaces.test.ts tests/hookIntegration.test.ts`
