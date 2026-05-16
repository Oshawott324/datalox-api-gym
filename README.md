# datalox-agent-replay

`datalox-agent-replay` is the repo-local implementation package for Datalox
Agent Replay: an MCP-compatible recorder/replay layer for agent tool I/O.

Datalox records agent-visible prompts, tool actions, file edits, verification
results, and replay evidence so teams can reproduce agent behavior later.
Approved anonymized sessions and trajectory/eval rows are derived from that
source data.

Primary product loop:

`agent run -> AgentTurnV1 events + tool I/O evidence -> replay/session bundle -> export/redaction gate -> approved replay dataset -> optional trajectory/eval rows`

This branch does not ship a parallel wiki/note/event product store.

## What It Writes

In an adopted repo, product data and review state live under `.datalox/`:

```text
.datalox/
  events/
    agent-turns/
    trajectory-rows/
    agent-task-trajectories/
  session-candidates/
  approvals/
docs/
DATALOX.md
AGENTS.md
```

Use:

- `.datalox/events/agent-turns/` for future `agent_turn.v1` turn events
- `.datalox/events/trajectory-rows/` for `debugging_trajectory.v1` row events
- `.datalox/events/agent-task-trajectories/` for mixed-domain `agent_task_trajectory.v1` row events
- `.datalox/session-candidates/` and `.datalox/approvals/` for future review/approval artifacts

Unapproved raw traces are not sellable data. The source asset is an approved
anonymized session bundle assembled from turns. `debugging_trajectory.v1` and
`agent_task_trajectory.v1` are compact row derivatives for training/eval
packaging.

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
  git clone https://github.com/Complexity-LLC/datalox-agent-replay.git "$PACK_REPO"
fi
cd "$PACK_REPO"
bash bin/setup-multi-agent.sh codex
bash bin/adopt-host-repo.sh "$TARGET_REPO"
node bin/datalox.js status --repo "$TARGET_REPO" --json
```

Start to use `datalox-mcp` from now on to generate trajectory rows.

This does two separate things:

- `https://github.com/Complexity-LLC/datalox-agent-replay.git` is the current public source repo.
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

Dataset commands:

```bash
node dist/src/cli/main.js record-trajectory --repo . --trajectory-row row.json --json
node dist/src/cli/main.js grade-trajectories --repo . --json
node dist/src/cli/main.js repair-trajectory --repo . --event-path .datalox/events/trajectory-rows/bad-row.json --trajectory-row corrected-row.json --json
node dist/src/cli/main.js export-trajectories --repo . --quality use --json
node dist/src/cli/main.js record-agent-task-trajectory --repo . --agent-task-trajectory row.json --json
node dist/src/cli/main.js export-agent-task-trajectories --repo . --quality use --json
```

Wrapper entrypoints:

```bash
node bin/datalox-claude.js -- --print "Update the docs."
node bin/datalox-codex.js -- exec "Update the docs."
node bin/datalox-wrap.js command --repo /path/to/repo --task "update docs" --prompt "Update the docs." -- <host-command> __DATALOX_PROMPT__
```

The installed shims infer the repo from the current working directory and
default post-run capture to `trajectory` mode. In that mode the wrapper records
only an explicit trajectory row supplied by the agent through
`DATALOX_TRAJECTORY_ROW_FILE` or `DATALOX_TRAJECTORY_ROW`. If the marker is
absent, it records nothing.

To stop Datalox-managed host interception later:

```bash
bash bin/disable-default-host-integrations.sh
```

To keep the wrapper but stop post-run recording:

```bash
export DATALOX_DEFAULT_POST_RUN_MODE=off
```

## MCP

The install-facing MCP surface is intentionally small:

- `record_trajectory`
- `export_trajectories`
- `record_agent_task_trajectory`
- `export_agent_task_trajectories`
- `grade_trajectories`
- `repair_trajectory`

Start the trajectory MCP server with:

```bash
datalox-mcp
```

For local source-tree testing, use:

```bash
node dist/src/mcp/trajectoryServer.js
```

For code-heavy `agent_task_trajectory.v1` rows, buyer-facing `--quality use`
export requires at least one exact `code_change` evidence block. Local code
`source_reference` blocks are useful provenance, but they do not replace
before/after snippets or patch hunks.

## Current Best Practice

- `trace`, `web`, and `pdf` are the only concrete source kinds.
- `agent_turn.v1` is the simple capture primitive.
- Product event data belongs under `.datalox/events/`.
- Approved anonymized replay/session bundles are the source product export target.
- `debugging_trajectory.v1` rows are compact training/eval derivatives.
- `agent_task_trajectory.v1` rows are compact mixed-domain task derivatives with domain-specific evidence blocks.
- Verified trajectory rows are export artifacts, not repo-local knowledge page types or the complete source session.
- Keep training rows small; store detailed consent, license, redaction, and provenance evidence in source events or curation systems.

## Docs

- [DATALOX.md](DATALOX.md)
- [docs/product-definition.md](docs/product-definition.md)
- [docs/agent-replay-option-a-implementation-plan.md](docs/agent-replay-option-a-implementation-plan.md)
- [docs/agent-turn-schema.md](docs/agent-turn-schema.md)
- [docs/trajectory-dataset-schema.md](docs/trajectory-dataset-schema.md)
- [docs/agent-task-trajectory-schema.md](docs/agent-task-trajectory-schema.md)
- [docs/task-orchestration.md](docs/task-orchestration.md)
- [docs/agent-configuration.md](docs/agent-configuration.md)
