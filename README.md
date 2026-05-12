# datalox-trajectory-mcp

`datalox-trajectory-mcp` is the session and trajectory focused repo-local implementation package for Datalox MCP.

Datalox captures approved agent debugging sessions and derives lean, outcome-labeled trajectories for coding-agent training and evaluation.

Primary product loop:

`agent run -> AgentTurnV1 events -> session/episode assembly -> export/redaction gate -> approved session dataset -> optional trajectory/eval rows`

This repo should not carry a second product loop around legacy note/skill promotion. Existing skills and notes are legacy or internal agent-guidance surfaces until migrated or isolated behind the session/trajectory pipeline.

Legacy/internal agent-guidance surfaces are:

- `skill` = reusable workflow entrypoint
- `note` = grounded supporting knowledge a skill can point to

Keep the capture taxonomy small:

- source kinds: `trace`, `web`, `pdf`
- capture primitive: `agent_turn.v1`
- source export target: approved anonymized session bundle
- trajectory derivative targets: `debugging_trajectory.v1`, `agent_task_trajectory.v1`

The legacy pack loop is:

`detect -> use -> record -> promote -> lint`

The per-turn capture schema is canonical in [docs/agent-turn-schema.md](docs/agent-turn-schema.md). The coding/debugging trajectory row schema is canonical in [docs/trajectory-dataset-schema.md](docs/trajectory-dataset-schema.md). The mixed-domain task trajectory schema is canonical in [docs/agent-task-trajectory-schema.md](docs/agent-task-trajectory-schema.md). Product language should follow [docs/product-definition.md](docs/product-definition.md).

## What It Writes

In an adopted repo, the main surfaces are:

```text
.datalox/
  events/
  session-candidates/
  approvals/
docs/
DATALOX.md
AGENTS.md
```

Use:

- `.datalox/events/` for new product capture data
- `.datalox/events/agent-turns/` for future `agent_turn.v1` turn events
- `.datalox/events/trajectory-rows/` for `debugging_trajectory.v1` row events
- `.datalox/events/agent-task-trajectories/` for mixed-domain `agent_task_trajectory.v1` row events
- `.datalox/session-candidates/` and `.datalox/approvals/` for future review/approval artifacts
- `agent-wiki/events/` only when an older repo already has legacy traces, or when legacy compatibility mode is explicitly requested
- `skills/` only when an older repo already has local skills, or when legacy compatibility mode is explicitly requested

Unapproved raw traces are not sellable data. The capture primitive is `agent_turn.v1`; the source asset is an approved anonymized session bundle assembled from turns; `debugging_trajectory.v1` and `agent_task_trajectory.v1` are compact row derivatives for training/eval packaging.

User-facing capture copy:

> Datalox captured this agent session. It includes prompts, tool actions, file edits, and verification results. You can keep it private, review it, or share approved anonymized sessions with your organization/data program.

## Install

### Agent Install

From the repo you want Datalox to manage, paste this into the agent chatbox and send it. The agent should run it from the target repo root.

```bash
TARGET_REPO="$(pwd)"
PACK_REPO="${HOME}/.datalox/cache/datalox-trajectory-mcp"
mkdir -p "$(dirname "$PACK_REPO")"
if [ -d "$PACK_REPO/.git" ]; then
  git -C "$PACK_REPO" pull --ff-only
else
  git clone https://github.com/Complexity-LLC/datalox-pack.git "$PACK_REPO"
fi
cd "$PACK_REPO"
bash bin/setup-multi-agent.sh codex
bash bin/adopt-host-repo.sh "$TARGET_REPO"
node bin/datalox.js status --repo "$TARGET_REPO" --json
```
Start to use datalox-mcp from now on to generate trajectory

This does two separate things:

- `https://github.com/Complexity-LLC/datalox-pack.git` is the current public source repo.
- Fresh installs from that URL use the published GitHub state. Local uncommitted or unpushed changes in another checkout are not present in the target repo until they are pushed or the target install points at that local checkout.
- `~/.datalox/cache/datalox-trajectory-mcp` is the local source directory and package identity. Keep the source checkout outside the target repo so the target repo does not receive source-only folders such as `agent-wiki/`.
- Do not clone `https://github.com/Complexity-LLC/datalox-trajectory-mcp.git` unless that GitHub repo has been created or the existing repo has been renamed.
- The source clone owns source-only scripts such as `bin/adopt-host-repo.sh`.
- `$TARGET_REPO` is the user's current project. Default adoption writes the Datalox instruction surfaces and `.datalox/install.json` there.

Post-install checks from the target repo:

```bash
which codex
node "${HOME}/.datalox/cache/datalox-trajectory-mcp/bin/datalox.js" status --repo . --json
codex exec "Check Datalox is active for this repo."
```

For Claude instead of Codex, run:

```bash
bash bin/setup-multi-agent.sh claude
```

If the source clone already exists, use it directly:

```bash
TARGET_REPO="$(pwd)"
PACK_REPO="${HOME}/.datalox/cache/datalox-trajectory-mcp"
cd "$PACK_REPO"
git pull --ff-only
bash bin/setup-multi-agent.sh codex
bash bin/adopt-host-repo.sh "$TARGET_REPO"
node bin/datalox.js status --repo "$TARGET_REPO" --json
```

If the host repo already has `AGENTS.md`, `CLAUDE.md`, or `.github/copilot-instructions.md`, adoption preserves that file and injects a small Datalox adapter instead of skipping the Datalox entrypoint entirely.

After adoption, the target repo has a local MCP entrypoint:

```bash
node bin/datalox-mcp.js
```

Use `datalox-mcp` only when the package has also been installed or linked onto `PATH`.

Fresh adopted repos now receive only the product bootstrap bundle by default:

- core runtime/instruction surfaces

They do not receive unrelated example or domain seed knowledge such as:

- `skills/`
- `github`
- `ordercli`
- unrelated domain review skills
- `agent-wiki/`
- `agent-wiki/notes/pdf/*`
- `agent-wiki/notes/web/*`

Fresh trajectory-product installs do not create `agent-wiki/` or `skills/` by
default. To install legacy skill/wiki compatibility files for an older
note/skill maintenance flow, run setup/adoption with `--include-legacy-guidance`.

Direct adoption from GitHub is also available:

```bash
bash bin/adopt-from-github.sh /path/to/your-project
```

Supported default host paths include the Codex shim, the Claude shim when a real `claude` CLI exists, the Claude hook, and the generic CLI wrapper. Canonical Claude native skill links are legacy optional and install only with `--include-legacy-guidance`.

Legacy Claude native skills are linked only when setup is run with
`--include-legacy-guidance`. When enabled, they use
`~/.claude/skills/<skill-name>/SKILL.md`. Restart Claude Code only if it was
already running before the top-level `~/.claude/skills` directory existed, or if
the host does not pick up the new links live.

The Claude hook is sidecar post-run automation. It can record what happened after a turn, but it is not proof that Claude used the right skill before acting. `CLAUDE.md`, wrapper/shim paths, MCP tools, and repo-local docs remain the robust fallback.

Automatic enforcement only applies on supported host adapter paths. MCP and repo instruction files are still available outside those paths, but they are guidance surfaces, not enforcement.

Inspect the current enforcement state with:

```bash
node dist/src/cli/main.js status --repo . --json
```

## Same-Repo Handoff

For a fresh session or a different agent entering the same repo, the canonical repo-local instruction is:

```text
Use this repo's Datalox Trajectory MCP. Read AGENTS.md and DATALOX.md before acting.
```

On supported installed host paths such as enforced Codex, that handoff should already be automatic. If the host only sees repo instructions or MCP tools, use the instruction above explicitly and then verify the current state with:

```bash
node bin/datalox.js status --repo . --json
```

## CLI

Resolve the current loop:

```bash
node dist/src/cli/main.js resolve --repo . --task "review ambiguous viability gate" --json
```

Record and promote:

```bash
node dist/src/cli/main.js record --repo . --task "review ambiguous viability gate" --workflow flow_cytometry --observation "dim dead tail overlaps live shoulder" --interpretation "likely artifact" --action "review exception note before widening gate" --json
node dist/src/cli/main.js promote --repo . --event-path agent-wiki/events/<event>.json --task "review ambiguous viability gate" --workflow flow_cytometry --observation "dim dead tail overlaps live shoulder" --interpretation "likely artifact" --action "review exception note before widening gate" --json
node dist/src/cli/main.js lint --repo . --json
```

`record`, `promote`, and `lint` are legacy/internal guidance-maintenance
commands. New product data should use `record-trajectory`,
`record-agent-task-trajectory`, and future turn/session capture commands.
Help and status paths are read-only and should not create event records.

Durable writes now require provenance. `patch` and `promote` need one of:

- `--event-path <recorded-event>`
- both `--session-id` and `--host-kind`
- `--admin-override` for an explicit maintainer bypass

Wrapper entrypoints:

```bash
node bin/datalox-claude.js -- --print "Update the docs."
node bin/datalox-codex.js -- exec "Update the docs."
node bin/datalox-wrap.js command --repo /path/to/repo --task "update docs" --prompt "Update the docs." -- <host-command> __DATALOX_PROMPT__
```

After `node bin/datalox.js setup codex`, `bash bin/setup-multi-agent.sh codex`, or `bash bin/setup-multi-agent.sh claude`, the user should not need Datalox flags at all:

```bash
codex exec "Update the docs."
claude --print "Update the docs."
```

The installed shims infer the repo from the current working directory and default post-run capture to `trajectory` mode. In that mode the wrapper records only an explicit `debugging_trajectory.v1` row supplied by the agent through `DATALOX_TRAJECTORY_ROW_FILE` or `DATALOX_TRAJECTORY_ROW`; it does not write legacy trace receipts from prose. Use `--post-run-mode review` only for explicit legacy guidance maintenance.

To stop Datalox-managed host interception later:

```bash
bash bin/disable-default-host-integrations.sh
```

To keep the wrapper but stop autonomous review only:

```bash
export DATALOX_DEFAULT_POST_RUN_MODE=off
```

## MCP

The install-facing MCP surface is intentionally small:

- `record_trajectory`
  Records one validated `debugging_trajectory.v1` row as a dataset candidate event.
- `export_trajectories`
  Exports sellable row candidates from recorded events into deterministic JSONL.
- `record_agent_task_trajectory`
  Records one validated `agent_task_trajectory.v1` mixed-domain row as a dataset candidate event.
- `export_agent_task_trajectories`
  Exports sellable mixed-domain row candidates into deterministic JSONL.
- `grade_trajectories`
  Grades recorded rows for training readiness without mutating source events.
- `repair_trajectory`
  Records a corrected row as a new event linked to the original row event.

Start the trajectory MCP server with:

```bash
datalox-mcp
```

For local source-tree testing, use:

```bash
node dist/src/mcp/trajectoryServer.js
```

The legacy full pack MCP remains available only when explicitly requested:

```bash
datalox-pack-mcp
node dist/src/mcp/server.js
```

Use the legacy full server for pack maintenance, adoption, capture, lint, and note/skill promotion tools. Use the trajectory server for dataset capture, grading, and export.

For code-heavy `agent_task_trajectory.v1` rows, buyer-facing `--quality use`
export requires at least one exact `code_change` evidence block. Local code
`source_reference` blocks are useful provenance, but they do not replace
before/after snippets or patch hunks. Put source files in `context.source_paths`
and `final.changed_artifacts`; keep `export.source_event_paths` limited to
`.datalox/events/...` provenance event paths. Recording downgrades claimed
`curation.quality: "use"` rows to `needs_review` when deterministic readiness
checks fail.

## Promotion Rules

Default behavior:

- first grounded occurrence: keep it as an event
- repeated gap with an existing matching skill: patch that skill and its linked note set
- repeated gap with no matching skill: create a reusable note
- repeated no-match after the skill threshold: create a live skill

Generated notes go to `agent-wiki/notes/`.
Generated skills go to `skills/`.

This promotion loop is legacy/internal. Fresh product installs do not ship
`agent-wiki/` as an active store; legacy repos may still read or maintain it
when it already exists or when adoption used `--include-legacy-guidance`.

## Legacy Web Capture

This command is legacy/internal guidance capture. It may create
`agent-wiki/notes/web/` when explicitly used, but fresh product adoption does
not create that wiki tree.

Capture a live site into repo-local design knowledge:

```bash
node dist/src/cli/main.js capture-web --repo . --url https://example.com --artifact design-doc --json
node dist/src/cli/main.js capture-web --repo . --url https://example.com --artifact design-tokens --json
node dist/src/cli/main.js capture-web --repo . --url https://example.com --artifact css-variables --json
node dist/src/cli/main.js capture-web --repo . --url https://example.com --artifact tailwind-theme --json
node dist/src/cli/main.js capture-web --repo . --url https://example.com --artifact note --json
```

Outputs:

- note: `agent-wiki/notes/web/<slug>.md`
- screenshots: `agent-wiki/assets/web/<slug>/desktop.png`, `mobile.png`
- design doc: `designs/web/<slug>.md`
- design tokens: `designs/web/<slug>.tokens.json`
- tailwind theme: `designs/web/<slug>.tailwind.ts`

Design tokens are the reusable artifact.
Tailwind output is derived from the tokens.

## Legacy PDF Capture

This command is legacy/internal guidance capture. It may create
`agent-wiki/notes/pdf/` when explicitly used, but fresh product adoption does
not create that wiki tree.

Capture a PDF into a repo-local note:

```bash
node dist/src/cli/main.js capture-pdf --repo . --path ./paper.pdf --json
```

Outputs:

- note: `agent-wiki/notes/pdf/<slug>.md`
- metadata: `agent-wiki/notes/pdf/<slug>.capture.json`

PDF capture writes notes first. Promotion into a skill should still come from later trace evidence.

## Publish Curated Web Captures

After capturing locally:

```bash
node dist/src/cli/main.js publish-web-capture --repo /path/to/corpus --capture <slug> --bucket "$DATALOX_R2_BUCKET" --json
```

This uploads:

- the note
- the derived artifact
- the screenshots
- `instances/<slug>/manifest.json`
- `indexes/latest.json`

## Current Best Practice

Keep the pack minimal:

- `trace`, `web`, and `pdf` are the only concrete source kinds
- `agent_turn.v1` is the simple capture primitive
- new product event data belongs under `.datalox/events/`, not `agent-wiki/events/`
- approved anonymized session bundles are the source product export target
- `debugging_trajectory.v1` rows are compact training/eval derivatives
- `agent_task_trajectory.v1` rows are compact mixed-domain task derivatives with domain-specific evidence blocks
- legacy `note` and `skill` outputs should not drive new product features
- verified trajectory rows are export artifacts, not repo-local knowledge page types or the complete source session
- fresh adopted repos should start from the core bootstrap bundle, not the full seed corpus
- read legacy supporting folders when they already exist, but do not generate new knowledge into them
- keep the training row small; store detailed consent, license, redaction, and provenance evidence in source events or curation systems

## Docs

- [DATALOX.md](DATALOX.md)
- [docs/product-definition.md](docs/product-definition.md)
- [docs/agent-turn-schema.md](docs/agent-turn-schema.md)
- [docs/trajectory-dataset-schema.md](docs/trajectory-dataset-schema.md)
- [docs/agent-task-trajectory-schema.md](docs/agent-task-trajectory-schema.md)
- [docs/task-orchestration.md](docs/task-orchestration.md)
- [docs/agent-configuration.md](docs/agent-configuration.md)
- [docs/automatic-enforcement-plan.md](docs/automatic-enforcement-plan.md)
- [docs/project-overview.md](docs/project-overview.md)
- [docs/implementation-checklist.md](docs/implementation-checklist.md)
