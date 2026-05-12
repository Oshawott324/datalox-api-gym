# TODO

Completed items were moved to:

- [docs/completed-todo-items.md](/Users/yifanjin/datalox-pack/docs/completed-todo-items.md)

That doc now holds:

- completed skill-boundary work
- completed concrete implementation steps
- completed pass-criteria proofs
- completed bootstrap-payload-shape work
- completed setup and partial-adoption recovery work
- completed native Codex active-session provenance work
- completed Claude Code surface provenance work

## Session-First Product Alignment

- [x] Goal: make approved agent sessions the source data asset and keep `debugging_trajectory.v1` rows as compact derivatives.
  Implementation:
  - update product docs to use the pipeline `agent run -> AgentTurnV1 events -> session/episode assembly -> export/redaction gate -> approved session dataset -> optional trajectory/eval rows`
  - define `AgentTurnV1` as the simple per-turn capture primitive
  - use this user-facing capture copy:
    - "Datalox captured this agent session. It includes prompts, tool actions, file edits, and verification results. You can keep it private, review it, or share approved anonymized sessions with your organization/data program."
  - keep `debugging_trajectory.v1` as the compact training/eval row contract, not the only sellable unit
  - keep unapproved raw traces out of sellable exports
  - keep legacy `skill` and `note` promotion as internal host guidance only
  Pass criteria:
  - `docs/product-definition.md`, `README.md`, `START_HERE.md`, `DATALOX.md`, and `docs/agent-configuration.md` agree that approved sessions are the source asset
  - `docs/agent-turn-schema.md` defines the per-turn capture shape without adding compliance-heavy fields
  - `docs/trajectory-dataset-schema.md` says the row is a compact derivative, not the complete source session
  - no product-facing doc says a perfect trajectory row is required before the captured session has value

- [x] Step 8.5: move future product event storage out of `agent-wiki/events`.
  Intent:
  - stop treating the legacy agent wiki event folder as the future product data store
  - keep old `agent-wiki/events` rows readable for legacy traces and migration
  - make repo-local `.datalox/` the visible product evidence root for agents and users
  Storage boundary:
  - new turn events: `.datalox/events/agent-turns/`
  - new trajectory row events: `.datalox/events/trajectory-rows/`
  - future review candidates: `.datalox/session-candidates/`
  - future approval/block records: `.datalox/approvals/`
  - legacy traces: `agent-wiki/events/` read-only for future product work
  Implementation:
  - update `record_trajectory` / `recordTrajectory` to write new `debugging_trajectory.v1` events under `.datalox/events/trajectory-rows/`
  - keep trajectory export and grading deterministic across both `.datalox/events/trajectory-rows/` and legacy `agent-wiki/events/`
  - allow `repair_trajectory` to repair legacy event paths but write corrected rows to `.datalox/events/trajectory-rows/`
  - update wrapper default trajectory capture expectations to use `.datalox/events/trajectory-rows/`
  - update docs and instruction surfaces so new product work targets `.datalox/`
  Pass criteria:
  - recording a trajectory row returns an event path under `.datalox/events/trajectory-rows/`
  - invalid trajectory rows create no `.datalox/events/trajectory-rows/` files
  - exporting trajectories includes both new `.datalox` rows and legacy `agent-wiki/events` rows
  - grading can target a single `.datalox` row and can still scan legacy rows
  - repairing a legacy row writes the repaired row under `.datalox/events/trajectory-rows/`
  - focused trajectory and wrapper tests pass

- [ ] Step 9: add per-turn capture and an explicit approved session bundle export path.
  Intent:
  - record useful agent work per completed turn without ingesting whole raw host transcripts
  - sell/review approved anonymized sessions directly instead of forcing every buyer workflow through compact trajectory rows
  - keep trajectory rows as a derived package for evals and training examples
  Implementation:
  - define a runtime `agent_turn.v1` schema from `docs/agent-turn-schema.md`
  - add a dedicated MCP tool named `record_agent_turn`
  - input should be `repo_path` plus one `AgentTurnV1` object
  - validate the turn before writing an event
  - write a normal event under `.datalox/events/agent-turns/` with `eventKind: "agent_turn"` and `payload.agentTurn`
  - return `{ eventPath, turnId, sessionId, exportable, blockedReasons }`
  - do not infer a turn from arbitrary prose-only summaries when structured tool/action data is absent
  - keep full raw logs, long command outputs, screenshots, and long diffs path-linked instead of inline by default
  - define a small `agent_session_bundle.v1` export artifact assembled from turn ids, prompts, tool calls, file edits, verification results, outcome labels, source event paths, and export/redaction status
  - add deterministic export filtering for approved/anonymized sessions
  - expose session export as a separate CLI/MCP surface from `export-trajectories`
  - derive `debugging_trajectory.v1` rows from approved session bundles only when compact training/eval packaging is needed
  Pass criteria:
  - `record_agent_turn` appears in the MCP tool list and can be called by an agent without CLI wrappers
  - a minimal turn from `docs/agent-turn-schema.md` records successfully
  - recorded events contain `payload.agentTurn.schema_version === "agent_turn.v1"`
  - invalid turn input creates no event file and returns field-level errors an agent can fix
  - turn events do not inline raw session JSONL, hidden reasoning, credentials, full files, or long command output
  - session export can include a captured session even when no `debugging_trajectory.v1` row exists yet
  - session export excludes turns/events with blocked export or redaction status
  - session export is deterministic for the same event directory
  - session export includes turn ids or event paths for provenance
  - trajectory export still works as a derivative path

- [ ] Step 10: add a lightweight session approval surface without turning MCP into a UI.
  Intent:
  - make approval visible and understandable for non-technical users before any session becomes shareable
  - keep MCP as the capture/control API, not the human review interface
  - avoid building a heavy SaaS dashboard before the review data model is stable
  Product boundary:
  - MCP owns candidate listing, approval commands, blocking commands, and approved export
  - the UI/report owns human review of "what will be shared"
  - filesystem or server-side approval records remain the source of truth
  Implementation:
  - add session candidate statuses: `private`, `needs_review`, `approved`, `blocked`
  - generate a local review artifact per candidate session, initially Markdown or static HTML
  - show plain-language sections for prompt, assistant summary, tool calls, file changes, verification, redaction status, and source event paths
  - include the user-facing copy:
    - "Datalox captured this agent session. It includes prompts, tool actions, file edits, and verification results. You can keep it private, review it, or share approved anonymized sessions with your organization/data program."
  - add CLI/MCP control surfaces after candidate export exists:
    - `list_session_candidates`
    - `approve_session`
    - `block_session`
    - `export_approved_sessions`
  - make approval write a durable approval record instead of mutating the captured `agent_turn.v1` evidence
  - keep automatic upload disabled unless an org policy explicitly enables it for approved sessions
  Pass criteria:
  - a non-technical reviewer can open one generated report and understand what would be shared
  - approving or blocking a session creates a separate durable decision record with reviewer, timestamp, session id, and decision
  - blocked sessions never appear in approved export
  - approved export includes only sessions with approval records and non-blocked redaction state
  - MCP tools expose approval actions but do not render or own UI state
  - the first UI surface can be local static HTML/Markdown; no full dashboard is required for MVP

## Trajectory Export Derivative Alignment

- [x] Goal: converge this repo on one derivative pipeline for `debugging_trajectory.v1` dataset rows.
  Implementation:
  - keep the row pipeline as `agent_turn.v1 events -> approved session bundle -> verified trajectory row -> curated dataset/eval corpus`
  - make Datalox MCP the first-class trajectory generation surface
  - keep [docs/trajectory-dataset-schema.md](docs/trajectory-dataset-schema.md) as the row contract
  - keep legacy `skill` and `note` promotion as internal host guidance only
  - route trajectory export behavior through structured events and `debugging_trajectory.v1` rows
  - do not add another repo-local knowledge page type
  Pass criteria:
  - product docs, agent instruction surfaces, and TODO agree on the B2B session-first pipeline plus trajectory row derivative
  - no product-facing doc reintroduces `trace -> note -> skill -> better future action` as a product loop
  - new product work references `docs/trajectory-dataset-schema.md` before adding row fields

- [x] Step 0: ship the MCP-first trajectory generation path as soon as possible.
  Intent:
  - let an agent produce `debugging_trajectory.v1` rows through Datalox MCP immediately after a debugging run
  - keep the path separate from legacy `trace -> note -> skill` promotion
  - optimize for a small number of high-quality rows now, not a broad data platform later
  Implementation:
  - add a dedicated MCP tool named `record_trajectory`
  - input should be `repo_path` plus one `DebuggingTrajectoryV1` row object
  - validate the row with `parseDebuggingTrajectoryV1`
  - write a normal event under `.datalox/events/trajectory-rows/` with `eventKind: "trajectory_row"` and `trajectoryRow`
  - return `{ eventPath, trajectoryId, sellable, blockedReasons }`
  - set or append `trajectoryRow.export.source_event_paths` to include the event path after write
  - do not call `promote_gap`, `compileRecordedEvent`, note generation, or skill generation from this MCP tool
  - if the row is valid but not sellable, still record it with `sellable: false`
  - if the row is invalid, fail before writing an event and return field-level errors that another agent can fix
  - add a short agent instruction snippet in docs: after a debugging run, build the row from observed task, context, steps, final fix, verification, and export gate, then call `record_trajectory`
  Pass criteria:
  - `record_trajectory` appears in the MCP tool list and can be called by an agent without using CLI wrappers
  - a minimal row from [docs/trajectory-dataset-schema.md](docs/trajectory-dataset-schema.md) records successfully
  - recorded events contain `trajectoryRow.schema_version === "debugging_trajectory.v1"`
  - the tool returns the repo-local event path and row id
  - `export.allowed: false` records the row but returns `sellable: false`
  - `export.redaction: "blocked"` records the row but returns `sellable: false`
  - invalid row input creates no event file
  - no `skills/` or `agent-wiki/notes/` files are created or modified by `record_trajectory`
  - row recording works in a dirty worktree and does not require git clean state
  - one smoke test records at least three synthetic debugging rows through the MCP tool and exports them to JSONL
  - the smoke test uses local fixtures only: no paid model, no real desktop UI, no network

- [x] Step 1: add a runtime schema module for the lean row.
  Implementation:
  - create `src/core/trajectorySchema.ts`
  - define `DebuggingTrajectoryV1` from `docs/trajectory-dataset-schema.md`
  - use a structured validator, preferably `zod`, for the exact required fields
  - export `parseDebuggingTrajectoryV1(input)` for strict validation
  - export `isSellableTrajectoryRow(row)` for the small export gate
  - export `toTrajectoryJsonlLine(row)` so JSONL formatting is centralized
  - reject unknown `schema_version`, missing required fields, empty `trajectory`, empty `final.fix_summary`, and invalid enum values
  - treat `export.allowed: false` and `export.redaction: "blocked"` as non-sellable, not as schema-shape failures
  Pass criteria:
  - `tests/trajectorySchema.test.ts` covers the minimal valid example from the schema doc
  - missing `task.prompt`, `trajectory`, `final.fix_summary`, `outcome`, or `export` fails validation
  - `outcome.verification: "not_run"` and `"reviewed"` are accepted when explicitly set
  - `export.allowed: false` validates as a row but fails `isSellableTrajectoryRow`
  - `export.redaction: "blocked"` validates as a row but fails `isSellableTrajectoryRow`
  - schema-doc JSON example parses in the test

- [x] Step 2: add explicit trajectory row capture into recorded events.
  Implementation:
  - extend `recordTurnResult` input and shared CLI/MCP command metadata with an optional trajectory row source
  - support one clear input path first: `--trajectory-row <json-file>` for CLI and `trajectoryRow` for MCP/native calls
  - store valid row candidates inside the recorded event payload as `trajectoryRow`
  - set `trajectoryRow.export.source_event_paths` to include the recorded event path after write
  - do not infer a row from arbitrary `summary`, `observations`, or `transcript` prose
  - if the row candidate is invalid, fail the record call with validator errors that an agent can fix
  Pass criteria:
  - recording with `--trajectory-row sample.json --json` writes a product event containing `trajectoryRow` under `.datalox/events/trajectory-rows/`
  - invalid row input fails before writing an event
  - source event paths include the event file that owns the row candidate
  - existing `datalox record`, `patch`, `promote`, wrappers, and MCP tools continue to work without trajectory row input

- [x] Step 3: add the trajectory export module.
  Implementation:
  - create `src/core/trajectoryExport.ts`
  - read `.datalox/events/trajectory-rows/*.json` and legacy `agent-wiki/events/*.json` in deterministic timestamp/path order
  - collect only explicit `trajectoryRow` candidates from `.datalox/events/trajectory-rows/` plus legacy `payload.trajectoryRow` candidates when present
  - validate every candidate with `parseDebuggingTrajectoryV1`
  - write sellable rows to JSONL only when `isSellableTrajectoryRow(row)` passes
  - return a structured report with counts: scanned events, candidate rows, exported rows, blocked rows, invalid rows
  - include rejection reasons with event paths for agent repair
  - keep detailed consent, license, provenance, and audit evidence in source events or curation systems, not required row fields
  Pass criteria:
  - export output is deterministic for the same event directory
  - blocked rows are reported but not written to sellable JSONL
  - invalid candidates fail the export unless `--allow-invalid` is explicitly added later
  - duplicate `id` values fail export with both source event paths listed
  - output contains one valid `DebuggingTrajectoryV1` object per line and no wrapper array

- [x] Step 4: add the CLI surface.
  Implementation:
  - add `datalox export-trajectories --repo <path> --output <path> [--include-blocked-report <path>] [--json]`
  - wire CLI logic through `src/core/trajectoryExport.ts`, not directly through `src/cli/main.ts`
  - create parent directories for `--output`
  - default output path can be `exports/trajectories/debugging_trajectory.v1.jsonl` only when `--output` is omitted
  - print a concise agent-readable report in JSON mode
  - do not mutate source events during export
  Pass criteria:
  - `node dist/src/cli/main.js export-trajectories --repo <fixture> --output <tmp>/rows.jsonl --json` exits 0 for valid fixtures
  - command writes JSONL rows and a structured JSON report
  - command exits nonzero with actionable errors for invalid candidates
  - command exits 0 with `exportedRows: 0` when no candidates exist
  - help text lists the new command

- [x] Step 5: add curation packaging without burdening the agent.
  Implementation:
  - keep buyer-facing split, quality, and tags in optional `curation`
  - add `--split <train|validation|test|eval>` only as an export-time override if needed
  - never require agents to classify pattern taxonomies during normal debugging work
  - keep curation rules deterministic and file-based
  Pass criteria:
  - rows without `curation` still export
  - export-time split assignment does not rewrite source events
  - curation metadata stays optional in schema tests

- [x] Step 6: isolate legacy skill/note promotion from product export.
  Implementation:
  - identify all paths that still write or promote `skill` and `note`
  - keep them available for host guidance while wrappers still need them
  - prevent trajectory export code from depending on note/skill promotion output
  - only include skill/note references when they already exist as optional curation tags or metadata
  - document the eventual removal/isolation point after row capture replaces legacy promotion for product work
  Pass criteria:
  - exporter tests pass in a fixture repo with no `skills/` and no `agent-wiki/notes/`
  - existing skill/note promotion tests still pass
  - no trajectory schema required field references `skill`, `note`, or `knowledge_feedback`
  - product docs keep note/skill promotion labeled as legacy/internal

- [x] Step 7: add focused end-to-end fixtures and tests.
  Implementation:
  - add fixture events under test temp directories, not committed generated runtime output
  - include one valid sellable row
  - include one blocked row with `export.allowed: false`
  - include one blocked row with `export.redaction: "blocked"`
  - include one invalid candidate with a missing required field
  - include one duplicate-id case
  Pass criteria:
  - `npm run build` passes
  - `npx vitest run tests/trajectorySchema.test.ts tests/trajectoryExport.test.ts` passes
  - existing focused wrapper/record tests still pass where touched
  - `node dist/src/cli/main.js lint --repo . --json` remains `ok`
  - no test requires real network, real desktop UI, or a paid model

- [x] Step 8: make recorded trajectory rows training-grade while staying token-small.
  Intent:
  - convert wrapper/MCP rows from "schema-valid evidence receipts" into high-signal training/eval examples
  - keep the row lean enough for buyers and agents to consume without replaying full transcripts
  - avoid over-using agents; use deterministic checks first and one focused agent review only for semantic judgment
  Training-grade row requirements:
  - include the actual bug/failure signal in `context.error` or `context.notes`
  - include only the relevant code snippets in `context.relevant_files.before/after`, not prose-only summaries
  - include `final.patch` when a diff is available; otherwise include concrete changed files plus why no patch exists
  - include 3-20 concise trajectory steps covering inspection, conclusion, edit, and verification
  - include tool steps for meaningful commands with `tool`, `command`, `exit_code`, and a short result summary
  - include verification evidence that names the tests/checks and result, not just "passed"
  - set `curation.quality: "needs_review"` by default; upgrade to `"use"` only after an agent reviewer accepts it
  Token-saving rules:
  - store raw command output, long diffs, screenshots, or transcripts as source artifacts by path, not inline in the row
  - keep inline snippets to the minimum needed to understand the fix
  - prefer unified diff hunks over full files
  - keep tool evidence to the command, exit code, and the 1-3 lines that prove the result
  - link source event paths and artifact paths in `export.source_event_paths` or optional metadata
  Review workflow:
  - deterministic validator checks schema, export blockers, patch presence, snippet presence, command evidence, and token budget
  - a single focused reviewer agent runs only when deterministic checks pass but semantic quality still needs judgment
  - reviewer agent uses a budget/cheap model by default, configurable by env or CLI
  - skip reviewer calls when deterministic checks already produce blocking diagnostics
  - use expensive models only for explicitly requested curation audits
  - reviewer returns structured diagnostics; it does not rewrite rows directly
  - repair is a separate explicit step that writes a new corrected trajectory row event
  - curation quality starts as `needs_review`; deterministic pass plus reviewer approval can upgrade it to `use`
  - do not run separate builder, reviewer, redaction, and curation agents for every row by default
  Implementation:
  - add a training-readiness checklist doc for `debugging_trajectory.v1`
  - add an agent-readable `trajectory_grade` result object with `quality`, `blocking_issues`, `repair_actions`, and `token_notes`
  - add CLI/MCP support to grade existing `trajectoryRow` events without rewriting them by default
  - add a repair mode that writes a new corrected trajectory row event instead of mutating the original evidence event
    - CLI: `datalox repair-trajectory --repo <path> --event-path <event-json> --trajectory-row <json-file> --json`
    - MCP: `repair_trajectory`
    - corrected rows link the original event path in `export.source_event_paths` and `metadata.datalox_repaired_from_event_path`
  - update wrapper guidance so default row capture marks rows `needs_review` unless a reviewer already accepted them
  Concrete implementation details:
  - create `docs/trajectory-training-readiness.md`
    - define training-grade vs schema-valid vs exportable
    - include compact good/bad row examples
    - document token budgets for snippets, patch, tool evidence, and metadata
  - create `src/core/trajectoryGrade.ts`
    - export `gradeTrajectoryRow(row, options)` for pure deterministic checks
    - export `gradeRecordedTrajectoryEvent(eventPayload, options)` for event-envelope use
    - never call models from this module
    - return stable issue codes suitable for agents to repair
  - define result shape:
    ```ts
    type TrajectoryGradeV1 = {
      schema: "datalox.trajectory_grade.v1";
      trajectory_id: string;
      quality: "use" | "needs_review" | "discard";
      exportable: boolean;
      deterministic_passed: boolean;
      reviewer_required: boolean;
      blocking_issues: Array<{
        code: string;
        path: string;
        message: string;
        repair_action: string;
      }>;
      warnings: Array<{
        code: string;
        path: string;
        message: string;
      }>;
      token_notes: {
        estimated_row_chars: number;
        largest_field_path?: string;
        largest_field_chars?: number;
        over_budget: boolean;
      };
    };
    ```
  - deterministic issue codes should include:
    - `missing_patch_or_explanation`
    - `prose_only_relevant_file`
    - `missing_before_after_snippet`
    - `missing_meaningful_tool_step`
    - `verification_evidence_too_generic`
    - `trajectory_too_short`
    - `trajectory_too_long`
    - `row_over_token_budget`
    - `export_blocked`
  - add CLI command:
    - `datalox grade-trajectories --repo <path> [--event-path <path>] [--json]`
    - default scans explicit `trajectoryRow` events
    - prints a deterministic report with counts by quality and issue code
    - exits nonzero only for malformed events or invalid schema, not for `needs_review`
  - add MCP tool:
    - `grade_trajectories`
    - input: `repo_path`, optional `event_path`
    - output: same report as CLI
    - no note/skill promotion and no row mutation
  - add optional reviewer command later, separate from deterministic grading:
    - `datalox review-trajectory --repo <path> --event-path <path> --model <budget-model>`
    - runs only when deterministic grade has `reviewer_required: true` and no blocking issues
    - reviewer output can recommend `quality: "use"` but cannot directly mutate the event
  - add curation filter to export:
    - optional `--quality use|needs_review|discard`
    - default product packaging should use `--quality use`
    - raw export for internal debugging may omit the filter
  - add tests with fixture rows, not live model calls
  - keep model-backed review behind an explicit env gate such as `DATALOX_LIVE_REVIEW=1`
  Pass criteria:
  - the current dogfood row is graded `needs_review`, not `"use"`, because it lacks real patch/snippets
  - a fixture row with real before/after snippets, patch, concise tool evidence, and passed verification grades `"use"`
  - a row with prose-only before/after summaries gets actionable diagnostics
  - a row with no patch and no explanation gets actionable diagnostics
  - grading does not require paid models; tests use deterministic fixtures or cheap-model live smoke only when explicitly enabled
  - export can still emit valid rows, but curated buyer packaging can filter to `curation.quality === "use"`
  Extended pass criteria:
  - `npm run build` passes
  - `npx vitest run tests/trajectoryGrade.test.ts tests/trajectoryExport.test.ts` passes
  - `grade-trajectories` returns `scannedEvents`, `candidateRows`, `useRows`, `needsReviewRows`, `discardRows`, and `issueCounts`
  - `grade-trajectories --event-path <trajectory-event>` grades exactly one row
  - invalid `trajectoryRow` returns schema diagnostics with file path and field path
  - deterministic grade does not mutate the source event
  - deterministic grade does not write notes, skills, or curation artifacts
  - the MCP `grade_trajectories` tool is available on the lean trajectory MCP surface
  - `repair-trajectory` writes a new linked row event and leaves the original event byte-for-byte unchanged
  - `export-trajectories --quality use` excludes `needs_review` rows
  - token budget checks flag oversized `final.patch`, oversized snippets, and oversized metadata independently
  - a row can be `exportable: true` and still `quality: "needs_review"`
  - expensive reviewer model is never invoked unless the explicit env/CLI gate is set

- [x] Step 8.6: enforce standalone exported trajectory rows.
  Intent:
  - make `debugging_trajectory.v1` rows usable for training/eval without access to the original repo checkout
  - treat file paths, source event paths, and artifact paths as provenance labels only, not required context
  - keep rows compact, but ensure the bug, edit, and verification can be understood from the exported JSONL line itself
  Standalone row contract:
  - `context.relevant_files[].path` identifies where the snippet came from, but buyers must not need to open that file
  - `context.relevant_files[].before` and `after` contain exact minimal code snippets for the behavior being fixed
  - `final.patch` may contain compact unified diff hunks, but must not contain placeholder ellipses or "see file" references
  - when no patch is available, `final.explanation` must explain the fix using the embedded snippets and changed file labels
  - `outcome.evidence` must name the verification command/check and the observed result
  - `export.source_event_paths` links audit evidence and repair lineage only
  Implementation:
  - update `docs/trajectory-dataset-schema.md`
    - add a "Standalone Export Contract" section near Product Meaning
    - state that exported JSONL rows must carry enough inline context to train/evaluate without repo access
    - state that `path`, `changed_files`, `source_event_paths`, and artifact paths are provenance labels only
    - update the minimal example so verification evidence is specific, not "Tests passed."
  - update `docs/trajectory-training-readiness.md`
    - add a self-contained row checklist before the token budget section
    - add a bad example where snippets say "see src/file.ts" or only list paths
    - add a good example where source paths exist but inline snippets explain the fix
    - document that optional source/audit bundles are separate from the default JSONL product
  - update `src/core/trajectoryGrade.ts`
    - keep existing checks for missing snippets, prose-only snippets, placeholder snippets, placeholder patches, generic verification, and token budget
    - add deterministic `not_self_contained` blocking diagnostics when the row's only fix evidence depends on external repo/source-event access
    - add helper functions rather than broad heuristics, for example:
      - `hasMeaningfulSnippetPair(file)` returns true only when both snippets exist, look code-like, are not placeholders, and are not external-reference-only
      - `isExternalReferenceOnly(value)` catches standalone evidence such as `see src/foo.ts`, `open agent-wiki/events/...`, `refer to source_event_paths`, `see repo`, or `see attached file`
      - `hasStandaloneTrainingPayload(row)` requires at least one meaningful snippet pair plus either `final.patch` or a concrete `final.explanation`
    - keep source paths allowed when they accompany real inline evidence
    - keep TypeScript spread syntax and normal prose safe; do not flag `...(row.curation ?? {})`
  - update `tests/trajectoryGrade.test.ts`
    - add a row with only file paths / "see file" explanations and assert `not_self_contained`
    - add a row with `source_event_paths` plus real inline snippets and assert it still grades `use`
    - add a row with no patch but a concrete explanation grounded in snippets and assert it can pass
    - keep the placeholder patch/snippet regression test from Step 8
  - update `tests/trajectoryExport.test.ts`
    - add or adjust an export fixture so `export-trajectories --quality use` exports only standalone `quality: "use"` rows
    - ensure rows with `quality: "needs_review"` or blocking self-containment issues are not part of buyer-facing fixture output
  - re-grade real dogfood data after the stricter rule:
    - legacy weak row: `agent-wiki/events/2026-05-04T05-54-50-295Z--trajectory-traj-training-grade-gate-20260504.json`
    - repaired row: `.datalox/events/trajectory-rows/2026-05-05T03-34-18-639Z--trajectory-traj-training-grade-gate-repaired-20260505.json`
    - repair the repaired row again only if it fails the stricter rule for a concrete reason
  - keep optional source/audit bundles separate from the default JSONL export contract
  Deterministic issue behavior:
  - `not_self_contained`
    - path: `context.relevant_files` when no meaningful inline before/after pair exists
    - path: `final.explanation` when the explanation only points to source files/events/artifacts
    - repair action: add compact exact before/after snippets or a concrete explanation grounded in those snippets
  - existing issue codes should still fire first when more precise:
    - `missing_before_after_snippet` for absent snippet fields
    - `prose_only_relevant_file` for prose summaries posing as snippets
    - `placeholder_relevant_file` / `placeholder_patch` for ellipses and placeholder hunks
    - `verification_evidence_too_generic` for "passed", "ok", or equivalent
  - self-containment must not require a full patch, full file, full transcript, or repo checkout
  Pass criteria:
  - docs say paths are provenance only and inline snippets plus trajectory plus verification are the training payload
  - the legacy weak dogfood row fails grading because it contains placeholder evidence
  - the repaired `.datalox/events/trajectory-rows/...traj-training-grade-gate-repaired...json` row grades `quality: "use"` under the stricter standalone rule
  - `export-trajectories --quality use` emits rows understandable without opening `agent-wiki/events`, `.datalox/events`, or source files
  - tests cover a row that has file paths but no meaningful inline snippets and expect `not_self_contained`
  - tests cover a valid standalone row with compact exact snippets and passed verification
  - tests cover `source_event_paths` as allowed provenance when inline evidence is sufficient
  - tests cover `final.explanation` with "see file/source event" as insufficient when no patch is present
  - tests cover concrete `final.explanation` as sufficient when it is grounded in inline snippets
  - `node dist/src/cli/main.js grade-trajectories --repo . --event-path agent-wiki/events/2026-05-04T05-54-50-295Z--trajectory-traj-training-grade-gate-20260504.json --json` reports a blocking issue on the weak legacy row
  - `node dist/src/cli/main.js grade-trajectories --repo . --event-path .datalox/events/trajectory-rows/2026-05-05T03-34-18-639Z--trajectory-traj-training-grade-gate-repaired-20260505.json --json` reports `useRows: 1`, `issueCounts: {}`, and no warnings
  - `node dist/src/cli/main.js export-trajectories --repo . --quality use --output /tmp/debugging_trajectory.v1.use.jsonl --json` succeeds and emits only standalone rows
  - `npx vitest run tests/trajectoryGrade.test.ts tests/trajectoryExport.test.ts` passes
  - `npm run check` passes
  - `git diff --check` passes

- [x] Step 8.7: tighten trajectory row builder guidance and capture-time quality normalization.
  Intent:
  - reduce variance where one agent emits real code snippets and another emits prose summaries for the same row shape
  - keep `record_trajectory` permissive enough to store weak-but-valid rows for repair, but prevent weak rows from pretending to be accepted training data
  - make the builder path produce Step 8.6-style standalone rows before export-time gating catches failures
  Problem signal:
  - older generated rows can be higher quality than newer rows when the agent chooses prose summaries for `context.relevant_files.before/after`
  - Step 8.6 protects buyer-facing export, but capture still trusts an agent-provided `curation.quality: "use"` until grade/export time
  - target repos installed from GitHub may not have local unpublished Step 8.6 guidance, so installer docs must make version/source state obvious
  Capture-time contract:
  - `record_trajectory` should still validate schema and write valid rows, including weak rows, because weak rows are repair candidates
  - when a row claims `curation.quality: "use"`, recording should run deterministic `gradeTrajectoryRow`
  - if deterministic grade is not `use`, recording should either downgrade `curation.quality` to `needs_review` with metadata or reject only when an explicit strict flag is set
  - the default should favor downgrade over rejection so agents do not lose evidence
  - `export-trajectories --quality use` remains the buyer-facing hard gate
  Implementation:
  - update `src/core/trajectoryExport.ts` record path or shared row-normalization helper
    - after schema parse, run `gradeTrajectoryRow` when `curation.quality === "use"`
    - if grade is not `use`, set `curation.quality: "needs_review"`
    - add metadata such as `datalox_quality_downgraded_from: "use"`, `datalox_quality_downgrade_issue_codes`, and `datalox_quality_downgraded_at`
    - avoid circular imports if needed by moving grade-independent row quality helpers into a small module
  - update MCP/CLI return payload for `record_trajectory`
    - include `quality`, `deterministicPassed`, and `qualityDowngraded` so the agent immediately sees that the row needs repair
    - keep existing `sellable` and `blockedReasons`
  - update row-builder guidance in docs and instruction surfaces
    - `docs/trajectory-training-readiness.md`: add a "Builder Instructions" section with "before/after must be exact code, not summaries"
    - `docs/trajectory-dataset-schema.md`: cross-link the builder rule from the standalone contract
    - `AGENTS.md` / `DATALOX.md` / README if they tell agents how to produce rows
  - update install guidance
    - README should state that already-running Codex/Cursor sessions do not hot-load newly installed MCP tools
    - README should state that GitHub install uses the published remote; local unpushed changes are not present in fresh target repos
    - include a short post-install check for `which codex`, `node bin/datalox.js status --repo ... --json`, and fresh wrapped session
  - update tests
    - a schema-valid row with prose `before/after` and `curation.quality: "use"` records, but stored row has `curation.quality: "needs_review"` and downgrade metadata
    - a standalone high-quality `use` row records without downgrade
    - CLI `record-trajectory --json` reports the downgrade fields
    - MCP `record_trajectory` reports the downgrade fields
    - export `--quality use` still excludes downgraded rows
  Pass criteria:
  - weak prose-snippet rows are never stored as `curation.quality: "use"` by default recording
  - high-quality standalone rows can still be stored as `curation.quality: "use"`
  - agents receive immediate structured feedback when their row was downgraded and why
  - no raw valid evidence is lost just because it is not training-grade yet
  - README install docs explain restart/reconnect and published-vs-local source behavior
  - focused tests pass: `npx vitest run tests/trajectoryGrade.test.ts tests/trajectoryExport.test.ts`
  - install/wrapper tests touched by README or record payload changes pass
  - `npm run check` passes
  - `git diff --check` passes

- [x] Step 8.8: design and implement `agent_task_trajectory.v1` for mixed-domain task episodes.
  Intent:
  - support real agent episodes that mix coding, shell commands, docs, spreadsheets, web/PDF evidence, analysis, and domain workflows in one task
  - avoid mutating `debugging_trajectory.v1` or adding ad hoc fields such as `context.code_snippets`
  - keep one generic trajectory envelope with strict domain-specific evidence blocks
  - make the schema useful for B2B session-derived training/eval data outside pure coding/debugging
  Schema boundary:
  - `debugging_trajectory.v1` remains the narrow coding/debugging row and keeps its current strict shape
  - `agent_task_trajectory.v1` is a new row schema, not a silent variant of `debugging_trajectory.v1`
  - generic does not mean arbitrary JSON: `evidence_blocks[]` must be a discriminated union with known `type` values and strict per-type fields
  - `task.domains[]` names the task domains because real work is mixed, and `task.workflows[]` should name the concrete workflow labels when known
  - every exported row must still be standalone: evidence blocks carry the minimal before/after, command, document, measurement, or source evidence needed to understand the task without opening the original repo/session
  Proposed envelope:
  ```ts
  type AgentTaskTrajectoryV1 = {
    schema_version: "agent_task_trajectory.v1";
    id: string;
    created_at: string;
    task: {
      prompt: string;
      domains: string[];
      workflows?: string[];
      environment?: string;
    };
    context?: {
      problem?: string;
      notes?: string[];
    };
    evidence_blocks: AgentTaskEvidenceBlockV1[];
    trajectory: Array<{
      role: "user" | "agent" | "tool";
      content: string;
      tool?: string;
      command?: string;
      exit_code?: number;
      artifacts_changed?: string[];
    }>;
    final: {
      summary: string;
      changed_artifacts?: string[];
      explanation?: string;
    };
    outcome: {
      label: "success" | "failure" | "partial";
      verification: "passed" | "failed" | "not_run" | "reviewed";
      evidence?: string;
    };
    export: {
      allowed: boolean;
      redaction: "none_needed" | "applied" | "blocked";
      source_event_paths?: string[];
    };
    curation?: {
      quality?: "use" | "needs_review" | "discard";
      tags?: string[];
      split?: "train" | "validation" | "test" | "eval";
      notes?: string;
    };
    metadata?: Record<string, unknown>;
  };
  ```
  Initial evidence block types:
  - `code_change`
    - fields: `type`, `path`, optional `language`, optional `symbol`, `before`, `after`, optional `patch`, optional `reason`
    - requires either exact `before` plus `after`, or a compact exact `patch`
  - `command_result`
    - fields: `type`, `command`, `exit_code`, `result_summary`, optional `evidence`, optional `artifact_paths`
    - requires a non-empty command, numeric exit code, and concrete result summary
  - `document_change`
    - fields: `type`, `artifact`, optional `format`, `before`, `after`, optional `section`, optional `reason`
    - for docs, slides, contracts, protocols, or markdown where source evidence is textual
  - `spreadsheet_change`
    - fields: `type`, `artifact`, optional `sheet`, optional `range`, `before`, `after`, optional `formula`, optional `validation`
    - for tabular edits, formulas, CSV/XLSX transformations, or financial/model sheets
  - `data_analysis`
    - fields: `type`, `artifact`, `question`, `method`, `result`, optional `input_summary`, optional `code_ref`, optional `validation`
    - for analysis tasks where the evidence is method/result, not a file diff
  - `lab_workflow`
    - fields: `type`, `workflow`, optional `assay`, `measurement_context`, `before`, `after`, optional `criteria`, optional `validation`
    - for biotech/lab episodes such as gating, sample QC, protocol interpretation, or assay review
  - `source_reference`
    - fields: `type`, `source_kind: "web" | "pdf" | "local_file"`, `title`, optional `source_path`, optional `url`, optional `excerpt`, optional `relevance`
    - for compact evidence excerpts; source links are provenance, not the only payload, and buyer-facing `quality: "use"` export requires excerpt plus relevance
  Implementation:
  - create `docs/agent-task-trajectory-schema.md`
    - state that this is the generic mixed-domain derivative row
    - explicitly say `debugging_trajectory.v1` is unchanged and still preferred for pure coding/debugging rows
    - include one mixed coding + command example and one non-code domain example
    - document that `context.code_snippets` is not part of either schema; code evidence belongs in a `code_change` evidence block or in `debugging_trajectory.v1.context.relevant_files`
  - create `src/core/agentTaskTrajectorySchema.ts`
    - define strict zod schemas for `AgentTaskTrajectoryV1` and each evidence block type
    - export `parseAgentTaskTrajectoryV1`, `isSellableAgentTaskTrajectoryRow`, and `toAgentTaskTrajectoryJsonlLine`
    - reject unknown top-level fields and unknown evidence block fields
    - reject unknown evidence block `type` values
  - create `src/core/agentTaskTrajectoryExport.ts`
    - record events under `.datalox/events/agent-task-trajectories/`
    - read only `.datalox/events/agent-task-trajectories/*.json` for the new export path
    - write one `agent_task_trajectory.v1` JSON object per JSONL line
    - keep source events immutable and repair by writing linked corrected events later
  - add CLI and MCP surfaces:
    - `record-agent-task-trajectory`
    - `export-agent-task-trajectories`
    - optional later: `grade-agent-task-trajectories`
    - do not reuse `record_trajectory` for this schema; keep names explicit so agents do not mix row contracts
  - add deterministic grade/readiness checks before buyer export:
    - non-empty `evidence_blocks`
    - every evidence block has type-specific concrete evidence
    - code/document/spreadsheet/lab before/after fields are not prose-only placeholders
    - source_reference excerpts cannot be only a URL/path
    - command_result evidence names the command, exit code, and observed result
    - export blockers are honored
    - token budgets flag oversized patches, excerpts, and metadata
  - update product docs after the schema exists:
    - `docs/product-definition.md` should describe `agent_task_trajectory.v1` as the mixed-domain derivative row
    - `docs/trajectory-dataset-schema.md` should remain the canonical narrow debugging row and link to the generic schema only as a separate contract
    - `README.md` / `DATALOX.md` should tell agents to pick the narrow debugging schema for pure code-debugging and the generic schema for mixed-domain episodes
  - add fixtures and tests only; no live model calls, network, or desktop UI
  Pass criteria:
  - `debugging_trajectory.v1` validation remains unchanged and still rejects unknown `context.code_snippets`
  - a valid `agent_task_trajectory.v1` row with both `code_change` and `command_result` evidence validates and records under `.datalox/events/agent-task-trajectories/`
  - a valid non-code row with `lab_workflow` and `source_reference` evidence validates without requiring code fields
  - empty `evidence_blocks` is rejected
  - unknown evidence block `type` is rejected
  - unknown fields inside an evidence block are rejected
  - `source_reference` with only a URL/path and no excerpt/relevance fails readiness grading
  - `code_change` evidence with prose-only before/after fails readiness grading
  - export excludes `export.allowed: false` and `redaction: "blocked"` rows
  - export is deterministic for the same `.datalox/events/agent-task-trajectories/` directory
  - `record_trajectory` and `export-trajectories` behavior for `debugging_trajectory.v1` does not change
  - no new `agent-wiki/events/` product writes are introduced
  - focused tests pass:
    - `npx vitest run tests/agentTaskTrajectorySchema.test.ts tests/agentTaskTrajectoryExport.test.ts tests/trajectorySchema.test.ts tests/trajectoryExport.test.ts`
  - `npm run check` passes
  - `git diff --check` passes

- [x] Step 8.9: make trajectory export repair-lineage aware before duplicate-id rejection.
  Intent:
  - allow `repair_trajectory` to keep immutable evidence events without breaking buyer-facing export
  - keep hard duplicate detection for unrelated same-id rows
  - ensure `export-trajectories --quality use` exports the final accepted repair, not every failed repair attempt
  - make stale installed-pack mismatches visible when diagnosing trajectory capture/export behavior
  Problem signal:
  - one task can legitimately produce multiple events with the same `trajectoryRow.id`:
    - original row downgraded to `needs_review`
    - one or more repair attempts also downgraded
    - final repaired row graded `curation.quality: "use"`
  - current export checks duplicate ids before quality filtering and training-grade filtering
  - result: `export-trajectories --quality use` fails on duplicate ids even when only the final repaired row is exportable
  - observed dogfood case:
    - `/Users/yifanjin/datalox-ui-v3-china/.datalox/events/trajectory-rows/2026-05-06T13-46-15-112Z--trajectory-traj-skill-schema-driven-trading-no-inference-20260506.json`
    - `/Users/yifanjin/datalox-ui-v3-china/.datalox/events/trajectory-rows/2026-05-06T13-46-41-076Z--trajectory-traj-skill-schema-driven-trading-no-inference-20260506.json`
    - `/Users/yifanjin/datalox-ui-v3-china/.datalox/events/trajectory-rows/2026-05-06T13-47-24-263Z--trajectory-traj-skill-schema-driven-trading-no-inference-20260506.json`
    - `/Users/yifanjin/datalox-ui-v3-china/.datalox/events/trajectory-rows/2026-05-06T13-47-52-647Z--trajectory-traj-skill-schema-driven-trading-no-inference-20260506.json`
  Root causes:
  - `repair_trajectory` writes a new immutable event with the same `trajectoryRow.id` and `metadata.datalox_repaired_from_event_path`
  - `exportTrajectories` calls duplicate detection before applying `--quality use` and before deterministic `gradeTrajectoryRow`
  - an installed target repo can have stale `datalox-trajectory-mcp` CLI code, making the active capture/export surface unclear
  Implementation:
  - update `src/core/trajectoryExport.ts`
    - keep schema validation before any filtering
    - build a repair-lineage index from `metadata.datalox_repaired_from_event_path`
    - treat rows referenced by a later repair event as superseded for export-candidate selection
    - apply export blockers, requested curation-quality filter, and `--quality use` deterministic grade filter before duplicate-id failure
    - run duplicate-id failure only against remaining export candidates
    - keep duplicate-id failure for unrelated same-id rows that are not connected by repair lineage
    - include rejected superseded rows in the report with a stable reason such as `superseded_by_repair`
    - keep deterministic ordering by event timestamp/path
  - update `tests/trajectoryExport.test.ts`
    - fixture: original `needs_review` row plus repaired `use` row with same id exports only the repaired row under `--quality use`
    - fixture: original row plus multiple failed repairs plus final `use` row exports only the final row
    - fixture: two unrelated `use` rows with the same id still fail duplicate detection
    - fixture: repair lineage pointing to a missing event does not silently mask unrelated duplicates
    - fixture: export report lists superseded repair-chain rows with source event paths
  - update CLI/status diagnostics if needed
    - status should make the active pack root and installed pack commit/source obvious enough for agents to spot stale target installs
    - README should recommend checking `node datalox-trajectory-mcp/bin/datalox.js status --repo <target> --json` and command availability after install/update
  Pass criteria:
  - `export-trajectories --quality use` succeeds for a repair chain where only the final repaired row grades `use`
  - exported JSONL contains exactly one row for a repaired trajectory id: the latest non-superseded row that passes quality and grade filters
  - `needs_review` original rows and failed repair attempts do not block buyer-facing `--quality use` export
  - unrelated same-id `use` rows still fail with `duplicate_id`
  - reports include stable rejection reasons for `quality_filter`, `training_grade_filter`, and `superseded_by_repair`
  - legacy `agent-wiki/events` rows remain readable but are not selected over a newer `.datalox/events/trajectory-rows` repair
  - focused tests pass:
    - `npx vitest run tests/trajectoryExport.test.ts`
  - dogfood command succeeds after patch:
    - `node bin/datalox.js export-trajectories --repo /Users/yifanjin/datalox-ui-v3-china --quality use --output /tmp/ui-v3-china-use.jsonl --json`
  - `npm run check` passes
  - `git diff --check` passes

- [x] Step 8.10: tighten `agent_task_trajectory.v1` readiness for code-heavy agent-company rows.
  Intent:
  - make mixed-domain trajectory rows useful for agent behavior distillation, not just high-level execution summaries
  - prevent code-heavy tasks from passing buyer-facing `quality: "use"` export when they only contain command results and prose source references
  - keep raw sessions as audit/source material, while requiring canonical rows to carry enough standalone code evidence for training/eval derivation
  Problem signal:
  - observed real row:
    - `.datalox/events/agent-task-trajectories/2026-05-08T03-58-36-334Z--agent-task-trajectory-traj-flowcyto-ship-ready-alpha-milestone6-20260508.json`
  - the row changed many code artifacts but had no `code_change` evidence block
  - `source_reference` entries pointed to local code files but their `excerpt` values were prose summaries, not exact code snippets
  - `export.source_event_paths` mixed source file paths with `.datalox/events/...` event paths
  - a buyer cannot understand or train on the actual code edits without opening the repo or raw session
  Data product rule:
  - raw sessions may contain `sed`, `apply_patch`, diffs, and tool outputs, but they are noisy source/audit material
  - `agent_task_trajectory.v1` is the canonical compact row and must be self-contained enough for buyer-specific exports
  - code-heavy rows must use `code_change` for code evidence; `source_reference` to a code file is provenance only
  - `export.source_event_paths` must contain event paths only; source files belong in `context.source_paths` and `final.changed_artifacts`
  Implementation:
  - update `src/core/agentTaskTrajectoryExport.ts`
    - add a helper such as `rowAppearsCodeHeavy(row)`:
      - true when `task.domains[]` includes coding-like domains (`coding`, `typescript`, `javascript`, `python`, `rust`, `mcp_apps`, `worker_threads`, `packaging`, etc.)
      - true when `final.changed_artifacts`, `context.source_paths`, or trajectory artifacts include code/test/package paths or extensions (`.ts`, `.tsx`, `.js`, `.py`, `.rs`, `package.json`, `src/`, `tests/`)
    - add `hasConcreteCodeChangeEvidence(row)`:
      - true only when at least one `code_change` block has exact `before`+`after` snippets or exact `patch`
      - reject prose-only, placeholder, path-only, or source-reference-only code evidence using the existing readiness helpers
    - in `gradeAgentTaskTrajectoryRow`, when `rowAppearsCodeHeavy(row)` and no concrete code change evidence exists, add blocking issue:
      - `code_heavy_row_missing_code_change`
      - path: `evidence_blocks`
      - repair action: add compact exact `code_change` before/after snippets or patch hunks for the key edit
    - validate `export.source_event_paths` semantics during readiness:
      - add `export_source_event_path_not_event` when a path does not start with `.datalox/events/`
      - do not fail schema validation for old rows; fail buyer-facing readiness/export `--quality use`
    - validate `source_reference` to local code files:
      - if `source_kind: "local_file"` and `source_path` looks like code/test/package path, the block cannot satisfy code evidence
      - if its `excerpt` is prose-only for a code file, add a readiness issue such as `source_reference_prose_only_code_excerpt`
  - update `src/core/agentTaskTrajectorySchema.ts` only if needed:
    - keep schema permissive enough to record weak rows as `needs_review`
    - do not add arbitrary fields or `context.code_snippets`
  - update `docs/agent-task-trajectory-schema.md`
    - state that code-heavy rows require at least one `code_change` evidence block before `quality: "use"` export
    - state that local code `source_reference` blocks are provenance/context and do not replace `code_change`
    - state that `export.source_event_paths` must only list `.datalox/events/...` provenance events
    - add a bad/good mini example for a local code source reference versus a real `code_change`
  - update `DATALOX.md` and `README.md`
    - tell agents recording mixed-domain implementation work to include exact code snippets/patches in `code_change`
    - tell agents to put source file paths in `context.source_paths` / `changed_artifacts`, not `export.source_event_paths`
  - update tests in `tests/agentTaskTrajectoryExport.test.ts`
    - fixture matching the FlowCyto failure mode:
      - code-heavy domains + many `src/`/`tests/` changed artifacts
      - only `command_result` + prose `source_reference`
      - `curation.quality: "use"`
      - export `--quality use` rejects with `readiness_filter` and issue code `code_heavy_row_missing_code_change`
    - fixture with exact `code_change` before/after plus command result passes `--quality use`
    - fixture with `export.source_event_paths` containing `src/core/preview.ts` rejects buyer-ready export with `export_source_event_path_not_event`
    - fixture with `export.source_event_paths` containing only `.datalox/events/...` passes when other evidence is sufficient
    - fixture proves local code `source_reference` prose excerpt does not count as code evidence
  Pass criteria:
  - code-heavy agent task rows without `code_change` evidence cannot export under `export-agent-task-trajectories --quality use`
  - code-heavy rows with exact `code_change` evidence and command verification can export under `--quality use`
  - source references to code files do not satisfy code evidence
  - `export.source_event_paths` rejects source files and accepts only `.datalox/events/...` paths for buyer-ready export
  - weak rows remain recordable as `needs_review`; they are not lost
  - focused tests pass:
    - `npx vitest run tests/agentTaskTrajectoryExport.test.ts tests/agentTaskTrajectorySchema.test.ts`
  - existing debugging trajectory tests still pass:
    - `npx vitest run tests/trajectoryExport.test.ts tests/trajectorySchema.test.ts`
  - `npm run check` passes
  - `git diff --check` passes
  Follow-up fix:
  - 2026-05-11: record-time normalization now also applies to `agent_task_trajectory.v1`.
    If a code-heavy mixed-domain row claims `curation.quality: "use"` but lacks
    concrete `code_change` evidence, `record-agent-task-trajectory` /
    `record_agent_task_trajectory` stores it as `needs_review` with downgrade
    metadata and returns `qualityDowngraded: true`.

- [x] Step 8.11: stop shipping `agent-wiki/` as a first-class trajectory-product artifact.
  Intent:
  - make the trajectory-product branch install cleanly without presenting `agent-wiki/` as the active product store
  - keep old repos readable, but stop teaching fresh agents to write product data or primary guidance through `agent-wiki/`
  - reduce confusion between legacy note/skill promotion and the current `.datalox/events/` session/trajectory product loop
  Product boundary:
  - `.datalox/events/` is the product data store
  - `.datalox/events/agent-turns/` is for turn capture
  - `.datalox/events/trajectory-rows/` is for `debugging_trajectory.v1`
  - `.datalox/events/agent-task-trajectories/` is for `agent_task_trajectory.v1`
  - `agent-wiki/events/` is legacy read-only compatibility only
  - useful stable agent guidance should live in `DATALOX.md`, `AGENTS.md`, and `docs/`; `skills/` is legacy/local guidance unless explicitly requested
  Implementation:
  - update install/adoption behavior:
    - inspect and patch `bin/adopt-host-repo.sh`
    - inspect and patch `src/core/packCore.ts`
    - inspect and patch `scripts/lib/agent-pack.mjs` only where fresh adoption copies or creates wiki artifacts
    - fresh trajectory-product adoption should not create or copy `agent-wiki/events/`
    - fresh trajectory-product adoption should not copy the seed `agent-wiki/` corpus unless explicitly requested by a legacy mode flag
  - keep legacy read compatibility:
    - `export-trajectories` may continue to read legacy `agent-wiki/events/` for old debugging rows
    - maintenance/legacy commands may read existing `agent-wiki/notes/` only when the repo already has them or when legacy mode is explicit
    - do not delete a host repo's existing `agent-wiki/` during adoption
  - update command names and help text if needed:
    - make legacy write surfaces visibly legacy, for example `record-legacy-event`
    - ensure `datalox record --help`, `status`, and other introspection commands are read-only
    - keep product writes explicit through `record-trajectory`, `record-agent-task-trajectory`, and future `record-agent-turn`
  - update docs:
    - `README.md`
    - `DATALOX.md`
    - `AGENTS.md`
    - `docs/product-definition.md`
    - `docs/task-orchestration.md`
    - state that fresh product installs do not ship `agent-wiki/` as the active store
    - state that legacy repos may still have `agent-wiki/` and agents may read it for compatibility
  - update tests:
    - adoption/bootstrap test: fresh trajectory-product install creates `.datalox/` and expected instruction surfaces, but does not create `agent-wiki/events/`
    - adoption/bootstrap test: fresh product install does not copy seed `agent-wiki/` corpus by default
    - legacy compatibility test: existing `agent-wiki/events/` debugging rows remain readable by `export-trajectories`
    - help/status test: `datalox record --help` or equivalent help path does not write events
    - product recording test: `record-trajectory` and `record-agent-task-trajectory` still write only under `.datalox/events/...`
  Pass criteria:
  - a fresh adopted repo for the trajectory-product branch has no generated `agent-wiki/events/`
  - fresh adoption does not ship the seed `agent-wiki/` corpus by default
  - existing host `agent-wiki/` content is preserved and readable, not deleted
  - legacy `agent-wiki/events/` rows can still be exported when present
  - no help/status/introspection command writes a legacy event
  - product writes continue to use only `.datalox/events/`
  - focused tests pass:
    - adoption/bootstrap tests touched by the install behavior
    - `npx vitest run tests/trajectoryExport.test.ts tests/agentTaskTrajectoryExport.test.ts`
  - `npm run check` passes
  - `git diff --check` passes


## Refactor `agent-pack.mjs`

- [ ] Goal: split `scripts/lib/agent-pack.mjs` into smaller modules without behavior drift.
  This is a boundary-extraction refactor, not a redesign.
  Do not change the runtime contract, promotion rules, retrieval policy, or live loop semantics as part of the split.

- [x] Step 1: inventory the current responsibilities inside `scripts/lib/agent-pack.mjs`.
  Identify and pin the main seams:
  - frontmatter / markdown parsing
  - skill/note read models
  - retrieval and candidate shaping
  - adjudication packet shaping
  - promotion decision compiler
  - event/note/skill write paths
  - lint / pack maintenance helpers

- [x] Step 2: extract parsing helpers into a read-only module first.
  Target examples:
  - `splitFrontmatter`
  - `parseFrontmatter`
  - `parseSkillDoc`
  - `parseNoteDoc`
  Requirements:
  - no output-shape changes
  - no frontmatter compatibility changes
  - CRLF handling must stay intact
  Completed first pass:
  - extracted markdown/frontmatter parsing into `scripts/lib/agent-pack/markdown.mjs`
  - kept `scripts/lib/agent-pack.mjs` as the compatibility surface for existing script imports
  - added focused parser and export-contract coverage in `tests/agentPackMarkdown.test.ts`

- [ ] Step 3: extract retrieval into its own module.
  Target examples:
  - candidate normalization helpers
  - note/skill lookup helpers
  - `resolveLocalKnowledge`
  Requirements:
  - no score/contract regressions
  - no retrieval-policy drift
  - `resolve` output must stay byte-for-byte compatible where possible

- [ ] Step 4: extract promotion/adjudication into its own module.
  Target examples:
  - `buildAdjudicationPacket`
  - stable promotion memory helpers
  - `decideAdjudicatedPromotion`
  - `recordTurnResult`
  - `compileRecordedEvent`
  Requirements:
  - keep the current skill-generation proof loop intact
  - do not reintroduce heuristic patch-vs-create logic
  - keep the note-stage and matched-note rules exactly as they work now

- [ ] Step 5: extract write surfaces into a persistence module.
  Target examples:
  - event file writes
  - note writes
  - skill writes
  Requirements:
  - preserve file locations
  - preserve generated frontmatter/content format
  - preserve provenance and log/index updates

- [ ] Step 6: extract lint/maintenance helpers last.
  Only move these after retrieval and promotion are already stable.
  Requirements:
  - no behavior cleanup mixed into the move
  - keep broken-link and missing-note checks intact

- [ ] Step 7: leave a thin compatibility surface in `scripts/lib/agent-pack.mjs`.
  It can become a barrel/orchestration file, but it should not keep growing as the default place for new logic.

- [ ] Constraint: no behavior rewrites inside the refactor.
  Specifically do not mix in:
  - retrieval redesign
  - new heuristics
  - prompt/protocol changes
  - note/skill schema changes
  - CLI/MCP contract renames

- [ ] Required proof after each extraction phase:
  - `npm run build`
  - `npx vitest run tests/bridgeSurfaces.test.ts tests/wrapperSurfaces.test.ts`
  - no regression in:
    - retrieval contract
    - enforcement loop
    - note promotion
    - skill creation

- [ ] Final pass criteria:
  1. `scripts/lib/agent-pack.mjs` is reduced to orchestration or thin exports, not a 4k+ line sink.
  2. The fresh-repo skill-generation proof documented in `docs/bootstrap-payload-shape-live-2026-04-23.md` still passes.
  3. Focused bridge/wrapper suites still pass.
  4. No runtime contract drift in:
     - `resolve`
     - `promote`
     - wrapper post-run payloads
     - MCP/CLI promotion surfaces


## Bootstrap Payload Shape

- Completed bootstrap payload work was moved to:
  - [docs/completed-todo-items.md](/Users/yifanjin/datalox-pack/docs/completed-todo-items.md)
  That includes:
  - problem confirmation
  - target contract
  - bootstrap split
  - minimal default seed set
  - removal of whole-tree adoption
  - focused proofs and pass criteria

- [ ] Make optional seed knowledge explicit.
  If the pack still ships extra example/domain skills, they should live behind a separate install path, not fresh-repo bootstrap.
  Examples:
  - example skills bundle
  - domain bundle
  - demo corpus
  But do not add a large new product surface unless needed; start with a small explicit split.


## Online Retrieval And Note Capture

- Completed online retrieval / note-capture work was moved to:
  - [docs/completed-todo-items.md](/Users/yifanjin/datalox-pack/docs/completed-todo-items.md)
  That includes:
  - authoritative match boundary tightening
  - candidate-only retrieval contract
  - bounded ambiguous-case adjudicator
  - note-safe online capture boundary
  - focused proofs and live validation
  6. periodic note-backed synthesis remains the primary path for creating new reusable skills


## Periodic Trace Maintenance And Skill Synthesis

- Completed maintenance-loop work was moved to:
  - [docs/completed-todo-items.md](/Users/yifanjin/datalox-pack/docs/completed-todo-items.md)
  Grounded live proof:
  - [docs/periodic-trace-maintenance-live-2026-04-25.md](/Users/yifanjin/datalox-pack/docs/periodic-trace-maintenance-live-2026-04-25.md)


## Same-Repo Session And Agent Bootstrap

- Completed same-repo bootstrap work was moved to:
  - [docs/completed-todo-items.md](/Users/yifanjin/datalox-pack/docs/completed-todo-items.md)
  Grounded live proof:
  - [docs/same-repo-bootstrap-live-2026-04-24.md](/Users/yifanjin/datalox-pack/docs/same-repo-bootstrap-live-2026-04-24.md)


## Claude Native Skill Installation

- Completed native skill installation work was moved to:
  - [docs/completed-todo-items.md](/Users/yifanjin/datalox-pack/docs/completed-todo-items.md)
  That includes:
  - per-skill canonical link installation
  - disable/uninstall for new link shape
  - status reporting for native skill surfacing
  - doc updates
  - focused proofs and live validation
  Grounded live proof:
  - [docs/claude-native-skill-install-live-2026-04-27.md](/Users/yifanjin/datalox-pack/docs/claude-native-skill-install-live-2026-04-27.md)


## Maintenance Defaults And Skill Synthesis Boundary

- Completed work was moved to:
  - [docs/completed-todo-items.md](/Users/yifanjin/datalox-pack/docs/completed-todo-items.md)
  That includes:
  - default note-only maintenance
  - smaller default scan window
  - explicit `--synthesize-skills`
  - focused proofs


## Event Backlog Visibility And Maintenance Nudges

- Completed work was moved to:
  - [docs/completed-todo-items.md](/Users/yifanjin/datalox-pack/docs/completed-todo-items.md)
  That includes:
  - shared backlog stats and policy evaluation
  - `status --json` backlog output
  - Claude hook and Codex wrapper warnings
  - `agent-wiki/hot.md` next-turn visibility
  - configurable composite backlog policy
  - focused proofs


## Singleton Trace Rollup And Non-Repeated Event Drainage

- Completed work was moved to:
  - [docs/completed-todo-items.md](/Users/yifanjin/datalox-pack/docs/completed-todo-items.md)
  That includes:
  - `summarized` trace drainage status
  - bounded singleton rollup notes under `agent-wiki/notes/`
  - explicit singleton note preservation when structured evidence exists
  - rollup exclusion from skill synthesis
  - 100+ singleton backlog proof


## Native Codex MCP Loop Enforcement

- Completed work was moved to:
  - [docs/completed-todo-items.md](/Users/yifanjin/datalox-pack/docs/completed-todo-items.md)
  Grounded live proof:
  - [docs/native-codex-session-provenance-live-2026-04-30.md](/Users/yifanjin/datalox-pack/docs/native-codex-session-provenance-live-2026-04-30.md)
  That includes:
  - explicit MCP-first guidance for native Codex
  - active-session `currentSession` status output
  - wrapper sentinel environment variables
  - tests that distinguish installed Codex enforcement from active wrapper provenance


## Claude Code Surface Provenance And Status Clarity

- [x] Goal: make Claude Code status and proof distinguish its four different Datalox surfaces instead of treating them as one enforcement story.
  Current live status shows:
  - Claude shim wrapper is not installed:
    - `adapters.claude.installed: false`
    - `adapters.claude.automatic: false`
  - Claude Stop hook is installed:
    - `adapters.claude.hookInstalled: true`
  - Claude native skill links are installed and canonical:
    - `~/.claude/skills/<skill-name>`
  - simulated Claude wrapper sentinels work:
    - `DATALOX_ACTIVE_WRAPPER=claude` makes `currentSession.wrapperEnforced: true`

  Required boundary:
  - `datalox claude` / Claude shim wrapper = enforceable pre-run guidance injection
  - Claude Stop hook = post-turn sidecar automation; it can record, compile, and maintain after a response, but cannot force pre-turn `resolve_loop`
  - Claude native skills = useful discovery surface, but still model-chosen and often restart-dependent
  - Claude MCP = guidance-only unless Claude Code actually calls the tools

- [x] Step 1: model Claude surfaces explicitly in status output.
  Target files:
  - `src/core/installCore.ts`
  - `src/adapters/capabilities.ts`
  - tests for install/status
  Requirements:
  - keep existing `adapters.claude` raw fields for compatibility
  - add an agent-readable Claude surface summary, for example:
    - `wrapper`: installed, automatic, active, pre-run enforced
    - `stopHook`: installed, post-turn sidecar, not pre-run enforced
    - `nativeSkills`: installed, canonical, restart-sensitive
    - `mcp`: available when detectable, guidance-only
  - do not mark Claude as active wrapper-enforced unless `currentSession.activeWrapper === "claude"` and `currentSession.wrapperEnforced === true`
  - explain when the hook is installed but the shim wrapper is not installed
  Pass criteria:
  - `datalox status --json` lets an agent answer "what can Datalox enforce in Claude Code right now?" without reading docs
  - live status no longer forces agents to infer behavior from `hookInstalled`, `nativeSkillLinks`, and `installed` separately

- [x] Step 2: add Claude-specific active-session detection and notes.
  Target files:
  - `src/core/installCore.ts`
  - `bin/datalox-claude.js`
  - `src/adapters/claude/run.ts`
  Requirements:
  - preserve the current sentinel behavior:
    - `DATALOX_ACTIVE_WRAPPER=claude`
    - `DATALOX_HOST_KIND=claude`
    - `DATALOX_ENFORCEMENT=wrapper`
  - detect active Claude wrapper enforcement from those sentinels
  - if no Claude wrapper sentinel is present, report native Claude Code as guidance-only or hook-backed, not wrapper-enforced
  - include a clear note that Stop-hook automation happens after the model turn
  Pass criteria:
  - simulated `DATALOX_ACTIVE_WRAPPER=claude ... datalox status --json` reports wrapper-enforced Claude
  - status without the wrapper sentinel can still report hook/native-skill availability without claiming pre-run enforcement

- [x] Step 3: document the Claude Code boundary in agent-facing guidance.
  Target files:
  - `CLAUDE.md`
  - `skills/use-datalox-through-host-cli/SKILL.md`
  - `agent-wiki/notes/use-datalox-through-host-cli.md`
  - optional live proof doc under `docs/`
  Requirements:
  - say that Claude Code has separate wrapper, hook, native skill, and MCP surfaces
  - say that the Stop hook is post-turn sidecar automation
  - say that native skills and MCP are model-chosen unless the wrapper is active
  - keep Datalox additive to Claude native skills; do not shadow or replace them
  Pass criteria:
  - a fresh Claude Code session can read the guidance and know whether it is wrapper-enforced, hook-backed, native-skill available, or MCP guidance-only

- [x] Step 4: add focused and live proofs.
  Target files:
  - `tests/adoptionScripts.test.ts`
  - `tests/wrapperSurfaces.test.ts`
  - `tests/hookIntegration.test.ts`
  - optional `docs/claude-code-surface-provenance-live-<date>.md`
  Requirements:
  - test status for Claude shim installed vs not installed
  - test hook installed but shim not installed
  - test canonical native skill links
  - test wrapper sentinel makes `currentSession.wrapperEnforced: true`
  - test hook path still records/compiles/maintains without pretending to be pre-run enforcement
  Pass criteria:
  - `npm run build`
  - focused status/install tests pass
  - focused Claude wrapper tests pass
  - focused Claude hook tests pass
  - live proof shows the four-surface boundary with concrete `status --json` excerpts

  Completed:
  - added `adapters.claude.surfaces.wrapper`, `stopHook`, `nativeSkills`, and `mcp` to `status --json`
  - kept raw `adapters.claude` fields for compatibility
  - documented the boundary in `CLAUDE.md`, `skills/use-datalox-through-host-cli/SKILL.md`, and `agent-wiki/notes/use-datalox-through-host-cli.md`
  - wrote live proof: [docs/claude-code-surface-provenance-live-2026-05-02.md](/Users/yifanjin/datalox-pack/docs/claude-code-surface-provenance-live-2026-05-02.md)
  - passed `npm run build`
  - passed `npx vitest run tests/adoptionScripts.test.ts tests/wrapperSurfaces.test.ts tests/hookIntegration.test.ts`


## Host Adapter Capability Profiles

- [ ] Goal: stop treating every non-Codex / non-Claude host as one generic adapter when the host has native instruction, skill, MCP, CLI, or hook surfaces.
  `generic_cli` should remain a fallback for unknown command-line agents, not the model for known hosts.

- [ ] Step 1: split host identity from execution mechanism.
  Target files:
  - `src/adapters/capabilities.ts`
  - `src/adapters/shared.ts`
  - `src/adapters/generic/run.ts`
  Requirements:
  - keep `generic_cli` for unknown placeholder-based wrapping
  - allow known hosts to reuse the generic wrapper internally while preserving their real `hostKind`
  - record provenance as `opencode`, `gemini`, `cursor`, etc. instead of collapsing to `generic`
  - status and post-run payloads expose the real host id
  Pass criteria:
  - a known-host wrapper can call shared/generic execution without producing `hostKind: "generic"`
  - existing generic CLI behavior remains unchanged for unknown hosts

- [ ] Step 2: add a host capability registry for known agents.
  Target files:
  - `src/adapters/capabilities.ts`
  - `src/core/installCore.ts`
  - `.datalox/manifest.json`
  Requirements:
  - define host profiles for at least:
    - `opencode`
    - `gemini`
    - `cursor`
    - `windsurf`
    - `copilot`
  - each profile declares:
    - instruction files / rule files it reads
    - native skill directory shape
    - MCP config shape when known
    - CLI command shape when known
    - hook/plugin support when known
    - enforcement level and whether prompt injection is actually enforceable
  - do not claim enforcement where the host only provides guidance surfaces
  Pass criteria:
  - `status --json` can explain what Datalox can and cannot enforce for each known host
  - missing or unsupported host surfaces produce agent-readable reasons

- [ ] Step 3: implement OpenCode first.
  Target files:
  - `src/adapters/capabilities.ts`
  - `src/core/installCore.ts`
  - `src/cli/main.ts`
  - tests for install/status
  Requirements:
  - support OpenCode project/global skills at documented paths:
    - `.opencode/skills/<name>/SKILL.md`
    - `~/.config/opencode/skills/<name>/SKILL.md`
  - preserve `AGENTS.md` as the committed project instruction baseline
  - support `opencode run` as the first CLI wrapper target if a wrapper is needed
  - inspect or configure OpenCode MCP/plugin surfaces only when the shape is explicit
  - fix or remove stale assumptions such as `~/.opencode/skills/datalox-pack` if current OpenCode docs do not support them
  Pass criteria:
  - OpenCode install/status can be tested without hiding under `generic_cli`
  - OpenCode provenance records as `hostKind: "opencode"`
  - docs say whether OpenCode setup is enforced, conditional, or guidance-only

- [ ] Step 4: keep service-backed mode dependent on accurate host identity.
  Requirements:
  - service-backed trace writes include real `hostKind` and stable `agentId` when available
  - host profile data feeds the service namespace / provenance contract
  - do not use service-backed mode to paper over weak host integration
  Pass criteria:
  - service-backed TODO steps can rely on known host identity instead of `generic`
  - traces from different hosts in the same repo remain distinguishable but share the same repo namespace


## Cross-Host Automatic Bounded Maintenance Trigger

- Completed work was moved to:
  - [docs/completed-todo-items.md](/Users/yifanjin/datalox-pack/docs/completed-todo-items.md)
  That includes:
  - shared automatic note-only maintenance helper
  - visible repo-local maintenance lock
  - Codex/generic wrapper wiring
  - Claude hook wiring
  - config/env controls
  - focused Codex and Claude proofs


## Service-Backed Shared Trace Plane

- Current foundation already exists:
  - `datalox maintain` / `maintain_knowledge` runs a bounded repo-local maintenance pass
  - current maintenance scans `agent-wiki/events/`
  - repeated unresolved traces compact into `agent-wiki/notes/`
  - covered events are marked so the same trace group does not keep re-promoting
  - note-backed skill synthesis runs only from existing notes, on an explicit later pass
  Service-backed work should reuse this materialization loop. Do not build a second note/skill promotion path.

- [ ] Goal: make `mode: "service_backed"` real so different agents and sessions can share traces, events, and coordination state for the same repo without turning notes and skills into a hidden global blob.
  The target boundary is:
  - shared/service-backed:
    - raw traces
    - recorded events
    - session state
    - leases / signals / checkpoints
    - maintenance coverage state
  - repo-owned:
    - `agent-wiki/notes/`
    - `skills/`
    - visible control artifacts
    - repo-local materialized reusable knowledge

- [ ] Step 1: define the service-backed boundary in config and docs.
  Ground it in the already-existing `service_backed` mode instead of inventing a parallel concept.
  Target files:
  - `.datalox/config.schema.json`
  - `.datalox/config.json`
  - `.datalox/manifest.json`
  - `docs/product-definition.md`
  Requirements:
  - `repo_only` stays the default
  - `service_backed` is documented as:
    - shared trace/event plane
    - repo-local note/skill materialization plane
  - do not describe the service as the primary durable home for notes or skills
  Pass criteria:
  - config schema can express the service-backed fields without ambiguity
  - docs explicitly say "agents share what happened; the repo owns what was learned"

- [ ] Step 2: add a stable repo identity and service namespace contract.
  The service must know when two sessions belong to the same repo and when they do not.
  Target files:
  - `src/domain/agentConfig.ts`
  - `src/agent/loadAgentConfig.ts`
  - `src/types/legacy-agent-pack.d.ts`
  - `scripts/lib/agent-pack.mjs`
  Add or clarify fields such as:
  - `repoId`
  - `workspaceRoot`
  - `branch` when available
  - `sessionId`
  - `agentId` / `hostKind`
  Requirements:
  - same repo from two agents resolves to the same service namespace
  - different repos cannot accidentally share traces
  - no heuristic matching for repo identity when a stable id is available
  Pass criteria:
  - two synthetic sessions with the same repo id land in the same trace namespace
  - a second repo with a different id does not see those traces

- [ ] Step 3: implement a service-backed trace/event client.
  This should be a real client surface, not a hidden fallback branch inside unrelated code.
  Target files:
  - `src/core/packCore.ts`
  - `src/adapters/shared.ts`
  - `src/cli/main.ts`
  - new dedicated module if needed, such as:
    - `src/core/serviceBackedTraceClient.ts`
  Requirements:
  - in `repo_only`, keep current local event behavior
  - in `service_backed`, record traces/events to the shared service using the repo namespace contract
  - agent-readable errors only; avoid human-first ceremony
  - do not silently fall back from service-backed writes to some hidden local substitute
  Pass criteria:
  - service-backed write path is exercised in tests
  - when the service rejects a write, the failure is explicit and attributable
  - `repo_only` behavior remains unchanged

- [ ] Step 4: teach retrieval and maintenance to read shared traces for the current repo.
  The online and maintenance loops must be able to see traces from other agents in the same repo.
  Target files:
  - `scripts/lib/agent-pack.mjs`
  - `src/core/packCore.ts`
  - `src/adapters/shared.ts`
  Requirements:
  - online capture can still stay cheap
  - the existing `maintainKnowledge` planner reads a bounded unresolved trace set from the service for the current repo
  - local `agent-wiki/events/` traces and service-backed traces use one normalized planner input shape
  - no cross-repo bleed
  - current local note/skill retrieval remains repo-local
  - do not create a parallel service-only maintenance loop
  Pass criteria:
  - agent A writes a trace in service-backed mode
  - agent B in a fresh session, same repo, can see that trace in `maintainKnowledge` planner input
  - agent C in a different repo cannot

- [ ] Step 5: keep existing periodic maintenance as the materialization boundary.
  Shared traces must feed the current maintenance loop, compact into repo-local notes first, then synthesize repo-local skills from note-backed evidence.
  Target files:
  - `scripts/lib/agent-pack.mjs`
  - `scripts/agent-maintain.mjs`
  - `src/surface/sharedCommands.ts`
  Requirements:
  - do not create global notes or global skills
  - service-backed traces compact into repo-local notes
  - note-backed synthesis stays the primary path for new skills
  - notes created during the current pass must stay excluded from skill synthesis until a later pass, matching current repo-local behavior
  - covered/compacted service events are marked so they do not keep exploding the maintenance input
  - `repo_only` continues to scan only local `agent-wiki/events/`
  Pass criteria:
  - two service-backed traces from two different agents in the same repo compact into one repo-local note
  - repeating the same maintenance run does not re-promote the same unresolved traces forever
  - a repeated reusable workflow can still synthesize one repo-local skill from note-backed evidence
  - the existing repo-local maintenance regression still passes unchanged

- [ ] Step 6: share coordination state across agents in service-backed mode.
  This is where leases, signals, or checkpoints belong if Datalox wants cross-agent coordination.
  Target files:
  - `src/core/packCore.ts`
  - `src/cli/main.ts`
  - `src/surface/sharedCommands.ts`
  Requirements:
  - coordination state is scoped by repo id
  - it remains optional and does not block trace sharing
  - do not mix coordination metadata into skill or note files
  Pass criteria:
  - two agents in the same repo can exchange one coordination artifact through the shared plane
  - the same call in a different repo namespace returns nothing

- [ ] Step 7: add one explicit status/doctor surface for service-backed mode.
  The system needs a visible way to say whether the shared plane is actually connected.
  Target files:
  - `src/cli/main.ts`
  - `src/core/packCore.ts`
  - `README.md`
  - `START_HERE.md`
  Requirements:
  - `status --json` must say whether:
    - service-backed mode is enabled
    - the shared trace plane is reachable
    - the current repo id is known
  - keep the output machine-readable first
  Pass criteria:
  - fresh service-backed repo returns a positive status with repo id + connectivity
  - broken connectivity returns a clear explicit failure state

- [ ] Step 8: prove it with a fresh multi-agent live test.
  Use cheap models where possible.
  Required live proof shape:
  1. fresh repo in `service_backed` mode
  2. agent/session A records a trace
  3. fresh agent/session B in the same repo sees that trace
  4. maintenance compacts shared traces into one repo-local note
  5. repeated note-backed evidence can synthesize one repo-local skill
  6. agent/session C in a different repo does not see repo A's traces
  Write the result into a dedicated live proof doc under `docs/`.

- [ ] Final pass criteria:
  1. `mode: "service_backed"` is a real implemented mode, not just a schema value.
  2. Multiple agents in the same repo can share traces/events without sharing raw chat state.
  3. Notes and skills still materialize into the repo filesystem, not a hidden global store.
  4. Periodic maintenance compacts shared traces into repo-local notes and then repo-local skills.
  5. No cross-repo trace bleed occurs.
  6. `repo_only` mode keeps its current local-only behavior.
