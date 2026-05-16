# Start Here

Datalox records agent tool I/O and session evidence so agent teams can replay
and audit behavior later. Approved replay/session bundles can become B2B source
data, with compact trajectory/eval rows as derivatives.

Primary product loop:

```text
agent run -> AgentTurnV1 events + tool I/O evidence -> replay/session bundle -> export/redaction gate -> approved replay dataset -> optional trajectory/eval rows
```

The turn capture contract is
[docs/agent-turn-schema.md](docs/agent-turn-schema.md). The compact debugging
row contract is
[docs/trajectory-dataset-schema.md](docs/trajectory-dataset-schema.md). Mixed
domain task rows use
[docs/agent-task-trajectory-schema.md](docs/agent-task-trajectory-schema.md).
The concrete replay migration plan is
[docs/agent-replay-option-a-implementation-plan.md](docs/agent-replay-option-a-implementation-plan.md).

User-facing capture copy:

> Datalox captured this agent session. It includes prompts, tool actions, file edits, and verification results. You can keep it private, review it, or share approved anonymized sessions with your organization/data program.

## Fastest Path

From the repo you want the agent to work on, paste this setup block into the
agent chatbox:

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

Fresh adoption creates instruction surfaces, `.datalox/` config, the install
stamp, and host shims. Product data writes under `.datalox/events/`.

## New Session In The Same Repo

Use this repo handoff:

```text
Use this repo's Datalox Agent Replay. Read AGENTS.md and DATALOX.md before acting.
```

To confirm state:

```bash
node bin/datalox.js status --repo . --json
```

## What You Should See

- `.datalox/events/`: product capture data
- `.datalox/session-candidates/`: future review candidates
- `.datalox/approvals/`: future approval records
- `DATALOX.md`, `AGENTS.md`, and host instruction files
- host shims under `bin/` and `~/.local/bin`

## What The Agent Reads First

1. `.datalox/manifest.json`
2. `.datalox/config.json`
3. `docs/product-definition.md`
4. `docs/agent-turn-schema.md` when the work touches session capture, session export, or data sale
5. `docs/trajectory-dataset-schema.md` when the work touches trajectory recording, trajectory export, or data sale
6. `docs/agent-task-trajectory-schema.md` when the work touches mixed-domain trajectories
7. `DATALOX.md`
8. the selected `skills/<name>/SKILL.md` only when the task matches that skill

## One-Click Options

- Full setup from the target repo:
  `TARGET_REPO="$(pwd)" && PACK_REPO="${HOME}/.datalox/cache/datalox-agent-replay" && mkdir -p "$(dirname "$PACK_REPO")" && ([ -d "$PACK_REPO/.git" ] && git -C "$PACK_REPO" pull --ff-only || git clone https://github.com/Oshawott324/datalox-agent-replay.git "$PACK_REPO") && cd "$PACK_REPO" && bash bin/setup-multi-agent.sh codex && bash bin/adopt-host-repo.sh "$TARGET_REPO"`
- Adopt a target repo from an existing Datalox Agent Replay clone:
  `bash bin/adopt-host-repo.sh /path/to/host-repo`
- Pull from GitHub and adopt:
  `bash bin/adopt-from-github.sh /path/to/host-repo`
- Install supported host shims:
  `bash bin/setup-multi-agent.sh codex`
- Stop machine-level host interception:
  `bash bin/disable-default-host-integrations.sh`

Fresh adopted repos get only the product bootstrap bundle by default:

- runtime/instruction surfaces
- `.datalox/config.json`
- `.datalox/manifest.json`
- `.datalox/install.json`
- host shims

## Normal Usage After Setup

After setup, keep using the host normally.

- Codex:
  `codex exec "Update the onboarding docs."`
- Claude:
  `claude --print "Update the onboarding docs."`

The installed shims route supported runs through Datalox automatically and
default to `trajectory` capture mode. The wrapper records only an explicit row
supplied by the agent through `DATALOX_TRAJECTORY_ROW_FILE` or
`DATALOX_TRAJECTORY_ROW`; default rows should be
`curation.quality: "needs_review"` until accepted.

If a host only sees repo instructions or MCP tools, Datalox is guidance-only
until a wrapper or plugin owns the loop.
