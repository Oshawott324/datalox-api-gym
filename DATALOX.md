# Datalox

This repo is the portable implementation package for Datalox API Gym:
resettable, verifiable API worlds where agents can practice realistic tool use
before touching production systems.

The product object is an API world, not a replay log. A useful API world has
stateful entities, side effects, async events, permission boundaries, seeded
task scenarios, hidden verifier state, replay evidence, and training/eval
exports.

Replay is a feature of API Gym. It freezes exact tool observations from live
APIs, MCP tools, domain tools, or previous world runs so the same episode can
be reused later without live upstream calls.

Core replay surfaces:

- exact replay primitive: `tool_io_record.v1`
- replay lookup key: `request_hash + sequence_index`
- normalized view over replay records and imported traces: `action_observation.v1`
- proxy tool catalog metadata: `mcp_tool_catalog.v1`
- optional turn review context: `agent_turn.v1`
- portable replay artifact: `replay_bundle.v1`
- optional downstream adapters: `debugging_trajectory.v1`, `agent_task_trajectory.v1`

Primary API Gym loop:

`API world -> task scenario -> agent run -> verifier/replay evidence -> training/eval exports`

Snapshot authoring loop:

`live MCP/API/domain env -> agent rollout -> tool_io_record.v1 -> replay_bundle.v1 -> world pack/version`

Datalox API Gym owns API-world packaging, tool contracts, verifier metadata,
run evidence, replay mode, and export adapters. This repo does not own
production API aggregation, sandbox runtimes, model trainers, reward model
research, or generic robot/lab simulators.

Near-term target:

```text
billing-support-miniworld@2026-06
  fake_billing_api + fake_support_api + fake_crm_api + fake_email_api
  -> sampled state scenarios -> verifier/replay evidence -> export rows
```

API aggregators connect agents to real APIs. Datalox API Gym gives agents
resettable practice worlds for API workflows. See
[docs/project-definition.md](docs/project-definition.md).

Do not keep note/skill promotion as a second loop in this repo.

## Read Order

On each loop:

1. read `.datalox/manifest.json`
2. read `.datalox/config.json`
3. read `docs/project-definition.md` when it exists
4. read `docs/action-observation-schema.md` when the work touches raw trace normalization or action schema
5. read `docs/tool-io-store-schema.md` when the work touches tool-call capture or replay
6. read `docs/replay-bundle-schema.md` when the work touches replay bundles, approval, or export
7. read `docs/agent-turn-schema.md` when the work touches turn review data
8. read trajectory schema docs only when deriving optional trajectory/eval rows
9. read a selected `skills/<name>/SKILL.md` only when the user explicitly asks for that local skill

## Knowledge Surfaces

The repo-local replay data surfaces are:

- `.datalox/events/agent-turns/`
- `.datalox/tool-io/records/`
- `.datalox/mcp-tool-catalogs/`
- `.datalox/replay-bundles/`
- `.datalox/approvals/`
- `.datalox/derivatives/trajectories/`
- `docs/action-observation-schema.md`
- `docs/tool-io-store-schema.md`
- `docs/replay-bundle-schema.md`
- `docs/agentic-rl-layer-map.md`
- `docs/agent-turn-schema.md`
- `docs/derivatives/trajectory/trajectory-dataset-schema.md`
- `docs/derivatives/trajectory/agent-task-trajectory-schema.md`

Fresh replay adoption creates `.datalox/`, instruction surfaces, and shims. It
does not create a parallel wiki/note/event store.

## Replay Bundle Rule

Raw traces and prose summaries are not replay records.

A replay bundle should preserve:

- `agent_turn.v1` source turn ids or event paths
- `tool_io_record.v1` source record ids or record paths
- `mcp_tool_catalog.v1` source catalog ids or catalog paths when captured by the MCP VCR proxy
- prompts or task requests
- agent-visible actions
- tool calls and command results
- file edits, diffs, or changed snippets
- verification commands and outcomes
- export/redaction status

User-facing capture copy:

> Datalox captured replay evidence for this agent session. It includes tool requests, tool observations, optional turn context, file edits, and verification results. You can keep it private, review it, or share an approved anonymized replay bundle with your organization/data program.

## Turn Recording

`action_observation.v1` is the strict normalized view of one replayable action
and observation. It is not a second store.

`tool_io_record.v1` is the exact persisted replay primitive. It records one
agent-visible tool request and observation with a deterministic request hash
and sequence index.

`AgentTurnV1` is the simple turn review primitive. It records one completed
turn with the user prompt when safe, a short assistant summary, meaningful tool
call references, file change summaries, verification evidence, and
export/redaction status.

Replay bundles are assembled from `tool_io_record.v1` records and optional
`agent_turn.v1` events. A trajectory row is derived only when compact
training/eval packaging is useful.

## Optional Derivative Trajectory Rows

Trajectory rows are derivative artifacts. They are valid only when they follow
[docs/derivatives/trajectory/trajectory-dataset-schema.md](docs/derivatives/trajectory/trajectory-dataset-schema.md) or
[docs/derivatives/trajectory/agent-task-trajectory-schema.md](docs/derivatives/trajectory/agent-task-trajectory-schema.md)
and include grounded evidence, a final outcome, and an export gate.

For mixed-domain implementation work, code-heavy derivative rows must include
exact `code_change` evidence before `quality: "use"` derivative export. Use
compact before/after snippets or patch hunks for the key code edit. A
local-file `source_reference` is provenance and context; it does not replace
`code_change`.

## Install

The source clone should live outside the target repo:

```bash
TARGET_REPO="$(pwd)"
PACK_REPO="${HOME}/.datalox/cache/datalox-api-gym"
mkdir -p "$(dirname "$PACK_REPO")"
[ -d "$PACK_REPO/.git" ] && git -C "$PACK_REPO" pull --ff-only || git clone https://github.com/Oshawott324/datalox-api-gym.git "$PACK_REPO"
cd "$PACK_REPO"
bash bin/setup-multi-agent.sh codex
bash bin/adopt-host-repo.sh "$TARGET_REPO"
node bin/datalox.js status --repo "$TARGET_REPO" --json
```

Supported default paths:

- Codex shim: `~/.local/bin/codex`
- Claude shim: `~/.local/bin/claude`
- Generic wrapper: `datalox wrap`
- MCP entrypoint: `datalox-mcp`
- MCP VCR proxy: `datalox proxy --mode record --config datalox.replay.json` or
  `datalox proxy --mode replay --bundle .datalox/replay-bundles/<id>`

The Claude hook is sidecar post-run automation. It cannot prove Claude used the
right guidance before acting. Wrapper/shim paths, MCP tools, and repo-local docs
are the robust surfaces.
