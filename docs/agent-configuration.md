# Agent Configuration

The agent-facing contract is intentionally small.

Product boundary:

- Datalox MCP is the product-facing instrumentation and control layer.
- `datalox-trajectory-mcp` is the repo-local implementation package.
- Approved B2B session data and derived trajectory/evals are the primary product focus.
- `agent_turn.v1` is the simple per-turn capture primitive.
- Approved anonymized sessions are the source dataset asset.
- Lean, outcome-labeled trajectory exports are compact training/eval derivatives.
- Local `skills/` are agent guidance only, not a product data store.

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
skills/
```

## Read Order

1. `.datalox/manifest.json`
2. `.datalox/config.json`
3. `docs/product-definition.md`
4. `docs/agent-turn-schema.md` when touching session capture, session export, or data sale
5. `docs/trajectory-dataset-schema.md` when touching trajectory recording, trajectory export, or data sale
6. `docs/agent-task-trajectory-schema.md` when touching mixed-domain task trajectories
7. selected `skills/<name>/SKILL.md` only when the task matches that skill

## Write Rule

New product writes go only to:

- `.datalox/events/agent-turns/`
- `.datalox/events/trajectory-rows/`
- `.datalox/events/agent-task-trajectories/`
- `.datalox/session-candidates/`
- `.datalox/approvals/`
- deterministic export artifacts under the chosen export output path

`.datalox/events/` is the source product evidence surface. Turns can later be
assembled into sessions, reviewed, anonymized, shared, or used to derive compact
trajectory rows.

## Source Kinds

Concrete source kinds only:

- `trace`
- `web`
- `pdf`

## Product Export Targets

- `agent_turn.v1` as the capture primitive
- approved anonymized session bundle
- `debugging_trajectory.v1` as the coding/debugging derivative
- `agent_task_trajectory.v1` as the mixed-domain derivative

Turn capture must follow [agent-turn-schema.md](./agent-turn-schema.md).
Debugging rows must follow
[trajectory-dataset-schema.md](./trajectory-dataset-schema.md). Mixed-domain
rows must follow
[agent-task-trajectory-schema.md](./agent-task-trajectory-schema.md).

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
- outcome label
- verification status
- small export gate

## Machine Setup

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
bash bin/setup-multi-agent.sh codex
bash bin/adopt-host-repo.sh "$TARGET_REPO"
node bin/datalox.js status --repo "$TARGET_REPO" --json
```

The source clone owns `bin/adopt-host-repo.sh`. The adopted host repo receives
the install stamp, instruction surfaces, `.datalox/` config, and host shims.

After setup, the user should keep using `codex` or `claude` normally from the
target repo.

## Stop

To stop Datalox-managed host interception:

- `bash bin/disable-default-host-integrations.sh`
- `node bin/datalox.js disable all --json`

To keep the wrapper but stop autonomous post-run recording:

- set `DATALOX_DEFAULT_POST_RUN_MODE=off`
- or pass `--post-run-mode off`

The default wrapper post-run mode is `trajectory`. It records only an explicit
row supplied by the agent through `DATALOX_TRAJECTORY_ROW_FILE` or
`DATALOX_TRAJECTORY_ROW`.
