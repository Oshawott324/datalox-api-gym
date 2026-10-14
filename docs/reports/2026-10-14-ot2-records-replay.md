# OT-2 records: replay and offset-measurement task

Date: 2026-10-14. Source: the robot export of 2026-10-12 in
[ot2-reference-trajectories](https://github.com/Jiantao-Zhao/ot2-reference-trajectories) (commit `e71d4eb`, MIT).

## 1. All five recorded arc outcomes reproduce

Every recorded attempt was a drop-tip move to the trash (`moveToAddressableAreaForDropTip`), and each script call
issued it before picking up a tip. Run `ac20a023` served the slot-3 call and then the slot-7 call, so the slot-7
attempt started with the slot-3 tip still attached. Replaying that tip state in the official planner (opentrons
8.8.2) reproduces 5 of 5 outcomes, with the definition tip length and with the calibrated one
(`probes/ot2_reference/replay_arc_records.py`, kept as a test).

| Case | Highest accepted `minimumZHeight` |
| --- | ---: |
| P20, no tip | 179.59 mm |
| P20, tip at engine length 30.95 mm | 148.65 mm |
| P20, tip at calibrated length 30.85 mm | 148.74 mm |
| P300, tip at engine length 51.10 mm | 147.46 mm |
| P300, tip at calibrated length 48.70 mm | about 149.9 mm |

The 2026-10-04 report explained the slot-3 result with a tip about 1.4 mm shorter than nominal. That was wrong:
the calibrated P20 tip is 0.1 mm shorter; the cause is the engine's tip state.

`opentrons analyze` uses definition tip lengths, not the robot's calibration, so for the P300 the analyzer's limit
is about 2.4 mm below the robot's. A new maintenance run that does not know a tip is attached plans for the bare
nozzle; the tip end then travels one tip length lower than planned. That follows from the planner and has not
been checked on the robot.

## 2. Robot facts now in the reference data

- Software 26.6.0 (`opentrons-ot2` line, not on PyPI), firmware v1.1.0-25e5cea, protocol API up to 2.28.
- Tip lengths 30.85 mm (P20) and 48.70 mm (P300); both unchanged by the 2026-09-30 recalibration.
- Calibration snapshots before and after the recalibration at 2026-09-30 13:48 UTC.
- The second offset file was marked at 2026-09-30 12:59:37 against the earlier calibration and was used by the
  15-point check on 2026-10-01, after the recalibration.
- The slot-3 definition supplied by the robot export is identical to the approximation used before.

## 3. New task: `measure_offset`

Built from the robot's calibration log. The agent measures one rack's labware offset with the tools the
operator's scripts used: read the open run's applied offsets, open a run with or without offsets, move to the
well top, jog, read the absolute position (`moveRelative` with distance 0), and ask the operator how the tip sits.
The trap is the recorded failure: the file says one offset while the open run applied another.

| Method (scripted) | Run matches file | Run differs from file |
| --- | --- | --- |
| Zero-offset run, absolute readback (the method that worked) | pass | pass |
| Run's own applied offset plus jog | pass | pass |
| File value plus jog (team procedure in the log) | pass | `OFFSET_INCORRECT` |
| Centred position minus starting position (the old mark bug) | `OFFSET_INCORRECT` | `OFFSET_INCORRECT` |

60 seeds per method; no contacts. True offsets are the robot's measured zeros or authored offsets within 1 mm.

## 4. Tests

`tests/ot2_protocol`: 29 passed, including the replay (5/5, both tip lengths) and the method comparison above.

## 5. Scope and limitations

- Results use opentrons 8.8.2, not the robot's 26.6.0.
- Operator observations are coarse text with fixed thresholds (centred within 0.2 mm, "slightly" up to 1 mm);
  they stand in for a person's eye and are not calibrated against one.
- Contact in `measure_offset` is a rule on the final tip position against the tube mouth and depth, not a swept
  path check.
- No model runs are included.
