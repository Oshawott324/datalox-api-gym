# Datalox

This repo is the portable implementation package for Datalox Agent Replay.

Datalox records agent-visible prompts, tool actions, file edits, verification
results, and replay evidence so teams can reproduce agent behavior later.
Approved anonymized sessions and trajectory/eval rows are derived from that
source data.

The capture taxonomy is intentionally small:

- source kinds: `trace`, `web`, `pdf`
- capture primitive: `agent_turn.v1`
- source export target: approved anonymized replay/session bundle
- trajectory derivative targets: `debugging_trajectory.v1`, `agent_task_trajectory.v1`

Primary product loop:

`agent run -> AgentTurnV1 events + tool I/O evidence -> replay/session bundle -> export/redaction gate -> approved replay dataset -> optional trajectory/eval rows`

Do not keep note/skill promotion as a second product loop in this repo.

## Read Order

On each loop:

1. read `.datalox/manifest.json`
2. read `.datalox/config.json`
3. read `docs/product-definition.md` when it exists
4. read `docs/agent-turn-schema.md` when the work touches session capture, session export, or data sale
5. read `docs/trajectory-dataset-schema.md` when the work touches debugging trajectory recording, trajectory export, or data sale
6. read `docs/agent-task-trajectory-schema.md` when the work touches mixed-domain agent episodes
7. read a selected `skills/<name>/SKILL.md` only when the user explicitly asks for that local skill

## Knowledge Surfaces

The repo-local product data surfaces are:

- `.datalox/events/agent-turns/`
- `.datalox/events/trajectory-rows/`
- `.datalox/events/agent-task-trajectories/`
- `.datalox/session-candidates/`
- `.datalox/approvals/`
- `docs/agent-turn-schema.md`
- `docs/trajectory-dataset-schema.md`
- `docs/agent-task-trajectory-schema.md`

Fresh product adoption creates `.datalox/`, instruction surfaces, and shims. It
does not create a parallel wiki/note/event store.

## Trajectory Dataset Rule

Unapproved raw traces are not sellable data.

The source data product is an approved anonymized agent session bundle. It should preserve:

- `agent_turn.v1` source turn ids or event paths
- prompts or task requests
- agent-visible actions
- tool calls and command results
- file edits, diffs, or changed snippets
- verification commands and outcomes
- export/redaction status

User-facing capture copy:

> Datalox captured this agent session. It includes prompts, tool actions, file edits, and verification results. You can keep it private, review it, or share approved anonymized sessions with your organization/data program.

A trajectory export row is a compact derivative. It is valid only when it
follows [docs/trajectory-dataset-schema.md](docs/trajectory-dataset-schema.md)
or [docs/agent-task-trajectory-schema.md](docs/agent-task-trajectory-schema.md)
and includes grounded evidence, a final outcome, and an export gate.

For mixed-domain implementation work, code-heavy rows must include exact
`code_change` evidence before buyer-facing `quality: "use"` export. Use compact
before/after snippets or patch hunks for the key code edit. A local-file
`source_reference` is provenance and context; it does not replace `code_change`.

## Turn Recording

`AgentTurnV1` is the simple capture primitive. It records one completed turn with
the user prompt when safe, a short assistant summary, meaningful tool calls, file
change summaries, verification evidence, and export/redaction status.

Approved replay/session bundles are assembled from `agent_turn.v1` events. A
trajectory row is derived only when compact training/eval packaging is useful.

## Trajectory Recording

After a coding-debugging run, the agent should build one lean
`debugging_trajectory.v1` row from observed facts:

- task prompt or problem statement
- minimal context needed to understand the fix
- concise user/agent/tool trajectory steps
- final fix summary and changed files or patch
- explicit outcome label and verification status
- small export gate

Then call MCP tool `record_trajectory` with `repo_path` and `trajectory_row`.

`context.relevant_files[].before` and `after` must contain exact minimal code
snippets, not prose summaries. Put prose in `context.notes`,
`trajectory.content`, or `final.explanation`.

`record_trajectory` writes a structured event under
`.datalox/events/trajectory-rows/`, stores the row at `trajectoryRow`, appends
the owning event path to `trajectoryRow.export.source_event_paths`, and returns
the deterministic readiness details.

If a row claims `curation.quality: "use"` but deterministic training-grade
checks fail, `record_trajectory` still records the valid evidence but stores it
as `needs_review` with downgrade metadata. Repair the row with real code
snippets, then use `repair_trajectory` to write a corrected linked event.

Wrapper runs use the same explicit-row rule. For coding-debugging work, write
the row to a repo-local file such as `.datalox/trajectory-rows/<stable-id>.json`
and append:

```text
DATALOX_TRAJECTORY_ROW_FILE: .datalox/trajectory-rows/<stable-id>.json
```

The wrapper records that row in default `trajectory` mode. If the marker is
absent, the wrapper records nothing.

CLI equivalents:

- `datalox record-trajectory --repo . --trajectory-row row.json --json`
- `datalox grade-trajectories --repo . --json`
- `datalox repair-trajectory --repo . --event-path .datalox/events/trajectory-rows/bad-row.json --trajectory-row corrected-row.json --json`
- `datalox export-trajectories --repo . --quality use --json`
- `datalox record-agent-task-trajectory --repo . --agent-task-trajectory row.json --json`
- `datalox export-agent-task-trajectories --repo . --quality use --json`

## Install

The source clone should live outside the target repo:

```bash
TARGET_REPO="$(pwd)"
PACK_REPO="${HOME}/.datalox/cache/datalox-agent-replay"
mkdir -p "$(dirname "$PACK_REPO")"
[ -d "$PACK_REPO/.git" ] && git -C "$PACK_REPO" pull --ff-only || git clone https://github.com/Complexity-LLC/datalox-agent-replay.git "$PACK_REPO"
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

The Claude hook is sidecar post-run automation. It cannot prove Claude used the
right guidance before acting. Wrapper/shim paths, MCP tools, and repo-local docs
are the robust surfaces.
