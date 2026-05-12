# Start Here

This pack is for one simple outcome:

Datalox records agent debugging sessions that can become approved B2B session data and compact trajectory/eval derivatives.

Primary product loop:

`agent run -> AgentTurnV1 events -> session/episode assembly -> export/redaction gate -> approved session dataset -> optional trajectory/eval rows`

This repo should not keep legacy note/skill promotion as a second product loop. Existing skills and notes are legacy or internal agent-guidance surfaces until the session/trajectory pipeline replaces or isolates them.

Legacy/internal agent-guidance surfaces are:

- `skill` first
- linked `note` second

The turn capture contract is [docs/agent-turn-schema.md](docs/agent-turn-schema.md). The compact trajectory row contract is [docs/trajectory-dataset-schema.md](docs/trajectory-dataset-schema.md).

User-facing capture copy:

> Datalox captured this agent session. It includes prompts, tool actions, file edits, and verification results. You can keep it private, review it, or share approved anonymized sessions with your organization/data program.

## Fastest Path

1. From the repo you want the agent to work on, paste the setup block below into the agent chatbox.
2. Let the agent clone the source pack, install the host integration, adopt the current repo, and verify status.
3. The normal read path should be:
   - read `AGENTS.md` and `DATALOX.md`
   - use `skills/` only when this repo has explicit legacy guidance
4. For session export, trajectory export, or data-sale work, read `docs/product-definition.md` first; read `docs/agent-turn-schema.md` before changing turn capture fields, and read `docs/trajectory-dataset-schema.md` before changing trajectory row fields or wording.
5. Watch these files:
   - `.datalox/events/`
   - `.datalox/session-candidates/`
   - `.datalox/approvals/`
   - `agent-wiki/events/` for legacy events only

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
bash bin/setup-multi-agent.sh claude
bash bin/adopt-host-repo.sh "$TARGET_REPO"
node bin/datalox.js status --repo "$TARGET_REPO" --json
```

`https://github.com/Complexity-LLC/datalox-pack.git` is the current public GitHub source repo. `~/.datalox/cache/datalox-trajectory-mcp` is the local checkout/package path and stays outside the target project, so source-only folders such as `agent-wiki/` do not appear in the managed repo. Do not use `https://github.com/Complexity-LLC/datalox-trajectory-mcp.git` until that GitHub repo exists.

## New Session In The Same Repo

If this is a fresh session or a different agent entering the same repo, the canonical repo-local handoff is:

`Use this repo's Datalox Trajectory MCP. Read AGENTS.md and DATALOX.md before acting.`

On supported installed host paths such as enforced Codex, that handoff should already be automatic. If you want to confirm the current repo state, run:

- `node bin/datalox.js status --repo . --json`

## What You Should See

- `.datalox/events/`: new product capture data
- no root `agent-wiki/` or `skills/` unless legacy guidance was explicitly requested

## What The Agent Reads First

1. `.datalox/manifest.json`
2. `.datalox/config.json`
3. `docs/product-definition.md` when it exists
4. `docs/agent-turn-schema.md` when the work touches session capture, session export, or data sale
5. `docs/trajectory-dataset-schema.md` when the work touches trajectory recording, trajectory export, or data sale
6. `DATALOX.md`
7. `agent-wiki/hot.md` if it exists
8. the selected `skills/<name>/SKILL.md` only when this repo has legacy/local skills
9. the linked notes for that skill only when those notes exist

## One-Click Options

- Full setup from the target repo:
  `TARGET_REPO="$(pwd)" && PACK_REPO="${HOME}/.datalox/cache/datalox-trajectory-mcp" && mkdir -p "$(dirname "$PACK_REPO")" && ([ -d "$PACK_REPO/.git" ] && git -C "$PACK_REPO" pull --ff-only || git clone https://github.com/Complexity-LLC/datalox-pack.git "$PACK_REPO") && cd "$PACK_REPO" && bash bin/setup-multi-agent.sh claude && bash bin/adopt-host-repo.sh "$TARGET_REPO"`
- Adopt a target repo from an existing source-pack clone:
  `bash bin/adopt-host-repo.sh /path/to/host-repo`
- Pull from GitHub and adopt:
  `bash bin/adopt-from-github.sh /path/to/host-repo`
- Install supported host shims/hooks:
  `bash bin/setup-multi-agent.sh claude`
- Automatic post-turn hook recording for hosts with hook support:
  `node bin/datalox-auto-promote.js`
  Default hook events are recorded as `trace`. Set `DATALOX_HOOK_EVENT_CLASS=candidate` only when the hook should enter the promotion ladder.
- Stop machine-level host interception:
  `bash bin/disable-default-host-integrations.sh`

If the host repo already has `AGENTS.md`, `CLAUDE.md`, or `.github/copilot-instructions.md`, adoption preserves that file and injects a small Datalox adapter instead of skipping the Datalox entrypoint.

Fresh adopted repos get only the core bootstrap bundle by default:

- runtime/instruction surfaces
- `.datalox/install.json`

They do not get `agent-wiki/`, `skills/`, or unrelated example/domain bundles by default. Legacy guidance can be installed explicitly with `--include-legacy-guidance`.

## Normal Usage After Setup

The user's agent can run `bash bin/setup-multi-agent.sh claude` once from the source pack and `bash bin/adopt-host-repo.sh "$TARGET_REPO"` for the current project. After that, the user should keep using the host normally.

- Codex:
  `codex exec "Update the onboarding docs."`
- Claude:
  `claude --print "Update the onboarding docs."`

The installed shims route those runs through Datalox automatically and default to `trajectory` capture mode. The wrapper records only an explicit `debugging_trajectory.v1` row supplied by the agent through `DATALOX_TRAJECTORY_ROW_FILE` or `DATALOX_TRAJECTORY_ROW`; default rows should be `curation.quality: "needs_review"` until accepted, and legacy review mode must be requested explicitly.

That automation is only true on supported host adapter paths. If a host only sees repo instructions or MCP tools, Datalox is guidance-only until a wrapper, hook, or plugin owns the loop.

Claude native skills are legacy optional and linked at `~/.claude/skills/<skill-name>/SKILL.md` only when setup is run with `--include-legacy-guidance`. Restart Claude Code only if it was already running before `~/.claude/skills` existed, or if the host does not pick up new skill links live. The Claude hook is sidecar post-run automation; `CLAUDE.md`, wrapper/shim paths, MCP tools, and repo-local docs remain the fallback.

To stop the host interception later, run `bash bin/disable-default-host-integrations.sh`.

To see whether the current repo is actually automatic or only guidance-only, run:

- `node bin/datalox.js status --repo . --json`

For the concrete enforcement roadmap, read [docs/automatic-enforcement-plan.md](docs/automatic-enforcement-plan.md).
