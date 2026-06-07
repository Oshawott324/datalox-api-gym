# Verified Replay Quickstart

This is the first product proof path for Datalox API Gym.

Primary replay loop:

```text
agent tool call -> tool_io_record.v1 -> replay_bundle.v1 -> deterministic replay -> optional derivatives
```

Run from the repo root:

```bash
npm run demo:verified-replay
```

The demo uses:

- `examples/verified-replay-quickstart/fixture-upstream.mjs`
- `examples/verified-replay-quickstart/datalox.record.json`
- `examples/verified-replay-quickstart/run-demo.mjs`

It performs the full local VCR loop:

1. Build the TypeScript project.
2. Start a deterministic MCP upstream fixture through Datalox record mode.
3. Record three real MCP tool calls.
4. Pack `verified-replay-demo` as a `replay_bundle.v1`.
5. Verify the bundle checksums.
6. Remove live source stores from the demo workspace.
7. Replay the same tool calls from the bundle with upstream off.
8. Call an unseen request and return a structured `replay_miss`.
9. Tamper with a copied bundle and prove verification fails.

The demo writes ignored local output under:

```text
examples/verified-replay-quickstart/output/
```

The final summary includes:

- `bundle_id`
- `tool_record_count`
- `mcp_tool_catalog_count`
- `replay_hit_count`
- `replay_miss_count`
- `upstream_calls_during_replay`
- `tamper_detected`
- `elapsed_ms`

Pass criteria:

- demo succeeds on a clean checkout with no secrets and no network dependency
- replay works while upstream is off
- replay miss is deterministic and agent-readable
- tamper failure is visible and deterministic
- output includes bundle id, tool record count, catalog count, hit count, miss
  count, and elapsed time

This quickstart proves the local engine wedge only. It does not build a sandbox,
construct a stateful world, or compute reward.
