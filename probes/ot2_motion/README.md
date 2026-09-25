# OT-2 Motion Feasibility Probe

Status: Phase 0 implemented. Phase 1 asset inventory started. No physical robot
has been connected, and no complete instrument scene has been admitted.

This probe runs five fixed movements through official Opentrons 9.1.1 software,
records the intermediate simulator movements, and checks those segments against
an authored geometric obstacle. It answers whether the software and geometry
dependencies can support the next implementation phase.

## Implemented Scope

- OT-2; API level 2.26; left P300 Single GEN2, model `p300_single_v2.1`.
- Corning 96-well 360 uL flat plates, definition v1, slots 1 and 3.
- Opentrons 300 uL tip rack, definition v1, slot 5; nominal tip length 51.1 mm.
- Native raised movement, direct movement, minimum-height option, labware-offset
  update, and a repeated same-position request.
- Fixed-orientation, axis-aligned solid boxes and spheres, translated along a
  closed straight segment. Meshes and rotating bodies are not admitted.

The native coordinates are in millimeters relative to the deck, at the native
critical point. With the attached tip in this setup that point is the tip end.
Calibration is the official simulator's nominal configuration, not a measured
robot setup. The native planner chooses intermediate coordinates; we do not
replace it with an assumed raise/traverse/lower policy.

`reference.py` instruments `hardware_control.API.move_to` and delegates every
movement to the unmodified simulator. `use_virtual_hardware=False` selects the
lower-level simulator path; hardware is explicitly created with
`build_hardware_simulator`, and both simulation flags are checked. This fixed
authoring probe is not a generic adapter, an agent action surface, or a live
hardware runner. Runtime adapter work remains in `datalox-gated-runtime`.

## Reproduce in Linux

From the repository root, with Docker available:

```bash
bash probes/ot2_motion/build_image.sh
docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --pids-limit 256 --memory 2g \
  --tmpfs /tmp:rw,nosuid,nodev,size=256m datalox-ot2-motion:phase0
```

The image uses a digest-pinned Python 3.12 base and hash-locked wheels. The build
needs network access for dependencies. Execution uses no network, host mounts,
robot credentials, device mounts, or Docker socket and runs as UID 65534. The
build script sends only the selected code, tests, and source inventory, excluding
other repo files and local captures. It works with legacy Docker and BuildKit.

Proxy-dependent builds can pass Docker's standard `--build-arg HTTP_PROXY=...`
and `--build-arg HTTPS_PROXY=...` options to the build script. The address must be
reachable from the Docker VM; do not put credentials in a Dockerfile.

## Reproduce on the Development Host

Use a dedicated Python 3.12 environment, not an existing application's environment:

```bash
python3.12 -m venv .venv-ot2-motion
.venv-ot2-motion/bin/python -m pip install --only-binary=:all: --require-hashes \
  -r probes/ot2_motion/requirements.lock
.venv-ot2-motion/bin/python -m pytest -q tests/instrument_models
.venv-ot2-motion/bin/python -m probes.ot2_motion \
  --out runs/ot2-motion-phase0/local.json
```

Output creation is exclusive: choose a new filename for each retained run. Native
instrumentation always starts in a fresh subprocess with a temporary Opentrons
configuration. The container command is the network-isolated execution path;
host execution alone is not a network sandbox.

## What the Geometry Check Means

A translated sphere sweeps a capsule. A translated convex box sweeps the convex
hull of its two endpoint bodies. We construct that full solid and query FCL
distance against the static obstacle. This avoids fixed-position sampling and
includes initial overlap, endpoint contact, and thin obstacles between endpoints.
It does not compute first contact time, forces, bending, or a calibrated physical
clearance. The `1e-8 mm` contact tolerance is numerical, not sensor accuracy or a
physical safety margin. Nonfinite or invalid solver results raise an error.

The integrated example uses a **0.5 mm radius sphere**, not a pipette or tip model,
and a **0.01 mm thick authored wall**, not sourced trash/rack geometry. It shows
that native raised and direct paths produce different intersections with that
fixture. It does not establish clearance for a real instrument.

The tests include analytic box/sphere expectations, containment, grazing,
endpoint contact, near-clear movement, an open channel, reversed traversal,
fresh-process reproducibility, and asset-digest rejection. Randomized checks use
independent analytic formulas rather than the same FCL query as their oracle.

## Sources and Geometry Admission

`sources/` retains raw provenance using the existing source-pack schema. It stays
outside the API pack catalog until operation/response evidence is ready; this
inventory is not a released provider behavior pack. It pins the official source
and three hardware asset URLs and digests. CAD binaries remain in ignored local
storage while distribution terms and hardware correspondence are reviewed.

To inspect acquired files, save them under the `local_filename` values in
`sources/assets.jsonl`, then run:

```bash
.venv-ot2-motion/bin/python -m probes.ot2_motion.inspect_assets \
  --directory runs/ot2-motion-assets \
  --out runs/ot2-motion-assets/inspection.json
```

The inspector verifies every byte digest before processing. The detailed STL has
42,172 faces and is not watertight. It is not admitted as a collision solid. STEP
solid import, DXF units, deck alignment, moving-body segmentation, and accurate
pipette/tip/labware cavities remain pending. No holes are silently filled and no
asset is rescaled to fit the software coordinates.

## Next Gate

Phase 1 must establish one source-backed geometric setup, including explicit
coordinate transforms and missing-component coverage. Until then, whole-instrument
collision predictions remain unavailable. Pickup/discard contact mechanics,
hidden physical placement, agent observations, scene visualization, and paired
physical validation have not been implemented in this increment.

See the [implementation plan](../../docs/reports/2026-09-21-ot2-motion-simulation-implementation-plan.md)
and [Phase 0 results](../../docs/reports/2026-09-24-ot2-motion-phase0-results.md).
