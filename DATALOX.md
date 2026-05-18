# Datalox

This repo is the portable implementation package for Datalox Agent Replay.

Datalox records agent-visible tool I/O, turn summaries, file edits, and
verification evidence so teams can reproduce agent behavior later. Approved
replay bundles are the source product, and trajectory/eval rows are optional
derivatives.

The capture taxonomy is intentionally small:

- source kinds: `trace`, `web`, `pdf`
- replay primitive: `tool_io_record.v1`
- review primitive: `agent_turn.v1`
- source export target: approved anonymized `replay_bundle.v1`
- optional derivative targets: `debugging_trajectory.v1`, `agent_task_trajectory.v1`

Primary product loop:

`agent run -> tool I/O records -> replay bundle -> approval/export -> optional derivatives`

Do not keep note/skill promotion as a second product loop in this repo.

## Read Order

On each loop:

1. read `.datalox/manifest.json`
2. read `.datalox/config.json`
3. read `docs/product-definition.md` when it exists
4. read `docs/tool-io-store-schema.md` when the work touches tool-call capture or replay
5. read `docs/replay-bundle-schema.md` when the work touches replay bundles, approval, or export
6. read `docs/agent-turn-schema.md` when the work touches turn review data
7. read trajectory schema docs only when deriving optional trajectory/eval rows
8. read a selected `skills/<name>/SKILL.md` only when the user explicitly asks for that local skill

## Knowledge Surfaces

The repo-local product data surfaces are:

- `.datalox/events/agent-turns/`
- `.datalox/tool-io/records/`
- `.datalox/replay-bundles/`
- `.datalox/approvals/`
- `.datalox/derivatives/trajectories/`
- `docs/tool-io-store-schema.md`
- `docs/replay-bundle-schema.md`
- `docs/agent-turn-schema.md`
- `docs/trajectory-dataset-schema.md`
- `docs/agent-task-trajectory-schema.md`

Fresh product adoption creates `.datalox/`, instruction surfaces, and shims. It
does not create a parallel wiki/note/event store.

## Replay Bundle Rule

Unapproved raw traces are not sellable data.

The source data product is an approved anonymized replay bundle. It should
preserve:

- `agent_turn.v1` source turn ids or event paths
- `tool_io_record.v1` source record ids or record paths
- prompts or task requests
- agent-visible actions
- tool calls and command results
- file edits, diffs, or changed snippets
- verification commands and outcomes
- export/redaction status

User-facing capture copy:

> Datalox captured this agent session. It includes prompts, tool actions, file edits, and verification results. You can keep it private, review it, or share approved anonymized sessions with your organization/data program.

## Turn Recording

`tool_io_record.v1` is the exact replay primitive. It records one agent-visible
tool request and observation with a deterministic request hash and sequence
index.

`AgentTurnV1` is the simple turn review primitive. It records one completed
turn with the user prompt when safe, a short assistant summary, meaningful tool
call references, file change summaries, verification evidence, and
export/redaction status.

Approved replay bundles are assembled from `tool_io_record.v1` records and
`agent_turn.v1` events. A trajectory row is derived only when compact
training/eval packaging is useful.

## Optional Derivative Trajectory Rows

Trajectory rows are derivative artifacts. They are valid only when they follow
[docs/trajectory-dataset-schema.md](docs/trajectory-dataset-schema.md) or
[docs/agent-task-trajectory-schema.md](docs/agent-task-trajectory-schema.md)
and include grounded evidence, a final outcome, and an export gate.

For mixed-domain implementation work, code-heavy derivative rows must include
exact `code_change` evidence before buyer-facing `quality: "use"` export. Use
compact before/after snippets or patch hunks for the key code edit. A
local-file `source_reference` is provenance and context; it does not replace
`code_change`.

## Install

The source clone should live outside the target repo:

```bash
TARGET_REPO="$(pwd)"
PACK_REPO="${HOME}/.datalox/cache/datalox-agent-replay"
mkdir -p "$(dirname "$PACK_REPO")"
[ -d "$PACK_REPO/.git" ] && git -C "$PACK_REPO" pull --ff-only || git clone https://github.com/Oshawott324/datalox-agent-replay.git "$PACK_REPO"
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
