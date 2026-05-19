# Replay Quickstart

This is the smallest useful Datalox Agent Replay loop.

```text
record_tool_io -> replay_tool_io -> pack_replay_bundle -> verify_replay_bundle
```

At the product layer this is:

```text
agent tool call -> tool_io_record.v1 -> replay_bundle.v1 -> deterministic replay -> optional derivatives
```

The example uses MCP tools because exact tool I/O recording belongs at the
agent/tool boundary, not in a prose summary.

## 1. Record One Tool Call

Call `record_tool_io` with the exact tool request and the exact observation the
agent saw:

```json
{
  "repo_path": "/path/to/repo",
  "session_id": "demo-session",
  "turn_id": "turn-1",
  "call_id": "call-1",
  "tool_name": "search_policy",
  "arguments": {
    "query": "Beijing business-trip taxi reimbursement limit",
    "top_k": 5
  },
  "observation": {
    "status": "ok",
    "content": ["doc1 ...", "doc2 ..."]
  },
  "export": {
    "allowed": true,
    "redaction": "none_needed"
  }
}
```

This writes one `tool_io_record.v1` file under:

```text
.datalox/tool-io/records/
```

The record includes a deterministic `request_hash` and `sequence_index`.

## 2. Replay The Observation

Call `replay_tool_io` with the same tool name, same arguments, and the intended
sequence index:

```json
{
  "repo_path": "/path/to/repo",
  "tool_name": "search_policy",
  "arguments": {
    "top_k": 5,
    "query": "Beijing business-trip taxi reimbursement limit"
  },
  "sequence_index": 0
}
```

Argument key order does not matter. Replay resolves by deterministic request
hash plus sequence index and returns the recorded observation. Replay mode must
fail clearly when no matching record exists.

## 3. Pack A Replay Bundle

Call `pack_replay_bundle`:

```json
{
  "repo_path": "/path/to/repo",
  "bundle_id": "demo-replay-bundle",
  "export": {
    "allowed": true,
    "redaction": "none_needed"
  }
}
```

This writes:

```text
.datalox/replay-bundles/demo-replay-bundle/
  manifest.json
  tool-io/
  checksums.json
```

## 4. Verify The Bundle

Call `verify_replay_bundle`:

```json
{
  "repo_path": "/path/to/repo",
  "bundle": ".datalox/replay-bundles/demo-replay-bundle"
}
```

The result must report `verified: true` before downstream systems use the
bundle as replay evidence.

## 5. Use The MCP VCR Proxy

When an agent already calls an upstream MCP server, point the agent at Datalox
instead of asking it to call `record_tool_io` manually.

Record mode:

```bash
datalox proxy --mode record --repo . --config datalox.replay.json --json
```

Example proxy config:

```json
{
  "schema_version": "datalox_replay_proxy_config.v1",
  "upstream": {
    "command": "node",
    "args": ["server.js"],
    "cwd": "."
  }
}
```

Record mode forwards `tools/list` and `tools/call` to the upstream MCP server.
It records exact `tool_io_record.v1` observations under
`.datalox/tool-io/records/` and snapshots the upstream tool catalog as
`mcp_tool_catalog.v1` under `.datalox/mcp-tool-catalogs/`.

After recording, pack and verify a bundle:

```bash
datalox bundle pack --repo . --bundle-id demo-replay-bundle --json
datalox bundle verify --repo . --bundle .datalox/replay-bundles/demo-replay-bundle --json
```

Replay mode:

```bash
datalox proxy --mode replay --repo . --bundle .datalox/replay-bundles/demo-replay-bundle --json
```

Replay mode verifies the bundle before serving requests. It answers
`tools/list` from bundled MCP catalog metadata and answers `tools/call` from
bundled tool I/O records. It must not start upstream or call live tools as a
fallback.

## Contract

- Do not create replay records from assistant summaries.
- Do not call live tools during replay as a hidden fallback.
- Keep optional trajectory rows downstream from verified replay evidence.
