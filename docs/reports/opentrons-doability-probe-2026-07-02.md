# Opentrons Doability Probe

Date: 2026-07-02

Question: can we build a real Opentrons source pack from exact JSON bodies or a
local probe, rather than synthetic fixtures?

## Result

Yes, but split it into two different pack types:

```text
opentrons_protocol_analysis_v1
  Doable now from a local Opentrons package probe.
  Grounding: captured JSON output from `python -m opentrons.cli analyze`.

opentrons_robot_http_v1
  Doable only after robot-server capture.
  Grounding: `/openapi` and HTTP endpoint responses from a real/simulated
  robot-server process or robot.
```

Do not claim HTTP endpoint response grounding from the current `opentrons`
PyPI package alone.

Update: `opentrons_protocol_analysis_v1` is now built under
`greenfield_lab_campaign_ops/source_packs/`. It contains captured analyzer JSON
for core liquid handling, waste, gripper movement, temperature module,
magnetic block, heater-shaker, thermocycler, absorbance reader, Flex stacker,
invalid deck placement, and the vacuum-module API-version gate.

## What Worked

Installed Opentrons 9.1.0 in a temp venv:

```bash
python -m venv /tmp/opentrons_probe_venv
/tmp/opentrons_probe_venv/bin/python -m pip install opentrons==9.1.0
```

Available CLI tools:

```text
opentrons_execute
opentrons_simulate
python -m opentrons.cli analyze
```

`opentrons_simulate` produced an authentic Flex protocol run log for this
protocol:

```python
from opentrons import protocol_api

requirements = {"robotType": "Flex", "apiLevel": "2.22"}

def run(protocol: protocol_api.ProtocolContext):
    protocol.load_trash_bin("D3")
    tiprack = protocol.load_labware("opentrons_flex_96_tiprack_200ul", "A1")
    plate = protocol.load_labware("corning_96_wellplate_360ul_flat", "B1")
    pipette = protocol.load_instrument("flex_1channel_1000", "left", tip_racks=[tiprack])
    pipette.pick_up_tip()
    pipette.aspirate(50, plate["A1"])
    pipette.dispense(50, plate["B1"])
    pipette.drop_tip()
```

Probe command:

```bash
/tmp/opentrons_probe_venv/bin/opentrons_simulate -o runlog /tmp/opentrons_simple_protocol.py
```

Observed run log:

```text
Picking up tip from A1 of Opentrons Flex 96 Tip Rack 200 uL on slot A1
Aspirating 50.0 uL from A1 of Corning 96 Well Plate 360 uL Flat on slot B1 at 716.0 uL/sec
Dispensing 50.0 uL into B1 of Corning 96 Well Plate 360 uL Flat on slot B1 at 716.0 uL/sec
Dropping tip into Trash Bin on slot D3
```

`python -m opentrons.cli analyze` produced structured JSON:

```bash
/tmp/opentrons_probe_venv/bin/python -m opentrons.cli analyze \
  --human-json-output /tmp/opentrons_analysis.json \
  /tmp/opentrons_simple_protocol.py
```

Observed summary:

```text
result: ok
robotType: OT-3 Standard
commands: 9
labware: 2
pipettes: 1
errors: 0
```

The analysis JSON includes command records for:

```text
home
loadLabware
loadLabware
loadPipette
pickUpTip
aspirate
dispense
moveToAddressableAreaForDropTip
dropTipInPlace
```

This is enough to build a real captured-probe source pack for protocol
analysis, deck/labware/pipette requirements, and dry-run command evidence.

## What Did Not Work From PyPI

The `opentrons` PyPI package does not provide a runnable robot HTTP server.
It provides protocol simulation/execution tools.

The installed package has no `robot_server` package or HTTP server entry point.
The only relevant console scripts are:

```text
opentrons_execute
opentrons_simulate
```

Therefore, we cannot capture real HTTP responses for:

```text
/openapi
/robot/move
/robot/home
/runs
/runs/{runId}/actions
/runs/{runId}/commands
/protocols
/protocols/{protocolId}/analyses
```

from PyPI alone.

## Public Docs Finding

The official Opentrons HTTP API docs page embeds a Redoc state object containing
the OpenAPI document:

```text
openapi: 3.1.0
title: Opentrons HTTP API Spec
version: 4
paths: 87
```

The docs state that the robot OpenAPI can be retrieved from a robot on port
`31950` at `/openapi`.

The embedded OpenAPI includes robot-control and run-management endpoints such
as:

```text
/robot/move
/robot/home
/runs
/runs/{runId}/actions
/runs/{runId}/commands
/protocols
/protocols/{protocolId}/analyses
```

But the OpenAPI object does not expose explicit `examples` entries for the
checked operations. Redoc renders response samples from schemas, but those are
not the same as captured endpoint responses.

## Robot Server Feasibility

The Opentrons monorepo has `robot-server`, but its `pyproject.toml` depends on
monorepo-local packages:

```text
opentrons = { path = "../api", editable = true }
opentrons-shared-data = { path = "../shared-data", editable = true }
server-utils = { path = "../server-utils", editable = true }
opentrons-hardware = { path = "../hardware", editable = true }
hardware-testing = { path = "../hardware-testing", editable = true }
```

So a local robot-server probe is possible, but it is a separate monorepo setup
task, not something the published `opentrons` package gives us directly.

## Recommendation

Built:

```text
opentrons_protocol_analysis_v1
```

Ground it with captured local `opentrons.cli analyze` JSON fixtures and the
official simulation/analyze behavior.

Next Opentrons action:

```text
Use opentrons_protocol_analysis_v1 as the physical-operation dry-run source
pack for task generation. Keep opentrons_robot_http_v1 as a separate capture
project for live robot-server endpoints.
```

Do not build or claim:

```text
opentrons_robot_http_v1 response_body_status: captured_probe_response
```

until we either:

```text
1. run robot-server locally from the Opentrons monorepo and capture /openapi +
   endpoint responses, or
2. capture from a real robot at http://<robot>:31950/openapi and selected
   dry-run-safe endpoints.
```
