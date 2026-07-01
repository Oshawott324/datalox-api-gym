# lab_campaign_ops_v0

This is the Step 5 world/task/state skeleton for the Lab Campaign Ops
direction.

The world now defines the minimum structure future task families, tools,
oracles, and verifiers must use when coordinating provider-shaped lab workflows
across:

```text
benchling_assay_v1
opentrons_http_v1
tetrascience_context_v1
```

The benchmark identity is a multi-provider lab operations workflow, not an
Opentrons-only simulator. Opentrons is one source pack inside the world.

The world now has two admitted task families:

```text
stale_instrument_data_handoff
od600_qc_handoff_nominal
```

`stale_instrument_data_handoff` composes only:

```text
benchling_assay_v1
tetrascience_context_v1
```

It does not force Opentrons into a task where robot/protocol analysis is not
needed.

`od600_qc_handoff_nominal` composes all three source packs:

```text
benchling_assay_v1
opentrons_http_v1
tetrascience_context_v1
```

It requires the agent path to upload and analyze an Opentrons-style protocol,
create a dry-run plan, inspect current instrument evidence, and draft a
Benchling-style assay result that cites both the accepted dry-run evidence and
the current instrument record.

Hidden oracle and known-bad plans execute through the same agent-visible dry-run
tool names:

```text
benchling_assay_v1.get_assay_request
tetrascience_context_v1.list_instrument_records
tetrascience_context_v1.get_instrument_record
opentrons_http_v1.upload_protocol
opentrons_http_v1.analyze_protocol
opentrons_http_v1.get_protocol_analysis
opentrons_http_v1.create_dry_run_plan
benchling_assay_v1.create_assay_result_draft
```

The runtime operates on a copied task JSON state only. It does not call live
providers.

## Files

```text
task_schema.json
  Schema skeleton for generated task metadata.

state_schema.json
  Schema skeleton for minimal cross-provider sandbox state.

source_pack_refs.json
  Source packs this world is allowed to compose in Step 2.

validate_world_schemas.py
  Filesystem validator for this schema skeleton and both Step 5 templates.

templates/stale_instrument_data_handoff.json
  Source-pack/task-family template for a stale instrument-data handoff hazard.

templates/od600_qc_handoff_nominal.json
  Source-pack/task-family template for an all-three-provider OD600 QC handoff.

task_generator.py
  Filesystem generator/admission harness for both task families.

tools.py
  Public dry-run tool functions needed by these task families.

runtime.py
  Minimal plan executor that writes tool-call and state-diff traces.
```

Generated bundles contain:

```text
task.json
agent_task.json
initial_state.json
visible_artifacts/
hidden/verifier_expectations.json
hidden/oracle_plan.json
hidden/known_bad_plans.json
admission.json
runs/oracle/tool_calls.jsonl
runs/oracle/state_diffs.jsonl
runs/oracle/final_state.json
runs/<known_bad_plan_id>/tool_calls.jsonl
runs/<known_bad_plan_id>/state_diffs.jsonl
runs/<known_bad_plan_id>/final_state.json
```

## Validation

Run from the repository root:

```bash
python greenfield_lab_campaign_ops/source_packs/validate_source_packs.py
python greenfield_lab_campaign_ops/worlds/lab_campaign_ops_v0/validate_world_schemas.py
python -m greenfield_lab_campaign_ops.demo --clean
python -m compileall -q greenfield_lab_campaign_ops
```

## Boundary

This step implements only the provider-shaped public-tool runtime required by
`stale_instrument_data_handoff` and `od600_qc_handoff_nominal`. It is not a
generic framework and does not claim full Benchling, Opentrons, or TetraScience
API coverage.

The synthetic task state is marked `speculative_calibration_only`. Do not treat
it as exact Benchling or TetraScience provider payload semantics.

The admitted invariants are:

```text
SUBMISSION_CITES_CURRENT_INSTRUMENT_RECORD
RESULT_CITES_PROTOCOL_DRY_RUN_AND_CURRENT_RECORD
```

For stale-data handoff, the oracle drafts an assay result citing the current
instrument record. The known-bad drafts the result from the stale prior-run
record and must fail admission with `SUBMISSION_CITES_CURRENT_INSTRUMENT_RECORD`.

For nominal OD600 QC handoff, the oracle uploads/analyzes a protocol, creates an
accepted dry-run plan, reads the current instrument record, and drafts a result
citing both evidence classes. The known-bad omits the protocol/dry-run evidence
from the result draft and must fail admission with
`RESULT_CITES_PROTOCOL_DRY_RUN_AND_CURRENT_RECORD`.
