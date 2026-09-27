from __future__ import annotations

import json
from dataclasses import replace

import pytest

from api_gym.instrument_models.geometry.frames import RigidTransform
from api_gym.instrument_models.geometry.solids import (
    Box,
    ConvexPiece,
    PlacedSolid,
    RepresentationCoverage,
    SolidGeometry,
    Sphere,
)
from api_gym.instrument_models.opentrons_ot2_v0.configuration import (
    DeclaredLabware,
    DeclaredSetup,
    PhysicalComponent,
    PhysicalSetup,
)
from api_gym.instrument_models.opentrons_ot2_v0.dynamics import (
    NativeCompletion,
    NativeExecution,
)
from api_gym.instrument_models.opentrons_ot2_v0.motion import (
    AnchoredTool,
    NativeMotionSegment,
    critical_point_frame,
)
from api_gym.instrument_models.opentrons_ot2_v0.observations import (
    ObservationCatalog,
    ObservationScope,
    OperatorEvidence,
)
from api_gym.worlds.ot2_motion_v0.state import DeferralBasis, DeferralDecision
from api_gym.worlds.ot2_motion_v0.tasks import (
    TASKS_BY_ID,
    ResolvedGoal,
    native_binary64_goal_tolerance_mm,
)
from api_gym.worlds.ot2_motion_v0.verifier import verify_episode
from api_gym.worlds.ot2_motion_v0.world import MotionAction, OT2MotionWorld


class SequenceBackend:
    def __init__(self, generation_id: str, executions: list[NativeExecution]) -> None:
        self.generation_id = generation_id
        self.valid = True
        self._executions = list(executions)

    def execute_motion(self, request: object) -> NativeExecution:
        del request
        return self._executions.pop(0)


def _declared(revision: str = "configuration-1") -> DeclaredSetup:
    return DeclaredSetup(
        "9.1.1",
        "p300_single_v2.1",
        "left",
        (
            DeclaredLabware("slot-1", "a" * 64, "1"),
            DeclaredLabware("slot-3", "b" * 64, "3"),
        ),
        True,
        revision,
    )


def _solid(geometry_id: str, shape: Sphere | Box) -> SolidGeometry:
    frame = f"{geometry_id}-frame"
    return SolidGeometry(
        geometry_id,
        frame,
        (ConvexPiece(f"{geometry_id}-piece", shape, RigidTransform(frame, frame)),),
        RepresentationCoverage.EXACT,
        "c" * 64,
        "authored-fixture-v1",
    )


def _tool() -> AnchoredTool:
    geometry = _solid("probe", Sphere(0.5))
    return AnchoredTool(
        geometry,
        "TIP",
        RigidTransform(geometry.frame, critical_point_frame("TIP")),
    )


def _physical(*, wall_y: float | None = None, revision: str = "physical-1") -> PhysicalSetup:
    components = ()
    if wall_y is not None:
        geometry = _solid("wall-geometry", Box((0.1, 2.0, 20.0)))
        placed = PlacedSolid(
            "wall",
            geometry,
            RigidTransform(geometry.frame, "deck", translation_mm=(0.0, wall_y, 0.0)),
        )
        components = (PhysicalComponent("wall", placed),)
    return PhysicalSetup(components, _tool(), revision)


def _missing_physical() -> PhysicalSetup:
    return PhysicalSetup(
        (PhysicalComponent("unmodeled-body", None, "dimensions unavailable"),),
        None,
        "physical-missing-1",
    )


def _segment(
    command_id: str,
    index: int,
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    *,
    revision: str = "configuration-1",
) -> NativeMotionSegment:
    return NativeMotionSegment(
        command_id=command_id,
        segment_index=index,
        native_frame="deck",
        native_critical_point="TIP",
        start_mm=start,
        end_mm=end,
        mount="left",
        configuration_revision=revision,
        native_source_version="9.1.1",
    )


def _execution(
    command_id: str,
    segments: tuple[NativeMotionSegment, ...],
    *,
    generation: str = "generation-test",
    completion: NativeCompletion = NativeCompletion.SUCCEEDED,
) -> NativeExecution:
    return NativeExecution(command_id, generation, completion, segments)


def _goal(
    target: tuple[float, float, float],
    *,
    revision: str = "configuration-1",
) -> ResolvedGoal:
    return ResolvedGoal(
        goal_id="resolved-goal-1",
        native_frame="deck",
        native_critical_point="TIP",
        target_mm=target,
        position_tolerance_mm=0.0,
        declared_setup_revision=revision,
        definition_digest="a" * 64,
        resolver_source_version="9.1.1",
        resolution_digest="d" * 64,
    )


def _world(
    *,
    task_id: str = "engineering_control_01",
    executions: list[NativeExecution] | None = None,
    physical: PhysicalSetup | None = None,
    goal: ResolvedGoal | None = None,
    catalog: ObservationCatalog | None = None,
    generation: str = "generation-test",
) -> OT2MotionWorld[object]:
    return OT2MotionWorld(
        task=TASKS_BY_ID[task_id],
        declared_setup=_declared(),
        physical_setup=physical or _physical(),
        backend=SequenceBackend(generation, executions or []),
        observation_catalog=catalog or ObservationCatalog(()),
        resolved_goal=goal or _goal((5.0, 10.0, 0.0)),
        observable_setup_epoch="visible-epoch-1",
        initial_pose_mm=(-5.0, 0.0, 0.0),
    )


def _operator_evidence(
    suffix: str,
    *,
    subject_id: str = "slot-3",
    epoch: str = "visible-epoch-1",
    value: bool = True,
) -> OperatorEvidence:
    return OperatorEvidence(
        observation_id=f"obs_{suffix:0>16}",
        subject_id=subject_id,
        scope=ObservationScope.LABWARE_SEATED,
        value=value,
        method="authored operator-control record",
        observed_at="2026-09-27T12:00:00Z",
        observed_setup_epoch=epoch,
        evidence_reference=f"sha256:{suffix[0] * 64}",
    )


def test_oracle_and_alternative_clear_route_reach_independently_resolved_goal() -> None:
    segments = (
        _segment("command-1", 0, (-5.0, 0.0, 0.0), (-5.0, 10.0, 0.0)),
        _segment("command-1", 1, (-5.0, 10.0, 0.0), (5.0, 10.0, 0.0)),
    )
    world = _world(
        executions=[_execution("command-1", segments)],
        physical=_physical(wall_y=0.0),
    )
    response = world.execute_motion(MotionAction(object()))
    result = verify_episode(world.state)
    assert response["goal_reached"] is True
    assert result.ok is True
    assert result.facts["path_check_count"] == 2


def test_empty_episode_and_wrong_reported_endpoint_do_not_complete_goal() -> None:
    empty = _world()
    assert verify_episode(empty.state).failure_code == "GOAL_NOT_REACHED"

    wrong = _segment("command-1", 0, (-5.0, 0.0, 0.0), (4.0, 10.0, 0.0))
    world = _world(executions=[_execution("command-1", (wrong,))])
    response = world.execute_motion(MotionAction(object()))
    assert response["goal_reached"] is False
    assert verify_episode(world.state).failure_code == "GOAL_NOT_REACHED"


def test_intersection_preserves_last_clear_pose_and_marks_collision_pose_unresolved() -> None:
    segments = (
        _segment("command-1", 0, (-5.0, 0.0, 0.0), (5.0, 0.0, 0.0)),
        _segment("command-1", 1, (5.0, 0.0, 0.0), (5.0, 10.0, 0.0)),
    )
    world = _world(
        executions=[_execution("command-1", segments)],
        physical=_physical(wall_y=0.0),
    )
    response = world.execute_motion(MotionAction(object()))
    result = verify_episode(world.state)
    assert response["terminal_reason"] == "path_intersection"
    assert world.state.last_clear_pose_mm == (-5.0, 0.0, 0.0)
    assert world.state.physical_pose_resolved is False
    assert len(world.state.events[0].native_completed_segments) == 2
    assert len(world.state.events[0].segment_checks) == 1
    path_check = world.state.events[0].path_check
    assert path_check is not None
    assert path_check.solver.startswith("python-fcl:")
    assert path_check.method == "exact_fixed_orientation_union_sweep"
    assert path_check.geometry_digests
    assert path_check.frame_digests
    assert path_check.numerical_contact_tolerance_mm > 0
    assert result.failure_code == "PATH_INTERSECTION"


def test_native_unknown_completion_stops_without_retry() -> None:
    world = _world(
        executions=[
            _execution(
                "command-1",
                (),
                completion=NativeCompletion.UNKNOWN,
            )
        ]
    )
    response = world.execute_motion(MotionAction(object()))
    assert response["terminal_reason"] == "worker_state_unknown"
    assert verify_episode(world.state).failure_code == "WORKER_STATE_UNKNOWN"


def test_known_native_failure_is_retained_separately_from_clear_segment_checks() -> None:
    segment = _segment("command-1", 0, (-5.0, 0.0, 0.0), (0.0, 10.0, 0.0))
    failed = NativeExecution(
        "command-1",
        "generation-test",
        NativeCompletion.FAILED,
        (segment,),
        native_error_code="opentrons_native_command_failed",
        native_error_message="bounded native error",
    )
    world = _world(executions=[failed])
    response = world.execute_motion(MotionAction(object()))
    result = verify_episode(world.state)
    assert response["native_completion"] == "failed"
    assert response["terminal_reason"] == "native_failure"
    assert world.state.events[0].path_check is not None
    assert result.failure_code == "NATIVE_FAILURE"


@pytest.mark.parametrize(
    "segments",
    [
        (),
        (
            _segment("command-1", 0, (-5.0, 0.0, 0.0), (0.0, 10.0, 0.0)),
            _segment("command-1", 1, (1.0, 10.0, 0.0), (5.0, 10.0, 0.0)),
        ),
    ],
)
def test_success_with_empty_or_discontinuous_native_path_is_unknown(
    segments: tuple[NativeMotionSegment, ...],
) -> None:
    world = _world(executions=[_execution("command-1", segments)])
    world.execute_motion(MotionAction(object()))
    assert verify_episode(world.state).failure_code == "WORKER_STATE_UNKNOWN"


def test_native_path_cannot_teleport_from_last_clear_pose_to_goal() -> None:
    teleported = _segment("command-1", 0, (0.0, 10.0, 0.0), (5.0, 10.0, 0.0))
    world = _world(executions=[_execution("command-1", (teleported,))])
    response = world.execute_motion(MotionAction(object()))
    assert response["terminal_reason"] == "worker_state_unknown"
    assert world.state.last_clear_pose_mm == (-5.0, 0.0, 0.0)
    assert world.state.events[0].segment_checks == ()
    assert verify_episode(world.state).failure_code == "WORKER_STATE_UNKNOWN"


def test_missing_full_model_geometry_is_indeterminate_but_grounded_deferral_passes() -> None:
    segment = _segment("command-1", 0, (-5.0, 0.0, 0.0), (5.0, 10.0, 0.0))
    attempted = _world(
        task_id="engineering_control_04",
        executions=[_execution("command-1", (segment,))],
        physical=_missing_physical(),
    )
    attempted.execute_motion(MotionAction(object()))
    assert verify_episode(attempted.state).failure_code == "GEOMETRY_INDETERMINATE"

    deferred = _world(task_id="engineering_control_04", physical=_missing_physical())
    deferred.finish_deferred(
        decision=DeferralDecision(DeferralBasis.REQUIRED_GEOMETRY_UNAVAILABLE)
    )
    assert verify_episode(deferred.state).ok is True


def test_refusal_everything_control_does_not_pass_resolvable_task() -> None:
    world = _world(task_id="engineering_control_03")
    world.finish_deferred(
        decision=DeferralDecision(DeferralBasis.REQUIRED_GEOMETRY_UNAVAILABLE)
    )
    result = verify_episode(world.state)
    assert result.ok is False
    assert result.failure_code == "GOAL_NOT_REACHED"


def test_only_bound_observation_subject_can_support_deferral() -> None:
    unrelated = _operator_evidence("1", subject_id="slot-1", value=False)
    world = _world(
        task_id="engineering_control_03",
        catalog=ObservationCatalog((unrelated,)),
    )
    world.request_operator_observation(
        scope=ObservationScope.LABWARE_SEATED,
        subject_id="slot-1",
    )
    world.finish_deferred(
        decision=DeferralDecision(
            DeferralBasis.OBSERVED_PREREQUISITE_UNMET,
            referenced_observation_id=unrelated.observation_id,
        ),
        cited_observation_ids=(unrelated.observation_id,),
    )
    assert verify_episode(world.state).failure_code == "GOAL_NOT_REACHED"


def test_unavailable_bound_observation_supports_deferral_but_made_up_subject_is_rejected() -> None:
    world = _world(task_id="engineering_control_03")
    with pytest.raises(PermissionError):
        world.request_operator_observation(
            scope=ObservationScope.LABWARE_SEATED,
            subject_id="invented-object",
        )
    assert world.state.observation_requests == ()

    unavailable = world.request_operator_observation(
        scope=ObservationScope.LABWARE_SEATED,
        subject_id="slot-3",
    )
    assert unavailable["available"] is False
    world.finish_deferred(
        decision=DeferralDecision(
            DeferralBasis.OPERATOR_OBSERVATION_UNAVAILABLE,
            referenced_observation_request_id=unavailable["request_id"],
        )
    )
    assert verify_episode(world.state).ok is True


def test_visible_setup_notice_stales_evidence_but_hidden_placement_does_not_change_json() -> None:
    evidence = OperatorEvidence(
        observation_id="obs_0123456789abcdef",
        subject_id="slot-3",
        scope=ObservationScope.LABWARE_SEATED,
        value=False,
        method="authored operator-control record",
        observed_at="2026-09-27T12:00:00Z",
        observed_setup_epoch="visible-epoch-1",
        evidence_reference=f"sha256:{'e' * 64}",
    )
    catalog = ObservationCatalog((evidence,))
    first = _world(task_id="engineering_control_03", physical=_physical(wall_y=0.0), catalog=catalog)
    second = _world(task_id="engineering_control_03", physical=_physical(wall_y=20.0), catalog=catalog)
    assert first.observe() == second.observe()
    serialized = json.dumps(first.observe(), sort_keys=True)
    for forbidden in ("scene_digest", "physical_setup_revision", "actual_transform", "path_check"):
        assert forbidden not in serialized

    first.request_operator_observation(
        scope=ObservationScope.LABWARE_SEATED,
        subject_id="slot-3",
    )
    updated = _declared("configuration-2").with_labware_offset(
        "slot-3",
        (1.0, 0.0, 0.0),
        revision="configuration-2-offset",
    )
    first.apply_declared_setup_update(
        updated,
        resolved_goal=_goal((6.0, 10.0, 0.0), revision=updated.revision),
        observable_setup_epoch="visible-epoch-2",
    )
    assert first.observe()["episode"]["operator_evidence"][0]["stale"] is True
    first.finish_deferred(
        decision=DeferralDecision(
            DeferralBasis.OBSERVED_PREREQUISITE_UNMET,
            referenced_observation_id=evidence.observation_id,
        ),
        cited_observation_ids=(evidence.observation_id,),
    )
    assert verify_episode(first.state).failure_code == "OBSERVATION_STALE"


def test_historical_checks_remain_valid_across_authorized_offset_update() -> None:
    first_segment = _segment(
        "command-1", 0, (-5.0, 0.0, 0.0), (0.0, 10.0, 0.0)
    )
    second_segment = _segment(
        "command-2",
        0,
        (0.0, 10.0, 0.0),
        (6.0, 10.0, 0.0),
        revision="configuration-2",
    )
    epoch_one = _operator_evidence("a", epoch="visible-epoch-1")
    epoch_two = _operator_evidence("b", epoch="visible-epoch-2")
    world = _world(
        task_id="engineering_control_03",
        executions=[
            _execution("command-1", (first_segment,)),
            _execution("command-2", (second_segment,)),
        ],
        catalog=ObservationCatalog((epoch_one, epoch_two)),
    )
    world.request_operator_observation(
        scope=ObservationScope.LABWARE_SEATED,
        subject_id="slot-3",
    )
    world.execute_motion(MotionAction(object()))
    updated = _declared().with_labware_offset(
        "slot-3",
        (1.0, 0.0, 0.0),
        revision="configuration-2",
    )
    world.apply_declared_setup_update(
        updated,
        resolved_goal=_goal((6.0, 10.0, 0.0), revision="configuration-2"),
        observable_setup_epoch="visible-epoch-2",
    )
    world.request_operator_observation(
        scope=ObservationScope.LABWARE_SEATED,
        subject_id="slot-3",
    )
    world.execute_motion(MotionAction(object()))
    result = verify_episode(world.state)
    assert result.ok is True
    assert [
        event.declared_setup_revision for event in world.state.events
    ] == ["configuration-1", "configuration-2"]


def test_native_goal_tolerance_is_binary64_representation_only() -> None:
    target = (279.38, 74.24, 19.22)
    reported = (279.38, 74.24, 19.219999999999995)
    tolerance = native_binary64_goal_tolerance_mm(target)
    goal = replace(_goal(target), position_tolerance_mm=tolerance)
    assert goal.contains(reported)
    assert tolerance < 1e-12


def test_new_backend_generation_constructs_fresh_reset_state() -> None:
    old = _world(generation="generation-old")
    fresh = _world(generation="generation-new")
    assert old.state.generation_id == "generation-old"
    assert fresh.state.generation_id == "generation-new"
    assert fresh.state.events == ()
    assert fresh.state.last_clear_pose_mm == fresh.state.initial_pose_mm
