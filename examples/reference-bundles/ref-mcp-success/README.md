# ref-mcp-success

This reference bundle records one successful MCP tool call through the Datalox
MCP VCR proxy.

Bundle path:

```text
.datalox/replay-bundles/ref-mcp-success/
```

Recorded call:

```json
{
  "tool": "policy_lookup",
  "arguments": {
    "query": "Beijing taxi reimbursement limit",
    "top_k": 2
  }
}
```

Expected behavior:

- record mode calls the deterministic upstream fixture once
- the bundle contains one `tool_io_record.v1`
- the bundle contains one `mcp_tool_catalog.v1`
- replay mode serves `tools/list` from the bundled catalog
- replay mode returns the recorded observation without starting upstream

Verify:

```bash
npm run build
node dist/src/cli/main.js bundle verify --repo . --bundle .datalox/replay-bundles/ref-mcp-success --json
```
