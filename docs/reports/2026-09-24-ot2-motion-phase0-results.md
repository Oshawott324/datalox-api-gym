# OT-2 Motion Phase 0: Implementation Results

Date: 2026-09-24

## Result

We can extract intermediate movements from official Opentrons software and check
the full path against mathematical solids. The five fixed reference commands and
the geometry tests run on macOS arm64 and network-disabled Linux arm64.

This completes Phase 0's dependency feasibility gate for the declared scope. It
does not complete milestone A: no sourced full instrument geometry, observation
projection, interactive world, or runtime adapter has been admitted. No robot was
connected and no agent training or physical transfer claim is supported.

## Repository State

- Implemented on `codex/lablongrun-phase2`, starting at `5fea065a`.
- Fetched `origin`; observed `origin/main` at `8873970c`.
- The separate instrument-demo checkout remained at `bb10f505d49b6d9c359c1f346c30bb85b3203cda`.
- Preserved existing local changes and the separate checkout; did not merge an
  older world over that implementation.
- New shared mathematics lives in `api_gym/instrument_models/geometry/`.
- Fixed reference instrumentation, dependency locks, and raw source inventory
  live in `probes/ot2_motion/`. Generic runtime work remains outside API Gym.

## Native Movement Evidence

Software: Opentrons and shared-data 9.1.1; Python protocol API 2.26. Hardware is
constructed explicitly with `API.build_hardware_simulator`. The tested setup is a
left P300 Single GEN2, model `p300_single_v2.1`, nominal tip length 51.1 mm, Corning
360 uL plates in slots 1 and 3, and a 300 uL tip rack in slot 5.

The hook observes `hardware_control.API.move_to`, calls the unchanged official
implementation, then reads its reported position. The coordinates describe the
native critical point relative to the deck in millimeters. In this mounted-tip
setup that point is the tip end, not the motor carriage. Calibration and position
are nominal software state, not physical measurements.

| Probe | Observed native behavior |
| --- | --- |
| Raised cross-plate movement | Three segments: Z 19.22 to 74.49, X 14.38 to 279.38 at that height, then Z back to 19.22; Y 74.24 throughout |
| Direct return across plates | One segment at Z 19.22 |
| `minimum_z_height=100` | Three segments, with the native planner selecting Z 110; the probe does not replace it with Z 100 |
| Labware offset `(1, -2, 0.5)` | The reported target shifts by exactly that vector within floating-point precision |
| Same-position request | Native zero-length segment retained |

Fresh subprocesses reproduce the reference record. Setup includes a simulated
tip pickup to establish native tip state; its contact phases are excluded from
the recorded movement claim. Homing, pickup, return/discard, travel-limit
enforcement, other mounts, and contact recovery still need separate admission.

The installed `hardware_control/api.py` digest matches the file retrieved from
official commit `ad074b80e267084f08065b6d559b791140dfa671`. Labware definitions
have canonical JSON hashes in each report. This checks the cited file and
definitions, not every file in the upstream source tree.

## Geometry Decision

The shared kernel admits fixed-orientation, axis-aligned boxes and spheres under
linear translation against static boxes/spheres. It constructs the complete swept
solid: a capsule for a sphere, or the convex hull of the two endpoint boxes. FCL
distance then classifies intersection/contact within a `1e-8 mm` numerical
tolerance. It uses neither stepwise position sampling nor scenario-name rules.

The first continuous-query configuration tried during the dependency spike did
not pass all box-crossing/contact controls. It was not admitted. The selected
swept-solid formulation uses the fixed-orientation translation scope explicitly;
arbitrary rotating or non-convex bodies require a different admission exercise.
There is one contact predicate, with invalid/nonfinite results raising an error.

Tests include a 0.01 mm obstacle between clear endpoints, head-on crossing,
containment, grazing and endpoint contact, a 0.000001 mm near-clear gap, stationary
movement, reversed traversal, and an open channel represented by separate walls.
Independent analytic controls cover 200 randomized box scenarios in both
directions and 100 sphere scenarios. These are numerical tests, not 300 real
instrument configurations or benchmark tasks.

The integrated native-path example uses an authored sphere of radius 0.5 mm and
an authored wall. The raised path clears that wall; the direct path intersects
it. This is evidence that the components can be connected. It is not evidence
that a real pipette clears a real rack. The kernel does not calculate first
contact time, force, bending, measurement uncertainty, or full-instrument safety.

## Asset Audit

All three files were downloaded from official hardware commit
`ef9ede131ed1d64daf9a0df5b2140a0a8e56b632`. Immutable URLs, byte counts, digests,
coverage, and unresolved distribution status are in
`probes/ot2_motion/sources/assets.jsonl`.

| Asset | Inspection | Admission |
| --- | --- | --- |
| Detailed STL | 2,108,684 bytes; 19,147 processed vertices; 42,172 faces; not watertight; not a volume | Not admitted as a collision solid |
| Detailed STEP | 3,943,530 bytes; millimeter unit declarations present in source; structured solid/component import pending | Not admitted |
| Deck DXF | 1,167,094 bytes; structured units and coordinate alignment pending | Not admitted |

STL bounds in its unaligned source coordinates are `[0, 0, 0]` to
`[624.2999878, 662, 567.4500122]`. We have not interpreted these as verified deck
coordinates. Trimesh standard vertex processing was used; no holes were filled,
parts rescaled, or unsupported missing components invented.

CAD binaries remain in ignored local storage. The inventory follows the existing
raw source-pack schema but is intentionally outside the API pack catalog. The
catalog requires operation/response evidence; no placeholder responses were
added just to satisfy that requirement.

## Verification

| Check | Result |
| --- | --- |
| Motion/geometry/source tests, macOS 15.5 arm64, Python 3.12.5 | 31 passed |
| Same tests, Linux arm64 container, Python 3.12.14 from pinned base | 31 passed |
| Existing `tests/test_source_packs.py` | 19 passed; existing assertions unchanged |
| Integrated feasibility report | Passed on both platforms |
| CAD digest verification | All three match pinned records |

The retained macOS and Linux reports have identical native movement records and
collision verdicts. Host metadata and measured timing differ as expected.

Container execution used `--network none`, a read-only root filesystem, no host
or device mounts, a temporary writable `/tmp`, UID 65534, dropped capabilities,
and process/memory limits. Build-time package downloads require network access;
test execution does not. The same locked algorithm runs on both tested hosts.
Other architectures, the entire repository test suite, and real hardware were
not tested in this increment.

Retained local outputs, excluded from version control:

- `runs/ot2-motion-phase0/2026-09-24-macos-final.json`
- `runs/ot2-motion-phase0/2026-09-24-linux-final.json`
- `runs/ot2-motion-assets/inspection.json`

Per-query timing in those reports is a nine-segment feasibility observation, not
the plan's p95 performance benchmark. Commands for independent reproduction are
in the [probe README](../../probes/ot2_motion/README.md).

## Next Implementation Gate

1. Import the pinned STEP through an established BRep tool and the DXF through a
   structured reader. Identify which solids correspond to the selected robot
   revision, fixed deck, and moving components; retain source identities.
2. Establish deck/software coordinate transforms from independent dimensions.
   Add unit, transform, and alignment checks before connecting imported geometry
   to the native paths.
3. Inventory missing P300 GEN2 body, tip taper/seating, well/rack cavity, and trash
   geometry. Use manufacturer drawings or authorized measurements; leave any
   whole-instrument prediction indeterminate when required coverage is absent.
4. Admit one geometric scene, then implement declared configuration versus hidden
   physical placement and the observation boundary before an agent can use it.

The existing science-demo leakage remains unfixed in this increment. It is still
a prerequisite for new agent evaluations that use those science worlds. No
viewer or larger task set is a substitute for the next geometry admission gate.
