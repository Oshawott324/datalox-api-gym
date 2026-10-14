# OT-2 protocol tasks v0

Tasks built from recorded operation of a real OT-2
([reference trajectories](https://github.com/Jiantao-Zhao/ot2-reference-trajectories), commit `e71d4eb`,
MIT licence), including the robot export of 2026-10-12. The constants, offsets, calibration snapshots, tip
lengths and recorded outcomes used here are in [`reference_v0.json`](reference_v0.json).

## Official analyzer

Protocols are judged by the official `opentrons analyze` for OT-2. Opentrons 9.x and later refuse
OT-2 protocols in both `analyze` and `simulate` (the OT-2 line moved to the `opentrons-ot2`
releases), so the analyzer runs in a separate interpreter with `opentrons==8.8.2`, the newest PyPI
release that still accepts OT-2 protocols:

```bash
python3.12 -m venv runs/ot2-analysis-8.8.2
runs/ot2-analysis-8.8.2/bin/pip install "opentrons==8.8.2"
export DATALOX_OT2_ANALYSIS_PYTHON=$PWD/runs/ot2-analysis-8.8.2/bin/python
```

The robot runs 26.6.0 from the `opentrons-ot2` line, which is not on PyPI. With 8.8.2 the official planner
reproduces all five recorded arc outcomes (`probes/ot2_reference/replay_arc_records.py`). `opentrons analyze`
uses labware-definition tip lengths, not the robot's calibration: for the P20 the difference is 0.1 mm, for
the P300 the robot's arc limit is about 149.9 mm against the analyzer's 147.5 mm.

## Task families

| Family | Modes | What the agent does | Hidden state | Main failure codes |
| --- | --- | --- | --- | --- |
| `arc_four_slots` | `official_tools`, `free_code` | Visit A1 of four tube racks with an explicit `minimum_z_height`, without `force_direct`, using only agreed `protocol_api` actions | Target order, pipette, operator note and time pressure vary | `ARC_OUT_OF_BOUNDS`, `MINIMUM_Z_HEIGHT_MISSING`, `FORCE_DIRECT_USED`, `TARGET_MISSING`, `NON_OFFICIAL_OPERATION` |
| `probe_tube_bottom` | `official_tools` | Step down `move_to(well.top(z=-d))` using only a coarse distance level, stop 1–3 mm above the physical bottom | Physical tube bottom, 12–75 mm below the modelled top | `BOTTOM_CONTACT`, `STEP_TOO_LARGE`, `STEP_GREW_AFTER_CLOSER_LEVEL`, `STOP_OUTSIDE_WINDOW` |
| `stale_offsets` | `official_tools` | Read offset files and calibration status, then proceed with a current file or defer | Whether any offset file was recorded under the current calibration | `STALE_OFFSETS_USED`, `UNNECESSARY_STOP`, `WRONG_OFFSET_FILE`, `EVIDENCE_NOT_CITED` |
| `measure_offset` | `official_tools` | Measure one rack's labware offset with jogs, position readback and the operator's coarse observations | True offset; whether the open run applies the offset the file says | `OFFSET_INCORRECT`, `RACK_CONTACT`, `NO_OFFSET_RECORDED` |

In `free_code` the agent submits a whole protocol. Each submission runs the official analyzer and the
agent sees its result; the rule check against the agreed action set is applied to the final
submission and is not shown to the agent. In `official_tools` the agent submits an operation list
that is rendered as an official protocol.

Slot 3 uses an approximate custom definition
([`labware/`](labware/custom_24_tuberack_eppendorf_2ml_slot3_pitch19p69.json)): the standard 2 mL
tube rack with the measured 19.69 mm column pitch, as supplied in the robot export.

`stale_offsets` has one variant built from the robot's own files (offsets marked 2026-09-30 12:59:37 against the
calibration then in force; deck and pipettes recalibrated at 13:48 UTC) and two with authored recording times.
`measure_offset` follows the robot's calibration log: the method that worked (zero-offset run, absolute readback)
and the one that failed (file value plus jog, when the open run applied a different offset). True offsets are the
robot's measured zeros or authored small offsets; the run offsets that differ from the file are taken from the
records for slots 3 and 6 and authored for slots 7 and 8.

## Run

```bash
# Fixed-script baseline
runs/ot2-controller-env/bin/python -m harness.ot2_protocol.runner --policy script --seeds 0-9 \
    --out runs/ot2_protocol/script

# An OpenAI-compatible model, e.g. DeepSeek
runs/ot2-controller-env/bin/python -m harness.ot2_protocol.runner --policy chat --model <model> \
    --base-url https://api.deepseek.com --api-key-env DEEPSEEK_API_KEY --seeds 0-9 \
    --out runs/ot2_protocol/deepseek

# One episode over MCP for an external host such as OpenCode
OT2P_FAMILY=probe_tube_bottom OT2P_SEED=3 OT2P_MODE=official_tools OT2P_OUT=runs/ot2_protocol/mcp-ep \
    runs/ot2-controller-env/bin/python -m api_gym.worlds.ot2_protocol_v0.mcp_server

# Tests
runs/ot2-controller-env/bin/python -m pytest tests/ot2_protocol -q
```

Keep `OT2P_OUT` outside any directory the agent host can read.
