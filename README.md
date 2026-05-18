# datalox-agent-replay

`datalox-agent-replay` is the repo-local implementation package for Datalox
Agent Replay: an MCP-compatible recorder/replay layer for agent tool I/O.

Datalox records agent-visible prompts, tool actions, file edits, verification
results, and replay evidence so teams can reproduce agent behavior later.
Approved replay bundles are the source data product. Trajectory/eval rows are
optional derivatives from those bundles.

Primary product loop:

`agent run -> tool I/O records -> replay bundle -> approval/export -> optional derivatives`

This branch does not ship a parallel wiki/note/event product store.

## What It Writes

In an adopted repo, product data and review state live under `.datalox/`:

```text
.datalox/
  events/
    agent-turns/
  tool-io/
    records/
  replay-bundles/
  approvals/
  derivatives/
    trajectories/
docs/
DATALOX.md
AGENTS.md
```

Use:

- `.datalox/tool-io/records/` for `tool_io_record.v1` replay records
- `.datalox/events/agent-turns/` for `agent_turn.v1` review events
- `.datalox/replay-bundles/` for `replay_bundle.v1` source product artifacts
- `.datalox/approvals/` for review/approval artifacts
- `.datalox/derivatives/trajectories/` for optional compact trajectory/eval derivatives

Unapproved raw traces are not sellable data. The source asset is an approved
anonymized replay bundle assembled from tool I/O records and turns.
`debugging_trajectory.v1` and `agent_task_trajectory.v1` are compact row
derivatives for training/eval packaging.

User-facing capture copy:

> Datalox captured this agent session. It includes prompts, tool actions, file edits, and verification results. You can keep it private, review it, or share approved anonymized sessions with your organization/data program.

## Install

From the repo you want Datalox to manage, paste this into the agent chatbox and
send it. The agent should run it from the target repo root.

```bash
TARGET_REPO="$(pwd)"
PACK_REPO="${HOME}/.datalox/cache/datalox-agent-replay"
mkdir -p "$(dirname "$PACK_REPO")"
if [ -d "$PACK_REPO/.git" ]; then
  git -C "$PACK_REPO" pull --ff-only
else
  git clone https://github.com/Oshawott324/datalox-agent-replay.git "$PACK_REPO"
fi
cd "$PACK_REPO"
bash bin/setup-multi-agent.sh codex
bash bin/adopt-host-repo.sh "$TARGET_REPO"
node bin/datalox.js status --repo "$TARGET_REPO" --json
```

After setup, use `datalox-mcp` as the replay capture surface. Trajectory
commands are derivative-only implementation-era commands and are not the
product capture path.

This does two separate things:

- `https://github.com/Oshawott324/datalox-agent-replay.git` is the current public source repo.
- `~/.datalox/cache/datalox-agent-replay` is the local source directory and package identity.
- `$TARGET_REPO` is the user's current project.
- Default adoption writes instruction surfaces and `.datalox/install.json` into the target repo.
- Fresh adoption does not create the removed wiki store or copy seed note/skill corpora.

Post-install checks from the target repo:

```bash
which codex
node "${HOME}/.datalox/cache/datalox-agent-replay/bin/datalox.js" status --repo . --json
codex exec "Check Datalox is active for this repo."
```

For Claude instead of Codex, run:

```bash
bash bin/setup-multi-agent.sh claude
```

If the source clone already exists, use it directly:

```bash
TARGET_REPO="$(pwd)"
PACK_REPO="${HOME}/.datalox/cache/datalox-agent-replay"
cd "$PACK_REPO"
git pull --ff-only
bash bin/setup-multi-agent.sh codex
bash bin/adopt-host-repo.sh "$TARGET_REPO"
node bin/datalox.js status --repo "$TARGET_REPO" --json
```

After adoption, the target repo has a local MCP entrypoint:

```bash
node bin/datalox-mcp.js
```

## CLI

Replay bundle commands:

```bash
node bin/datalox.js bundle pack --repo . --bundle-id <id> --json
node bin/datalox.js bundle verify --repo . --bundle .datalox/replay-bundles/<id> --json
```

MCP VCR proxy commands:

```bash
node bin/datalox.js proxy --mode record --repo . --config datalox.replay.json --json
node bin/datalox.js proxy --mode replay --repo . --bundle .datalox/replay-bundles/<id> --json
```

Current trajectory commands are derivative-only implementation-era commands and
are not the source product capture path.

Wrapper entrypoints:

```bash
node bin/datalox-claude.js -- --print "Update the docs."
node bin/datalox-codex.js -- exec "Update the docs."
node bin/datalox-wrap.js command --repo /path/to/repo --task "update docs" --prompt "Update the docs." -- <host-command> __DATALOX_PROMPT__
```

The installed shims infer the repo from the current working directory. Replay
capture is the target default; existing trajectory post-run behavior is an
implementation gap tracked in
[docs/agent-replay-option-a-implementation-plan.md](docs/agent-replay-option-a-implementation-plan.md).

To stop Datalox-managed host interception later:

```bash
bash bin/disable-default-host-integrations.sh
```

To keep the wrapper but stop post-run recording:

```bash
export DATALOX_DEFAULT_POST_RUN_MODE=off
```

## MCP

The install-facing MCP surface should be replay-first:

- `record_tool_io`
- `record_agent_turn`
- `pack_replay_bundle`
- `verify_replay_bundle`
- `replay_tool_io`

Start the MCP server with:

```bash
datalox-mcp
```

For local source-tree testing:

```bash
node dist/src/mcp/replayServer.js
```

For code-heavy `agent_task_trajectory.v1` rows, buyer-facing `--quality use`
export requires at least one exact `code_change` evidence block. Local code
`source_reference` blocks are useful provenance, but they do not replace
before/after snippets or patch hunks.

## Current Best Practice

- `trace`, `web`, and `pdf` are the only concrete source kinds.
- `agent_turn.v1` is the simple capture primitive.
- Exact replay data belongs under `.datalox/tool-io/records/`.
- Turn review data belongs under `.datalox/events/agent-turns/`.
- Approved anonymized replay bundles are the source product export target.
- `debugging_trajectory.v1` rows are optional compact training/eval derivatives.
- `agent_task_trajectory.v1` rows are optional compact mixed-domain task derivatives with domain-specific evidence blocks.
- Verified trajectory rows are derivative artifacts, not repo-local knowledge page types or the complete source session.
- Keep training rows small; store detailed consent, license, redaction, and provenance evidence in source events or curation systems.

## Docs

- [DATALOX.md](DATALOX.md)
- [docs/product-definition.md](docs/product-definition.md)
- [docs/agent-replay-option-a-implementation-plan.md](docs/agent-replay-option-a-implementation-plan.md)
- [docs/tool-io-store-schema.md](docs/tool-io-store-schema.md)
- [docs/replay-bundle-schema.md](docs/replay-bundle-schema.md)
- [docs/agent-turn-schema.md](docs/agent-turn-schema.md)
- [docs/trajectory-dataset-schema.md](docs/trajectory-dataset-schema.md)
- [docs/agent-task-trajectory-schema.md](docs/agent-task-trajectory-schema.md)
- [docs/task-orchestration.md](docs/task-orchestration.md)
- [docs/agent-configuration.md](docs/agent-configuration.md)
