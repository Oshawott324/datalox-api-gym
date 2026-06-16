# API Source Pack Schema

This document defines the minimal, agent-readable schema guidance for API
source packs. These shapes are intentionally small and filesystem-based. Add
fields only when they preserve source evidence or make downstream world design
clearer.

## `source_pack.json`

`source_pack.json` identifies one provider/version source pack and lists the
record files it contains.

```json
{
  "schema_version": "api_gym.api_source_pack.v0",
  "source_pack_id": "api.example.2026-06-12",
  "provider": "example",
  "version": "2026-06-12",
  "status": "raw",
  "source_types": ["openapi", "docs", "test_mode_probe"],
  "records": {
    "docs_index": "docs_index.jsonl",
    "operations": "operations.jsonl",
    "schemas": "schemas.jsonl",
    "examples": "examples.jsonl",
    "response_cases": "response_cases.jsonl",
    "probes": "probes.jsonl",
    "observed_errors": "observed_errors.jsonl",
    "world_candidates": "world_candidates.jsonl"
  },
  "live_execution": {
    "allowed": false,
    "reason": "Source substrate only; no live provider action is executed by API Gym."
  }
}
```

Recommended `status` values:

- `raw`: source files captured but not normalized
- `normalized`: operations and schemas are normalized enough for agent review
- `selected`: at least one world references this pack through
  `worlds/<world_id>/source_refs.json`

List only record files that exist and contain at least one row in the pack.
`api-gym source-pack validate` fails when `source_pack.json` lists a missing or
empty record file.

## `operations.jsonl`

One normalized operation per line.

```json
{"id":"operation:listWidgets","source_pack_id":"api.example.2026-06-12","operation_id":"listWidgets","method":"GET","path":"/widgets","summary":"List widgets","source_refs":[{"kind":"openapi","path":"raw/openapi.json","pointer":"/paths/~1widgets/get"}],"agent_notes":["Read-only operation candidate. No world action semantics proven yet."]}
```

Rules:

- `id` must be stable inside the source pack.
- `source_refs` must point to raw source material or recorded evidence.
- Do not infer side effects beyond the cited source.

## `schemas.jsonl`

One normalized schema or important field group per line.

```json
{"id":"schema:Widget","source_pack_id":"api.example.2026-06-12","name":"Widget","kind":"response_schema","source_refs":[{"kind":"openapi","path":"raw/openapi.json","pointer":"/components/schemas/Widget"}],"fields":[{"name":"id","type":"string","required":true},{"name":"status","type":"string","required":false}]}
```

Rules:

- Preserve provider names when they are explicit.
- Keep derived names visibly derived.
- Prefer structured fields over prose when the source supports it.

## `examples.jsonl`

Concrete request or response examples from source material.

```json
{"id":"example:listWidgets:success","operation_ref":"operation:listWidgets","kind":"response","status":200,"source_refs":[{"kind":"docs","url":"https://docs.example.invalid/widgets"}],"body":{"data":[{"id":"wid_123","status":"active"}]}}
```

Rules:

- Examples are evidence, not generated fixtures.
- Mark synthetic examples with `kind: "synthetic_world_candidate"` and keep
  them out of provider-grounding claims.

## `response_cases.jsonl`

Response cases are the source-pack surface for API-gated dry runs. An agent can
call an original-shaped provider API, while the Datalox gate chooses a
grounded response case instead of touching the live provider.

```json
{"id":"response_case:listWidgets:success","source_pack_id":"api.example.2026-06-12","operation_ref":"operation:listWidgets","case":"success","status":200,"response_mode":"body_shape","source_refs":[{"kind":"docs","url":"https://docs.example.invalid/widgets"}],"body_shape":{"object":"Widget"}}
```

Rules:

- Every operation listed in `operations.jsonl` must have at least one response
  case.
- `response_mode` must be one of `body`, `body_excerpt`, `body_shape`,
  `error_shape`, `headers`, or `no_body`.
- The payload field must match `response_mode`. For example,
  `response_mode: "body_excerpt"` requires `body_excerpt`, and
  `response_mode: "error_shape"` requires `error_shape`.
- Prefer concrete `body` or `body_excerpt` rows from official examples,
  OpenAPI examples, safe test-mode probes, or recorded observations.
- Use `body_shape` only when the provider docs support the response contract but
  no concrete body has been captured yet. Add `gating_notes` so the runtime
  knows this is shape coverage, not a concrete fixture.
- Use `error_shape` for documented provider errors such as validation,
  permission, not-found, conflict, or rate-limit outcomes.
- Response cases must cite source evidence. They are not lane labels and not
  world runtime behavior by themselves.
- Structural validation only proves the rows are well-formed. A runtime world
  should still use a separate coverage gate to decide whether selected response
  cases are sampled well enough for dry-run behavior.

## `probes.jsonl`

Probe definitions or probe result indexes. Probes must be safe and explicitly
scoped.

```json
{"id":"probe:listWidgets:test-mode:2026-06-12","operation_ref":"operation:listWidgets","mode":"test_mode","live_execution_allowed":false,"command":"python probes/list_widgets.py --record-only","output_ref":"raw/probes/list_widgets_2026-06-12.json","safety":{"requires_test_credentials":true,"mutates_provider":false}}
```

Rules:

- Do not store secrets.
- Test-mode probes must refuse production credentials by default.
- A probe record does not grant API Gym permission to execute live provider
  actions during world sessions.

## `observed_errors.jsonl`

Observed or documented error behavior.

```json
{"id":"observed_error:listWidgets:401","operation_ref":"operation:listWidgets","status":401,"code":"unauthorized","message_shape":{"error":{"type":"string","message":"string"}},"source_refs":[{"kind":"docs","url":"https://docs.example.invalid/errors"}],"agent_readable_rule":"Credentials are missing or invalid."}
```

Rules:

- Error messages should be agent-readable and stable where possible.
- Separate documented errors from probe-observed errors with `source_refs`.
- Do not smooth over provider behavior with local compatibility hacks.

## `world_candidates.jsonl`

Candidate mappings from source substrate into future world design. These rows
are planning evidence, not runtime contracts.

```json
{"id":"world_candidate:widget_triage_v0","source_pack_id":"api.example.2026-06-12","candidate_world":"widget_triage_v0","operation_refs":["operation:listWidgets"],"design_status":"candidate","notes":["Read-only inspection could support task setup. Mutable workflow actions still need grounded source records."],"not_world_contract":true}
```

Rules:

- A candidate row does not create a world.
- The world contract begins under `worlds/<world_id>`.
- Once selected, cite the source pack from `worlds/<world_id>/source_refs.json`.

## Validation Expectations

Agents should validate source packs with code before relying on them. Minimal
checks:

```python
import json
from pathlib import Path

root = Path("source_packs/apis/example/2026-06-12")
pack = json.loads((root / "source_pack.json").read_text())

assert pack["schema_version"] == "api_gym.api_source_pack.v0"
assert pack["source_pack_id"]

for rel_path in pack["records"].values():
    path = root / rel_path
    assert path.exists(), path
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            row = json.loads(line)
            assert row["id"], (path, line_number)
            assert row.get("source_pack_id") == pack["source_pack_id"] or row.get("operation_ref")
```

Validation should prove structure and citations. It should not invent provider
semantics or repair missing evidence with heuristics.
