# Reference Replay Bundles

These examples are public proof artifacts for Datalox Agent Replay.

They demonstrate the current core loop:

```text
agent tool call -> tool_io_record.v1 -> replay_bundle.v1 -> deterministic replay -> optional derivatives
```

## Bundles

- [ref-mcp-success](./ref-mcp-success/README.md)
- [ref-mcp-repeated-call](./ref-mcp-repeated-call/README.md)
- [ref-mcp-error-observation](./ref-mcp-error-observation/README.md)

Each bundle is stored under:

```text
.datalox/replay-bundles/<bundle-id>/
```

Each bundle was generated through the MCP VCR proxy against the deterministic
fixture in [fixtures/reference-upstream.mjs](./fixtures/reference-upstream.mjs).

## Regenerate

From the repo root:

```bash
node examples/reference-bundles/generate-reference-bundles.mjs --build
```

The generator:

1. starts the MCP proxy in record mode
2. calls the deterministic upstream fixture
3. packs a `replay_bundle.v1`
4. verifies checksums
5. removes live source tool stores
6. starts the MCP proxy in replay mode with upstream disabled
7. confirms replayed observations match the recorded observations

Generated bundles use `source.repo_path: "."` so the public manifests do not
contain machine-local absolute paths.

## Verify

```bash
npm run build
node dist/src/cli/main.js bundle verify --repo . --bundle .datalox/replay-bundles/ref-mcp-success --json
node dist/src/cli/main.js bundle verify --repo . --bundle .datalox/replay-bundles/ref-mcp-repeated-call --json
node dist/src/cli/main.js bundle verify --repo . --bundle .datalox/replay-bundles/ref-mcp-error-observation --json
```

Replay mode must not start the upstream fixture or call live tools. It only
serves bundled observations by `request_hash + sequence_index`.
