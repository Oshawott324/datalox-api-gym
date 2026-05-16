# Agent Configuration

The agent-facing contract is intentionally small.

Product boundary:

- Datalox MCP is the product-facing instrumentation and control layer.
- `datalox-agent-replay` is the repo-local implementation package.
- Approved B2B replay bundles and derived trajectory/evals are the primary product focus.
- `tool_io_record.v1` is the exact replay primitive.
- `agent_turn.v1` is the simple per-turn review primitive.
- Approved anonymized replay bundles are the source dataset asset.
- Lean, outcome-labeled trajectory exports are optional compact training/eval derivatives.
- Local `skills/` are agent guidance only, not a product data store.

Primary product loop:

```text
agent run -> tool I/O records -> replay bundle -> approval/export -> optional derivatives
```

## Main Surfaces

```text
.datalox/
  manifest.json
  config.json
  tool-io/
    records/
  replay-bundles/
  events/
    agent-turns/
  approvals/
  derivatives/
    trajectories/
docs/
DATALOX.md
AGENTS.md
skills/
```

## Read Order

1. `.datalox/manifest.json`
2. `.datalox/config.json`
3. `docs/product-definition.md`
4. `docs/tool-io-store-schema.md` when touching tool-call capture or replay
5. `docs/replay-bundle-schema.md` when touching replay bundles, approval, or export
6. `docs/agent-turn-schema.md` when touching turn review data
7. trajectory schema docs only when deriving optional trajectory/eval rows
8. selected `skills/<name>/SKILL.md` only when the task matches that skill

## Write Rule

New product writes go only to:

- `.datalox/events/agent-turns/`
- `.datalox/tool-io/records/`
- `.datalox/replay-bundles/`
- `.datalox/approvals/`
- `.datalox/derivatives/trajectories/`
- deterministic export artifacts under the chosen export output path

`.datalox/tool-io/records/` and `.datalox/events/agent-turns/` are the source
evidence surfaces. They can later be assembled into replay bundles, reviewed,
anonymized, shared, or used to derive compact trajectory rows.

## Source Kinds

Concrete source kinds only:

- `trace`
- `web`
- `pdf`

## Product Export Targets

- `tool_io_record.v1` as the exact replay primitive
- `agent_turn.v1` as the turn review primitive
- `replay_bundle.v1` as the source product artifact
- `debugging_trajectory.v1` as an optional coding/debugging derivative
- `agent_task_trajectory.v1` as an optional mixed-domain derivative

Tool I/O capture must follow [tool-io-store-schema.md](./tool-io-store-schema.md).
Replay bundles must follow [replay-bundle-schema.md](./replay-bundle-schema.md).
Turn review capture must follow [agent-turn-schema.md](./agent-turn-schema.md).
Derivative rows must follow the trajectory schema docs.

## Replay Capture

Use this user-facing copy when a session is captured:

> Datalox captured this agent session. It includes prompts, tool actions, file edits, and verification results. You can keep it private, review it, or share approved anonymized sessions with your organization/data program.

An exportable replay bundle should preserve:

- source `agent_turn.v1` ids or event paths
- source `tool_io_record.v1` ids or record paths
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

Replay capture is the target wrapper default. Any remaining trajectory-mode
wrapper behavior is an implementation gap tracked in the Option A plan, not the
product contract.
