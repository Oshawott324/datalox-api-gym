# Opentrons Motion Simulation

An offline prototype for checking movements produced by the Opentrons software
against modeled obstacles, before attempting them on an instrument.

The current code accepts movement commands in a persistent official Opentrons
9.1.1 simulator, records intermediate movements, and checks their full paths
against explicitly supplied geometry. Reset creates a fresh simulator process.
The runnable example uses an authored geometric fixture; it has not been
validated on a physical robot.

## Start Here

- [Example output](probes/ot2_motion/examples/reference-result.json): a complete,
  freshly generated run, including coordinates, geometry results, and versions.
- [Code and setup](probes/ot2_motion/README.md): supported behavior, dependencies,
  and reproduction instructions.
- [Build specification](docs/reports/2026-09-26-ot2-motion-build-spec.md):
  implementation steps toward an interactive instrument model.
- [Initial results](docs/reports/2026-09-24-ot2-motion-phase0-results.md):
  reference-software checks and current limitations.
- [CAD inspection](docs/reports/2026-09-27-ot2-cad-inspection.md): what the
  source files contain, and which geometry is still missing.
- [Interactive example](probes/ot2_motion/interactive_example.py): direct and
  raised movements evaluated in separate reset episodes, or a supplied sequence
  of supported movement commands.
- [Interactive container](docs/ot2-motion-container.md): build and run the
  native worker, motion world, and MCP integration without network or robot access.
- [Agent connection](docs/ot2-motion-agent-interface.md): prepare a fresh
  session and connect an MCP-capable agent through five bounded tools.
- [Implementation status](docs/reports/2026-09-27-ot2-motion-implementation.md):
  tested behavior, repository ownership, and remaining physical inputs.

## What You Can Check Today

| Command or check | What it demonstrates |
| --- | --- |
| Raised traversal between plates | The native planner supplies the intermediate upward, lateral, and downward movements |
| Direct traversal | A different native path can intersect an obstacle the raised path clears |
| Minimum-height option | The requested option changes the native planner's path |
| Labware-offset update | Updated configuration changes the commanded target |
| Repeated position request | The same destination is recorded without inventing extra movement |
| Thin obstacle between clear endpoints | Whole-path checking detects an intersection that endpoint-only checks miss |

The collision example uses a **0.5 mm radius sphere and an authored thin wall**.
These are mathematical fixtures, not accurate pipette or rack geometry. The
example establishes the connection between native movements and geometric
checks; it does not establish clearance for a real OT-2.

## Run the Original Reference Probe

With Git and Docker installed:

```bash
git clone --branch opentrons-motion-simulation --single-branch \
  https://github.com/Oshawott324/datalox-api-gym.git
cd datalox-api-gym
bash probes/ot2_motion/build_image.sh
docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --pids-limit 256 --memory 2g \
  --tmpfs /tmp:rw,nosuid,nodev,size=256m datalox-ot2-motion:phase0
```

The default container command runs the 31 focused tests. Building the image
downloads dependencies; execution is network-disabled and uses no robot
credentials or device mounts.

To execute the combined movement-and-geometry probe in that image:

```bash
docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --pids-limit 256 --memory 2g \
  --tmpfs /tmp:rw,nosuid,nodev,size=256m datalox-ot2-motion:phase0 \
  python -m probes.ot2_motion --out /tmp/result.json
```

A successful run prints `"feasibility_passed": true`. The temporary result is
removed with the container; the [checked-in example](probes/ot2_motion/examples/reference-result.json)
shows the complete record. [Python-only instructions](probes/ot2_motion/README.md#reproduce-on-the-development-host)
also describe how to retain a local result.

## Code Map

- [reference.py](probes/ot2_motion/reference.py) calls the official simulator and
  records its movement segments.
- [Geometry](api_gym/instrument_models/geometry) checks fixed-orientation
  translations of boxes, spheres, convex polyhedra, and unions of convex pieces.
- [Instrument model](api_gym/instrument_models/opentrons_ot2_v0) separates
  configured offsets, modeled physical placement, native movement coordinates,
  and available operator observations.
- [Motion world](api_gym/worlds/ot2_motion_v0) evaluates each path once and
  verifies the resulting episode facts. Final verification does not rerun the
  collision queries.
- [__main__.py](probes/ot2_motion/__main__.py) combines those two parts and writes
  the result.
- [Tests](tests/instrument_models) cover reference movements, geometry,
  reproducibility, and source integrity.
- [Sources](probes/ot2_motion/sources) pin software and CAD references.

## Current Limits

The STEP inspection found 26 valid source-labeled solids. Their correspondence
to the selected GEN2 pipette, the motion reference point, and the software deck
frame is unresolved. Tip, rack, plate, and trash geometry are still missing from
the admitted scene. An incomplete scene cannot establish whole-instrument
clearance.

The authored fixture is an engineering control, not a realistic instrument
benchmark. The model detects geometric intersections; it does not calculate
contact forces, tip bending, liquid delivery, or biological outcomes. A detected
intersection ends the modeled episode with an unresolved physical pose.

The first MCP bundle contains one runnable task. Four task definitions exist in
the world code; they are not four independently integrated instrument scenarios.
Managed sessions require a fresh native process and do not support resuming from
the database after shutdown. Researcher visualization exports are separate from
agent observations and do not control the instrument.

Physical comparisons still require an instrument owner and independently checked
geometry. No agent-learning or physical-transfer result is claimed.

The [build specification](docs/reports/2026-09-26-ot2-motion-build-spec.md) gives
the acceptance tests and sequence for each stage.

---

This branch is part of [Datalox API Gym](https://github.com/Oshawott324/datalox-api-gym/tree/main).
It focuses on OT-2 movement modeling. It is an independent project, not an
official Opentrons simulator release.
