# OT-2 Motion Implementation

Date: 2026-09-27

## What Runs

The official Opentrons simulator now stays alive across supported movement
commands. The controller records the intermediate movements that the simulator
actually reports. The world checks those paths against supplied solids, records
the check evidence, and evaluates the resulting episode without repeating the
geometry queries.

The current example compares two fresh episodes with the same initial visible
setup. A direct movement intersects an authored wall; the native raised route
clears that wall and reaches the requested position. The collision body is a
0.5 mm radius sphere. Neither it nor the wall represents real instrument parts.

## Implementation Status

| Build stage | Current result | Remaining gate |
| --- | --- | --- |
| CAD inspection | Hash-verified STEP/DXF parsing, units, labeled component inventory, explicit coverage report | Exact hardware correspondence and collision admission |
| Coordinates and setup | Named rigid transforms; configured offsets and modeled physical placement are separate | Source-backed deck landmarks and measured alignment |
| Geometry | Whole-path translation checks for convex pieces and their unions; unsupported and missing geometry remain explicit | Admitted pipette, tip, labware, and trash solids |
| Native worker | Persistent simulator, typed commands, source checks, fresh-process reset, failure-prefix retention | Broader operation admission after geometry is grounded |
| World | Objectives, operator observations, hidden physical setup, terminal outcomes, and incremental verification | Real observation records and stronger physical tasks |
| Researcher viewer | Versioned motion renderer over recorded segments and declared geometry | No whole-instrument scene until its geometry is admitted |
| Agent interface | Five bounded tools on the existing MCP runtime; actual stdio client integration tested | Only engineering_control_02 is bundled; controlled model comparison remains |
| Offline packaging | Two-repository image with separate controller/native interpreters and source-content manifest | Publish matched source revisions before distributing a reproducible release |
| Physical comparison | No robot connected | Instrument owner, approved setup, measurements, and supervised runs |

## Meaning of a Result

- Native command success means the official software accepted/completed the
  simulated command. It does not establish physical clearance.
- A geometric intersection means the supplied material intersects a supported
  swept path. It is not a prediction of force, bending, or damage.
- Missing geometry or an overlapping enclosing representation cannot establish
  an exact physical collision result. Coverage accompanies each check.
- On a terminal intersection, the world retains the last clear pose and marks
  the subsequent physical pose unresolved. It does not invent a contact time.
- A successful task must reach its independently resolved goal. Alternative
  valid routes are accepted. A task permitting deferral still requires relevant,
  available evidence or a declared information/coverage limitation.

## Ownership

API Gym owns geometry, instrument configuration, observation projections, tasks,
and world verification. `datalox-gated-runtime` owns the managed native process,
session integration, MCP transport, and researcher visualization service.

The implementation is on the existing `opentrons-motion-simulation` branch.
Its matching runtime revision is
`883776fa3cb426c012f7aba25cf125c42e68b7f0` on
`codex/opentrons-motion-runtime`. Both checkouts are isolated from unrelated
local changes. The runtime revision must be supplied explicitly when building
the interactive image; committing it does not publish it to a remote.

## What This Does Not Establish

The source STEP contains 26 valid labeled solids, but their moving-part
correspondence and deck alignment remain unresolved. The chosen GEN2 pipette,
attached tip, selected rack, plates, and trash do not yet have admitted collision
geometry. See the [CAD inspection](2026-09-27-ot2-cad-inspection.md).

The authored controls test software and geometry integration. They are not a
biological benchmark, evidence of agent learning, or evidence of transfer to a
real robot. The worker isolation test runs with Docker networking disabled,
read-only code, no robot-device mounts, and an allowlisted source directory.
That test does not establish a separate security boundary for an agent with
filesystem, browser, or network tools. Keep the trusted world, verifier, and
researcher viewer outside the agent's filesystem and tool access.

Managed sessions have a single runtime owner. Reopening a used session cannot
silently reset its history. After shutdown, ordinary resumed verification and
finalization are unsupported; the trusted verifier snapshot already persisted
during execution remains available for inspection. An exception after possible
native motion invalidates the worker until a trusted reset. Database rollback
does not undo native movement.

## Run And Verify

Start with the [container instructions](../ot2-motion-container.md) for the
two-repository build, or the [agent interface instructions](../ot2-motion-agent-interface.md)
for trusted session preparation and an MCP connection. The native interpreter
is explicitly configured; the code ships no developer-specific path.

Parent verification on 2026-09-27:

- API Gym instrument suite: 94 passed, 2 skipped in the controller environment.
  The optional CAD-import checks were separately run in the pinned CAD environment.
- CAD-import suite: 6 passed.
- Selected runtime worker, lifecycle, world/provider, MCP, viewer, and wheel
  packaging regression tests: 162 passed. One upstream Starlette deprecation
  warning remains.
- Docker native-worker isolation orchestration: 1 passed; the host skips the
  inner-container-only assertion, which runs inside the launched container.
- Final interactive image: 30 tests passed, followed by the native direct/raised
  example, with networking disabled, a read-only filesystem, dropped
  capabilities, non-root execution, and no host mounts. Its embedded source
  manifest exactly matches the independently prepared final source context.
- Native example: direct route reports PATH_INTERSECTION, raised route reaches
  the independently resolved goal, and reset changes the worker generation
  while preserving the initial actor-visible observation.
- Researcher viewer: direct and raised documents generated from separate fresh
  official simulator workers. Desktop/mobile canvas, complete path framing,
  playback, and last-clear-pose assertions passed. Viewer timing is presentation
  timing, not measured instrument timing.

The suites overlap; these counts must not be added into a unique total.

Tested image ID:
`sha256:0e09e211e81f448ca5200b2fcff3906764ab9297dbb6b10020a1bda8e6f8157f`.
Selected source manifest SHA-256:
`c4dbc5d653fd4e6d6e34cfdffb97f39defca9f32da6601d1038a33a1b4098eef`.
The image is built locally; it has not been published to a registry.

## Next Physical Input

Identify one specific robot/pipette/labware configuration. Obtain geometry or
reviewed dimensions for the moving assembly and nearby material, plus landmarks
that connect those dimensions to the software deck frame. First compare native
command coordinates and harmless, supervised clear movements. Deliberate
collisions are not needed to begin validating the model.
