# Opentrons Motion Simulation

An offline prototype for checking movements produced by the Opentrons software
against modeled obstacles, before attempting them on an instrument.

The current code runs five fixed commands through the official Opentrons 9.1.1
simulator, records their intermediate movements, and checks the full paths against
a simple geometric fixture. It has not been validated on a physical robot.

## Start Here

- [Example output](probes/ot2_motion/examples/reference-result.json): a complete,
  freshly generated run, including coordinates, geometry results, and versions.
- [Code and setup](probes/ot2_motion/README.md): supported behavior, dependencies,
  and reproduction instructions.
- [Build specification](docs/reports/2026-09-26-ot2-motion-build-spec.md):
  implementation steps toward an interactive instrument model.
- [Initial results](docs/reports/2026-09-24-ot2-motion-phase0-results.md):
  reference-software checks and current limitations.

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

## Run It

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
- [collision.py](api_gym/instrument_models/geometry/collision.py) checks swept
  boxes and spheres using FCL.
- [__main__.py](probes/ot2_motion/__main__.py) combines those two parts and writes
  the result.
- [Tests](tests/instrument_models) cover reference movements, geometry,
  reproducibility, and source integrity.
- [Sources](probes/ot2_motion/sources) pin software and CAD references.

## What Comes Next

The next implementation adds component-resolved geometry, separate configured
and physical labware positions, and an interactive command interface. This will
allow testing new movement sequences rather than only the five reference cases.

A researcher view and agent practice come after those pieces are connected.
Physical comparisons require an instrument owner and independently checked
geometry. Forces, tip bending, liquid delivery, and biological outcomes are
outside the current model.

The [build specification](docs/reports/2026-09-26-ot2-motion-build-spec.md) gives
the acceptance tests and sequence for each stage.

---

This branch is part of [Datalox API Gym](https://github.com/Oshawott324/datalox-api-gym/tree/main).
It focuses on OT-2 movement modeling. It is an independent project, not an
official Opentrons simulator release.
