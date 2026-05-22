# ref-mcp-error-observation

This reference bundle records an agent-visible MCP error observation through the
Datalox MCP VCR proxy.

Bundle path:

```text
.datalox/replay-bundles/ref-mcp-error-observation/
```

Recorded call:

```json
{
  "tool": "validation_error",
  "arguments": {
    "reason": "visible upstream validation"
  }
}
```

Expected behavior:

- the upstream fixture returns an MCP `isError` tool result
- Datalox records the returned MCP result as the exact agent-visible observation
- replay mode returns the same `isError` result from the bundle
- replay mode does not call the upstream fixture

Verify:

```bash
npm run build
node dist/src/cli/main.js bundle verify --repo . --bundle .datalox/replay-bundles/ref-mcp-error-observation --json
```
