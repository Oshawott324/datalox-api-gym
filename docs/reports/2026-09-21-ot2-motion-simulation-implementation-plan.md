# OT-2 Movement Simulation: Implementation and Validation Plan

Date: 2026-09-21

Status (2026-09-24): Phase 0 feasibility implemented and tested; Phase 1 asset
inventory started. Milestones A and B remain incomplete.

First deliverable: a bounded offline movement model, not a complete physical simulator

### Implementation Progress

| Phase | Current evidence | Status |
| --- | --- | --- |
| 0. Dependency and motion feasibility | Official 9.1.1 intermediate movements extracted; independent swept-geometry checks; 31 tests pass on macOS arm64 and network-disabled Linux arm64 | Complete within declared primitive/probe scope |
| 1. One sourced geometric setup | STEP/STL/DXF acquired and digest-pinned; STL inspected and found non-watertight | In progress; no instrument scene admitted |
| 2. Observation boundary | No new world or agent interface added | Pending |
| 3. Interactive motion transition model | Five fixed reference commands exercised by authoring probe | Pending; probe is not a runtime adapter |
| 4. Instrument path checks | Shared box/sphere sweep kernel tested; full instrument bodies, uncertainty and scene checks absent | Pending beyond primitive feasibility |
| 5-7. World/viewer, agent evaluation, physical validation | Not started under this plan | Pending |

Run instructions: [OT-2 motion probe](../../probes/ot2_motion/README.md).
Evidence and next admission gate:
[2026-09-24 Phase 0 results](2026-09-24-ot2-motion-phase0-results.md).

## 1. What We Are Building

An agent prepares or executes a movement through a supported Opentrons interface.
Our offline environment runs the corresponding software behavior, calculates the
movement against a specified deck setup, and records whether the modeled moving
parts intersect an obstacle or exceed the modeled travel limits. The agent sees
only the configuration, instrument responses, and human observations available
through its declared interface.

The first question is:

> Given this robot configuration and these modeled objects, what happens along
> this movement, and does the agent have enough information to proceed?

The later research question is:

> Does practice in this environment improve behavior on an independently checked
> real setup, beyond documentation, skills, and ordinary preflight checks?

We can start the first deliverable using public sources. The second requires an
instrument owner, permission, a measurement plan, and supervised validation. The
Rednote operator's reply is not a prerequisite for offline implementation. His
reported incident remains an unverified case until supporting records arrive.

### Two Separate Milestones

| Milestone | Required evidence | Permitted claim |
| --- | --- | --- |
| A. Offline geometry and software behavior | Pinned source assets; reference-software comparisons; independently checked geometric tests; observation isolation | A resettable, source-backed model of the declared movement scope |
| B. Paired instrument validation | An owner-approved setup; measured geometry/configuration; supervised reference observations; held-out agent evaluation | Agreement and transfer results for the specific tested setup and behaviors |

Passing A does not establish B. Finding a CAD file does not establish either.

## 2. Starting Point and Verified Gaps

The instrument-rich implementation was inspected in the
`datalox-api-gym-integrate-zheng` checkout on branch
`codex/integrate-zheng-lablongrun`, commit
`bb10f505d49b6d9c359c1f346c30bb85b3203cda`. The current planning checkout is
`datalox-api-gym`, branch `codex/lablongrun-phase2`; it contains older code and
unrelated local edits. Preserve both. Before implementation, compare the intended
target branch with the current remote and integrate necessary existing work;
do not copy an older world over the instrument-rich implementation.

Local checks on 2026-09-21 found:

| Existing capability | Verified limitation | Consequence |
| --- | --- | --- |
| PyLabRobot OT-2 backend and deck visualization | The installed `OpentronsOT2Simulator.move_pipette_head` stores the destination; it does not calculate the path or use its direct-movement options for collision checking | A successful animation cannot establish clearance |
| Incubator temperature, storage, shaking, and exposure bookkeeping | Eight-hour runs with and without conditioning produced identical OD600 values | Experimental outputs are not causally coupled to those operations |
| Thermocycler stages and completion checks | Temperatures jump to targets; amplification uses preset Ct values | Thermal and biological behavior are authored projections |
| Workcell inspection | Returns the whole science contract, including preset Ct values before a run | Evaluation information reaches the agent prematurely |
| Powder dispensing and weighing | Dispensing reveals exact delivered mass; delivery factors/noise repeat; seeds 1 and 99 gave identical inspection output | An agent can exploit information and regularity absent from the intended physical setup |
| Science workflow tests | All 13 tests passed despite the above probes | Passing present tests establishes local consistency, not instrument fidelity |

Relevant existing files in that checkout:

- `api_gym/worlds/pylabrobot_lab_v0/state_ot2.py`
- `api_gym/worlds/pylabrobot_lab_v0/services_ot2.py`
- `api_gym/worlds/pylabrobot_science_v0/tools.py`
- `api_gym/worlds/pylabrobot_science_v0/contracts.py`
- `api_gym/worlds/pylabrobot_science_v0/dynamics.py`
- `api_gym/worlds/pylabrobot_science_v0/operations/incubator_shaker.py`
- `tests/test_pylabrobot_science.py`

The runtime repo also contains an official virtual-server capture lane:
`envs/probed_opentrons_local_v0/evidence/README.md`. It identifies Opentrons
`9.1.1`, commit `ad074b80e267084f08065b6d559b791140dfa671`, and explicitly
excludes physical motion. That evidence README reports mismatches for all nine
recorded lifecycle comparison programs. Reuse acquisition machinery and source
provenance where applicable; neither the captures nor their operation counts
validate a movement model. Recheck current executable reports before reuse.

## 3. Initial Scope

### Included

- One OT-2 software version and one explicitly defined hardware configuration.
- One active single-channel pipette; account for other installed parts as
  obstacles when their geometry is supported, otherwise require them absent.
- One documented plate, one tip-rack configuration, and selected fixed obstacles.
- A static deck during each movement. Setup changes occur as explicit events
  between movements and invalidate affected derived geometry.
- Cartesian movements with fixed tool orientation, attached-tip and bare-nozzle
  cases, calibration transforms, documented travel limits, and path clearance.
- Agent inspection of declared configuration; explicit requests for available
  human observations; structured operation results; resettable offline episodes.
- Native tip-return/discard sequences only after their internal movement and
  contact phases have passed the same admission checks as other movements.

### Deferred

- Liquid-transfer accuracy, fluid dynamics, bubbles, evaporation, contamination,
  biological validity, and interpretation of real assay outcomes.
- Collision forces, tip bending, compliance, contact-based recovery, and motor
  damage. End a physical-model episode at first unmodeled contact rather than
  manufacture a post-collision state.
- Multi-channel pipettes, Flex, grippers, moving modules, and multiple robots.
- Vision, automatic labware recognition, arbitrary shell/SSH instrument control,
  a general robotics engine, and reinforcement-learning infrastructure.
- Public claims of safe hardware operation, unattended execution, or training
  benefit before the corresponding evidence exists.

The existing science demos stay available with their declared limitations.
Repair their information boundary before using them for new agent evaluations;
their biological dynamics are a separate workstream, not a dependency for this
OT-2 movement model.

## 4. Repository Ownership and Proposed Layout

Reuse existing contracts and engines. Most paths below remain proposed. The shared
geometry component and instrument-model tests now exist. Phase 0 authoring code is
under `probes/ot2_motion/`; its raw source inventory stays in that probe until
operation/response records meet the existing API-pack catalog requirements. No
generic runtime adapter or new session service was added.

| Responsibility | Owner |
| --- | --- |
| Source assets, instrument geometry/dynamics, observation rules, construction component | API Gym |
| Reference task families and hidden workflow verifier | API Gym reference world |
| Process isolation, session lifecycle, call-path adapters, capture, generic comparison/export | `datalox-gated-runtime` |
| Dataset manifests, held-out assignment, release packaging of evaluation rows | `datalox-rollout-collector` |
| Agent prompts, planning, memory/skills, retry policy, optimization and reward weighting | Downstream experiment harness / training team |

```text
datalox-api-gym/
  source_packs/apis/opentrons/<pinned-source-version>/
    ... existing source-pack layout and provenance conventions ...
  provider_api_packs/opentrons_ot2_motion_pack/v0/
    pack.json
  api_gym/instrument_models/
    geometry/
      frames.py                 # units, transforms, body poses
      collision.py              # small adapter to proven geometry engine
    opentrons_ot2_v0/
      assets.py                 # validated source-to-model conversion
      configuration.py          # versioned instrument setup
      motion.py                 # consumes reference-produced movement segments
      dynamics.py               # modeled state transitions
      observations.py           # explicit agent-visible projection
      checks.py                 # reusable instrument predicates
  api_gym/worlds/ot2_motion_v0/
    README.md
    spec.json
    source_refs.json
    state.py
    tasks.py
    verifier.py
  tests/instrument_models/
    test_geometry_frames.py
    test_geometry_collision.py
    test_ot2_motion_reference.py
    test_ot2_observations.py
    test_ot2_motion_world.py
```

Generic geometry code contains no Opentrons names, deck slots, task outcomes,
or assay rules. Instrument-specific transforms and allowed contact phases stay
in the OT-2 component. Extract only shared mathematics used by this implementation;
do not start a general instrument DSL or add speculative backends.

The runtime needs a narrow adapter at the actual selected call boundary. Extend
its existing SDK-adapter/capture patterns after inspecting them. Do not introduce
another session service, capture engine, benchmark runner, or generic state store
inside API Gym. Package through the established provider/world mechanisms when
their actual admission requirements are met.

## 5. Public Sources and Acquisition

### Geometry Sources

| Asset | Verified public location | Intended use | Remaining check |
| --- | --- | --- | --- |
| Detailed STEP | [OT-2 Reference Model Detailed.STEP](https://github.com/Opentrons/ot2/blob/master/reference-model/STEP/OT-2%20Reference%20Model%20Detailed.STEP) | Inspect solid geometry and component boundaries | Actual component coverage, units, hardware revision, reuse terms |
| Detailed STL | [OT-2 Reference Model Detailed.STL](https://github.com/Opentrons/ot2/blob/master/reference-model/STL/OT-2%20Reference%20Model%20Detailed.STL) | Mesh inspection and visualization | Mesh validity and suitability for each collision body |
| Deck drawing | [CNC_DECK_RevA2.DXF](https://github.com/Opentrons/ot2/blob/master/deck/CNC_DECK_RevA2.DXF) | Deck/slot dimensional cross-check | Revision and coordinate alignment |
| Labware definitions | [Labware Library](https://labware.opentrons.com/) and [schema](https://github.com/Opentrons/opentrons/blob/edge/shared-data/labware/schemas/2.json) | Named definitions, dimensions, well coordinates | Each selected definition's completeness and version |

The hardware repository tree checked on 2026-09-21 resolves to
`ef9ede131ed1d64daf9a0df5b2140a0a8e56b632`. Its reference-model directory's latest
commit is dated 2018-05-03; these are historical reference assets, not a guarantee
of correspondence to a currently installed pipette or robot revision.

For every retained asset record the origin URL, immutable revision, retrieval
time, byte digest, units, coordinate frame, license/distribution status, supported
components, and missing components using existing source-pack provenance fields
where available. Record derived-mesh conversion settings and source hashes.
Fetching a public file is not permission to redistribute an entire derived pack.

Outer dimensions and well coordinates do not necessarily describe wall
thickness, tube taper, tip shape, or a trash rim. Keep those omissions visible.
Obtain missing dimensions from manufacturer drawings or authorized measurements.
Self-authored geometry can test the engine but remains labeled self-authored.

### Software Sources

- [Opentrons movement semantics](https://docs.opentrons.com/python-api/robot-position/).
- [OT-2 labware offsets](https://docs.opentrons.com/ot-2/calibration/labware-offsets/).
- [Official simulation API](https://docs.opentrons.com/python-api/reference/execute-simulate/).
- The exact Opentrons source commit and package dependencies selected in Phase 0.

Current documentation is discovery material. Reconcile its behavior with the
pinned software version. Use `9.1.1` as the first candidate because an existing
virtual-server receipt identifies it; do not assume it matches a future partner's
instrument. A different hardware/software version is a separate evaluated cohort.

## 6. State and Information Boundaries

The same saved number must not represent both the controller's belief and
physical reality. Otherwise, changing a calibration can accidentally move both
the commanded trajectory and the virtual plate, hiding the very mismatch we
want to study.

| Information | Example | Access |
| --- | --- | --- |
| Task requirements | Intended destination, permitted operations, completion criteria | Agent from the start |
| Declared configuration | Loaded labware definition, exported calibration, configured pipette | Agent through the chosen interface or supplied setup files |
| Controller-reported state | Last reported position, acknowledged command, reported tip state | Agent when the real interface supplies it |
| Human observation | Operator confirmed this rack's identity and seating at a recorded time | Agent after that observation is supplied |
| Simulated physical truth | Actual modeled placement, body shape, hidden calibration discrepancy, contact | Dynamics and trusted evaluator |
| Evaluation expectations | Family label, known hazard location, oracle plan, held-out assignment | Trusted evaluation only |

Represent the following separately in provider-native state or a narrow
instrument configuration object:

- Software/API version, robot revision, pipette model/mount, labware definition
  IDs and hashes, configured slots, and exported calibration records.
- Named coordinate frames and source-derived transformations. Use explicit
  millimeter/second conventions; do not invent the calibration composition order.
- Controller-reported pose versus simulated physical body poses.
- Attached tip geometry and reported attachment status. Real successful seating
  is not inferred from a software flag unless the claim is explicitly nominal.
- Operation identity, accepted/started/completed/failed/unknown status, and logical
  ordering. Unsupported physical effects remain unmodeled.
- Observation source, timestamp, setup revision, and evidence reference.

The trusted episode controller owns reset, fault placement, hidden physical
configuration, and simulation time. The agent can perform ordinary supported
wait/poll operations; it cannot select its own hidden scenario or fast-forward
through an unexposed control endpoint.

An internal result should distinguish:

```text
reference_software_result: native response/error, or unavailable
geometry_result: clear_within_scope | intersection | indeterminate | unsupported
coverage: bodies, path segments, geometry revisions, uncertainty assumptions
evidence: source references and computed witnesses
```

These are internal concepts, not a new public provider response schema. Preserve
native responses on the agent's instrument interface. A separately evaluated
preflight tool may expose a prediction, but only from information also available
at deployment and with the same tool available to comparison agents.

## 7. Implementation Phases

### Phase 0: Freeze Scope and Test the Dependencies

1. Inspect the implementation branch, remote changes, dependencies, existing
   source packs, runtime adapter, and evidence policy. Record the target commit.
2. Select one active pipette, specific labware definitions, fixed tool orientation,
   and a small set of movement operations. Record exclusions before coding.
3. Bring up the pinned official software in an isolated, device-free process.
   Use no robot credentials, device mounts, or route to a physical instrument.
4. Identify a stable interception point that exposes ordered physical movement
   segments from the pinned software, not just high-level run-log descriptions.
5. Run a collision-library feasibility spike on required body/motion types.
   Preferred engine: [FCL](https://github.com/flexible-collision-library/fcl) through
   [python-fcl](https://github.com/BerkeleyAutomation/python-fcl). It provides
   collision, distance, and continuous-collision queries; verify the exact
   primitive/mesh combinations and solver options instead of assuming universal
   support. Test a thin obstacle crossed between two clear endpoints.
6. Pin a reproducible Linux test environment. Check the development host separately;
   native installation differences must not silently select a weaker algorithm.

Deliverable: scope/source manifest and a short feasibility report.

Exit gate: reference motion segments are obtainable for the chosen commands;
units and frames are understood; the chosen engine catches the analytical crossing
case. If segment extraction or supported collision queries fail, stop and revise
the design before building a viewer or generating tasks.

### Phase 1: Import and Validate One Geometric Setup

1. Acquire and pin the public assets; inventory which required bodies they cover.
2. Use existing mesh tooling such as [Trimesh](https://trimesh.org/) for inspection
   and conversions it supports. Use an established STEP/BRep importer for any
   required solid conversion; keep it in offline asset preparation. Do not write
   a STEP parser or require CAD conversion for every episode.
3. Validate finite coordinates, positive dimensions, explicit units, transforms,
   component identities, and the geometric properties required by the solver.
   Surface-shell and solid-containment semantics must be tested separately.
4. Cross-check selected deck positions/dimensions against the DXF and pinned
   software definitions. Resolve disagreement; do not rescale until it looks right.
5. Construct open wells as open geometry, not solid plate-sized boxes. Collision
   geometry must preserve the cavities relevant to the chosen movement.
6. Distinguish display meshes from collision meshes. Store the bounded conversion
   error. A simplified enclosing shape may establish clearance when disjoint;
   its overlap establishes only possible contact, not a measured collision.

Deliverable: one versioned scene with an asset-coverage report.

Exit gate: all bodies needed for each admitted query have sourced geometry or
declared, justified bounds. Missing critical geometry yields `indeterminate`.
An authored fixture can pass mathematical tests but cannot promote that setup to
instrument-grounded status.

### Phase 2: Enforce the Observation Boundary

1. Add explicit serializers for task information, reported state, observations,
   and trusted evaluator state. Use field allowlists, not secret-name filtering.
2. Add regression tests for the existing science-world leakage: preset Ct values
   remain hidden before acquisition; exact powder mass is exposed only by a
   documented measurement surface, not automatically by simulated dispensing.
3. For the OT-2 world, separate declared offsets from hidden actual placement.
   Keep both accessible to the evaluator, only the declared record to the agent.
4. Add an operator-observation channel with a concrete scope, setup revision,
   and timestamp. A human saying the rack is seated is not proof of liquid volume.
5. Mount only agent-visible files in the rollout environment. Deny access to state
   databases, source fixtures containing hidden values, evaluator outputs, and
   trusted visualization payloads; test filesystem access as well as tool output.

Deliverable: observation projection plus causal visibility tests.

Exit gate: two episodes with different hidden placements but identical supplied
evidence produce identical agent observations until a supported measurement or
operator observation distinguishes them. Hidden setup cannot be read through a
debug endpoint, viewer token, file, log, or error detail.

### Phase 3: Produce and Execute Realistic Movement Segments

1. Run supported commands through the pinned official virtual software. Extract
   ordered movement segments at the selected non-hardware boundary. Preserve
   command IDs and links from each segment to its originating command.
2. Carry through actual path options, mount selection, tip/nozzle reference point,
   calibration transforms, and source-defined travel limits. Do not derive motion
   from the animation or force every action into an assumed three-segment path.
3. Start with explicit positioning from a supplied initial pose and a known
   pre-mounted-tip state. Add home, pickup, return, and discard only when their
   complete internal motions and state transitions can be represented.
4. Model intended tip-rack engagement using source-backed, phase-specific contact
   allowances. Never suppress all collisions with the destination rack or target
   labware. Unknown contact mechanics limit that operation's claim.
5. Run the same supported code/interface against the reference software and the
   candidate. Compare observable results and ordered segment values with declared
   numeric precision; keep geometry predictions as a separate comparison axis.
6. Support branching within the admitted action surface. New input values must
   produce new derived trajectories; this is an executable environment, not lookup
   of a previously recorded path.

Deliverable: operation-to-segment adapter, motion transition model, and reference
comparison cases. Generic adapter plumbing belongs in the runtime repo.

Exit gate: every admitted operation has normal, invalid, boundary, repeated-call,
and reset cases where those concepts apply. Unsupported calls return explicit
unsupported outcomes at the evaluation boundary; never silently fall through to
hardware or substitute a different action.

### Phase 4: Check the Entire Path and Preserve Uncertainty

1. Check the swept moving geometry over every segment, including the attached tip
   and relevant pipette bodies. Check path intersections, not only endpoints.
2. Use proven continuous/swept collision algorithms for admitted combinations.
   Fixed-interval position sampling is not a substitute: it can miss thin objects.
3. Use an immutable static-geometry acceleration structure and swept bounds for
   candidate selection; verify candidate selection cannot discard a true contact.
   Cache geometry by content hash, and invalidate pose/calibration-dependent data
   on the corresponding setup revision.
4. Handle both surface intersection and solid containment; a body starting inside
   another body must not be labeled clear because no surface crossing was found.
5. Separate numeric tolerance, asset-conversion error, and physical measurement
   uncertainty. Define each before evaluation. Use justified bounds for a
   conservative clearance result; when such bounds are unavailable or overlap,
   return `indeterminate` rather than a false certainty.
6. Record the intersected bodies, segment, and contact witness where supported.
   If computing minimum clearance, use a solver with a valid whole-path bound;
   endpoint distances are not the minimum clearance along a trajectory.
7. Match the real observation boundary. The OT-2 lacks well-bottom contact sensing
   according to its documentation. A hidden collision must not manufacture a
   vendor collision alarm. Stop the simulation experiment at an unmodeled contact
   as a trusted evaluator termination, not as an invented native error response.

Deliverable: reusable geometry predicates, independent numerical tests, and
per-query scope/uncertainty reporting.

Exit gate: all analytic clear/intersection/containment cases pass; ambiguous
coverage remains indeterminate; no numerical failure is converted to clear.

### Phase 5: Package a Small Interactive World and Viewer

1. Compose the model into `ot2_motion_v0` using the existing runtime session,
   isolation, call-routing, evidence, and reset mechanisms.
2. Expose the supported native SDK/API path selected in Phase 0. If an MCP client
   is used, place a thin adapter over the same behavior and state. Compare its
   mapping with the SDK before claiming cross-interface equivalence.
3. Preserve the same public call contract for later supervised comparison. A
   future physical authoring runner is separately permissioned; there is no
   agent-selectable live/sim switch or live address inside a dry-run lease.
4. Extend the existing visualization format and service. Draw the actual calculated
   segments, configured offsets, modeled obstacles, and check results. Show which
   geometry is unavailable. Animation timing never drives authoritative state.
5. Keep the evaluator's full scene and contact overlays outside agent access.
   An agent-facing view, if introduced later, must have its own observable-only
   projection and equivalent real-world input.
6. Provide one local launch procedure, one example agent connection, reset, and an
   exported result with version/source references. Do not publish partner records.

Deliverable: a clickable local demo plus an executable downstream-agent example.

Exit gate: viewer and model agree on the movement; two sessions cannot affect each
other; repeated reset matches a fresh instance; offline execution has no provider
egress. Clean-checkout reproduction requires no developer-specific absolute paths.

### Phase 6: Evaluate Agent Behavior Offline

1. Start with 6-8 hand-reviewed case families from the matrix below. Generate
   variants through geometry, configuration, and information availability, not
   by adding a bespoke verifier branch for each named case.
2. Give the agent an objective and legitimate constraints, not the fault label,
   exact repair sequence, future observations, or expected final answer.
3. Admit cases using independent geometric expectations and both positive and
   negative controls. An oracle plan passing the same implementation is necessary
   but insufficient evidence of correctness.
4. Establish a scripted reference policy and agent baseline before adding practice.
   Compare three controlled conditions: documentation/checks; matched-budget
   documentation plus curated skills; the same setup plus simulation practice and
   resulting skills. Keep the model, available observations, tools, approvals,
   preflight access, and evaluation budget fixed.
5. Treat generated skill documents as an experimental agent-side intervention.
   Freeze and inspect them before held-out evaluation. No hidden state, fixture
   values, test IDs, or held-out outputs may enter the skills.
6. Run a small development smoke test before scaling. An initial feasibility target
   is 24 configurations across the admitted families and 3 runs per condition;
   this is an engineering budget, not a statistically powered transfer study.
   Predeclare split membership outside API Gym before using any held-out cases.
7. Reserve unseen layouts/definition variants and combinations of hazards where
   feasible. Randomizing a seed for the same fixed case is not meaningful holdout.

Report task completion, predicted hazardous moves, correct requests for missing
information, unnecessary stops, tool calls, runtime, and model cost separately.
Report denominators, variation, and disagreements; a policy that refuses everything
must not appear successful. Statistical design for a paper follows pilot variance
and the actual number of independent layouts/instruments.

Deliverable: an offline comparison with frozen inputs, explicit limits, and no
claim of weight training unless the downstream team actually performs it.

### Phase 7: Validate on an Owner-Approved Instrument

1. Confirm the operator, instrument/software identity, permitted records, data
   rights, exact action scope, budget, supervision, and stopping procedure.
2. Obtain existing ordinary-run logs and configuration first. The minimum record is
   one script or command sequence, model/version, labware definitions, calibration
   export when available, and an operator description of what was actually set up.
3. Compare declared geometry to measurements or manufacturer drawings. Record
   disagreement and uncertainty instead of adjusting expected values to make a fit.
4. Use supervised, non-contact reference movements approved by the instrument owner
   to compare modeled targets/path behavior with observed behavior. A commanded
   position is controller evidence, not an independent measurement of actual pose.
5. Keep intentionally dangerous commands offline. Geometric measurements and
   historical records can support a collision prediction without causing another
   collision. Operator intervention is recorded as an outcome, not hidden.
6. Reconstruct the collaborator's historical failure only if enough records arrive.
   Keep multiple plausible causes open until the evidence distinguishes them.
7. Freeze the model, then evaluate on fresh approved configurations. A case used to
   repair the model becomes a development/regression case. Report any absence of
   independent held-out physical cases explicitly.

Deliverable: paired setup/command/observation records and a discrepancy report.
Claim transfer only for the tested scope; agreement on commanded coordinates alone
does not establish physical pose accuracy, collision safety, or liquid delivery.

## 8. Initial Case and Test Matrix

These are proposed engineering cases, not observed incidents or biological tasks.
Admit each only when its required geometry and software behavior are covered.

| Family | Controlled difference | Expected check | Agent-visible evidence |
| --- | --- | --- | --- |
| Ordinary clear movement | A known path with measured or sourced clearance | Clear within declared scope; objective completed | Declared configuration and normal responses |
| Calibration-sensitive reachability | Change only the controller calibration record | Native rejection or a changed valid path, depending on actual reference behavior | The calibration record when supplied/read |
| Direct versus raised traversal | Two supported path options around the same obstacle | Different swept intersections when geometry warrants | Documented options and supplied setup |
| Attached tip versus nozzle | Same intended reference position with different tool body geometry | Correct tool-reference conversion and contact result | Reported attachment and configured tip type |
| Declared versus physical placement | Same controller record, independently varied actual placement | Evaluator sees different physical prediction; agent is initially unable to distinguish | A later authorized observation, or explicit missing information |
| Setup changed after inspection | Move a modeled object between operations | Old clearance/observation invalidated | Only the notice or inspection the experiment legitimately supplies |
| Tip return versus discard | Different destinations and full native command sequences | Target/sequence semantics and phase-specific contact allowances | User objective and actual supported command documentation |
| Incomplete geometry | Remove a critical sourced dimension | Indeterminate/unsupported, never clear | The same coverage limitation a deployment-time checker would know |

Required controls and properties:

- Oracle success, empty-plan failure, known-bad movement, and correct expected
  failure attribution for each admitted family. Legitimate alternative paths pass.
- Analytical line/swept-body intersection, thin-obstacle crossing, grazing contact,
  starting overlap, cavity traversal, containment, and end-of-segment contact.
- Transform identity/inverse/composition; a common rigid frame transformation leaves
  geometric relationships unchanged. Robot travel limits transform consistently.
- Segment subdivision leaves the swept-contact verdict unchanged within the declared
  tolerance. Changing display resolution does not change the physical verdict.
- Ignoring tip length, reversing an offset sign, dropping an obstacle, checking only
  endpoints, or leaking hidden placement is detected by a targeted test.
- Equivalent visible histories cannot reveal different hidden truth without an
  observation. Add process/filesystem access tests, not only serializer unit tests.
- Reset after accepted, rejected, interrupted, and terminal-contact cases restores
  the nominal reset state. No mounted tip, pending command, or cached pose persists.

Verifier scaling: compute instrument predicates from model state and ordered events,
then compose task-specific completion constraints. Return a vector of outcomes;
reward shaping belongs to the consumer. Independently validate the shared geometry
kernel because running the same mistaken calculation in model and verifier would
only establish agreement with ourselves.

## 9. Performance and Reproducibility

- Parse/convert geometry once per asset digest, not once per action or verification.
- Cache immutable static acceleration structures; store per-session transforms and
  attached-tool state separately. A session never mutates another session's cache.
- Check changed moving bodies against candidate static obstacles. Verify that the
  broadphase covers the full swept region, not only the final pose.
- Reuse emitted transition/check evidence for incremental verification and perform
  a final integrity/state check. Avoid re-running an entire protocol for each step.
- Benchmark geometry time, reference-software time, observation serialization,
  verifier time, and viewer time separately, with p50/p95 and machine details.
- Provisional target: p95 geometry checking below 100 ms per admitted short movement
  on the recorded reference machine. Measure before treating it as achievable;
  never weaken collision coverage or precision to hit it.
- Identical setup, action sequence, versions, and controller seed reproduce state
  and results. Authored uncertainty sweeps remain sensitivity experiments, not
  measured physical error distributions. Fit stochastic distributions only when
  enough repeated physical measurements justify them.

## 10. Access and Collaboration Work in Parallel

The immediate request is access to one understandable setup, not a large dataset
or a commitment to build our simulator.

| Route | First request | What it enables |
| --- | --- | --- |
| Existing Rednote operator | One follow-up for an existing script and retained configuration/error exports; no reenactment | Assess whether his specific failure can be reconstructed |
| Another current OT-2 operator through the team's network | Review one proposed setup and share an ordinary run/configuration if permitted | An independent validation route |
| Opentrons hardware team | Identify the needed revision and ask for missing pipette/tip/trash geometry and permitted use | Close named geometry omissions |

The official hardware README publishes `info@opentrons.com` for missing hardware
files. Contact only after the asset audit can name the missing components.

Our contribution: build the model, prepare reference-software tests, organize the
comparison, and return a useful discrepancy report. The operator confirms what is
known about their setup and decides which supervised checks are appropriate.
Research questions, interpretation, and any release can be agreed together as the
collaboration develops. No promised physical result depends on an unanswered email.

If instrument access remains unavailable after milestone A, publish or demonstrate
only the supported offline scope and prioritize access. Do not expand to many
instrument types as a substitute for physical validation.

## 11. Work Packages and Stop/Go Decisions

Progress below reflects the 2026-09-24 feasibility increment. Estimates are planning
ranges for a focused engineering effort, not dates or commitments from an instrument owner.

| ID | Work package | Depends on | Approximate effort | Done when |
| --- | --- | --- | --- | --- |
| P0 | Scope/version and motion/geometry feasibility spike | None | 1-2 days | Real segments obtainable; analytical collision spike passes |
| P1 | One sourced, validated scene | P0 | 2-4 days | Required geometry covered or explicitly indeterminate |
| P2 | Observation isolation and existing leakage regressions | None; align with P0 | 1-3 days | Hidden information inaccessible through all evaluated surfaces |
| P3 | Reference-backed motion adapter and transitions | P0, usable P1 scene | 3-5 days | Supported operations match reference software under named comparisons |
| P4 | Continuous path checks and independent tests | P1, P3 | 2-4 days | Required geometry cases, uncertainty, and failure attribution pass |
| P5 | Resettable world and existing viewer integration | P2-P4 | 2-3 days | Clean reproduction, isolation, and viewer/model agreement |
| P6 | Controlled agent feasibility study | P5 | 2-4 days plus model budget | Frozen comparison with held-out integrity and honest outcome metrics |
| P7 | Physical validation | Owner access and approved plan | External schedule | Independent paired records and discrepancy analysis |

Some tasks overlap. Reserve roughly 2-4 focused engineering weeks for milestone A
and the first offline study if source extraction and geometry are adequate. P0 can
invalidate this estimate; do not spend the full budget before that feasibility gate.

### First Execution Queue

- [x] Review branch differences and record the implementation base without changing unrelated work.
- [x] Pin source software and public CAD files; record unresolved component coverage and usage rights.
- [x] Extract one native movement sequence with actual intermediate segments.
- [x] Demonstrate whole-path detection of a thin obstacle crossing in an independent fixture.
- [ ] Add failing observation-leakage tests, then repair the affected observation projection.
- [ ] Build one nominal deck scene and its transform/cavity tests.
- [ ] Run a paired clear/intersecting offline movement without exposing hidden truth to the agent.
- [ ] Only then add the remaining admitted families, visualization, and agent study.

### Stop Conditions

- Missing critical geometry: continue on mathematical fixtures or obtain dimensions;
  keep the instrument-specific verdict indeterminate.
- Missing or ambiguous trajectory extraction: scope to supported explicit movements;
  do not infer a complete protocol path from a high-level log.
- Reference comparison mismatch: repair or narrow the supported operation before
  downstream evaluation; retain the mismatch evidence.
- Unknown physical write completion: stop physical authoring and reconcile only
  through the operator-approved procedure. Do not retry automatically.
- No physical access: milestone B remains pending, regardless of offline success.
- No benefit over the strong skills/checks baseline: report that result and reassess
  the value of simulation practice before expanding the simulator.

## 12. Completion Checklist

Milestone A is complete only when:

- [ ] The chosen software, geometry, setup scope, and omitted behaviors are pinned.
- [ ] Every supported motion has reference-software evidence and mathematical tests.
- [ ] Continuous checks cover relevant tool bodies, cavities, and intermediate paths.
- [ ] Declared configuration, physical truth, and observations remain separate.
- [ ] Agent access cannot expose hidden state or reach physical hardware.
- [ ] Reset, isolation, alternative valid solutions, and expected failure codes pass.
- [ ] An unfamiliar developer can run the model and example from documented inputs.
- [ ] The viewer reflects the model and labels geometry coverage honestly.

Milestone B additionally requires:

- [ ] Permission and data-use boundaries for the particular physical setup.
- [ ] Independently observed configuration/path evidence, with uncertainty recorded.
- [ ] A frozen model evaluated on fresh approved cases, or an explicit statement
      that the available cases are development-only.
- [ ] Agent comparisons with equal observation/tool access and reported interventions.
- [ ] Claims limited to the tested setup; no inferred general safety or biological validity.

The intended outcome is a model that can explain where its predictions come from,
identify what it cannot know, and support a fair test of whether offline experience
helps on real equipment. It is not a complete OT-2 digital twin at this stage.
