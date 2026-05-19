# Agent Replay Option A Implementation Plan

This is the concrete implementation plan for turning this repo into Option A:
an MCP-compatible VCR for agent tools.

## Project Boundary

Datalox Agent Replay is not a trajectory-first tool.

Primary replay loop:

```text
agent tool call -> tool_io_record.v1 -> replay_bundle.v1 -> deterministic replay -> optional derivatives
```

Trajectory rows are optional downstream derivatives. They may remain only under
a derivative boundary. They must not be the install-facing MCP surface, wrapper
default, or first-read project story.

After the replay design review, the entry wedge is sharper:

```text
tool_io_record.v1 -> action_observation.v1 -> replay_bundle.v1
```

MCP standardizes tool calling. Datalox should standardize replayable
action/observation evidence across agent hosts, tool wrappers, and raw traces.
Replay bundles remain the portable package, but the next implementation layer must
prove stable action schema normalization before adding richer derivative rows.

## Step 0: Freeze The Rename Baseline

Goal:

- finish the `datalox-agent-replay` identity cut before changing project logic

Change:

- keep package name as `datalox-agent-replay`
- keep cache path as `.datalox/cache/datalox-agent-replay`
- keep install docs pointed at the new repo URL
- keep active docs and instruction files free of old project names and legacy
  store names

Pass criteria:

- `npm test`
- `npm run check`
- `git diff --check`
- stale identity scan passes through `tests/repoIdentity.test.ts`
- GitHub repo exists at `Oshawott324/datalox-agent-replay`

## Step 1: Make Replay The Canonical Schema Layer

Goal:

- define the replay artifact before adding runtime behavior

Add:

- `docs/tool-io-store-schema.md`
- `docs/replay-bundle-schema.md`

Update:

- `docs/project-definition.md`
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

- first-read docs describe replay bundles as the portable replay artifact
- first-read docs describe trajectory rows only as optional derivatives
- no setup instruction tells agents to generate trajectory rows as the normal
  replay capture step
- active docs contain the replay pipeline:

```text
agent tool call -> tool_io_record.v1 -> replay_bundle.v1 -> deterministic replay -> optional derivatives
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

- let Datalox sit between an agent and upstream MCP tools as the enforced
  record/replay boundary
- make the proxy faithful enough that an agent can point its MCP client at
  Datalox instead of the upstream server without changing task behavior
- make replay mode deterministic: no upstream process, no live fallback, no
  fuzzy matching, and no unverified bundle reads

Current state:

- `src/mcp/replayProxyServer.ts`, `src/core/mcpProxyConfig.ts`, CLI routing, and
  `tests/mcpReplayProxy.test.ts` exist as an alpha implementation.
- The production gate is not passed until the proxy verifies bundles before
  replay, preserves upstream tool schemas, separates upstream failures from
  Datalox record-write failures, and has complete record/replay regression
  tests.

Add:

- `src/mcp/replayProxyServer.ts`
- `src/core/mcpProxyConfig.ts`
- `tests/mcpReplayProxy.test.ts`

Harden or add:

- `src/core/mcpToolCatalogSchema.ts` if the proxy needs a first-class persisted
  snapshot of upstream `tools/list`
- `src/core/mcpToolCatalogStore.ts` if catalog snapshots are persisted before
  bundle packing
- replay bundle packing support for proxy catalog artifacts if replay mode
  needs exact tool schemas without starting upstream
- `docs/replay-quickstart.md` proxy section
- `README.md`, `DATALOX.md`, and `START_HERE.md` install-facing proxy examples

Non-goals:

- do not implement a reward engine
- do not implement a sandbox runtime
- do not create trajectory rows from proxy traffic
- do not infer missing tool observations from logs, stdout, or final answers
- do not call upstream in replay mode as a hidden fallback

Proxy config v1:

```json
{
  "schema_version": "datalox_replay_proxy_config.v1",
  "upstream": {
    "command": "node",
    "args": ["server.js"],
    "cwd": ".",
    "env": {
      "EXAMPLE_API_BASE": "https://example.internal"
    }
  },
  "record": {
    "session_id": "optional-session-id",
    "turn_id": "optional-turn-id",
    "export": {
      "allowed": false,
      "redaction": "blocked"
    }
  }
}
```

Config rules:

- `schema_version` must be exactly `datalox_replay_proxy_config.v1`.
- `upstream.command` is required and must be non-empty.
- `upstream.args` defaults to `[]`.
- `upstream.cwd`, when present, resolves relative to the config file directory,
  not whichever directory launched the proxy.
- `upstream.env`, when present, is merged over `process.env` for the upstream
  MCP process only.
- `record.session_id`, `record.turn_id`, and `record.export` are optional
  metadata copied into each `tool_io_record.v1` created by the proxy.
- Unknown config fields fail strict validation.

CLI:

```bash
datalox proxy --mode record --config datalox.replay.json --json
datalox proxy --mode replay --bundle .datalox/replay-bundles/<id> --json
```

CLI rules:

- `--mode record` requires a valid config.
- `--mode replay` requires a replay bundle path.
- `--repo` resolves `.datalox` storage and relative bundle paths.
- `--json` must not change MCP stdio protocol output. If diagnostic output is
  needed, write it to stderr only when it cannot corrupt MCP stdio framing.
- startup failures must exit non-zero with an agent-readable error.

Architecture:

```text
agent MCP client
  -> Datalox proxy MCP server
    -> record mode: upstream MCP client -> upstream MCP server
    -> replay mode: verified replay bundle -> recorded observations
```

Record mode lifecycle:

1. Parse and validate proxy config.
2. Start upstream MCP server with configured command, args, cwd, and env.
3. Connect an MCP client to upstream.
4. Call upstream `tools/list`.
5. Expose the same tool names, descriptions, and input schemas to the agent.
6. For every downstream `tools/call`:
   - preserve exact agent-visible arguments
   - call upstream with the same tool name and arguments
   - preserve the exact upstream `CallToolResult` returned to the agent
   - record one `tool_io_record.v1` with:
     - `tool_name`
     - exact `arguments`
     - deterministic `request_hash`
     - computed `sequence_index`
     - exact observation content or structured error
     - source metadata showing proxy mode and upstream command
     - optional session, turn, and export metadata from config
   - return the upstream result unchanged after record succeeds
7. On shutdown, close the upstream client and child process cleanly.

Replay mode lifecycle:

1. Resolve the replay bundle path from `--repo` and `--bundle`.
2. Verify the replay bundle checksums before serving any MCP request.
3. Load bundled `tool_io_record.v1` records only from the verified bundle, not
   from source `.datalox/tool-io/records`.
4. Load the recorded tool catalog snapshot if implemented. If no catalog
   snapshot exists, expose only recorded tool names with a strict documented
   passthrough schema and mark this as an alpha limitation.
5. Do not start, connect to, or inspect the upstream MCP server.
6. For every downstream `tools/call`:
   - compute `request_hash = sha256(canonical_json({ tool_name, arguments }))`
   - increment the in-memory replay counter for that request hash
   - look up `request_hash + sequence_index` inside the verified bundle
   - return the recorded observation exactly when found
   - return a structured MCP error when missing

Tool catalog fidelity:

- The proxy should preserve upstream `tools/list` as part of the agent-visible
  environment.
- Record mode should not replace upstream schemas with a generic passthrough
  schema unless the SDK layer makes exact schema forwarding impossible.
- If `McpServer.registerTool` cannot preserve raw JSON Schema from upstream,
  implement the proxy with lower-level MCP request handlers for `tools/list` and
  `tools/call` instead of losing schema fidelity.
- Production replay should list the same tool names and input schemas that were
  visible during record mode. If that requires a catalog artifact, add a strict
  `mcp_tool_catalog.v1` artifact and bundle it with checksums.
- Tool catalog artifacts are replay metadata, not trajectory rows.

Suggested `mcp_tool_catalog.v1` if needed:

```ts
type McpToolCatalogV1 = {
  schema_version: "mcp_tool_catalog.v1";
  id: string;
  created_at: string;
  upstream: {
    command: string;
    args: string[];
    cwd?: string;
  };
  tools: Array<{
    name: string;
    description?: string;
    input_schema: unknown;
    output_schema?: unknown;
    annotations?: unknown;
  }>;
  export: {
    allowed: boolean;
    redaction: "none_needed" | "applied" | "blocked";
    approval_id?: string;
  };
};
```

Tool I/O record mapping:

```text
upstream tool name             -> tool_io_record.v1.tool_name
agent-provided arguments       -> tool_io_record.v1.arguments
sha256 canonical request       -> tool_io_record.v1.request_hash
same request occurrence order  -> tool_io_record.v1.sequence_index
upstream CallToolResult        -> observation.status="ok", observation.content
upstream tool exception        -> observation.status="error", upstream error fields
proxy recording failure        -> proxy error, not upstream error
```

Observation rules:

- A successful upstream MCP `CallToolResult` is recorded as
  `observation.status = "ok"` and `observation.content = <CallToolResult>`.
- An upstream MCP result with `isError: true` is still an upstream observation.
  Record the exact result. Do not convert it into a Datalox infrastructure
  failure.
- An exception thrown while calling upstream is recorded as
  `observation.status = "error"` with `error_code = "upstream_tool_error"`.
- A Datalox write, validation, checksum, or replay lookup failure is a proxy
  infrastructure error. It must not be mislabeled as an upstream tool error.
- Record mode should fail closed on Datalox write failure. Do not return an
  upstream answer while silently failing to record when the user is in record
  mode.
- Replay mode returns only recorded observations or structured replay misses.

Replay miss shape:

```json
{
  "isError": true,
  "content": [
    {
      "type": "text",
      "text": "{\"error\":{\"code\":\"replay_miss\",\"message\":\"...\"}}"
    }
  ],
  "structuredContent": {
    "error": {
      "code": "replay_miss",
      "message": "No tool_io_record.v1 replay record for request_hash=... sequence_index=...",
      "request_hash": "sha256:...",
      "sequence_index": 0
    }
  }
}
```

Sequence index rules:

- Record mode uses the content-addressed store rule: repeated identical
  `tool_name + arguments` records get sequence indexes `0`, `1`, `2`, ...
- Replay mode keeps an in-memory counter per `request_hash` for the current MCP
  proxy session.
- The first replayed call for a request hash uses `sequence_index = 0`.
- Repeated identical replay calls advance the sequence index.
- Replay counters must not be global across separate proxy process starts.
- Missing `sequence_index` must never fall back to the nearest available
  observation.

Bundle verification rules:

- Replay mode must call `verifyReplayBundle` before loading records.
- If verification fails, the proxy must refuse to serve tools.
- Replay mode reads bundled `tool-io/*.json` files, not source
  `.datalox/tool-io/records`.
- Any missing, extra, or mutated bundled file blocks replay.
- Duplicate `request_hash + sequence_index` keys block replay.

Process and transport rules:

- Record mode owns the upstream MCP child process lifecycle.
- Replay mode must not spawn the upstream command from config or bundle
  metadata.
- If upstream exits unexpectedly in record mode, subsequent tool calls return a
  structured upstream transport error.
- The proxy must not write normal diagnostics to stdout because stdout is the
  MCP transport.
- Long-running upstream stderr should be captured or piped to stderr without
  corrupting MCP stdout.

Security and export rules:

- The proxy records exact agent-visible arguments and observations. Redaction is
  an export/approval concern, not a record-time mutation.
- Default export status is blocked unless explicitly configured otherwise.
- Approved replay bundles, not raw local records, are the portable export asset.
- Proxy config may include environment variables for the upstream process, but
  env values should not be copied into replay records unless explicitly needed
  as non-secret provenance.

Implementation order:

1. Tighten proxy config parsing.
   - add `cwd`, `env`, and optional record metadata
   - keep strict unknown-field rejection
   - add config tests
2. Harden replay mode bundle loading.
   - call `verifyReplayBundle`
   - load only verified bundled records
   - fail before MCP serve when bundle is invalid
3. Preserve tool catalog fidelity.
   - decide whether low-level MCP handlers are needed
   - preserve raw upstream tool schemas in record mode
   - add `mcp_tool_catalog.v1` only if replay mode needs exact schema replay
4. Split error classes.
   - upstream call error
   - upstream transport error
   - Datalox record-write error
   - replay bundle verification error
   - replay miss
5. Strengthen record mode.
   - prove exact result returned to agent equals exact recorded content
   - fail closed if record write fails
   - preserve `isError: true` upstream results as observations
6. Strengthen replay mode.
   - prove upstream is not started
   - prove recorded results are byte-equivalent
   - prove repeated identical calls replay sequence indexes in order
   - prove missing calls return structured replay miss
7. Document install usage.
   - show how to point an MCP client at `datalox proxy --mode record`
   - show how to pack and verify a bundle
   - show how to point an MCP client at `datalox proxy --mode replay`
   - explain that replay mode has no live fallback
8. Add regression gates.
   - proxy tests
   - canonical docs tests
   - adoption docs checks
   - stale trajectory-surface scan

Record mode:

- forwards tool calls to upstream MCP
- records request hash, sequence index, arguments, and exact observation
- records upstream exceptions as structured tool observations
- returns upstream observation to the agent unchanged after successful record
- fails closed on Datalox record-write failure

Replay mode:

- does not start upstream MCP
- verifies the replay bundle before serving requests
- loads records only from the verified bundle
- looks up `request_hash + sequence_index`
- returns recorded observation unchanged
- fails deterministically when no record exists

Pass criteria:

Record mode:

- fake upstream MCP is started exactly once during record proxy startup
- `tools/list` exposes the upstream tool name, description, and input schema
- a successful upstream tool call returns the exact upstream `CallToolResult` to
  the agent
- the same call creates exactly one `tool_io_record.v1`
- the record contains exact `tool_name`, exact `arguments`, deterministic
  `request_hash`, correct `sequence_index`, exact observation content, source
  metadata, and export metadata
- two identical tool calls create sequence indexes `0` and `1`
- an upstream `isError: true` tool result is recorded and returned as the exact
  upstream observation, not converted into a Datalox infrastructure error
- an upstream thrown exception is recorded with
  `observation.status = "error"` and `error_code = "upstream_tool_error"`
- a forced Datalox record-write failure returns a proxy infrastructure error
  and does not masquerade as an upstream tool error

Replay mode:

- replay mode verifies the bundle before exposing tools
- replay mode fails startup when manifest or checksums are invalid
- replay mode does not start, connect to, or inspect the upstream MCP command
- `tools/list` in replay mode is derived from verified replay artifacts
- replay returns byte-equivalent observations for successful recorded calls
- replay returns byte-equivalent upstream error observations for recorded error
  calls
- repeated identical replay calls consume sequence indexes in order
- missing replay records return a structured `replay_miss` error containing
  `request_hash` and `sequence_index`
- replay never falls back to live upstream tools
- replay does not read source `.datalox/tool-io/records` after a bundle is
  packed

Config and CLI:

- invalid `schema_version` fails strict validation
- unknown config fields fail strict validation
- relative `upstream.cwd` resolves deterministically from the config file
  directory
- upstream env values are passed to upstream in record mode
- `datalox proxy --mode record` requires config
- `datalox proxy --mode replay` requires bundle
- startup diagnostics do not corrupt MCP stdout framing

Docs and adoption:

- README and replay quickstart show record proxy, bundle pack/verify, and replay
  proxy commands
- docs say replay mode has no live fallback
- docs do not present trajectory rows as proxy output
- fresh adoption keeps proxy guidance replay-first

Regression commands:

```bash
npm test
npx vitest run tests/mcpReplayProxy.test.ts
npx vitest run tests/replayBundle.test.ts tests/toolIoStore.test.ts
npx vitest run tests/replayCanonicalDocs.test.ts tests/adoptionScripts.test.ts
npm run check
git diff --check
```

## Step 6: Move Or Delete Trajectory Code

Goal:

- remove trajectory-first behavior from the replay core

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
- trajectory event roots as first-class replay stores
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

## Step 8: Canonicalize Action/Observation Records

Goal:

- turn messy agent/tool traces into stable, validated action/observation
  records before packaging them into replay bundles

Why this step exists:

- customer discovery says the accessible standardization gap is action schema
  standardization
- environment replay and reward engines can stay as references/provenance for
  now
- Datalox should prove it can normalize traces from different agent hosts into
  one replayable action/observation unit

Replay rule:

```text
raw trace -> adapter -> action_observation.v1 view over tool_io_record.v1 -> replay_bundle.v1 -> optional derivative
```

Do not add reward-engine, sandbox-runtime, or environment-factory logic in this
step. Keep those as future references on replay bundles after the core
action/observation unit is stable.

Update:

- `docs/tool-io-store-schema.md`
- `docs/project-definition.md`
- `README.md`
- `DATALOX.md`
- `.datalox/manifest.json` if canonical schema docs are listed there

Add:

- `docs/action-observation-schema.md`
- `src/core/actionObservationSchema.ts`
- `src/core/actionObservationNormalize.ts`
- `tests/actionObservationNormalize.test.ts`

Optional schema extension, only if implementation needs metadata beyond the
current `tool_io_record.v1` fields:

```ts
type ToolIoRecordV1 = {
  schema_version: "tool_io_record.v1";
  call_id: string;
  tool_name: string;
  tool_version?: string;
  arguments: unknown;
  argument_schema_ref?: string;
  request_hash: string;
  sequence_index: number;
  observation: {
    status: "ok" | "error";
    content?: unknown;
    error_code?: string;
    error_message?: string;
  };
  observation_schema_ref?: string;
  created_at: string;
};
```

Canonical action/observation view:

```ts
type ActionObservationV1 = {
  schema_version: "action_observation.v1";
  action: {
    type: "tool_call";
    name: string;
    version?: string;
    arguments: unknown;
    argument_schema_ref?: string;
    request_hash: string;
    sequence_index: number;
  };
  observation: {
    status: "ok" | "error";
    content?: unknown;
    error_code?: string;
    error_message?: string;
    observation_schema_ref?: string;
  };
  provenance: {
    source_kind: "mcp" | "wrapper" | "raw_trace";
    source_path?: string;
    host?: string;
    session_id?: string;
    turn_id?: string;
    call_id: string;
  };
};
```

Implementation details:

- keep `tool_io_record.v1` as the persisted replay primitive under
  `.datalox/tool-io/records/`
- implement `ActionObservationV1` as a strict normalized view over
  `tool_io_record.v1`, not a second replay store
- normalize tool names deterministically without aliases or fuzzy matching
- preserve exact `arguments` and `observation` values as agent-visible JSON
- derive `request_hash` only from canonical JSON of `{ tool_name, arguments }`
  unless the schema version is explicitly changed
- keep `sequence_index` ordering per identical request hash
- expose a normalization API that accepts:
  - an existing `ToolIoRecordV1`
  - a minimal raw trace event shaped like `{ tool, arguments, observation }`
  - wrapper-created tool I/O records
- reject ambiguous raw trace events with agent-readable validation errors
- do not infer missing observations from stdout prose
- do not infer tool versions or schema refs unless the source provides them
- keep reward/environment metadata out of this step except as explicit future
  fields documented as not implemented

Raw trace adapter input:

```ts
type RawActionObservationTraceInput = {
  source_kind: "raw_trace";
  source_path?: string;
  host?: string;
  session_id?: string;
  turn_id?: string;
  call_id: string;
  tool_name: string;
  tool_version?: string;
  arguments: unknown;
  argument_schema_ref?: string;
  observation: {
    status: "ok" | "error";
    content?: unknown;
    error_code?: string;
    error_message?: string;
  };
  observation_schema_ref?: string;
  sequence_index?: number;
};
```

Pass criteria:

- `ActionObservationV1` parser is strict and rejects unknown top-level fields
- normalizing a `ToolIoRecordV1` produces a stable
  `action_observation.v1` view with the same request hash and sequence index
- normalizing a raw trace event with the same tool name and arguments produces
  the same request hash as `recordToolIo`
- key order differences in raw arguments do not change the request hash
- repeated identical actions retain replay order through sequence index
- invalid raw traces fail deterministically with a clear error path
- no alias matching, fuzzy tool-name matching, or stdout/prose inference exists
- docs and TypeScript schemas agree on every implemented field
- `npm test`
- `npm run check`
- `git diff --check`

## Step 9: Export Derivatives From Replay Bundles

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

## Step 10: Regression Gates

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
- docs/code schema drift for action/observation fields
- prose-derived replay or derivative artifacts

Pass criteria:

- fresh adoption creates replay-focused replay surfaces only
- fresh adoption does not create legacy stores
- install-facing MCP is replay-first
- action/observation normalization remains strict and deterministic
- full test suite and stale-reference scan pass

## Final Done Definition

This migration is done only when:

- the repo name, install docs, package identity, and remote repo are
  `datalox-agent-replay`
- the primary MCP surface records and replays tool I/O
- messy host/tool traces can be normalized into strict action/observation
  records
- replay bundles are deterministic and verifiable
- wrapper default capture mode is replay
- trajectory rows are derivative-only or removed
- fresh adoption produces no legacy replay paths
- tests enforce all of the above
