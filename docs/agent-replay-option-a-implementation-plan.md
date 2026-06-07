# API Gym Option A Implementation Plan

This is the concrete implementation plan for turning this repo into Option A:
an MCP-compatible VCR for agent tools.

## Project Boundary

Datalox API Gym is not a trajectory-first tool.

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

## Implementation Status

Status date: 2026-05-20.

Option A is implemented and regression-gated in this repo.

| Step | Status | Evidence |
| --- | --- | --- |
| Step 0: Freeze rename baseline | Done | Repo/package/install-facing surfaces use `datalox-api-gym`; `tests/repoIdentity.test.ts` guards identity and legacy paths. |
| Step 1: Replay canonical schema layer | Done | First-read docs use `agent tool call -> tool_io_record.v1 -> replay_bundle.v1 -> deterministic replay -> optional derivatives`; `tests/replayCanonicalDocs.test.ts` guards drift. |
| Step 2: Content-addressed tool I/O store | Done | `src/core/toolIoStore.ts`, `src/core/toolIoSchema.ts`, and `tests/toolIoStore.test.ts` cover request hash and sequence index replay keys. |
| Step 3: Replay bundles | Done | `src/core/replayBundle.ts` and `tests/replayBundle.test.ts` cover pack, verify, checksums, MCP catalogs, and sealed-bundle verification. |
| Step 4: Install-facing MCP surface | Done | `src/mcp/replayServer.ts` exposes replay tools only; `tests/replayMcp.test.ts` guards the install-facing surface. |
| Step 5: MCP VCR proxy | Done | `src/mcp/replayProxyServer.ts` records upstream MCP calls and replays verified bundles without upstream fallback; `tests/mcpReplayProxy.test.ts` covers success, repeated calls, errors, replay misses, and catalog tampering. |
| Step 6: Trajectory boundary cleanup | Done | Trajectory schemas/code live under derivative boundaries; `tests/repoIdentity.test.ts` guards install-facing surfaces. |
| Step 7: Wrapper replay defaults | Done | Wrappers accept `off` or `replay`; trajectory is not a post-run mode; `tests/wrapperSurfaces.test.ts` guards defaults and failure modes. |
| Step 8: Action/observation canonicalization | Done | `action_observation.v1` is a strict normalized view over replay evidence; `tests/actionObservationNormalize.test.ts` and canonical-doc tests guard strict fields. |
| Step 9: Export derivatives from replay bundles | Done | `src/core/derivatives/trajectory/fromReplayBundle.ts` derives compact candidates only after bundle verification; `tests/derivatives/trajectory/fromReplayBundle.test.ts` covers verified, tampered, and weak candidates. |
| Step 10: Regression gates | Done | Full suite, stale-reference scans, adoption smoke tests, wrapper tests, proxy tests, reference-bundle tests, `npm run check`, and `git diff --check` are the close-out gates. |

Current proof artifacts:

- `.datalox/replay-bundles/ref-mcp-success`
- `.datalox/replay-bundles/ref-mcp-repeated-call`
- `.datalox/replay-bundles/ref-mcp-error-observation`

These reference bundles were generated through the MCP VCR proxy and verify as
sealed `replay_bundle.v1` artifacts. They are not required for the Option A
migration to work, but they make the format concrete for demos and design
partner conversations.

Out of scope for Option A:

- hosted replay infrastructure
- sandbox/runtime orchestration
- task environment construction
- behavioral mock construction
- reward functions or judge agents
- broad external runtime adapters beyond the current MCP proxy and wrapper
  paths

## Step 0: Freeze The Rename Baseline

Goal:

- finish the `datalox-api-gym` identity cut before changing project logic

Change:

- keep package name as `datalox-api-gym`
- keep cache path as `.datalox/cache/datalox-api-gym`
- keep install docs pointed at the new repo URL
- keep active docs and instruction files free of old project names and legacy
  store names

Pass criteria:

- `npm test`
- `npm run check`
- `git diff --check`
- stale identity scan passes through `tests/repoIdentity.test.ts`
- GitHub repo exists at `Oshawott324/datalox-api-gym`

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
- fresh adoption keeps proxy guidance API-world-first

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

## Step 7: Make Wrapper Replay Defaults Boring And Enforced

Goal:

- make every supported wrapper path API-world-first by default
- make wrapper enforcement visible to the child agent through stable environment
  sentinels
- make post-run behavior deterministic enough that an agent can reason about it
  without human interpretation
- prevent wrapper runs from silently producing trajectory rows, wiki events, or
  synthesized replay evidence

Why this step matters:

- MCP VCR proxy is the cleanest enforced capture boundary when an agent uses MCP
  tools directly.
- Wrappers are the broader host boundary. They catch Codex, Claude, and generic
  CLI runs where the model can still call local MCP tools or code paths that
  create `tool_io_record.v1` records.
- The wrapper must not pretend that stdout, summaries, final answers, or prose
  are replay records. Its job is to enforce guidance and attach turn context to
  explicit tool I/O evidence that already exists.

Current state:

- `WrapperPostRunMode` is already narrowed to `off | replay`.
- `finalizeWrappedRun` already defaults missing `postRunMode` to `replay`.
- `bin/datalox-codex.js`, `bin/datalox-claude.js`, and generated host shims set
  `DATALOX_DEFAULT_POST_RUN_MODE` to `replay` when unset.
- `tests/wrapperSurfaces.test.ts` already covers replay-only prompt injection,
  empty replay capture, and `agent_turn.v1` creation when explicit
  `tool_io_record.v1` records appear.
- This step is complete only when the default is documented, enforced by the
  adopted shims, rejected when invalid, and protected against regression by
  wrapper and adoption tests.

Non-goals:

- do not build a transcript parser
- do not infer tool calls from stdout, stderr, shell logs, final answers, or
  assistant summaries
- do not make trajectory rows from wrapper output
- do not run reward, grading, or trajectory export as part of wrapper post-run
- do not hide missing replay evidence behind a generated placeholder record
- do not make wrapper behavior depend on an LLM review decision

Definition of boring:

```text
pre-run:  inject replay guidance and stable environment sentinels
child:    run the real agent host command
post-run: compare tool_io_record.v1 ids before/after the child run
if new records exist: create one agent_turn.v1 that references them
if no records exist: create nothing and report replay_capture_empty
```

The wrapper should have no clever classifier. It should not inspect child output
to decide whether replay evidence exists. The only accepted replay evidence is
a valid `tool_io_record.v1` already written under:

```text
.datalox/tool-io/records/
```

Definition of enforced:

```text
the host command path routes through Datalox wrapper code
AND the child process receives DATALOX_ENFORCEMENT=wrapper
AND the child process receives DATALOX_SESSION_ID
AND wrapper post-run mode resolves to replay unless explicitly disabled
```

Guidance-only surfaces such as native instructions, MCP availability, or chat
memory do not count as enforced wrapper runs. They can help the model choose the
right behavior, but they cannot prove the child process went through Datalox.

Default contract:

```bash
DATALOX_DEFAULT_POST_RUN_MODE=replay
```

Allowed post-run modes:

```text
replay
off
```

Rules:

- missing `--post-run-mode` means `replay`
- missing `DATALOX_DEFAULT_POST_RUN_MODE` means `replay`
- `--post-run-mode replay` records only replay turn context
- `--post-run-mode off` disables post-run recording for that run
- `DATALOX_DEFAULT_POST_RUN_MODE=off` disables post-run recording until changed
- any other explicit CLI value must fail with an agent-readable error
- any other environment value must fail with an agent-readable error before the
  child command runs
- there is no `trajectory` post-run mode

Wrapper entrypoints:

```text
bin/datalox-codex.js
bin/datalox-claude.js
bin/datalox-wrap.js
src/cli/main.ts datalox codex
src/cli/main.ts datalox claude
src/cli/main.ts datalox wrap command
src/cli/main.ts datalox wrap prompt
generated Codex shim from src/core/installCore.ts
generated Claude shim from src/core/installCore.ts
```

Host-specific enforcement:

- Codex shim wraps `codex exec`, `codex e`, and `codex review`.
- Claude shim wraps prompt-bearing Claude runs and avoids wrapping management
  commands such as config, MCP setup, update, help, and version.
- Generic wrapper is enforced only when the caller explicitly invokes
  `datalox wrap command` and passes a concrete child command after `--`.
- `datalox wrap prompt` is guidance rendering only. It does not run a child
  command and must not create replay events.

Environment contract for wrapped child processes:

```text
DATALOX_REPO_PATH=<absolute target repo path>
DATALOX_SESSION_ID=<stable wrapper session id>
DATALOX_ORIGINAL_PROMPT=<user prompt before Datalox guidance>
DATALOX_PROMPT=<wrapped prompt with replay guidance>
DATALOX_GUIDANCE_JSON=<machine-readable guidance envelope>
DATALOX_SELECTION_BASIS=replay_capture | bootstrap_unavailable
DATALOX_WORKFLOW=<optional workflow>
DATALOX_MATCHED_SKILL=<optional skill id>
DATALOX_ACTIVE_WRAPPER=codex | claude | generic
DATALOX_HOST_KIND=codex | claude | generic
DATALOX_ENFORCEMENT=wrapper
DATALOX_DEFAULT_POST_RUN_MODE=replay | off
DATALOX_DEFAULT_REVIEW_MODEL=<cheap default model for future review hooks>
```

Rules:

- `DATALOX_SESSION_ID` is the join key between records created during the child
  run and the wrapper-created `agent_turn.v1`.
- Child agents and tools should pass `DATALOX_SESSION_ID` into
  `record_tool_io` or `recordToolIo`.
- Wrapper post-run must only attach records that were created after the
  pre-run snapshot.
- Existing records in `.datalox/tool-io/records/` must not be attached to a new
  turn just because they are present.
- Wrapper-owned environment variables are process-local. They must not be
  written into replay records except as explicit source metadata such as
  `source.host`.

Wrapped prompt contract:

The wrapped prompt should tell the child agent:

- record exact replay evidence first
- use `record_tool_io`, `record_agent_turn`, and `pack_replay_bundle` when MCP
  tools are available
- use `DATALOX_SESSION_ID` as `session_id`
- do not synthesize replay data from prose summaries
- leave post-run recording empty when no agent-visible tool I/O was captured

The prompt should not mention trajectory rows as the normal capture path.

Post-run algorithm:

1. Build the loop envelope.
   - resolve `repoPath`
   - auto-bootstrap only when safe
   - generate or reuse `sessionId`
   - render API-world-first wrapped prompt
2. Snapshot replay evidence before the child command.
   - call `readToolIoRecords(repoPath)`
   - store only record ids in memory
3. Run the child command.
   - replace explicit placeholders such as `__DATALOX_PROMPT__`
   - pass the wrapper environment contract
   - preserve the child exit code, stdout, and stderr
4. Resolve post-run mode.
   - CLI flag wins over environment
   - default is `replay`
   - invalid values fail closed before any child process runs
5. If mode is `off`, create no events and report `disabled`.
6. If the repo is not active, create no events and report `disabled`.
7. If no child process ran, create no events and report `disabled`.
8. Read replay evidence after the child command.
   - call `readToolIoRecords(repoPath)` again
   - compute `newToolRecords = after - before` by record id
9. If `newToolRecords` is empty:
   - create no `agent_turn.v1`
   - create no trajectory derivative
   - report `replay_capture_empty`
   - include the reason:

```text
No explicit tool_io_record.v1 records were created during this wrapped run;
Datalox did not synthesize replay evidence from prose.
```

10. If `newToolRecords` is non-empty:
    - create exactly one `agent_turn.v1`
    - include the original prompt when available
    - include one `tool_calls[]` entry per new tool record
    - include `tool_io_ref.record_id`
    - include `tool_io_ref.request_hash`
    - include `tool_io_ref.sequence_index`
    - include child command verification status from the child exit code
    - set export to blocked by default
    - report `replay_evidence_recorded`

`agent_turn.v1` mapping:

```text
wrapper session id              -> agent_turn.session_id
original prompt                 -> agent_turn.user_prompt
child host kind                 -> assistant_summary
new tool_io_record.v1.tool_name -> tool_calls[].tool
new tool_io_record.v1.call_id   -> tool_calls[].call_id
record id/hash/index            -> tool_calls[].tool_io_ref
child command + args            -> verification.command
child exit code 0               -> verification.status="passed"
child exit code nonzero         -> verification.status="failed"
default export                  -> export.allowed=false, redaction="blocked"
```

Implementation order:

1. Tighten post-run mode parsing.
   - keep `WrapperPostRunMode = "off" | "replay"`
   - make invalid `--post-run-mode` fail before the child command runs
   - make invalid `DATALOX_DEFAULT_POST_RUN_MODE` fail before the child command
     runs
   - remove any stale mode strings from code, docs, tests, and help output
2. Normalize wrapper entrypoint defaults.
   - set `DATALOX_DEFAULT_POST_RUN_MODE` to `replay` in `bin/datalox-codex.js`
   - set `DATALOX_DEFAULT_POST_RUN_MODE` to `replay` in `bin/datalox-claude.js`
   - make generated Codex and Claude shims export the same default
   - make generic `datalox wrap command` resolve the same default even when no
     shim is involved
3. Make enforcement visible.
   - set `DATALOX_ACTIVE_WRAPPER`
   - set `DATALOX_HOST_KIND`
   - set `DATALOX_ENFORCEMENT=wrapper`
   - expose wrapper enforcement in `datalox status --json`
   - keep native sessions without wrapper sentinels marked as `guidance_only`
4. Keep the child-agent contract explicit.
   - include `DATALOX_SESSION_ID` in the wrapped prompt
   - include replay MCP tools in the wrapped prompt
   - keep the prompt short enough that it does not become the task
   - do not instruct the child to write trajectory rows
5. Make post-run evidence attachment deterministic.
   - snapshot record ids before the child command
   - attach only new records by id
   - create one turn event for all new records
   - create nothing when no records were added
   - never parse child stdout/stderr for replay evidence
6. Keep output channels predictable.
   - child stdout stays on stdout
   - child stderr stays on stderr
   - wrapper post-run summary goes to stderr for command wrappers
   - `--json` returns structured wrapper result and preserves child exit code
7. Keep install/adoption API-world-first.
   - generated host shims route supported host runs through wrappers
   - adopted instruction surfaces describe wrapper replay capture
   - no adopted first-read file tells agents to create trajectory rows as the
     default capture step
8. Add regression gates.
   - wrapper behavior tests
   - adoption script tests
   - canonical docs tests
   - stale mode scan for removed post-run modes

Required code changes:

- `src/cli/main.ts`
  - strict `parsePostRunMode`
  - CLI help lists only `<off|replay>`
  - invalid explicit mode errors before child execution
- `src/adapters/shared.ts`
  - keep replay as `finalizeWrappedRun` default
  - keep before/after `tool_io_record.v1` snapshot logic
  - keep `replay_capture_empty` as the no-evidence result
  - keep `agent_turn.v1` creation grounded only in new tool records
- `bin/datalox-codex.js`
  - default `DATALOX_DEFAULT_POST_RUN_MODE` to `replay`
  - set wrapper sentinels for direct wrapper entrypoint runs
- `bin/datalox-claude.js`
  - default `DATALOX_DEFAULT_POST_RUN_MODE` to `replay`
  - set wrapper sentinels for direct wrapper entrypoint runs
- `bin/datalox-wrap.js`
  - keep generic wrapper thin and route behavior through `src/cli/main.ts`
- `src/core/installCore.ts`
  - generated Codex shim sets wrapper sentinels and replay default
  - generated Claude shim sets wrapper sentinels and replay default
  - status reports wrapper-enforced only when sentinels prove wrapper execution
- `tests/wrapperSurfaces.test.ts`
  - prove prompt, default, empty capture, explicit evidence, invalid mode, and
    no derivative writes
- `tests/adoptionScripts.test.ts`
  - prove adopted shims and docs use replay defaults
- `tests/replayCanonicalDocs.test.ts`
  - prove first-read docs stay API-world-first

Pass criteria:

Default and mode parsing:

- `datalox wrap command` with no `--post-run-mode` resolves to `replay`
- `datalox codex` with no `--post-run-mode` resolves to `replay`
- `datalox claude` with no `--post-run-mode` resolves to `replay`
- `DATALOX_DEFAULT_POST_RUN_MODE=replay` resolves to `replay`
- `DATALOX_DEFAULT_POST_RUN_MODE=off` resolves to `off`
- `--post-run-mode off` disables post-run recording for that run
- `--post-run-mode replay` records replay turn context when evidence exists
- invalid `--post-run-mode` fails before the child command runs
- invalid `DATALOX_DEFAULT_POST_RUN_MODE` fails before the child command runs
- no code path accepts or emits a trajectory post-run mode

Prompt and enforcement:

- wrapped prompt contains `# Datalox API Gym`
- wrapped prompt contains `record_tool_io`
- wrapped prompt contains `DATALOX_SESSION_ID`
- wrapped prompt says not to synthesize replay data from prose summaries
- wrapped prompt does not tell the child to write trajectory rows
- child process receives `DATALOX_ACTIVE_WRAPPER`
- child process receives `DATALOX_HOST_KIND`
- child process receives `DATALOX_ENFORCEMENT=wrapper`
- child process receives `DATALOX_REPO_PATH`
- child process receives `DATALOX_SESSION_ID`
- `datalox status --json` reports wrapper-enforced only when wrapper sentinels
  are present

No-evidence behavior:

- a wrapped child command that writes no `tool_io_record.v1` exits with the
  child exit code
- post-run result is `mode="replay"` and `trigger="replay_capture_empty"`
- no `agent_turn.v1` event is created
- no trajectory derivative directory is created
- no legacy event directory is created
- summary is agent-readable and says no explicit tool I/O records were created
- stdout/stderr prose from the child is not converted into replay data

Evidence behavior:

- when the child creates one new `tool_io_record.v1`, wrapper creates one
  `agent_turn.v1`
- the turn references the exact record id, request hash, and sequence index
- the turn uses the wrapper `DATALOX_SESSION_ID`
- the turn includes the original prompt when available
- the turn verification status follows the child exit code
- existing pre-run tool records are not attached to the new turn
- two new tool records in one child run create one turn with two tool-call refs
- default export state is blocked

Shim and adoption behavior:

- generated Codex shim routes supported Codex commands through
  `bin/datalox-codex.js`
- generated Claude shim routes prompt-bearing Claude runs through
  `bin/datalox-claude.js`
- generated shims export `DATALOX_DEFAULT_POST_RUN_MODE=replay` when unset
- management commands that should not be wrapped still call the real host binary
- adopted docs describe wrapper capture as replay capture
- adopted docs do not present trajectory rows as wrapper output

Output and exit behavior:

- child stdout is preserved
- child stderr is preserved
- wrapper post-run summary is written to stderr in non-json command mode
- `--json` output includes the post-run result
- wrapper process exits with the child exit code
- disabled post-run mode returns `trigger="disabled"`
- inactive repo returns `trigger="disabled"` without writing events

Regression commands:

```bash
npm run check
npx vitest run tests/wrapperSurfaces.test.ts
npx vitest run tests/adoptionScripts.test.ts
npx vitest run tests/replayCanonicalDocs.test.ts
git diff --check
```

Full gate when unrelated repo identity drift is clean:

```bash
npm test
```

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

Status: done as of 2026-05-20.

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

Verification:

- `tests/derivatives/trajectory/fromReplayBundle.test.ts`
- `tests/derivatives/trajectory/agentTaskTrajectoryExport.test.ts`
- `tests/derivatives/trajectory/trajectoryExport.test.ts`

## Step 10: Regression Gates

Status: done as of 2026-05-20.

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
- install-facing MCP is API-world-first
- action/observation normalization remains strict and deterministic
- full test suite and stale-reference scan pass

Verification:

- `tests/repoIdentity.test.ts`
- `tests/adoptionScripts.test.ts`
- `tests/replayMcp.test.ts`
- `tests/mcpReplayProxy.test.ts`
- `tests/wrapperSurfaces.test.ts`
- `tests/replayCanonicalDocs.test.ts`
- `tests/referenceBundles.test.ts`
- `npm test`
- `npm run check`
- `git diff --check`

## Final Done Definition

Status: complete as of 2026-05-20.

This migration is done only when:

- the repo name, install docs, package identity, and remote repo are
  `datalox-api-gym`
- the primary MCP surface records and replays tool I/O
- messy host/tool traces can be normalized into strict action/observation
  records
- replay bundles are deterministic and verifiable
- wrapper default capture mode is replay
- trajectory rows are derivative-only or removed
- fresh adoption produces no legacy replay paths
- tests enforce all of the above
