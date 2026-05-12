# Agent Configuration

The agent-facing contract is intentionally small.

Product boundary:

- Datalox MCP is the product-facing instrumentation and control layer.
- `datalox-trajectory-mcp` is the repo-local implementation package.
- Approved B2B session data and derived trajectory/evals are the primary product focus.
- Do not keep legacy note/skill promotion as a second product loop in this repo.
- Existing skills/notes are legacy or internal agent-guidance surfaces until migrated.
- `AgentTurnV1` is the simple per-turn capture primitive.
- Approved anonymized sessions are the source dataset asset.
- Lean, outcome-labeled trajectory export creates compact training/eval derivatives.

## Legacy/Internal Guidance Model

- `skill` = the primary reusable workflow entrypoint
- `note` = grounded supporting knowledge that a skill can point to

Current legacy guidance behavior may still be:

1. detect the relevant skill
2. read `skills/<name>/SKILL.md` only when the repo has legacy/local skills
3. read the linked `metadata.datalox.note_paths` only when those files exist
4. act from the skill plus its linked notes only for explicit legacy guidance work

## Main Surfaces

```text
.datalox/
  manifest.json
  config.json
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

## Read Order

1. `.datalox/manifest.json`
2. `.datalox/config.json`
3. `docs/product-definition.md`
4. `docs/agent-turn-schema.md` when touching session capture, session export, or data sale
5. `docs/trajectory-dataset-schema.md` when touching trajectory recording, trajectory export, or data sale
6. `docs/agent-task-trajectory-schema.md` when touching mixed-domain task trajectories
7. `agent-wiki/hot.md` only when this repo already has legacy wiki content
8. selected `skills/<name>/SKILL.md` only when this repo has legacy/local skills
9. linked `metadata.datalox.note_paths` only when those files exist

## Write Rule

New product writes should go to:

- `.datalox/events/agent-turns/`
- `.datalox/events/trajectory-rows/`
- `.datalox/events/agent-task-trajectories/`
- `.datalox/session-candidates/`
- `.datalox/approvals/`
- `agent_turn.v1` event payloads that follow [agent-turn-schema.md](./agent-turn-schema.md)
- trajectory JSONL export artifacts that follow `debugging_trajectory.v1` or `agent_task_trajectory.v1`

`.datalox/events/` is the source product evidence surface. Turns can later be assembled into sessions, reviewed, anonymized, shared, or used to derive compact trajectory rows.

`agent-wiki/events/` remains readable as a legacy trace/event store, but new product behavior should not write future session or trajectory data there.

Legacy skill/note writes may still happen for current host guidance, but new product work should not depend on them.

Legacy supporting folders may still be readable during migration, but they are no longer the primary surface.
Fresh product adoption does not create or copy `agent-wiki/` or `skills/` unless legacy compatibility is explicitly requested.

## Source Kinds

Concrete source kinds only:

- `trace`
- `web`
- `pdf`

## Product Export Targets

- `agent_turn.v1` as the capture primitive
- approved anonymized session bundle
- `debugging_trajectory.v1` as the compact trajectory derivative

Legacy `skill` and `note` outputs may still exist for current host guidance, but new product work should target captured turns, assembled sessions, and derived trajectory rows. Turn capture must follow [agent-turn-schema.md](./agent-turn-schema.md). Trajectory dataset rows must follow [trajectory-dataset-schema.md](./trajectory-dataset-schema.md), not introduce another repo-local knowledge page type.

## Session Capture

Use this user-facing copy when a session is captured:

> Datalox captured this agent session. It includes prompts, tool actions, file edits, and verification results. You can keep it private, review it, or share approved anonymized sessions with your organization/data program.

An exportable session bundle should preserve:

- source `agent_turn.v1` ids or event paths
- prompt or task request
- agent-visible actions
- tool calls and command results
- file edits, diffs, or changed snippets
- verification commands and outcomes
- export/redaction gate

Do not inline raw host session JSONL, hidden reasoning, credentials, full files,
or long command output into turn events. Store long artifacts by path when they
need to remain available for later review.

## Trajectory Export

The exported debugging trajectory row is the compact derivative:

```text
problem -> context -> trajectory -> final fix -> verification -> outcome
```

Before treating an event as exportable data, ensure the row has:

- explicit schema version
- task prompt or problem statement
- minimal context
- concise trajectory steps
- final fix summary
- verification status
- outcome label
- small export gate

## Capture

- `capture-web` writes repo-local notes plus optional design artifacts
- `capture-pdf` writes repo-local notes from PDFs

## Lint

Lint checks:

- missing linked notes
- malformed notes
- missing skill playbook sections
- orphan notes
- overlapping skills

## Machine Setup

The user's agent may perform one-time machine setup.

Preferred first-time setup from the repo the user wants Datalox to manage:

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

The source clone owns `bin/adopt-host-repo.sh`. The adopted host repo owns host-local shims such as `bin/setup-multi-agent.sh`, `bin/install-default-host-integrations.sh`, and `bin/disable-default-host-integrations.sh`.

After setup, the user should keep using `codex` or `claude` normally from the target repo.

Claude native skills are legacy optional and install at `~/.claude/skills/<skill-name>/SKILL.md` only when setup is run with `--include-legacy-guidance`. Restart Claude Code only if it was already running before `~/.claude/skills` existed, or if the host does not pick up the new links live.

The Claude hook is sidecar post-run automation. `CLAUDE.md`, wrapper/shim paths, MCP tools, and repo-local docs remain the fallback when native skills are not surfaced.

## Stop

To stop Datalox-managed host interception:

- `bash bin/disable-default-host-integrations.sh`
- `node bin/datalox.js disable all --json`

To keep the wrapper but stop autonomous post-run review:

- set `DATALOX_DEFAULT_POST_RUN_MODE=off`
- or pass `--post-run-mode off`

The default wrapper post-run mode is `trajectory`. It records only an explicit
`debugging_trajectory.v1` row supplied by the agent through
`DATALOX_TRAJECTORY_ROW_FILE` or `DATALOX_TRAJECTORY_ROW`. Legacy trace
recording, promotion, and second-pass review require explicit `record`,
`promote`, or `review` modes. Default trajectory rows should stay
`curation.quality: "needs_review"` until deterministic grading and reviewer
approval justify `quality: "use"`.
