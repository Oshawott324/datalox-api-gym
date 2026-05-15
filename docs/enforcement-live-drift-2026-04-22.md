# Enforcement Live Drift - 2026-04-22

This note records grounded drift found in the real enforced Codex wrapper path.

Concrete follow-up plan:

- [enforcement-fix-plan.md](./enforcement-fix-plan.md)

It is intentionally narrower than retrieval drift:

- real `datalox codex` runs only
- fresh temp repos
- cheap live model
- minimal prompt context

## Setup

Real Codex binary used for all runs:

```bash
/Users/yifanjin/.cursor/extensions/openai.chatgpt-26.417.40842-darwin-arm64/bin/macos-aarch64/codex
```

All runs used:

- `node dist/src/cli/main.js codex`
- `-m gpt-5.4-mini`
- `--post-run-mode promote`

## Tasks Run

### 1. Fresh adopted repo, one-off control task

Repo:

- `/tmp/datalox-enforce-host-nXoE5q`

Command:

```bash
node dist/src/cli/main.js codex \
  --repo /tmp/datalox-enforce-host-nXoE5q \
  --post-run-mode auto \
  --codex-bin /Users/yifanjin/.cursor/extensions/openai.chatgpt-26.417.40842-darwin-arm64/bin/macos-aarch64/codex \
  --json -- \
  exec --skip-git-repo-check -m gpt-5.4-mini \
  "Read README.md and say one sentence about this repo."
```

### 2. Fresh adopted repo, explicit reusable wrapper-gap task

Repo:

- `/tmp/datalox-enforce-host-nXoE5q`

Command:

```bash
node dist/src/cli/main.js codex \
  --repo /tmp/datalox-enforce-host-nXoE5q \
  --task "debug repeated wrapper failure in unsupported host cli path" \
  --workflow repo_engineering \
  --skill repo-engineering.use-datalox-through-host-cli \
  --post-run-mode promote \
  --codex-bin /Users/yifanjin/.cursor/extensions/openai.chatgpt-26.417.40842-darwin-arm64/bin/macos-aarch64/codex \
  --json -- \
  exec --skip-git-repo-check -m gpt-5.4-mini \
  "The same unsupported host CLI path keeps failing under the wrapper. Explain the reusable correction for future agents in a short paragraph."
```

### 3. Fresh auto-bootstrapped repo, generic setup-gap task

Repo:

- `/tmp/datalox-gap-host-p3Lch1`

Command:

```bash
node dist/src/cli/main.js codex \
  --repo /tmp/datalox-gap-host-p3Lch1 \
  --post-run-mode promote \
  --codex-bin /Users/yifanjin/.cursor/extensions/openai.chatgpt-26.417.40842-darwin-arm64/bin/macos-aarch64/codex \
  --json -- \
  exec --skip-git-repo-check -m gpt-5.4-mini \
  "Inspect the repo setup instructions. If there is a reusable setup gap, explain the correction for future agents in one short paragraph."
```

The same command was run twice on the same repo.

## What Works

- the enforced Codex wrapper path does run end to end
- it records an event automatically
- it can create an operational note from a single strong run with no existing note

Produced artifacts:

- control event:
  - [reading-additional-input-from-stdin.json](/tmp/datalox-enforce-host-nXoE5q/removed-wiki-store/events/2026-04-22T14-28-23-945Z--reading-additional-input-from-stdin.json)
- explicit wrapper-gap note:
  - [repo-engineering-generic-wrapped-runs-abort-with-the-datalox-prompt-placeholder.md](/tmp/datalox-enforce-host-nXoE5q/removed-wiki-store/notes/repo-engineering-generic-wrapped-runs-abort-with-the-datalox-prompt-placeholder.md)
- generic setup-gap note:
  - [flow-cytometry-readme-uses-scripts-bootstrap-sh-and-agents-requires-docs-product.md](/tmp/datalox-gap-host-p3Lch1/removed-wiki-store/notes/flow-cytometry-readme-uses-scripts-bootstrap-sh-and-agents-requires-docs-product.md)

## Drift

### 1. Default workflow leaks into unrelated fresh-agent runs

In the generic setup-gap repo, the live run had no matched skill and no flow-cytometry task, but the enforced envelope still used:

- `selectionBasis: "repo_context"`
- `workflow: "flow_cytometry"`

That leaked into:

- event payload workflow
- note workflow
- note id/path
- tags

Actual artifact:

- [flow-cytometry-readme-uses-scripts-bootstrap-sh-and-agents-requires-docs-product.md](/tmp/datalox-gap-host-p3Lch1/removed-wiki-store/notes/flow-cytometry-readme-uses-scripts-bootstrap-sh-and-agents-requires-docs-product.md)

Expected:

- no unrelated default workflow on an unscoped repo-context run
- or a neutral workflow such as `unknown` / unset

### 2. Event summarization still captures Codex transport noise

The one-off control run recorded:

- title/summary from `Reading additional input from stdin...`

instead of from the actual child answer.

Actual artifact:

- [reading-additional-input-from-stdin.json](/tmp/datalox-enforce-host-nXoE5q/removed-wiki-store/events/2026-04-22T14-28-23-945Z--reading-additional-input-from-stdin.json)

Expected:

- event summaries should be derived from the child answer or explicit DATALOX markers
- Codex transport boilerplate and plugin/analytics warnings should not win

### 3. Linked note text can recursively expand `__DATALOX_PROMPT__`

The explicit `repo-engineering.use-datalox-through-host-cli` run surfaced a real wrapper bug:

- the linked note action contains `__DATALOX_PROMPT__`
- the wrapper replaces placeholders across the final child args
- the placeholder inside note text is expanded into the wrapped prompt itself

That causes prompt recursion in the child command/transcript.

Actual artifact:

- [clarify-generic-wrap-placeholder-contract.json](/tmp/datalox-enforce-host-nXoE5q/removed-wiki-store/events/2026-04-22T14-33-06-385Z--clarify-generic-wrap-placeholder-contract.json)

Expected:

- placeholder replacement should apply only to explicit command placeholders
- linked note prose should not be rewritten recursively

### 4. Note quality is only partly acceptable

The system did create notes, but the generated note shape is still rough:

- `kind: trace` on a promoted note
- `When to Use` is mostly a lowercased echo of the original prompt
- `Evidence` includes a noisy dump of repo root paths instead of compact grounded evidence
- workflow/tags may be wrong because of the default workflow leak

Example:

- [flow-cytometry-readme-uses-scripts-bootstrap-sh-and-agents-requires-docs-product.md](/tmp/datalox-gap-host-p3Lch1/removed-wiki-store/notes/flow-cytometry-readme-uses-scripts-bootstrap-sh-and-agents-requires-docs-product.md)

### 5. Repeated identical runs do not mature reliably

The first generic setup-gap run produced:

- `adjudicationDecision: create_operational_note`
- `decision.action: create_note_from_gap`

The second identical run on the same repo produced:

- `adjudicationDecision: record_trace`
- `decision.action: record_only`

So the same real task on the same repo did not stably progress toward a skill.

Actual artifacts:

- first event:
  - [stale-setup-entrypoints.json](/tmp/datalox-gap-host-p3Lch1/removed-wiki-store/events/2026-04-22T14-36-10-420Z--stale-setup-entrypoints.json)
- second event:
  - [stale-setup-entrypoints.json](/tmp/datalox-gap-host-p3Lch1/removed-wiki-store/events/2026-04-22T14-38-28-147Z--stale-setup-entrypoints.json)

Expected:

- repeated identical runs should at least be directionally stable
- if the first run is strong enough to create a note, the second identical run should not regress to `record_only`
- skill creation was not observed in these fresh-agent live runs

## Recommended Next Fixes

1. Stop inheriting unrelated default workflow into unscoped repo-context runs.
2. Sanitize Codex stderr boilerplate before summary/title extraction.
3. Restrict `__DATALOX_PROMPT__` replacement to explicit command placeholders, not note prose.
4. Tighten promoted note rendering:
   - better `When to Use`
   - compact evidence
   - correct note kind/workflow
5. Stabilize repeated adjudication so the same real run does not bounce between `create_operational_note` and `record_trace`.

## Validation After Fixes

Fresh real `datalox codex` runs were repeated after implementing fixes 1-3.

### Fixed

1. Unscoped repo-context runs no longer inherit `flow_cytometry` in the enforced envelope.
   - Fresh repos now show:
     - `selectionBasis: "repo_context"`
     - `workflow: "unknown"`
2. Summary/title extraction no longer uses `Reading additional input from stdin...`.
   - Fresh control runs now record the actual child answer as `summary` / `title`.
3. `__DATALOX_PROMPT__` no longer recursively expands inside the already-rendered wrapped prompt.
   - A fresh real Codex run with the literal prompt text:
     - `Mention __DATALOX_PROMPT__ literally once, then say done.`
   - preserved the literal token in both:
     - wrapped prompt
     - child stdout
   - without nesting a second wrapped prompt into the child command.

### Residual Drift

- Codex transport noise is no longer winning summary extraction, but large warning / HTML dumps still remain in stored `stderr` / transcript sections.
  - That is now a transcript hygiene issue, not a title/summary issue.

## Phase 1 Validation - 2026-04-23

Phase 1 from [enforcement-fix-plan.md](./enforcement-fix-plan.md) was implemented and re-tested through fresh real `datalox codex` runs with `gpt-5.4-mini`.

### Result

Weak retrieval candidates still appear, but they no longer assign authoritative workflow during post-run recording.

### Fresh live proof

#### 1. Generic repo-description control run

- repo: `/tmp/datalox-phase1-live-av9h5E`
- recorded:
  - `workflow: "unknown"`
  - `matchedSkillId: null`
- weak candidate still surfaced:
  - `web-capture.capture-web-knowledge`
  - `whyMatched: ["primary_term_overlap"]`

#### 2. Literal `__DATALOX_PROMPT__` run

- repo: `/tmp/datalox-phase1-literal-XSGOmW`
- recorded:
  - `workflow: "unknown"`
  - `matchedSkillId: null`
- weak candidate still surfaced:
  - `repo-engineering.use-datalox-through-host-cli`
  - `whyMatched: ["primary_term_overlap"]`

### Interpretation

This fixes the residual post-run workflow adoption bug from the previous live pass.

The remaining enforcement work is now:

1. stabilize repeated adjudication
2. fix promoted note semantics
3. tighten promoted note rendering
4. tighten transcript hygiene

## Phase 2 Validation - 2026-04-23

Phase 2 from [enforcement-fix-plan.md](./enforcement-fix-plan.md) was implemented and re-tested through fresh real `datalox codex` runs with `gpt-5.4-mini`.

### Result

Repeated identical runs no longer regress from promoted-note behavior back to trace-only behavior.

### Fresh live proof

#### Fresh repo

- repo: `/tmp/datalox-phase2-live-n1nfJr`

#### Command

```bash
node dist/src/cli/main.js codex \
  --repo /tmp/datalox-phase2-live-n1nfJr \
  --post-run-mode promote \
  --codex-bin /Users/yifanjin/.cursor/extensions/openai.chatgpt-26.417.40842-darwin-arm64/bin/macos-aarch64/codex \
  --json -- \
  exec --skip-git-repo-check -m gpt-5.4-mini \
  "Inspect the repo setup instructions. If there is a reusable setup gap, explain the correction for future agents in one short paragraph."
```

This exact command was run twice on the same fresh repo.

#### First run

- recorded:
  - `workflow: "unknown"`
  - `eventClass: "candidate"`
  - `adjudicationDecision: "create_operational_note"`
  - `decision.action: "create_note_from_gap"`
- note created:
  - [unknown-readme-md-agents-md-or-github-copilot-instructions-md-mention-scripts-bo.md](/tmp/datalox-phase2-live-n1nfJr/removed-wiki-store/notes/unknown-readme-md-agents-md-or-github-copilot-instructions-md-mention-scripts-bo.md)

#### Second identical run

- recorded:
  - `workflow: "unknown"`
  - `eventClass: "candidate"`
  - `adjudicationDecision: "record_trace"`
- compiled result:
  - `decision.action: "create_note_from_gap"`
  - `decision.reason: "an identical repeated run already established this reusable gap; do not regress to trace only."`
- note created:
  - [unknown-readme-md-references-scripts-bootstrap-sh-docs-product-definition-md-and.md](/tmp/datalox-phase2-live-n1nfJr/removed-wiki-store/notes/unknown-readme-md-references-scripts-bootstrap-sh-docs-product-definition-md-and.md)

### Interpretation

This satisfies the Phase 2 pass criterion:

- the same real wrapped run on the same repo no longer bounces backward from promoted-note behavior to `record_only`
- stable promotion memory now prevents regression even when the second run emits `record_trace`

### Residual Drift

Phase 2 fixed adjudication stability, but not note identity/rendering:

- the second identical run still wrote a different promoted note path because its explicit markers changed
- that is no longer an adjudication-regression bug
- it is now a later-phase note semantics/rendering issue

## Phase 3 Validation - 2026-04-23

Phase 3 from [enforcement-fix-plan.md](./enforcement-fix-plan.md) was implemented and re-tested through fresh real `datalox codex` runs with `gpt-5.4-mini`.

### Result

Promoted operational notes now carry the correct semantics:

- `kind: workflow_note`
- `workflow: "unknown"` when the run is unscoped
- stable promoted note identity across repeated identical real runs

### Fresh live proof

#### Fresh repo

- repo: `/tmp/datalox-phase3-live-HTAZrk`

#### Command

```bash
node dist/src/cli/main.js codex \
  --repo /tmp/datalox-phase3-live-HTAZrk \
  --post-run-mode promote \
  --codex-bin /Users/yifanjin/.cursor/extensions/openai.chatgpt-26.417.40842-darwin-arm64/bin/macos-aarch64/codex \
  --json -- \
  exec --skip-git-repo-check -m gpt-5.4-mini \
  "Inspect the repo setup instructions. If there is a reusable setup gap, explain the correction for future agents in one short paragraph."
```

This exact command was run twice on the same fresh repo.

#### First run

- promoted note:
  - `relativePath: removed-wiki-store/notes/unknown-inspect-the-repo-setup-instructions-if-there-is-a-reusable-setup-gap-exp.md`
  - `kind: "workflow_note"`
  - `workflow: "unknown"`
  - `title: "Canonical bootstrap entrypoints"`

#### Second identical run

- recorded:
  - `adjudicationDecision: "record_trace"`
- compiled result:
  - `decision.action: "create_note_from_gap"`
- promoted note:
  - same `relativePath` as the first run
  - same `kind: "workflow_note"`
  - same `workflow: "unknown"`
  - same stable title: `"Canonical bootstrap entrypoints"`

### Interpretation

This satisfies the Phase 3 pass criteria:

- promoted operational notes are no longer written as `kind: trace`
- note workflow stays correct or `unknown`
- note slug/title basis is grounded in the reusable gap and stays stable across repeated identical runs

### Residual Drift

Phase 3 fixed note semantics, but the next cleanup is still Phase 4:

- `When to Use` is still generic and template-shaped
- `Evidence` is still too large and path-dump heavy
- stored transcript/evidence still contains transport-warning residue

## Phase 4 Validation - 2026-04-23

Phase 4 from [enforcement-fix-plan.md](./enforcement-fix-plan.md) was implemented and re-tested through a fresh real `datalox codex` run with `gpt-5.4-mini`.

### Result

Promoted note rendering is now compact and grounded:

- `When to Use` is signal-first instead of a lowercased prompt echo
- `Evidence` is limited to the event path plus compact grounded observations
- placeholder bullets no longer persist into generated notes
- promoted note bodies stay small enough to inject back into later loops

### Fresh live proof

#### Fresh repo

- repo: `/tmp/datalox-phase4-live-AaVtH0`

#### Command

```bash
node dist/src/cli/main.js codex \
  --repo /tmp/datalox-phase4-live-AaVtH0 \
  --post-run-mode promote \
  --codex-bin /Users/yifanjin/.cursor/extensions/openai.chatgpt-26.417.40842-darwin-arm64/bin/macos-aarch64/codex \
  --json -- \
  exec --skip-git-repo-check -m gpt-5.4-mini \
  "Inspect the repo setup instructions. If there is a reusable setup gap, explain the correction for future agents in one short paragraph."
```

#### Promoted note

- note:
  - [unknown-inspect-the-repo-setup-instructions-if-there-is-a-reusable-setup-gap-exp.md](/tmp/datalox-phase4-live-AaVtH0/removed-wiki-store/notes/unknown-inspect-the-repo-setup-instructions-if-there-is-a-reusable-setup-gap-exp.md)
- size:
  - `1389` bytes

Key rendered lines:

- `## When to Use`
  - `When \`START_HERE.md\` and \`.datalox/manifest.json\` reference \`adopt-*\` scripts that do not exist.`
- `## Evidence`
  - `removed-wiki-store/events/2026-04-23T03-38-20-699Z--align-bootstrap-entrypoints.json`
  - one compact grounded observation bullet

What is no longer present:

- no `Use this note when inspect the repo setup instructions...`
- no placeholder bullets like `Add a concrete observed case here...`
- no repo-root path dump such as:
  - `.claude/`
  - `.cursor/`
  - `skills/`
  - `removed-wiki-store/`

### Interpretation

This satisfies the Phase 4 pass criteria:

- `When to Use` is no longer a prompt echo
- evidence is compact and grounded
- the promoted note body is small enough to reuse in later loops without obvious context bloat

### Residual Drift

Phase 4 fixes note rendering, but Phase 5 remains:

- stored event `stderr` / transcript payloads can still carry large Codex warning or HTML dumps
- that is now a transcript hygiene issue, not a promoted-note rendering issue

## Phase 5 Validation - 2026-04-23

Phase 5 from [enforcement-fix-plan.md](./enforcement-fix-plan.md) was implemented and re-tested through both focused wrapper tests and a fresh real `datalox codex` run with `gpt-5.4-mini`.

### Result

Stored event transcripts no longer carry the large Codex analytics/plugin warning dumps or embedded HTML bodies that previously dominated evidence.

The Phase 5 guarantees now hold:

- stored transcript/evidence sections do not contain the large warning / HTML dump
- real child error text still survives when it is the actual failure evidence

### Focused proof

The wrapper suite now includes explicit regression coverage for:

- dropping Codex plugin warning / HTML dumps from stored transcripts
- preserving a real failure line while stripping transport noise around it

### Fresh live proof

#### Fresh repo

- repo: `/tmp/datalox-phase5-live3-DRGTpu`

#### Command

```bash
node dist/src/cli/main.js codex \
  --repo /tmp/datalox-phase5-live3-DRGTpu \
  --post-run-mode auto \
  --codex-bin /Users/yifanjin/.cursor/extensions/openai.chatgpt-26.417.40842-darwin-arm64/bin/macos-aarch64/codex \
  --json -- \
  exec --skip-git-repo-check -m gpt-5.4-mini \
  "Read README.md and say one sentence about this repo."
```

#### Recorded event

- event:
  - [there-s-no-readme-md-in-this-checkout-but-the-repo-is-a-datalox-portable-agent-p.json](/tmp/datalox-phase5-live3-DRGTpu/removed-wiki-store/events/2026-04-23T04-27-01-105Z--there-s-no-readme-md-in-this-checkout-but-the-repo-is-a-datalox-portable-agent-p.json)

Transcript checks on the stored event:

- `contains_html: false`
- `contains_plugin_manager: false`
- `contains_analytics_403: false`
- `contains_manifest_warning: false`
- `contains_cloudflare: false`
- `contains_shell_snapshot: false`
- `contains_rmcp: false`

### Interpretation

This satisfies the Phase 5 pass criteria:

- the stored event transcript no longer contains the large Codex warning / HTML dump
- focused failure-path tests prove that a real child error line still survives after transport-noise stripping

### Residual Note

The returned wrapper JSON still has verbose `child.stderr` because Codex echoes session progress on stderr. That is no longer the stored-evidence problem Phase 5 was targeting.
