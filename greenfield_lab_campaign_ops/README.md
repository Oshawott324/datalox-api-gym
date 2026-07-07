# Greenfield Lab Campaign Ops

This package contains the greenfield skeleton for `lab_campaign_ops_v0`.

Step 1 defines how provider-shaped tool families are represented. Step 2
defines the minimal world/task/state schemas those source packs compose. Step 3
adds the first task-family generation/admission skeleton for
`stale_instrument_data_handoff`. Step 4 executes that task family's hidden
oracle and known-bad plans through public dry-run tools and writes run traces.

Current source packs:

```text
opentrons_http_v1
opentrons_protocol_analysis_v1
benchling_assay_v1
tetrascience_context_v1
labstep_workflow_v1
```

Current build-ready source packs under the strict gate:

```text
opentrons_protocol_analysis_v1
labstep_workflow_v1
```

Ruled out for current task/world build until recaptured or rebuilt:

```text
benchling_assay_v1
opentrons_http_v1
tetrascience_context_v1
```

`labstep_workflow_v1` is the first exact-public-JSON source pack in this
greenfield package. Its fixtures are byte-for-byte copies of public Labstep
example JSON files linked from `https://apidoc.labstep.com/openapi.yaml`.

`opentrons_protocol_analysis_v1` is grounded in captured local
`opentrons==9.1.0` analyzer JSON. It covers broad physical-operation planning
for liquid handling, waste, gripper movement, temperature module,
heater-shaker, thermocycler, absorbance reader, magnetic block, Flex stacker,
and structured analyzer failures. It does not claim live robot HTTP run or
hardware-control response bodies.

Validate the source packs from the repository root:

```bash
python greenfield_lab_campaign_ops/source_packs/validate_source_packs.py
```

Audit which packs meet the stricter task-build gate:

```bash
python greenfield_lab_campaign_ops/source_packs/audit_readiness.py
```

Validate the world schema skeleton from the repository root:

```bash
python greenfield_lab_campaign_ops/worlds/lab_campaign_ops_v0/validate_world_schemas.py
```

Generate and admit the Step 4 stale-data task:

```bash
python -m greenfield_lab_campaign_ops.demo --clean
```

The source packs are dry-run contracts. They do not execute live provider calls,
do not require credentials, and do not allow hardware or production writes.

Source-pack grounding is split into two claims:

```text
tool_surface_status
  Whether the operation names and API surface are grounded from docs/specs.

response_body_status
  Whether request/response bodies are exact public JSON examples, captured
  probe responses, derived source examples, or not captured yet.
```

Do not use `source_status: source_grounded` for a pack with speculative
fixtures. The validator rejects that combination.

Fixtures in this Step 1 skeleton are for schema exercise only unless their
`fixture_status` says otherwise. Do not treat synthetic fixtures as provider
captures.

The `lab_campaign_ops_v0` world schema currently covers:

```text
worklist
samples/entities
plate map
protocol analysis state
instrument/readout records
result upload records
dry-run boundary events
```

The Step 4 task bundle is still a calibration artifact. Synthetic task state is
marked `speculative_calibration_only`; it should not be represented as exact
provider API behavior. The Step 4 runtime is intentionally narrow: it only
implements the four public dry-run tools needed for the stale-data handoff
family.
