# Source-Pack Readiness Gate

Date: 2026-07-02

Purpose: rule out source packs that do not meet the current build requirement:
use exact public JSON bodies or captured probe responses, not synthetic or
derived shapes.

## Gate

A source pack is admitted for task/world build only if all of these are true:

```text
source_status == source_grounded
tool_surface_status == source_grounded
response_body_status in {exact_public_json_body, captured_probe_response}
fixtures are all source_copied_example or captured_probe_response
```

`derived_from_source_example` is not enough for the current standard. It can be
useful research scaffolding, but it is not admissible as a benchmark grounding
claim because the response body was not copied exactly from docs and was not
captured from a probe.

Run the machine-readable audit:

```bash
python greenfield_lab_campaign_ops/source_packs/audit_readiness.py
python greenfield_lab_campaign_ops/source_packs/audit_readiness.py --json
```

## Current Decision

| Source pack | Decision | Reason |
| --- | --- | --- |
| `opentrons_protocol_analysis_v1` | Admit | Captured local `opentrons==9.1.0` analyzer JSON; broad physical-operation coverage across liquid handling, waste, gripper movement, temperature module, heater-shaker, thermocycler, absorbance reader, magnetic block, Flex stacker, and analyzer failures. |
| `labstep_workflow_v1` | Admit, supporting role | Exact public Labstep JSON examples. Useful for ELN/workflow/provenance records, but shallow and not the core long-horizon physical-operation world. |
| `benchling_assay_v1` | Rule out for now | Fixture is `derived_from_source_example`, not exact public JSON or captured probe response. It also only covers assay-result creation shape, not full worklist/request/result lifecycle. |
| `opentrons_http_v1` | Rule out for now | HTTP response bodies are not captured; fixture is speculative. Keep only as a future robot-server or real-robot capture target. |
| `tetrascience_context_v1` | Rule out for now | Response bodies are not captured; fixture is speculative. Keep only as a future public-example/probe/partner-capture target. |

## Practical Consequence

For near-term task generation, use:

```text
opentrons_protocol_analysis_v1
labstep_workflow_v1, only when a record/provenance layer is needed
```

Do not build benchmark tasks that require Benchling, TetraScience, or Opentrons
HTTP semantics until those packs are recaptured or rebuilt under the gate.

If we need richer multi-provider complexity next, first add a new source pack
that passes the same gate. Good candidates are providers with exact public JSON,
self-hosted demo servers, or local simulators that can be probed in CI.
