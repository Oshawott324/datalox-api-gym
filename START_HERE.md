# Start Here

Datalox records agent tool I/O and turn evidence so agent teams can replay and
audit behavior later. Approved replay bundles are the source product, with
compact trajectory/eval rows as optional derivatives.

Primary product loop:

```text
agent run -> tool I/O records -> replay bundle -> approval/export -> optional derivatives
```

The exact replay primitive is
[docs/tool-io-store-schema.md](docs/tool-io-store-schema.md). The source bundle
contract is [docs/replay-bundle-schema.md](docs/replay-bundle-schema.md). The
turn review contract is [docs/agent-turn-schema.md](docs/agent-turn-schema.md).
Compact trajectory rows use the trajectory schemas only as derivatives.
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
stamp, and host shims. Product replay data writes under `.datalox/tool-io/`,
`.datalox/events/agent-turns/`, and `.datalox/replay-bundles/`.

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

- `.datalox/tool-io/records/`: exact replay records
- `.datalox/events/agent-turns/`: turn review events
- `.datalox/replay-bundles/`: source replay bundles
- `.datalox/approvals/`: future approval records
- `.datalox/derivatives/trajectories/`: optional trajectory/eval derivatives
- `DATALOX.md`, `AGENTS.md`, and host instruction files
- host shims under `bin/` and `~/.local/bin`

## What The Agent Reads First

1. `.datalox/manifest.json`
2. `.datalox/config.json`
3. `docs/product-definition.md`
4. `docs/tool-io-store-schema.md` when the work touches tool-call capture or replay
5. `docs/replay-bundle-schema.md` when the work touches replay bundles, approval, or export
6. `docs/agent-turn-schema.md` when the work touches turn review data
7. trajectory schema docs only when deriving optional trajectory/eval rows
8. `DATALOX.md`
9. the selected `skills/<name>/SKILL.md` only when the task matches that skill

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

The installed shims route supported runs through Datalox automatically. Replay
capture is the target default. Use `datalox-mcp` for replay capture tools:

- `record_tool_io`
- `record_agent_turn`
- `pack_replay_bundle`
- `verify_replay_bundle`
- `replay_tool_io`

If a host only sees repo instructions or MCP tools, Datalox is guidance-only
until a wrapper or plugin owns the loop.
