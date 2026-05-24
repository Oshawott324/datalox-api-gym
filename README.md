# datalox-agent-replay

`datalox-agent-replay` is the repo-local implementation package for Datalox
Agent Replay: an MCP-compatible recorder/replay layer for agent tool I/O.

Datalox acts like a VCR for agent tools. It records the exact agent-visible
tool request and observation, stores that pair by deterministic request hash,
packs the records into sealed replay bundles, and can replay the same
observations later without calling live upstream tools.

In the broader agentic RL stack, Datalox owns the tool-I/O record/replay layer.
It is complementary to sandbox runtimes, environment builders, behavioral mocks,
and reward engines. During replay, recorded observations can act like
record-based mocks, but Datalox does not construct fake stateful environments or
invent unseen behavior.

Primary replay loop:

`agent tool call -> tool_io_record.v1 -> replay_bundle.v1 -> deterministic replay -> optional derivatives`

This branch does not ship a parallel wiki/note/event replay store.

## What It Writes

In an adopted repo, replay data and review state live under `.datalox/`:

```text
.datalox/
  events/
    agent-turns/
  tool-io/
    records/
  mcp-tool-catalogs/
  replay-bundles/
  approvals/
  derivatives/
    trajectories/
docs/
DATALOX.md
AGENTS.md
```

Use:

- `.datalox/tool-io/records/` for exact `tool_io_record.v1` request/observation records
- `.datalox/mcp-tool-catalogs/` for `mcp_tool_catalog.v1` snapshots of agent-visible MCP `tools/list` metadata
- `.datalox/events/agent-turns/` for optional `agent_turn.v1` review events that point at recorded tool I/O
- `.datalox/replay-bundles/` for portable `replay_bundle.v1` artifacts with manifests and checksums
- `.datalox/approvals/` for review/approval metadata
- `.datalox/derivatives/trajectories/` for optional compact training/eval adapters

The durable replay primitive is `tool_io_record.v1`. `action_observation.v1`
is a strict normalized view over recorded tool I/O and imported raw traces; it
is not a second store. `mcp_tool_catalog.v1` preserves the MCP proxy tool list
metadata needed to replay `tools/list` without live upstream tools.
`agent_turn.v1` is optional review context. A
`replay_bundle.v1` is the portable artifact that can be verified and replayed.
`debugging_trajectory.v1` and `agent_task_trajectory.v1` rows are downstream
derivatives when a team wants compact examples instead of full replay bundles.

User-facing capture copy:

> Datalox captured replay evidence for this agent session. It includes tool requests, tool observations, optional turn context, file edits, and verification results. You can keep it private, review it, or share an approved anonymized replay bundle with your organization/data program.

## Install

From the repo you want Datalox to manage, paste this into the agent chatbox and
send it. The agent should run it from the target repo root.

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

After setup, use `datalox-mcp` as the replay capture surface. Trajectory rows
are derivative-only artifacts and are not the replay capture path.

This does two separate things:

- `https://github.com/Oshawott324/datalox-agent-replay.git` is the current public source repo.
- `~/.datalox/cache/datalox-agent-replay` is the local source directory and package identity.
- `$TARGET_REPO` is the user's current project.
- Default adoption writes instruction surfaces and `.datalox/install.json` into the target repo.
- Fresh adoption does not create the removed wiki store or copy seed note/skill corpora.

Post-install checks from the target repo:

```bash
which codex
node "${HOME}/.datalox/cache/datalox-agent-replay/bin/datalox.js" status --repo . --json
codex exec "Check Datalox is active for this repo."
```

For Claude instead of Codex, run:

```bash
bash bin/setup-multi-agent.sh claude
```

If the source clone already exists, use it directly:

```bash
TARGET_REPO="$(pwd)"
PACK_REPO="${HOME}/.datalox/cache/datalox-agent-replay"
cd "$PACK_REPO"
git pull --ff-only
bash bin/setup-multi-agent.sh codex
bash bin/adopt-host-repo.sh "$TARGET_REPO"
node bin/datalox.js status --repo "$TARGET_REPO" --json
```

After adoption, the target repo has a local MCP entrypoint:

```bash
node bin/datalox-mcp.js
```

## CLI

Verified replay demo:

```bash
npm run demo:verified-replay
```

This records real MCP tool calls through the Datalox proxy, packs and verifies
a replay bundle, replays with upstream off, shows a deterministic replay miss,
and proves bundle tampering fails verification. See
[docs/verified-replay-quickstart.md](docs/verified-replay-quickstart.md).

Replay bundle commands:

```bash
node bin/datalox.js bundle pack --repo . --bundle-id <id> --json
node bin/datalox.js bundle verify --repo . --bundle .datalox/replay-bundles/<id> --json
```

MCP VCR proxy commands:

```bash
node bin/datalox.js proxy --mode record --repo . --config datalox.replay.json --json
node bin/datalox.js proxy --mode replay --repo . --bundle .datalox/replay-bundles/<id> --json
```

Record-mode proxy snapshots upstream MCP `tools/list` into
`.datalox/mcp-tool-catalogs/` and records exact tool calls into
`.datalox/tool-io/records/`. Replay-mode proxy verifies a replay bundle and
serves both `tools/list` and `tools/call` from bundled artifacts without
starting upstream.

Fixture world commands:

```bash
node bin/datalox.js fixtures install ../datalox-replay-fixtures/fixtures/github-pr-review-basic --json
node bin/datalox.js fixtures list --json
node bin/datalox.js fixture-sets install support-triage-basic@2026-06.0 --catalog ../datalox-replay-fixtures/catalog.json --json
node bin/datalox.js replay --fixture github-pr-review-basic@2026-05.0
```

Fixture install only caches and verifies data. Replay activation is separate.
See [docs/fixture-worlds-and-sets.md](docs/fixture-worlds-and-sets.md).

OpenAI-compatible fixture-set runs:

```bash
export OPENAI_BASE_URL=https://api.groq.com/openai/v1
export OPENAI_API_KEY=<key>
node bin/datalox.js run \
  --fixture-set support-triage-basic@2026-06.0 \
  --catalog ../datalox-replay-fixtures/catalog.json \
  --model <cheap-model> \
  --split train \
  --max-tasks 1 \
  --out exports/fixture-runs/support-triage-basic.jsonl \
  --json
```

`datalox run` auto-installs the fixture set, exposes replayed MCP tool
catalogs as OpenAI function tools, serves observations from
`request_hash + sequence_index`, and writes `datalox_fixture_run.v1` JSONL.
It works with OpenAI-compatible model servers, including vLLM and Groq. A
replay miss is returned to the model as a tool result with `liveFallback=false`;
the runner never calls live upstream tools to fill missing records.

Trajectory derivation code lives under `src/core/derivatives/trajectory/` and
is not exposed by the install-facing CLI or MCP surface.

Action/observation normalization lives in `src/core/actionObservation*.ts`. It
is a strict view over tool I/O records and raw trace events; it does not create
a second replay store.

Wrapper entrypoints:

```bash
node bin/datalox-claude.js -- --print "Update the docs."
node bin/datalox-codex.js -- exec "Update the docs."
node bin/datalox-wrap.js command --repo /path/to/repo --task "update docs" --prompt "Update the docs." -- <host-command> __DATALOX_PROMPT__
```

The installed shims infer the repo from the current working directory. Replay
capture is the wrapper default. If a wrapped run creates explicit
`tool_io_record.v1` records, the wrapper records an `agent_turn.v1` event that
references those exact records. If no tool I/O evidence appears, the wrapper
records nothing and reports why; it does not synthesize replay data from prose.
Wrappers do not write trajectory rows.

To stop Datalox-managed host interception later:

```bash
bash bin/disable-default-host-integrations.sh
```

To keep the wrapper but stop post-run recording:

```bash
export DATALOX_DEFAULT_POST_RUN_MODE=off
```

## MCP

The install-facing MCP surface should be replay-first:

- `record_tool_io`
- `record_agent_turn`
- `pack_replay_bundle`
- `verify_replay_bundle`
- `replay_tool_io`

Start the MCP server with:

```bash
datalox-mcp
```

For local source-tree testing:

```bash
node dist/src/mcp/replayServer.js
```

For code-heavy `agent_task_trajectory.v1` rows, a use-quality derivative export
requires at least one exact `code_change` evidence block. Local code
`source_reference` blocks are useful provenance, but they do not replace
before/after snippets or patch hunks.

## Core Contract

- Record exact tool I/O first; derive everything else from replay evidence.
- Use `request_hash + sequence_index` as the replay lookup key.
- Never synthesize replay records from prose summaries.
- Replay mode returns recorded observations or fails clearly; it does not call live tools as a hidden fallback.
- `action_observation.v1` is the normalized view over replay records and imported traces.
- `agent_turn.v1` adds compact turn review context when useful, but the replayable evidence remains in `.datalox/tool-io/records/`.
- `debugging_trajectory.v1` and `agent_task_trajectory.v1` are optional downstream adapters, not the capture layer.

## Docs

- [DATALOX.md](DATALOX.md)
- [docs/project-definition.md](docs/project-definition.md)
- [docs/agentic-rl-layer-map.md](docs/agentic-rl-layer-map.md)
- [docs/reference-bundle-plan.md](docs/reference-bundle-plan.md)
- [docs/pitch-deck.md](docs/pitch-deck.md)
- [examples/reference-bundles/README.md](examples/reference-bundles/README.md)
- [docs/replay-quickstart.md](docs/replay-quickstart.md)
- [docs/agent-replay-option-a-implementation-plan.md](docs/agent-replay-option-a-implementation-plan.md)
- [docs/action-observation-schema.md](docs/action-observation-schema.md)
- [docs/tool-io-store-schema.md](docs/tool-io-store-schema.md)
- [docs/replay-bundle-schema.md](docs/replay-bundle-schema.md)
- [docs/agent-turn-schema.md](docs/agent-turn-schema.md)
- [docs/derivatives/trajectory/trajectory-dataset-schema.md](docs/derivatives/trajectory/trajectory-dataset-schema.md)
- [docs/derivatives/trajectory/agent-task-trajectory-schema.md](docs/derivatives/trajectory/agent-task-trajectory-schema.md)
- [docs/task-orchestration.md](docs/task-orchestration.md)
- [docs/agent-configuration.md](docs/agent-configuration.md)
