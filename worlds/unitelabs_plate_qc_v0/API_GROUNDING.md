# Unitelabs API Grounding

`unitelabs_plate_qc_v0` is still a dry-run world. The next product step is to
ground its MCP tool semantics against a real UniteLabs tenant OpenAPI contract
without triggering workflows, devices, or live hardware actions.

Use one explicit contract source:

```bash
api-gym unitelabs sample-api-contract \
  --openapi-file /path/to/unitelabs-openapi.json \
  --out worlds/unitelabs_plate_qc_v0/evidence/unitelabs_api_contract_sample.json
```

For a tenant-hosted OpenAPI JSON URL:

```bash
UNITELABS_OPENAPI_TOKEN=... \
api-gym unitelabs sample-api-contract \
  --openapi-url <exact-openapi-json-url-from-unitelabs-swagger-ui> \
  --bearer-token-env UNITELABS_OPENAPI_TOKEN \
  --out worlds/unitelabs_plate_qc_v0/evidence/unitelabs_api_contract_sample.json
```

The command only reads the supplied OpenAPI document. It does not create a
workflow run, poll a run, send lab commands, or call a live device endpoint.

The output is a normalized contract sample:

- all OpenAPI operations with method, path, operation id, tags, parameters, and schema refs
- workflow, run, log, and artifact operation groups
- a dry-run tool mapping section marked `requires_human_mapping`
- `live_execution.allowed=false`

Use the sample to update the world only after reviewing the real contract:

1. Compare dry-run MCP tools against real UniteLabs operation names, request
   bodies, response bodies, and error surfaces.
2. Change `tools.py`, `services.py`, and `spec.json` only where the real
   contract proves the semantics.
3. Keep `live_execution.allowed=false` for V0.
4. Add real read-only run/log/artifact samples only when credentials and tenant
   permissions are available.

References:

- https://docs.unitelabs.io/technical-reference/rest-api/
- https://docs.unitelabs.io/automate/guides/deploy-a-workflow/
- https://docs.unitelabs.io/automate/guides/run-a-workflow/
- https://docs.unitelabs.io/automate/concepts/logs/
