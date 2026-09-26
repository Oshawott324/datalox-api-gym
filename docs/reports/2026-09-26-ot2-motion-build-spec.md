# OT-2 Motion Environment: End-to-End Build Specification

Date: 2026-09-26

Status: implementation specification. Phase 0 exists; the stages below are planned.

This expands the [implementation plan](2026-09-21-ot2-motion-simulation-implementation-plan.md)
into code boundaries, algorithms, operation contracts, and acceptance tests. It
does not report the proposed capabilities as implemented.

## 1. The Finished System

An agent gets a movement task, the configured instrument and labware information,
and access to a small set of instrument operations. Each operation runs through
the pinned Opentrons virtual software. A separate model checks the entire path
against the modeled physical setup. The agent can inspect available information,
ask for a defined operator observation, change its plan, and act again.

The researcher can watch the scene, reset it, compare agents, and inspect why a
movement was clear, intersected an object, or could not be assessed. During
practice, the researcher can provide post-episode feedback to the agent. During
evaluation, hidden geometry and evaluation answers remain inaccessible.

Later, an instrument owner runs an approved subset of the same operations. We
compare software behavior, measured geometry, and agent decisions separately.

The first complete deliverable is **an interactive movement environment**, not
an assay simulator, a prerecorded animation, or evidence that an agent can
operate an unattended laboratory.

### What Already Exists

Commit `cad31ed6` contains:

- A pinned Opentrons 9.1.1 reference probe producing intermediate movement
  segments for five fixed commands.
- Exact translational swept-volume constructions for the supported box/sphere
  cases, with independent analytical tests.
- Linux isolation/build instructions and matching macOS/Linux probe results.
- Downloaded and digest-pinned STEP/STL/DXF source records. The downloaded STL
  is non-watertight and has not been admitted as solid collision geometry.

The recorded test result is 31 motion/source tests plus 19 existing source-pack
tests. This document adds no new implementation-test results.

Missing: a component-resolved scene, full moving-tool geometry, an interactive
native worker, a motion world, observation isolation, a motion viewer, agent
experiments, and physical validation.

## 2. One Action, End to End

```text
Agent requests move_to(well reference, movement options)
  -> runtime validates the supported operation and serializes it
  -> isolated worker resolves the reference to native Opentrons objects
  -> official virtual software executes the operation and emits ordered segments
  -> OT-2 model places each supported moving body along those segments
  -> shared geometry kernel checks each full swept volume against static material
  -> trusted controller records software results, geometry checks, and coverage
  -> agent receives the supported native result through the declared adapter
  -> researcher viewer and verifier consume separate trusted records
```

Changing an input must cause a new calculation. Stored traces are regression
fixtures, not the response generator.

For example, `force_direct=True` changes the native path; it is not merely an
animation preference. Opentrons documents the default raised traversal and the
risk of direct movement. The pinned source and probe determine the actual
segments used here. [Official movement documentation](https://docs.opentrons.com/python-api/robot-position/)

### What Happens on Contact

The existing probe captures the simulator's accepted movement. Initially, we
will check those segments immediately after the native command returns. If a
segment intersects modeled material:

1. Retain the native software outcome separately from the geometric finding.
2. Record the earliest intersecting segment in command order. Do not claim the
   exact first-contact point or time unless an admitted solver calculates it.
3. End the episode at the evaluator boundary and discard the worker.
4. Preserve the last fully clear modeled state. Mark the pose within the
   intersecting segment unresolved; do not use the simulator's final position
   as the physical post-collision position.

We do not generate a fictional Opentrons collision error or simulate a bent tip
continuing to move. The episode ending can reveal failure; it cannot become a
contact sensor that the agent repeatedly queries within that episode.

## 3. Repository and Process Boundaries

| Component | Owner | Implementation location |
| --- | --- | --- |
| Source import and admission | API Gym | `probes/ot2_motion/` and its source inventory |
| Transforms and collision mathematics | API Gym | `api_gym/instrument_models/geometry/` |
| OT-2 geometry, motions, observations | API Gym | `api_gym/instrument_models/opentrons_ot2_v0/` |
| Reference tasks and final outcome checks | API Gym | `api_gym/worlds/ot2_motion_v0/` |
| Worker process lifecycle, routing, capture/export | Gated Runtime | existing provider runtime and SDK-adapter packages |
| Split assignment and benchmark packaging | Rollout Collector | existing dataset/collection surfaces |
| Agent practice, skills, model calls, reward weighting | Consumer harness | outside the world and instrument model |

Proposed API Gym files:

```text
probes/ot2_motion/
  import_cad.py                  # one-time structured import and inspection
  compare_commands.py            # reference/candidate parity programs
  cad-requirements.in             # separate from the runtime dependencies
  cad-requirements.lock
api_gym/instrument_models/
  geometry/
    frames.py                    # rigid transforms, explicit mm units
    collision.py                 # existing primitives; admitted extensions
    solids.py                    # validated solid/mesh representations
  opentrons_ot2_v0/
    assets.py                    # source/derived digest and coverage validation
    configuration.py             # declared setup and separate physical setup
    motion.py                    # native segment to moving-body transforms
    dynamics.py                  # ordered instrument-model state transitions
    observations.py              # explicit visible-field projections
    checks.py                    # reusable path/coverage/observation checks
api_gym/worlds/ot2_motion_v0/
  README.md
  spec.json
  source_refs.json
  state.py
  tasks.py
  verifier.py
tests/instrument_models/
  test_ot2_cad_import.py
  test_geometry_frames.py
  test_geometry_solids.py
  test_ot2_configuration.py
  test_ot2_motion_reference.py    # extend existing tests
  test_ot2_observations.py
  test_ot2_motion_world.py
```

Names above are proposed. Follow the actual package contracts when adding them;
do not introduce a second world loader or copy session services into API Gym.
Promote source/API packs only when their real operation/evidence requirements
are satisfied. A CAD inventory alone does not meet those requirements.

The runtime currently has `WorldImplementationV1.initialize_episode`, `handle`,
`request_for_tool`, `verify`, and related methods. Its existing provider backend
closes the session but has no world-worker cleanup hook. A managed worker needs
an explicit opt-in lifecycle contract in that repository. The existing
Hamilton/PyLabRobot adapter and Opentrons HTTP lifecycle world are patterns to
inspect, not working OT-2 motion adapters.

## 4. Internal Data Contracts

These are trusted internal records, not claimed vendor JSON responses. Prefer
frozen typed Python records and strict JSON schemas at process boundaries.

| Record | Required contents | Access |
| --- | --- | --- |
| `AssetRecord` | source URL/revision/digest; component identity; source units; conversion settings; derived digest; rights; representation; coverage | Public metadata after review |
| `DeclaredSetup` | software version; pipette model/mount; labware IDs/definition digests/slots; configured offsets; reported tip state; setup revision | Agent projection |
| `PhysicalSetup` | modeled body geometry and poses; source or authored status; placement uncertainty; modeled actual tip; physical setup revision | Controller only |
| `OperatorObservation` | subject; observed property; value; method; timestamp; setup revision; evidence reference | Agent after delivery |
| `MotionSegment` | command ID; segment index; native frame and critical point; start/end coordinates; mount; configuration revision; native source version | Controller; selected reported information only if supported |
| `PathCheck` | checked segment/body pairs; outcome; coverage; solver/version; numeric tolerance; geometry/frame digests; uncertainty policy | Evaluator and researcher |
| `EpisodeOutcome` | goal completion; native failures; intersections; unresolved coverage; terminal reason; observation use; command count | Consumer after episode |

A command ID plus segment index identifies one movement. Session generation IDs
prevent delayed worker responses from a previous reset entering a new episode.

### Calibration Must Not Move the World Twice

For the first model, configured labware offsets affect the official software's
target calculation. The plate's modeled actual pose is an independent input.

```text
configured labware definition + slot + configured offset
  -> native commanded tip-reference path

source-backed object shape + actual modeled placement
  -> physical obstacle in the same deck frame

path + moving-tool shape vs physical obstacle
  -> geometric result
```

Native segments already include configured offsets. Never add them a second
time. Setting a software offset does not move the physical plate.

Initially assume nominal robot kinematics: the modeled tip reference follows
the reported native path. This supports studying labware placement/configuration
differences. Modeling pipette-axis calibration or actual encoder error requires
additional source-backed kinematics and evidence; an arbitrary XYZ perturbation
must not be advertised as that model.

## 5. Stage A: Convert CAD into Identified Components

### Implementation

1. Read the existing source inventory, verify file hashes, and open STEP using
   CadQuery/OCCT. Preserve assembly labels and component transforms. CadQuery
   documents STEP and assembly import and explicit unit conversion; test the
   selected release on our assets before pinning it. [CAD import/export](https://cadquery.readthedocs.io/en/stable/importexport.html)
2. Keep CAD conversion dependencies separate from the Opentrons environment.
   Conversion runs during authoring, not on every agent action.
3. Read DXF with `ezdxf`, including drawing units and block insertion transforms.
   Unitless data remains unresolved until another source establishes the units.
   [DXF units](https://ezdxf.readthedocs.io/en/stable/concepts/units.html)
4. Enumerate every solid/shell, bounding box, label, transform, and validity
   result. Produce a numbered component image and machine-readable inventory.
5. Map components to deck, fixed structures, moving tool, and selected labware
   using a reviewed mapping file tied to source digests. Do not infer identity
   from visual similarity or unstable array order.
6. Export separate display and collision artifacts. Retain the source solid and
   meshing settings. A rendering mesh is not automatically collision-admissible.
7. Record missing tool/tip/rack/trash dimensions explicitly. Obtain them from
   drawings or authorized measurements before admitting corresponding checks.

Generated local artifacts:

```text
runs/ot2-motion-assets/<source-digest>/
  inventory.json
  component-map.json
  coverage.json
  display.glb
  collision/<component-id>.<admitted-format>
  conversion.json
```

These remain local until redistribution rights and admission are resolved. The
converter must not silently heal holes, fuse separate parts, fill cavities, or
rescale until the model appears correct.

### Acceptance

- Synthetic STEP assemblies retain separate components and transforms.
- Unit conversion is checked against known dimensions, including a non-mm case.
- Open shells and missing units are rejected for solid queries.
- Repeated conversion preserves equivalent geometry and recorded settings.
- A report says exactly which required moving and static bodies are present.

**Output:** an inspectable component inventory. The current historical CAD may
not contain the selected pipette/tip geometry; the report must establish that,
not assume it.

## 6. Stage B: Put Software and Geometry in the Same Coordinates

### Implementation

`frames.py` supplies `RigidTransform`, composition, inverse, and point/shape
application. Validate finite values, orthonormal rotation, positive determinant,
and a valid homogeneous last row. Conversion to millimeters happens before rigid
alignment; scaling is not a calibration operation.

Use explicitly matched, non-collinear deck landmarks to solve a rigid alignment
between CAD and the software deck frame. Check additional landmarks that were
not used in fitting. Record correspondences, residuals, and a source-justified
acceptance tolerance. Resolve inconsistent geometry rather than fit away the
disagreement.

`configuration.py` constructs the declared and physical setups separately.
`motion.py` anchors the tool geometry to the **native critical point**. The
current probe's attached-tip path uses the tip end, not the carriage center.
Tool geometry is transformed relative to that point. A tip length alone does not
define its taper, radius, or the entire pipette body.

### Acceptance

- Identity, inverse, and composition tests pass.
- Applying one common rigid transform preserves geometric relationships.
- Native target changes match the existing offset probe.
- Changing the declared offset leaves the modeled physical plate unchanged.
- Changing physical placement leaves the native configured target unchanged.
- Nozzle and tip-end reference conversions have independent expected values.

**Output:** one correctly aligned scene, with explicit unsupported geometry.

## 7. Stage C: Extend the Kernel to Realistic Shapes

### Supported Motion and Algorithm

Keep tool orientation fixed within each segment. For a convex moving body with
vertices `V`, translated from `p0` to `p1`, its swept volume is:

```text
convex_hull((V + p0) union (V + p1))
```

This covers the entire continuous translation, not sampled positions. A sphere
produces a capsule. A tool represented as a validated union of convex pieces is
checked piece by piece. Do not replace an entire non-convex tool with its convex
hull and then call every overlap a real collision.

Represent static material using admitted solids or cavity-preserving closed
meshes. A well is empty space surrounded by material; a solid plate-sized box
would give the wrong answer for entry into a well.

For each sweep:

1. Compute its full enclosing bounds and select potentially overlapping static
   bodies. This broadphase must enclose every point in the sweep.
2. Run admitted FCL swept-solid/obstacle queries for those body combinations.
3. Check solid containment as well as surface contact. Surface-only mesh
   intersection misses a body wholly inside another body. If using boundary
   meshes, cover containment in both directions and all disconnected material
   components, including an obstacle enclosed by the sweep.
4. Return coverage, body IDs, and the intersecting segment. Include geometric
   witnesses only when the selected solver supplies valid ones.

The current box/sphere kernel is tested; convex/mesh combinations still require
their own admission tests. See [python-fcl](https://github.com/BerkeleyAutomation/python-fcl).
For mesh point containment, Trimesh requires watertight geometry; this is one
reason the downloaded STL cannot be used as an admitted solid today.
[Trimesh containment](https://trimesh.org/trimesh.html#trimesh.Trimesh.contains)

### Precision and Uncertainty

Maintain separate fields for numerical tolerance, meshing error, physical
measurement uncertainty, and scenario perturbations. A converter's requested
mesh tolerance is not automatically a proven physical error bound.

- Exact admitted model geometry: report clear or intersection **within that model**.
- Justified enclosing geometry: disjoint enclosing volumes establish clearance;
  overlap establishes possible contact and therefore an indeterminate verdict.
- Missing relevant geometry or unresolved error bounds: report indeterminate.
- Unmodeled motion types or numerical computation failure: report unsupported
  or computation error, with no successful-clear result.

Use authored parameter sweeps for initial robustness tests. Label them authored;
do not invent a Gaussian calibration-drift distribution. Later measurements can
support an empirical uncertainty model.

### Acceptance

Thin wall between clear endpoints; grazing and endpoint contact; initial
containment in both directions; tool entering a hollow well; tool crossing its
wall/bottom; disconnected obstacles; segment subdivision invariance; and tests
that deliberately remove a body or check endpoints only.

Maintain independent analytical fixtures and selected CAD-solid cross-checks.
The same erroneous kernel passing its own generated oracle is insufficient.

**Output:** whole-path checks for the admitted tool/scene, not bending or force
simulation. No learning model is needed for these geometric predicates.

## 8. Stage D: Replace the Fixed Probe with an Interactive Native Worker

### Initial Operation Surface

Start with a trusted, configured setup and a modeled pre-mounted tip. Setup
contact is outside the episode. The agent receives ordinary configuration
information, not unrestricted setup-authoring permissions.

| Operation | First implementation | Boundary |
| --- | --- | --- |
| Read loaded labware/pipette configuration | Serialize documented configured properties | Configured values are not physical measurements |
| `move_to` | Native well/point resolution and supported path options | Calls pinned official software |
| Inspect supplied calibration record | Read supplied versioned record | Does not discover unknown real calibration |
| Request operator observation | Explicit research-world operation | Returns only the declared observable property |
| Finish task | Research-world operation | Triggers final outcome checks, not a vendor command |
| Set labware offset | Separate, explicitly authorized setup-edit task | Changes software configuration only |
| Home, pick up, return, discard tips | Later operation admission | Requires all internal motion/contact phases |

Serialize a well reference as labware identity, well name, reference location
such as top/bottom, and offset. Construct native objects in the worker. Preserve
`force_direct` and `minimum_z_height` semantics. Do not accept executable Python,
pickle, arbitrary imports, hardware addresses, or file paths from the agent.

The first interface can be a clearly labeled MCP wrapper over these native
methods. It is not an official Opentrons HTTP API. Native return objects need a
documented serialization contract. Preserve meaningful results and errors; do
not invent instrument acknowledgments to fill a schema.

A transparent Python SDK facade is a subsequent adapter feature. It requires
explicit parity tests before claiming an unmodified arbitrary protocol can run
through this environment.

### Worker Lifecycle

The runtime owns one isolated native worker per active episode:

1. Create: establish generation ID and temporary configuration directory; start
   the device-free pinned simulator; load trusted setup.
2. Act: send a bounded typed message; allow one outstanding command; collect all
   ordered segments and the native outcome.
3. Reset: stop and clean up the native context/thread; discard mutable state;
   create a fresh worker and scene from the same specified starting conditions.
4. Close: release native context, thread, process, and temporary resources even
   after exceptions, timeouts, or agent disconnects.

Extend the runtime's world lifecycle with an explicit managed-worker capability.
Existing pure-state worlds keep their current contract. Resuming a persistent
motion session is unsupported until native simulator state restoration is
implemented and tested; reject it explicitly.

A crashed or timed-out native worker invalidates that episode. Automatically
retrying a command would erase uncertainty about whether movement occurred.
Native errors can occur after some segments: retain the observed prefix, not an
invented transactional rollback.

Reuse the current Linux isolation configuration: no device mounts, no provider
credentials, no external network in the simulator, read-only code/assets,
bounded writable temporary storage, non-root identity, and resource limits.
Agent ingress is mediated by the runtime outside that isolated process.

### Acceptance

Reference/candidate comparisons cover different targets, path options, offsets,
invalid arguments, boundary values, repeated calls, partial failure, and resets.
Test worker crash, timeout, stale-generation messages, close after exception,
and two simultaneous independent sessions. Deliberate live-host/device access
must fail.

**Output:** arbitrary supported input sequences within one episode, with no
re-execution of the full command history for each action.

## 9. Stage E: Enforce Observability and Compose the World

### Agent View

`observations.py` uses explicit field allowlists. The agent can receive declared
labware, configured offsets, reported tip state, documented software results,
and supplied observations. It cannot read actual hidden placement, geometric
contact answers, task-family names, oracle actions, or future observations.

An operator-observation request must have a specified information source. For
example, a rack-seating confirmation supplies that fact, not an exact six-axis
pose. A measured dimension includes method and uncertainty. In an offline
episode these observations are authored projections until grounded in real
records. Report their cost/count separately from autonomous actions.

Store observations with setup revisions. A later setup change makes affected
observations stale. Agents learn of changes only through the notification or
inspection channel defined for that experiment. Do not demand an impossible
distinction between observationally identical hidden states.

### World Construction

`state.py` composes the setup, ordered events, controller state, and terminal
status. `tasks.py` defines objectives and allowed configuration ranges.
`verifier.py` combines shared checks rather than branching on scenario names.

Start with four families after their geometry passes admission:

1. Reach a specified destination with ordinary clearance.
2. Choose a route when direct traversal intersects modeled material.
3. Reconcile a changed configured offset with the supplied setup evidence.
4. Request missing setup information or stop when the permitted evidence cannot
   establish the required condition.

Add tip/nozzle differences, changed setup after inspection, and incomplete
geometry as their observation and geometry contracts become available. Tip
return/discard stays deferred until operation admission, not merely until a
button can be drawn.

Example objective: move the mounted tip to the stated destination using the
supplied configuration and permitted checks. Put the destination and real
constraints in the prompt. Keep the hazardous route, hidden placement, and
expected repair sequence outside it. Accept alternative valid routes.

### Acceptance

- Identical visible inputs with different hidden placement give identical
  observations until a permitted observation distinguishes them.
- Tests attempt hidden-file reads, error/log disclosure, and direct access to
  researcher visualization endpoints, not just serializer inspection.
- Oracle, empty plan, hazardous plan, alternative valid plan, stale observation,
  and missing-geometry controls produce their specified outcomes.
- An unresolvable task allows an appropriate stop/request outcome; it is not
  mislabeled an agent failure for lacking an unavailable sensor.

**Output:** a resettable motion world with a defensible information boundary.

## 10. Stage F: Keep Verification Small and Incremental

Perform geometry checks once when each motion is evaluated. Record the exact
geometry digests, transforms, native segments, solver version, and check result
in the trusted event stream. Final verification consumes these checked events
and the final state. It does not repeat every mesh query after every tool call.

The shared checks are:

- Every executed modeled segment has a result and declared coverage.
- No required path check was bypassed or computed on a stale setup revision.
- The goal state was reached, or a task explicitly permitting deferral ended
  with the required evidence/request.
- The supplied observation supports the decision under its stated scope.
- A terminal contact, unsupported effect, or unknown worker state is not counted
  as successful physical completion.

Return separate outcome fields, not a hand-written scalar reward. Suggested
evaluation codes include `PATH_INTERSECTION`, `GEOMETRY_INDETERMINATE`,
`GOAL_NOT_REACHED`, `OBSERVATION_STALE`, and `WORKER_STATE_UNKNOWN`. These are
evaluation codes, not native Opentrons errors.

Cache immutable collision structures by geometry digest. Include pose/setup
revision, tool attachment, numerical policy, and solver version in any derived
query cache key. Never reuse a result merely because the command text matches.

Benchmark native software time, collision time, serialization time, and final
verification separately. Record p50/p95 and hardware. Retain the original
provisional 100 ms p95 geometry target as a target to measure, not a promised
latency or reason to reduce coverage.

An independent diagnostic audit can recompute stored checks. Production
verification remains incremental; correctness evidence comes from analytical
tests, source parity, and later physical comparisons, not duplicate execution
of the same formula.

## 11. Stage G: Build the Clickable Researcher View

The existing science export has a visualization schema and PyLabRobot renderer.
It does not establish support for CAD meshes, complete tool bodies, or path
overlays. Locate the actual viewer-service repository before editing its UI;
do not create another server in API Gym to bypass that ownership.

Extend the visualization contract with a versioned motion renderer. A Three.js
renderer can consume source-derived display meshes and the recorded transforms.
Keep render conversion, including millimeters-to-display units, explicit.

The researcher view contains:

- One scene with deck, admitted tool geometry, labware, and fixed obstacles.
- Step/play controls driven by the actual ordered movement segments.
- Configured location versus modeled actual placement, with a clear legend.
- Highlighted intersecting segment/body pair; unresolved coverage shown distinctly.
- A command panel showing input, native outcome, and separate modeled result.
- Reset and scenario selection routed to the trusted controller between episodes.

No interpolated contact force, broken-tip animation, or fabricated exact contact
time. The display can highlight an intersecting segment without pretending to
know the physical result after contact.

The full scene is researcher-only. Network and filesystem isolation must prevent
an agent with browser/shell tools from reaching it. A token in a URL is not
sufficient if the token or payload is available inside the rollout environment.

Acceptance includes desktop/mobile screenshots, nonblank canvas/mesh checks,
correct framing, action/step synchronization, and verification that changing
animation speed or mesh display detail cannot change outcomes.

**Output:** one local launch procedure, one agent connection example, reset, and
one exported run. Document the existing runtime commands once implemented;
this specification does not present nonexistent CLI flags as usable commands.

## 12. Stage H: Let Agents Practice and Test Whether It Helps

Use the consumer harness to run three conditions with the same model and final
evaluation tools/observations:

1. Documentation and the admitted action interface.
2. The same setup plus reviewed skill notes.
3. The same setup plus skill notes produced after simulation practice.

During practice, a terminal episode may expose a diagnosis: which modeled path
intersected what, what information was available, and the scope of the finding.
The next attempt starts a new episode. During held-out evaluation, that diagnosis
is withheld until scoring is finished.

A skill entry records the triggering condition, recommended action/check,
reason, evidence source, and applicability limits. It must not contain hidden
test values, task IDs, or a stored solution to an evaluation case. Generating
skills changes agent context; it is not model-weight training.

Freeze skills before testing on new layouts/configurations. Collector-owned
split assignment keeps practice and evaluation separated. Use the original
24-configuration, three-repeat budget only as an engineering pilot; repetitions
on one layout are not independent real-world evidence. Start smaller to debug
the harness using a low-cost capable model.

Report completion and hazardous proposed movements together, plus unnecessary
stops, correct requests for information, observation burden, unsupported cases,
tool count, time, and model cost. A policy that refuses every task cannot look
successful. Report practice cost separately from final evaluation cost.

**Output:** an executable comparison answering whether practice adds value over
documentation and curated notes within this model. It does not establish
physical transfer.

## 13. Stage I: Admit More Operations without Pretending Contact Is Solved

Extend one native operation at a time. Each admission record needs the native
call contract, emitted segments, moving bodies, contact phases, observable
results, state changes, and unsupported effects.

For tip pickup/return/discard, a blanket exception for the destination rack or
trash is incorrect. Separate travel through free space from intended mechanical
engagement. Admit only contact behavior supported by source/evidence. If the
model covers approach but not engagement, report partial coverage and stop at
that boundary; do not count the whole operation as physically verified.

Homing also needs its actual path and limit behavior. Successful virtual homing
alone does not establish that a physical robot can home through an obstructed
deck. Liquid operations require a separate delivery model; moving to a well is
not evidence that the requested liquid reached it.

Use the same algorithms and admission format for each addition. This grows
operation coverage without creating one verifier branch per failure story.

## 14. Stage J: Compare with a Real Instrument

We can implement Stages A-H using public sources and authored fixtures. Missing
source dimensions still limit geometry admission. Stage J needs an owner and
authorized evidence; simulation cannot manufacture that evidence.

### Ask for a Small, Specific Record

Instrument and pipette model; software/API version; labware definitions and
layout; available calibration export; one ordinary script/run log; and what the
operator can actually observe or measure. Ask which records already exist before
requesting a new experiment.

### Three Separate Comparisons

| Comparison | Evidence | What it establishes |
| --- | --- | --- |
| Software/path parity | Same supported commands/configuration and native logs | Agreement with controller behavior |
| Geometric agreement | Drawings/measurements and approved non-contact observations | Agreement for specific positions/clearances, with uncertainty |
| Agent transfer | Frozen agents/skills on fresh approved setups | Behavior under the tested real observations and supervision |

Commanded positions are not independent measurements. Cameras are optional if
the required comparison can be measured another way; real geometric accuracy
still requires real evidence.

The owner approves each physical action and stopping procedure. Dangerous
exploration stays offline. We do not reproduce collisions to prove a prediction.
If sensor coverage cannot establish the relevant outcome, label it unmeasured.

Compare predicted clear/intersection/indeterminate results with independently
established cases. Include false-clear and false-alarm findings; successful
commands alone are not a collision-validation dataset. Report any missing
independent cases explicitly.

Fix discrepancies using development cases, freeze the model again, and evaluate
fresh cases. A record used to calibrate the model cannot also establish its
held-out accuracy.

### Second Deployment

Install on a second approved setup after freezing the first package. Log time
spent on inventory, configuration, measurement, adapter changes, validation,
operator training, and maintenance. Distinguish a second layout on one machine
from a second instrument or laboratory. Record code changes versus configuration
changes and the fraction of checks/assets reused.

This is the route to measuring deployment reuse. It does not yet measure assay
success or cost per accepted biological measurement; those require an actual
assay and scientific acceptance criteria in a subsequent campaign.

## 15. Ordered Implementation Queue

Each row is a reviewable implementation increment, not a completion claim.
Advance only after its acceptance evidence is retained.

| Order | Change | Concrete exit artifact |
| --- | --- | --- |
| 1 | CAD importer, source mapping, dependency pin | Component inventory and missing-body report |
| 2 | Frames and split declared/physical configuration | Independently checked aligned scene |
| 3 | Admitted convex/solid collision queries | Whole-path and cavity/containment test report |
| 4 | Runtime worker lifecycle and native operation adapter | Interactive parity programs; reset/isolation tests |
| 5 | Observation projection, tasks, world integration | Valid/invalid/indeterminate world controls |
| 6 | Incremental checks and performance instrumentation | Stable outcome fields and measured latency breakdown |
| 7 | Motion renderer and launch documentation | Clickable agent-run demonstration with exported evidence |
| 8 | Consumer practice/skills comparison | Frozen offline comparison with holdout discipline |
| 9 | Additional operation admission | Per-operation coverage and parity records |
| 10 | Authorized paired validation and second setup | Discrepancy report and actual deployment-hour log |

Rows 1-3 can use authored fixtures to develop mathematics, but the published
instrument scene must retain its actual grounding/coverage status. Row 7 may
start its rendering skeleton earlier; its animation must consume real model
events before being shown as an executable demonstration. Row 9 is not a
prerequisite for a bounded movement comparison in row 10.

## 16. Decisions and Open Dependencies

Decided: pinned official motion software; separate geometric truth; continuous
whole-path checks; fixed-orientation first scope; isolated worker; explicit
unknowns; hidden evaluation state; context-based skills before any training
infrastructure; supervised physical comparison after offline admission.

Still to establish through implementation or access:

- Whether the STEP contains adequate separate components and correct revisions.
- Where the selected pipette/tip and labware wall geometry can be grounded.
- Which convex/mesh query combinations pass independent admission tests.
- The actual viewer-service owner and extension contract.
- An instrument owner, permitted measurements, and the cost of paired runs.

These are concrete dependencies. Their uncertainty should remain visible in
the progress report rather than being hidden behind a promised completion date.
