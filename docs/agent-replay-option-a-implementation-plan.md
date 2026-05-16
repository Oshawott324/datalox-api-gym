# Agent Replay Option A Implementation Plan

This is the concrete implementation plan for turning this repo into Option A:
an MCP-compatible VCR for agent tools.

## Product Boundary

Datalox Agent Replay is not a trajectory-first tool.

Primary product:

```text
agent run -> tool I/O records -> replay bundle -> approval/export -> optional derivatives
```

Trajectory rows are optional downstream derivatives. They may remain only under
a derivative boundary. They must not be the install-facing MCP surface, wrapper
default, or first-read product story.

## Step 0: Freeze The Rename Baseline

Goal:

- finish the `datalox-agent-replay` identity cut before changing product logic

Change:

- keep package name as `datalox-agent-replay`
- keep cache path as `.datalox/cache/datalox-agent-replay`
- keep install docs pointed at the new repo URL
- keep active docs and instruction files free of old product names and legacy
  store names

Pass criteria:

- `npm test`
- `npm run check`
- `git diff --check`
- stale identity scan passes through `tests/repoIdentity.test.ts`
- GitHub repo exists at `Complexity-LLC/datalox-agent-replay`

## Step 1: Make Replay The Canonical Schema Layer

Goal:

- define the source product before adding runtime behavior

Add:

- `docs/tool-io-store-schema.md`
- `docs/replay-bundle-schema.md`

Update:

- `docs/product-definition.md`
- `docs/agent-turn-schema.md`
- `README.md`
- `START_HERE.md`
- `DATALOX.md`
- `AGENTS.md`
- `.datalox/manifest.json`

Canonical paths:

```text
.datalox/events/agent-turns/
.datalox/tool-io/records/
.datalox/replay-bundles/
.datalox/approvals/
.datalox/derivatives/trajectories/
```

Pass criteria:

- first-read docs describe replay bundles as the source product
- first-read docs describe trajectory rows only as optional derivatives
- no setup instruction tells agents to generate trajectory rows as the normal
  product capture step
- active docs contain the replay pipeline:

```text
agent run -> tool I/O records -> replay bundle -> approval/export -> optional derivatives
```

## Step 2: Implement The Content-Addressed Tool I/O Store

Goal:

- record every agent-visible tool call and observation in a deterministic store

Add:

- `src/core/canonicalJson.ts`
- `src/core/hash.ts`
- `src/core/toolIoSchema.ts`
- `src/core/toolIoStore.ts`
- `tests/toolIoStore.test.ts`

Record shape:

```ts
type ToolIoRecordV1 = {
  schema_version: "tool_io_record.v1";
  call_id: string;
  tool_name: string;
  arguments: unknown;
  request_hash: string;
  sequence_index: number;
  observation: {
    status: "ok" | "error";
    content?: unknown;
    error_code?: string;
    error_message?: string;
  };
  created_at: string;
};
```

Rules:

- `request_hash = sha256(canonical_json({ tool_name, arguments }))`
- identical `tool_name + arguments` records are ordered by `sequence_index`
- replay lookup requires `request_hash + sequence_index`
- observations are stored exactly as agent-visible data, not summarized

Pass criteria:

- same object with different key order produces the same hash
- same request recorded twice produces sequence indexes `0` and `1`
- replay lookup returns the exact stored observation
- missing replay lookup fails deterministically
- no heuristic matching or fuzzy fallback exists

## Step 3: Implement Replay Bundles

Goal:

- seal enough records for a task episode to replay and verify later

Add:

- `src/core/replayBundleSchema.ts`
- `src/core/replayBundle.ts`
- `tests/replayBundle.test.ts`

Bundle layout:

```text
.datalox/replay-bundles/<bundle-id>/
  manifest.json
  tool-io/*.json
  agent-turns/*.json
  checksums.json
```

CLI:

```bash
datalox bundle pack --repo . --bundle-id <id> --json
datalox bundle verify --repo . --bundle .datalox/replay-bundles/<id> --json
```

Pass criteria:

- `bundle pack` creates a deterministic manifest and checksums
- `bundle verify` passes immediately after pack
- `bundle verify` fails when any bundled file is changed, removed, or added
- a bundle can be verified without reading source `.datalox/tool-io/records`

## Step 4: Replace The Install-Facing MCP Surface

Goal:

- make `datalox-mcp` expose replay tools, not trajectory tools

Remove from install-facing MCP:

- trajectory record/export tools
- trajectory grading/repair tools
- any server name or file name that makes the primary MCP surface trajectory-first

Add:

- `src/mcp/replayServer.ts`
- `tests/replayMcp.test.ts`

Install-facing MCP tools:

- `record_tool_io`
- `record_agent_turn`
- `pack_replay_bundle`
- `verify_replay_bundle`
- `replay_tool_io`

Update:

- `bin/datalox-mcp.js`
- `package.json` `mcp:stdio`
- `README.md`
- `DATALOX.md`
- `START_HERE.md`
- `tests/adoptionScripts.test.ts`

Pass criteria:

- MCP list-tools shows replay tools only
- install-facing MCP tool names do not include trajectory terms
- setup docs point agents to replay capture
- tests prove the adopted repo contains the replay MCP entrypoint

## Step 5: Add The MCP VCR Proxy

Goal:

- let Datalox sit between an agent and upstream MCP tools

Add:

- `src/mcp/replayProxyServer.ts`
- `src/core/mcpProxyConfig.ts`
- `tests/mcpReplayProxy.test.ts`

Proxy config:

```json
{
  "schema_version": "datalox_replay_proxy_config.v1",
  "upstream": {
    "command": "node",
    "args": ["server.js"]
  }
}
```

CLI:

```bash
datalox proxy --mode record --config datalox.replay.json --json
datalox proxy --mode replay --bundle .datalox/replay-bundles/<id> --json
```

Record mode:

- forwards tool calls to upstream MCP
- records request hash, sequence index, arguments, and observation
- returns upstream observation to the agent unchanged

Replay mode:

- does not start upstream MCP
- looks up `request_hash + sequence_index`
- returns recorded observation unchanged
- fails deterministically when no record exists

Pass criteria:

- fake upstream MCP is called in record mode
- fake upstream MCP is not started in replay mode
- replay returns byte-equivalent observations
- missing replay record returns a structured error for the agent

## Step 6: Move Or Delete Trajectory Code

Goal:

- remove trajectory-first behavior from the product core

Allowed final state:

- trajectory code exists only under a derivative module
- or trajectory code is deleted entirely until replay bundles are stable

If kept, move to:

```text
src/core/derivatives/trajectory/
docs/derivatives/trajectory/
tests/derivatives/trajectory/
.datalox/derivatives/trajectories/
```

Remove from primary docs and runtime:

- trajectory MCP server files
- trajectory default wrapper mode
- trajectory row environment markers
- trajectory event roots as first-class product stores
- trajectory commands from first-read docs

Pass criteria:

- install-facing MCP exposes no trajectory tools
- wrapper default is replay capture, not trajectory capture
- active first-read docs mention trajectory only as a derivative
- any remaining trajectory code is under `derivatives/trajectory`
- full test suite passes after move/delete

## Step 7: Change Wrapper Defaults To Replay

Goal:

- make enforced host runs produce replay evidence by default

Update:

- `src/core/installCore.ts`
- wrapper adapters under `src/adapters/`
- `bin/datalox-claude.js`
- `bin/datalox-codex.js`
- `bin/datalox-wrap.js`
- wrapper tests

New default:

```bash
DATALOX_DEFAULT_POST_RUN_MODE=replay
```

Pass criteria:

- wrapper records replay evidence when explicit tool I/O records exist
- wrapper does not synthesize fake replay data from prose summaries
- wrapper does not write trajectory rows by default
- missing replay evidence records nothing and reports a clear agent-readable
  reason

## Step 8: Export Derivatives From Replay Bundles

Goal:

- make trajectory/eval rows derive from approved replay bundles, not from
  hand-authored session summaries

Add:

- `src/core/derivatives/trajectory/fromReplayBundle.ts`
- `tests/derivatives/trajectory/fromReplayBundle.test.ts`

Rules:

- derivative rows must reference a replay bundle id
- code-heavy rows must include exact code evidence from bundled artifacts
- derivative export is blocked when the replay bundle is unverified

Pass criteria:

- verified replay bundle can produce a compact derivative candidate
- unverified replay bundle blocks derivative export
- derivative JSONL rows are standalone enough for training/eval
- source replay bundle remains the source-of-truth asset

## Step 9: Regression Gates

Goal:

- prevent the repo from drifting back to trajectory-first or legacy-store
  behavior

Extend:

- `tests/repoIdentity.test.ts`
- adoption smoke tests
- MCP list-tools tests
- wrapper tests

Hard checks:

```bash
npm test
npm run check
git diff --check
```

Stale active-reference scan must fail on:

- old repo/package names
- legacy wiki-store paths
- removed hook/autonomous promotion paths
- install-facing trajectory MCP names
- trajectory default wrapper mode

Pass criteria:

- fresh adoption creates replay-focused product surfaces only
- fresh adoption does not create legacy stores
- install-facing MCP is replay-first
- full test suite and stale-reference scan pass

## Final Done Definition

This migration is done only when:

- the repo name, install docs, package identity, and remote repo are
  `datalox-agent-replay`
- the primary MCP surface records and replays tool I/O
- replay bundles are deterministic and verifiable
- wrapper default capture mode is replay
- trajectory rows are derivative-only or removed
- fresh adoption produces no legacy product paths
- tests enforce all of the above
