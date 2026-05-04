# datalox-trajectory-mcp

`datalox-trajectory-mcp` is the trajectory-focused repo-local implementation package for Datalox MCP.

Datalox Trajectory Data is the primary product focus: lean, outcome-labeled debugging trajectories for coding-agent training and evaluation, captured through Datalox MCP.

Primary product loop:

`agent run -> structured event -> verified trajectory row -> curated dataset/eval corpus`

This repo should not carry a second product loop around legacy note/skill promotion. Existing skills and notes are legacy or internal agent-guidance surfaces until migrated or isolated behind the trajectory pipeline.

Legacy/internal agent-guidance surfaces are:

- `skill` = reusable workflow entrypoint
- `note` = grounded supporting knowledge a skill can point to

Keep the capture taxonomy small:

- source kinds: `trace`, `web`, `pdf`
- product export target: `debugging_trajectory.v1`

The legacy pack loop is:

`detect -> use -> record -> promote -> lint`

The exported dataset schema is canonical in [docs/trajectory-dataset-schema.md](docs/trajectory-dataset-schema.md). Product language should follow [docs/product-definition.md](docs/product-definition.md).

## What It Writes

In an adopted repo, the main surfaces are:

```text
skills/
agent-wiki/
  notes/
  events/
  index.md
  log.md
  lint.md
  hot.md
```

Use:

- `agent-wiki/events/` for structured evidence that can feed trajectory export
- `skills/` and `agent-wiki/notes/` for legacy or internal agent guidance while migration is in progress

Raw traces are not the product. A sellable dataset row must be a lean training example with a labeled outcome, verification status, and small export gate according to [docs/trajectory-dataset-schema.md](docs/trajectory-dataset-schema.md).

## Install

### Agent Install

From the repo you want Datalox to manage, paste this into the agent chatbox and send it. The agent should run it from the target repo root.

```bash
TARGET_REPO="$(pwd)"
git clone https://github.com/Complexity-LLC/datalox-pack.git datalox-trajectory-mcp
cd datalox-trajectory-mcp
bash bin/setup-multi-agent.sh codex
bash bin/adopt-host-repo.sh "$TARGET_REPO"
node bin/datalox.js status --repo "$TARGET_REPO" --json
```

This does two separate things:

- `https://github.com/Complexity-LLC/datalox-pack.git` is the current public source repo.
- `datalox-trajectory-mcp` is the local source directory and package identity. Do not clone `https://github.com/Complexity-LLC/datalox-trajectory-mcp.git` unless that GitHub repo has been created or the existing repo has been renamed.
- The source clone owns source-only scripts such as `bin/adopt-host-repo.sh`.
- `$TARGET_REPO` is the user's current project. Adoption writes the Datalox instruction surfaces, core skills, notes, and `.datalox/install.json` there.

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

Fresh adopted repos now receive only the core bootstrap bundle by default:

- core runtime/instruction surfaces
- the `maintain-datalox-pack` skill and its linked notes
- the `use-datalox-through-host-cli` skill and its linked note

They do not receive unrelated example or domain seed knowledge such as:

- `github`
- `ordercli`
- unrelated domain review skills
- `agent-wiki/notes/pdf/*`
- `agent-wiki/notes/web/*`

Direct adoption from GitHub is also available:

```bash
bash bin/adopt-from-github.sh /path/to/your-project
```

Supported default host paths include the Codex shim, the Claude shim when a real `claude` CLI exists, canonical Claude native skill links, the Claude hook, and the generic CLI wrapper.

Claude native skills are linked at `~/.claude/skills/<skill-name>/SKILL.md`. Restart Claude Code only if it was already running before the top-level `~/.claude/skills` directory existed, or if the host does not pick up the new links live.

The Claude hook is sidecar post-run automation. It can record what happened after a turn, but it is not proof that Claude used the right skill before acting. `CLAUDE.md`, wrapper/shim paths, MCP tools, and repo-local `skills/` remain the robust fallback.

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

The installed shims infer the repo from the current working directory and default autonomous second-pass review to `review` mode with `gpt-5.4-mini`.

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

Use the legacy full server for pack maintenance, adoption, capture, lint, and note/skill promotion tools. Use the trajectory server for dataset capture/export.

## Promotion Rules

Default behavior:

- first grounded occurrence: keep it as an event
- repeated gap with an existing matching skill: patch that skill and its linked note set
- repeated gap with no matching skill: create a reusable note
- repeated no-match after the skill threshold: create a live skill

Generated notes go to `agent-wiki/notes/`.
Generated skills go to `skills/`.

## Web Capture

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

## PDF Capture

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
- `debugging_trajectory.v1` rows are the product export target
- legacy `note` and `skill` outputs should not drive new product features
- verified trajectory rows are export artifacts, not repo-local knowledge page types
- fresh adopted repos should start from the core bootstrap bundle, not the full seed corpus
- read legacy supporting folders when they already exist, but do not generate new knowledge into them
- keep the training row small; store detailed consent, license, redaction, and provenance evidence in source events or curation systems

## Docs

- [DATALOX.md](DATALOX.md)
- [docs/product-definition.md](docs/product-definition.md)
- [docs/trajectory-dataset-schema.md](docs/trajectory-dataset-schema.md)
- [docs/task-orchestration.md](docs/task-orchestration.md)
- [docs/agent-configuration.md](docs/agent-configuration.md)
- [docs/automatic-enforcement-plan.md](docs/automatic-enforcement-plan.md)
- [docs/project-overview.md](docs/project-overview.md)
- [docs/implementation-checklist.md](docs/implementation-checklist.md)
