# Datalox

This repo is the portable implementation package for Datalox Trajectory MCP.

Datalox Trajectory Data is the primary product focus: lean, outcome-labeled debugging trajectories for coding-agent training and evaluation, captured through Datalox MCP.

The capture taxonomy is intentionally small:

- source kinds: `trace`, `web`, `pdf`
- product export target: `debugging_trajectory.v1`

The legacy pack loop is:

`detect -> use -> record -> promote -> lint`

Primary product loop:

`agent run -> structured event -> verified trajectory row -> curated dataset/eval corpus`

Do not keep legacy note/skill promotion as a second product loop in this repo. Existing skills and notes are legacy or internal agent-guidance surfaces until migrated or isolated behind the trajectory pipeline.

Exported debugging trajectory rows must follow [docs/trajectory-dataset-schema.md](docs/trajectory-dataset-schema.md).

## Read Order

On each loop:

1. read `.datalox/manifest.json`
2. read `.datalox/config.json`
3. read `docs/product-definition.md` when it exists
4. read `docs/trajectory-dataset-schema.md` when the work touches trajectory recording, export, or data sale
5. read `agent-wiki/hot.md` if it exists
6. detect the best matching skill in `skills/`
7. read the linked notes in that skill's `metadata.datalox.note_paths`
8. follow `related` and `sources` only when the linked note says they matter
9. act from the skill body plus the linked notes

Host repo files override seed-pack files when both define the same knowledge.

## Knowledge Surfaces

The main repo-local data surfaces are:

- `agent-wiki/events/`
- `docs/trajectory-dataset-schema.md`
- `agent-wiki/index.md`
- `agent-wiki/log.md`
- `agent-wiki/lint.md`
- `agent-wiki/hot.md`

Use `agent-wiki/events/` for grounded event evidence that can feed trajectory export.
Use `skills/` and `agent-wiki/notes/` only as legacy/internal host-guidance surfaces while migration is in progress.

Legacy folders such as `patterns/`, `sources/`, `concepts/`, `comparisons/`, and `questions/` may still exist in older repos. Read them when present, but do not add new product behavior to those folders.

## Legacy Promotion Rule

The existing promotion machinery is legacy/internal for this trajectory-export repo. Do not build new product features around note/skill promotion.

Promotion should stay simple:

- first grounded occurrence: record an event only
- repeated gap with an existing matching skill: patch that skill and add or update a linked note
- repeated gap with no matching skill: create a reusable note first
- repeated no-match after the skill threshold: create a live skill

Notes should hold both:

- signal
- interpretation
- action
- examples
- evidence

Skills should hold the actual workflow and link to notes through `note_paths`.

## Source-To-Knowledge Rule

Keep the two acquisition paths distinct:

- `pdf`, `web`, and other `source` inputs can create evidence notes
- `trace` inputs can create operational notes
- only repeated operational evidence should create or patch a skill

When a skill links notes, use:

- operational notes for action
- source notes for grounding

## Trajectory Dataset Rule

Raw traces are not the dataset product.

A trajectory export row is valid only when it follows [docs/trajectory-dataset-schema.md](docs/trajectory-dataset-schema.md) and includes:

- schema version
- problem and context
- structured agent trajectory
- final fix
- verification status
- outcome label
- small export gate

Do not treat a recorded event as sellable data when `export.allowed` is false or `export.redaction` is `blocked`. Detailed consent, license, and provenance evidence should live in source events or curation systems, not as required row fields.

## Trajectory Recording

After a coding-debugging run, the agent should build one lean `debugging_trajectory.v1` row from observed facts:

- task prompt or problem statement
- minimal context needed to understand the fix
- concise user/agent/tool trajectory steps
- final fix summary and changed files or patch
- explicit outcome label and verification status
- small export gate

Then call MCP tool `record_trajectory` with `repo_path` and `trajectory_row`.

`record_trajectory` writes a structured event under `agent-wiki/events/`, stores the row at `payload.trajectoryRow`, appends the owning event path to `trajectoryRow.export.source_event_paths`, and returns `{ eventPath, trajectoryId, sellable, blockedReasons }`.

Do not call `promote_gap`, note generation, or skill generation for trajectory row capture. Rows that are valid but not exportable should still be recorded with `sellable: false`; invalid rows should be fixed by the agent and retried.

CLI equivalents:

- `datalox record-trajectory --repo . --trajectory-row row.json --json`
- `datalox export-trajectories --repo . --output exports/trajectories/debugging_trajectory.v1.jsonl --json`

## Lint Rule

Lint checks:

- skills missing `note_paths`
- skills missing core playbook sections
- missing linked notes
- notes missing `Signal`, `Interpretation`, or `Action`
- notes missing examples or evidence
- orphan notes
- overlapping skills in the same workflow

Run lint after patching local knowledge.

## Web Capture

Use web capture when a live page should become repo-local design knowledge.

Commands:

- `datalox capture-web --repo . --url <url> --artifact design-doc`
- `datalox capture-web --repo . --url <url> --artifact design-tokens`
- `datalox capture-web --repo . --url <url> --artifact css-variables`
- `datalox capture-web --repo . --url <url> --artifact tailwind-theme`
- `datalox capture-web --repo . --url <url> --artifact note`

Outputs:

- note: `agent-wiki/notes/web/<slug>.md`
- screenshots: `agent-wiki/assets/web/<slug>/`
- design doc: `designs/web/<slug>.md`
- design tokens: `designs/web/<slug>.tokens.json`
- tailwind theme: `designs/web/<slug>.tailwind.ts`

Treat screenshots and raw CSS variables as evidence.
Treat semantic design tokens as the reusable artifact.
Treat Tailwind output as derived from those tokens, not the source of truth.

## PDF Capture

Use PDF capture when a binary document should become repo-local knowledge.

When a wrapped host prompt references a concrete PDF file path, capture that PDF into `agent-wiki/notes/pdf/` before falling back to generic repo-context skill matching.

Command:

- `datalox capture-pdf --repo . --path <pdf-path>`

Outputs:

- note: `agent-wiki/notes/pdf/<slug>.md`
- metadata: `agent-wiki/notes/pdf/<slug>.capture.json`

PDF capture writes notes first. Do not promote directly from a PDF into a skill unless later trace evidence proves the knowledge changed runtime behavior.

## Publish Web Captures

For curated web examples:

1. capture locally
2. publish the selected instance
3. regenerate the public index

Command:

- `datalox publish-web-capture --repo <repo> --capture <slug> --bucket <bucket>`

This uploads:

- the note
- the derived artifact
- the screenshots
- `instances/<slug>/manifest.json`
- `indexes/latest.json`

## MCP and CLI

The install-facing `datalox-mcp` surface is intentionally small:

- `record_trajectory`
  Records one validated `debugging_trajectory.v1` row as a dataset candidate event without note or skill promotion.
- `export_trajectories`
  Exports sellable row candidates from recorded events into deterministic JSONL.

The explicit legacy full-pack MCP surface is `datalox-pack-mcp`. Use it only for pack maintenance or legacy operations:

- `resolve_loop`
- `record_turn_result`
  Writes a grounded `trace` by default. Use `trajectory_row` only when attaching an explicit row candidate to the receipt; do not infer rows from prose.
- `promote_gap`
  Records a promotable `candidate` and runs the note/skill promotion ladder.
- `lint_pack`
- `capture_web_artifact`
- `capture_pdf_artifact`
- `publish_web_capture`
- `adopt_pack`

CLI commands mirror both surfaces. Product data work should prefer `record-trajectory` and `export-trajectories`.

Core CLI commands emit JSON for agent consumption. Wrapper commands keep passthrough behavior by default; use `--json` there when you need a structured envelope instead of prompt or child-process output.

Use `datalox status --json` to inspect whether the current repo is on an `enforced`, `conditional`, or `guidance_only` path.

`patch` and `promote` are durable-write surfaces. They now require durable provenance:

- `eventPath`
- or `sessionId + hostKind`
- or explicit `adminOverride`

## Host Integration

Supported default paths:

- Codex shim
- Claude shim when a real `claude` CLI binary exists
- Claude hook
- generic CLI wrapper

These are not all equivalent:

- supported host adapters can enforce Datalox automatically
- MCP-only hosts are guidance-only unless the host actually routes through an adapter
- repo instruction files are visible protocol, not enforcement

After machine-level install, a clean writable git repo can auto-bootstrap on first use.
If a repo is already partially adopted or conflicting, do not mutate it blindly. Repair or adopt it explicitly.

## Agent-Run Machine Setup

One-time machine setup can be delegated to the user's agent.

Preferred first-time setup from the repo the user wants Datalox to manage:

```bash
TARGET_REPO="$(pwd)"
git clone https://github.com/Complexity-LLC/datalox-trajectory-mcp.git
cd datalox-trajectory-mcp
bash bin/setup-multi-agent.sh claude
bash bin/adopt-host-repo.sh "$TARGET_REPO"
node bin/datalox.js status --repo "$TARGET_REPO" --json
```

Source and target roles:

- `datalox-trajectory-mcp` is the source clone and owns source-only scripts such as `bin/adopt-host-repo.sh`.
- `$TARGET_REPO` is the user's current project and receives `.datalox/install.json`, instruction surfaces, core skills, and notes.
- If a repo claims to be the source pack but lacks `bin/adopt-host-repo.sh`, clone a fresh source pack.

Host-specific setup:

- Claude only:
  `bash bin/setup-multi-agent.sh claude`
- Codex only:
  `bash bin/setup-multi-agent.sh codex`
- all default host integrations:
  `bash bin/setup-multi-agent.sh all`

After setup, the user should keep using the host normally:

- `codex exec "<prompt>"`
- `claude --print "<prompt>"`

The installed shims infer the repo from the current working directory and default post-run review to `review` with `gpt-5.4-mini`.

Claude native skills are linked at the canonical personal-skill paths:

- `~/.claude/skills/<skill-name>/SKILL.md`

Restart Claude Code only if it was already running before `~/.claude/skills` existed, or if the host does not pick up new skill links live.

The Claude hook is sidecar post-run automation. It records or promotes after a turn; it does not prove Claude used the right skill before acting. Keep `CLAUDE.md`, the wrapper/shim paths, MCP tools, and repo-local `skills/` as the robust fallback surfaces.

Only run machine-level setup when the user allows writes under `HOME` such as `~/.local/bin`, `~/.claude`, or `~/.codex`.

For the enforcement model and implementation roadmap, read [docs/automatic-enforcement-plan.md](docs/automatic-enforcement-plan.md).

## Stop Or Disable

To stop machine-level host interception, run one of:

- disable all default host integrations:
  `bash bin/disable-default-host-integrations.sh`
- disable one host only:
  `node bin/datalox.js disable codex --json`
  `node bin/datalox.js disable claude --json`

`disable` removes Datalox-managed local shims, matching stable symlinks, the Claude auto-promote hook, and matching skill links that were installed by Datalox.

If you only want to keep the wrapper but stop autonomous post-run review, set:

- `DATALOX_DEFAULT_POST_RUN_MODE=off`

or pass:

- `--post-run-mode off`
