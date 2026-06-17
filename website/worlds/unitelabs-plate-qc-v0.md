# UniteLabs Plate QC v0

`unitelabs_plate_qc_v0` is a deterministic dry-run lab workflow world for plate
transfer QC.

## World Contract

Source substrate:

- explicit UniteLabs OpenAPI contract sample
- UniteLabs workflow, run, log, and artifact docs
- no live workflow execution in V0

Episode state:

- one `state.sqlite` per sampled run
- deck layout
- labware inventory
- well volume ledger
- absorbance readout ledger
- workflow notes
- submitted protocol decision

Actions:

- `get_deck_state`
- `get_labware_state`
- `aspirate`
- `dispense`
- `read_absorbance`
- `add_workflow_note`
- `submit_protocol`

Dynamics:

- deterministic dry-run lab workflow logic
- no live hardware or device endpoint call

Verifier:

- checks source volume
- checks target volume
- checks readout order
- checks submitted target
- checks protocol decision and supporting readout evidence
- rejects live-action audit events in dry-run mode

Evidence:

- session manifest
- task package
- MCP tool trace
- verifier result
- run export

## Session Flow

```bash
api-gym session create \
  --world unitelabs_plate_qc_v0 \
  --scenario plate_transfer_qc \
  --seed 1 \
  --out runs/unitelabs-demo \
  --json

api-gym session check-tools --run runs/unitelabs-demo
api-gym session finalize --run runs/unitelabs-demo --json
```

The session manifest gives an external agent host the task package, MCP config,
expected tools, commands, and artifact paths.

## API Grounding

Use the grounding command only against an explicit OpenAPI document:

```bash
api-gym unitelabs sample-api-contract \
  --openapi-file /path/to/unitelabs-openapi.json \
  --out worlds/unitelabs_plate_qc_v0/evidence/unitelabs_api_contract_sample.json
```

The command reads the OpenAPI document. It does not create workflow runs, poll
runs, send lab commands, or call live device endpoints.
