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
benchling_assay_v1
tetrascience_context_v1
```

Validate the source packs from the repository root:

```bash
python greenfield_lab_campaign_ops/source_packs/validate_source_packs.py
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
