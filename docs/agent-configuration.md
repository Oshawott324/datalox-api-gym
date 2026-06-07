# Agent Configuration

The agent-facing contract is intentionally small.

Project boundary:

- Datalox MCP is the install-facing instrumentation and control layer.
- `datalox-api-gym` is the repo-local implementation package.
- Resettable, verifiable API worlds are the primary project focus; replay is the evidence mode.
- `action_observation.v1` is the strict normalized view over replay records and imported traces.
- `tool_io_record.v1` is the exact replay primitive.
- `mcp_tool_catalog.v1` preserves MCP proxy `tools/list` metadata.
- `agent_turn.v1` is optional per-turn review context.
- `replay_bundle.v1` is the portable artifact that can be verified and replayed.
- Lean, outcome-labeled trajectory exports are optional compact training/eval adapters.
- Local `skills/` are agent guidance only, not a replay data store.

Layer boundary:

- Datalox owns API-world packaging, tool contracts, verifier metadata, replay
  evidence, and export adapters.
- Datalox does not own production API aggregation, sandbox runtimes, model
  trainers, reward model research, or generic robot/lab simulators.

Primary API Gym loop:

```text
API world -> task scenario -> agent run -> verifier/replay evidence -> training/eval exports
```

## Main Surfaces

```text
.datalox/
  manifest.json
  config.json
  tool-io/
    records/
  mcp-tool-catalogs/
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
3. `docs/project-definition.md`
4. `docs/action-observation-schema.md` when touching raw trace normalization or action schema
5. `docs/tool-io-store-schema.md` when touching tool-call capture or replay
6. `docs/replay-bundle-schema.md` when touching replay bundles, approval, or export
7. `docs/agent-turn-schema.md` when touching turn review data
8. trajectory schema docs only when deriving optional trajectory/eval rows
9. selected `skills/<name>/SKILL.md` only when the task matches that skill

## Write Rule

New replay writes go only to:

- `.datalox/events/agent-turns/`
- `.datalox/tool-io/records/`
- `.datalox/mcp-tool-catalogs/`
- `.datalox/replay-bundles/`
- `.datalox/approvals/`
- `.datalox/derivatives/trajectories/`
- deterministic export artifacts under the chosen export output path

`.datalox/tool-io/records/`, `.datalox/mcp-tool-catalogs/`, and
`.datalox/events/agent-turns/` are the source evidence surfaces. They can later
be assembled into replay bundles, reviewed, anonymized, shared, or used to
derive compact trajectory rows.

## Replay Schema Targets

- `tool_io_record.v1` as the exact replay primitive
- `action_observation.v1` as the strict normalized view over replay records and imported traces
- `mcp_tool_catalog.v1` as MCP proxy `tools/list` metadata
- `agent_turn.v1` as optional turn review context
- `replay_bundle.v1` as the portable replay artifact
- `debugging_trajectory.v1` as an optional coding/debugging derivative
- `agent_task_trajectory.v1` as an optional mixed-domain derivative

Action/observation normalization must follow [action-observation-schema.md](./action-observation-schema.md).
Tool I/O capture must follow [tool-io-store-schema.md](./tool-io-store-schema.md).
Replay bundles must follow [replay-bundle-schema.md](./replay-bundle-schema.md).
Turn review capture must follow [agent-turn-schema.md](./agent-turn-schema.md).
Derivative rows must follow the trajectory schema docs.

## Replay Capture

Use this user-facing copy when a session is captured:

> Datalox captured replay evidence for this agent session. It includes tool requests, tool observations, optional turn context, file edits, and verification results. You can keep it private, review it, or share an approved anonymized replay bundle with your organization/data program.

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

## Optional Derivative Export

A debugging trajectory row is an optional compact derivative:

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
PACK_REPO="${HOME}/.datalox/cache/datalox-api-gym"
mkdir -p "$(dirname "$PACK_REPO")"
if [ -d "$PACK_REPO/.git" ]; then
  git -C "$PACK_REPO" pull --ff-only
else
  git clone https://github.com/Oshawott324/datalox-api-gym.git "$PACK_REPO"
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

Replay capture is the target wrapper default. Trajectory rows are optional
derivatives and are not the replay capture contract.
