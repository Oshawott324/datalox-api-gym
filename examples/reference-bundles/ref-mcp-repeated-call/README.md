# ref-mcp-repeated-call

This reference bundle records two identical MCP tool calls through the Datalox
MCP VCR proxy.

Bundle path:

```text
.datalox/replay-bundles/ref-mcp-repeated-call/
```

Recorded call, repeated twice:

```json
{
  "tool": "policy_lookup",
  "arguments": {
    "query": "identical policy lookup",
    "top_k": 2
  }
}
```

Expected behavior:

- both records have the same `request_hash`
- the first record has `sequence_index: 0`
- the second record has `sequence_index: 1`
- replay mode returns the first observation for the first call and the second
  observation for the second call
- replay mode does not use fuzzy matching or timestamps

Verify:

```bash
npm run build
node dist/src/cli/main.js bundle verify --repo . --bundle .datalox/replay-bundles/ref-mcp-repeated-call --json
```
