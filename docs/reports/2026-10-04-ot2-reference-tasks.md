# OT-2 reference tasks: first build and findings

Date: 2026-10-04. Source: recorded operation of a real OT-2
([reference trajectories](https://github.com/Jiantao-Zhao/ot2-reference-trajectories), commit `00767f8`).
Code: `api_gym/worlds/ot2_protocol_v0/`, `harness/ot2_protocol/`, `probes/ot2_reference/`.

## 1. The official OT-2 analyzer is not the one we pinned

Opentrons 9.1.1 (our motion worker) and 10.0.0 raise "This protocol is designed for an OT-2 robot"
in both `opentrons analyze` and `opentrons simulate`. OT-2 support moved to the `opentrons-ot2`
release line (robot stack v26.6.0, 2026-07-29). `opentrons==8.8.2` (PyPI, 2026-05-29) still
analyzes OT-2 protocols, takes about 2 s per protocol, and reproduces the recorded error text
exactly: `FailedToPlanMoveError`, error 4000, "Arc out of bounds in the Z-axis". The OT-2 tasks
use 8.8.2 until the robot's software version is known.

## 2. Arc limit versus the recorded robot outcomes

`probes/ot2_reference/arc_limit_sweep.py`, default calibration and nominal tip length:

| Pipette | Instrument max height | moveToWell limit (slots 3, 6, 7, 8) | Drop-tip move to trash |
| --- | ---: | ---: | ---: |
| p20 + 20 uL tips | 180.60 mm | 148.63 mm | 148.63 mm |
| p300 + 300 uL tips | 199.60 mm | 147.46 mm | 147.46 mm |

The limit does not depend on the destination slot or on labware offsets: the planner rejects an arc
when `minimum_z_height` + 1 mm exceeds the instrument's highest reachable Z with the tip attached.
Each millimetre of effective tip length moves the limit by one millimetre.

| Recorded outcome | Default prediction | Match |
| --- | --- | --- |
| slot 3, 180 mm, rejected (drop-tip move to trash) | rejected | yes |
| slot 3, 150 mm, accepted | rejected | **no** |
| slot 7, 150 mm, rejected (failing command not recorded) | rejected | yes |
| slot 7, 130 mm, accepted | accepted | yes |
| slot 6, 130 mm, accepted | accepted | yes |

Four of five match. The robot accepted 150 mm at slot 3, at least 1.37 mm above the default limit,
which a tip-length calibration about 1.4 mm shorter than nominal would explain. The same run then
rejected 150 mm at slot 7 with the same tip; a fixed limit cannot produce both, so either the slot-7
failure came from a different command or something changed between the two moves. The missing
inputs are the tip-length calibration, the robot software version and the command log of run
`ac20a023`.

## 3. The suggested probe step sizes can reach the tube bottom

The feedback table suggests 10 / 5 / 1 mm steps at the far / near / very close levels. Near covers
5–20 mm, so a 5 mm step taken at 5.x mm lands within 1 mm of the bottom. Over 200 random tube depths
(12–75 mm below the modelled top) that policy passed 163 times and reached the contact-risk level in
the rest. Steps of 10 / 3 / 1 mm cannot skip the very-close level and passed 200 of 200.

## 4. What is built

- Three task families with seeded variants and hidden state: arc moves (both modes), stepwise probing,
  stale labware offsets. Every safety requirement that is checked is stated in the public task.
- Checks with specific failure codes; known-bad controls fail with the expected code and alternative
  valid plans pass (`tests/ot2_protocol`, 21 tests).
- A static rule check for the agreed `protocol_api` action set (force_direct, raw coordinate
  locations, private interfaces, actions outside the set, geometry recomputed from definitions).
- A runner for fixed scripts and any OpenAI-compatible model, recording seconds per decision, and an
  MCP server for external hosts such as OpenCode.

Fixed-script baseline, seeds 0–5: 24 of 24 episodes passed.

## 5. Scope and limitations

- This change includes no model runs.
- Results describe the default Opentrons configuration. Matching this robot needs its tip-length
  calibration, its software version and the command log of run `ac20a023`.
- The slot-3 labware definition is an approximation (standard rack, measured column pitch); the
  original definition is not in the records.
- The source repository declares no license; its records are used with attribution at the author's
  invitation and will be removed on request.
