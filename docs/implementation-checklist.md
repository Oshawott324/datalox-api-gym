# Datalox Retrieval Checklist

Status: completed.

This pass upgraded note retrieval in `datalox-pack` without changing the core product boundary:

- `skills/` stay the primary execution entrypoints
- `removed-wiki-store/notes/` stays the primary knowledge body
- Datalox keeps ownership of:
  - note and skill schemas
  - workflow and skill scoping
  - loop injection
  - read/apply tracking
  - event -> note -> skill compilation

The only pluggable part is direct note retrieval.

## Core Rule

- [x] Skill-linked notes remain primary.
- [x] Direct note retrieval is backend-driven.
- [x] Supported note retrieval backends are:
  - `native`
  - `qmd`
- [x] QMD is a retrieval engine, not the knowledge system.

## Target Retrieval Flow

- [x] Resolve the best matching skill first.
- [x] Load linked notes from that skill first.
- [x] If no skill matches, retrieve direct notes through the selected backend.
- [x] Parse note markdown through the existing Datalox note parser.
- [x] Inject final note content into the loop through the existing wrapper path.
- [x] Keep read/apply tracking unchanged.

## Phase 1: Extract The Native Backend

- [x] Move current direct note retrieval out of `resolveLocalKnowledge()`.
- [x] Define a small backend interface for direct note retrieval only.
- [x] Keep the interface minimal:
  - query input
  - retrieved note candidates
  - backend name
- [x] Implement `native` by reusing the existing logic from:
  - `scoreNote()`
  - `explainNoteMatch()`
  - direct note fallback in `resolveLocalKnowledge()`
- [x] Keep current behavior as the default path.

## Phase 2: Add Backend Selection

- [x] Add a retrieval config surface to the pack config:
  - `retrieval.notesBackend = "native" | "qmd"`
- [x] Default to `native`.
- [x] Thread this selection through:
  - `resolveLocalKnowledge()`
  - `resolveLoop()`
  - CLI resolve surfaces
  - MCP resolve surfaces
- [x] Keep skill matching and note injection unchanged.

## Phase 3: Keep Skill-Linked Retrieval Primary

- [x] Preserve current skill scoring as the first retrieval stage.
- [x] Preserve loading of `skill.notePaths` as the first note source.
- [x] Do not replace skill-linked notes with QMD search results.
- [x] Allow direct-note retrieval only when:
  - no skill matched
- [x] Keep this initial pass conservative:
  - no supplemental-note merge logic
  - no heuristic “note set is insufficient” logic

## Phase 4: Add QMD As An Optional Direct-Note Backend

- [x] Integrate QMD through its CLI first, not MCP.
- [x] Use:
  - `qmd query ... --json`
- [x] Do not depend on QMD for note parsing or injection.
- [x] QMD only returns candidate paths and scores.
- [x] Datalox still:
  - maps returned files back to repo-relative note paths
  - parses note markdown
  - builds `whyMatched`
  - injects note fields into the loop

## Phase 5: Add Repo-Scoped Index Management

- [x] Scope QMD collections per repo.
- [x] Do not use a single global collection for all repos.
- [x] Start by indexing:
  - `removed-wiki-store/notes/`
- [x] Leave `removed-wiki-store/docs/` for later, when that surface is real.
- [x] Add one Datalox-managed sync command:
  - `datalox retrieval sync`
- [x] Sync:
  - ensures QMD is installed
  - creates or refreshes the repo note collection

## Phase 6: Keep Query Construction Simple

- [x] Build one direct-note query text from:
  - `workflow`
  - matched `skillId` when present
  - `task`
  - `step`
- [x] Keep the first version simple and deterministic.
- [x] Do not add LLM-generated query expansion inside Datalox in this phase.

## Phase 7: Preserve Note Usage Tracking

- [x] `resolveLoop()` still increments:
  - `read_count`
  - `last_read_at`
- [x] Successful managed runs still increment:
  - `apply_count`
  - `last_applied_at`
- [x] This tracking works for:
  - skill-linked notes
  - direct notes returned by `native`
  - direct notes returned by `qmd`

## Phase 8: Preserve Event Compilation Boundary

- [x] Retrieval changes do not change:
  - raw event capture
  - event compilation into notes
  - note promotion into skills
- [x] QMD does not become a source of truth for notes.
- [x] `removed-wiki-store/notes/` remains the source of truth.

## Phase 9: CLI And MCP Surfaces

- [x] Keep public surfaces small.
- [x] Add only what is necessary:
  - backend selection config
  - retrieval sync command
- [x] Do not add a separate public retrieval product surface.
- [x] Do not expose QMD-specific details in the core user flow unless necessary.

## Phase 10: Tests

- [x] Native retrieval tests keep current behavior.
- [x] Add tests proving:
  - skill-linked notes stay primary
  - direct note fallback still works under `native`
  - direct note fallback works under `qmd`
  - read/apply tracking still updates note metadata under both backends
  - retrieval backend swap does not change event compilation semantics
- [x] Add one integration test for repo-scoped QMD sync.
- [x] Add one integration test for direct note retrieval through QMD JSON output.

## Acceptance Criteria

- [x] `native` remains the default and matches current behavior.
- [x] `qmd` can be enabled without changing note or skill schemas.
- [x] Skill-linked note retrieval remains primary.
- [x] Direct note retrieval works under `qmd`.
- [x] The wrapped loop still injects parsed note content, not just file paths.
- [x] Note read/apply tracking still works end to end.
- [x] Event -> note -> skill compilation remains unchanged.

## Non-Goals

- [x] No vector database owned by Datalox in this pass.
- [x] No cloud retrieval service in this pass.
- [x] No replacement of skills with free-form search.
- [x] No separate memory browser or second wiki system.
- [x] No broad `removed-wiki-store/docs/` retrieval until that surface is actually adopted.
