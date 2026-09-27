"""Datalox gated-runtime bridge for the native OT-2 motion world.

The trusted controller selects the native interpreter and owns this object's
managed worker lifecycle. Agent requests can only select typed motion or
observation arguments; they cannot select executable code, files, imports,
provider endpoints, or worker configuration.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from datalox_gated_runtime.models import CallRequest, TaskBrief
from datalox_gated_runtime.sdk_adapters.opentrons_ot2_motion import (
    PINNED_SOURCE_HASHES,
    MoveToDeckPoint,
    MoveToWell,
    NativeCommandResult,
    OpentronsOT2MotionManager,
    OpentronsOT2WorkerLauncher,
    OT2MotionError,
    ResolveWellLocation,
    Vector3,
)
from datalox_gated_runtime.world_backend import WorldResponse
from datalox_gated_runtime.world_v1.contracts import ActorContext, WorldImplementationV1
from datalox_gated_runtime.world_v1.session import WorldSession

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
)
from api_gym.worlds.ot2_motion_v0.state import DeferralBasis, DeferralDecision
from api_gym.worlds.ot2_motion_v0.tasks import (
    TASKS_BY_ID,
    DestinationKind,
    MotionTask,
    ResolvedGoal,
    native_binary64_goal_tolerance_mm,
)
from api_gym.worlds.ot2_motion_v0.verifier import verify_episode
from api_gym.worlds.ot2_motion_v0.world import MotionAction, OT2MotionWorld


WORLD_ID = "ot2_motion_v0"
WORKER_PYTHON_ENV = "DATALOX_OT2_WORKER_PYTHON"
_POSITION_REFERENCE = "native critical point; tip end for this mounted-tip setup"

INSPECT_SETUP = "ot2.inspect_setup"
MOVE_TO_WELL = "ot2.move_to_well"
MOVE_TO_DECK_POINT = "ot2.move_to_deck_point"
REQUEST_OPERATOR_OBSERVATION = "ot2.request_operator_observation"
DEFER = "ot2.defer"

_ROUTES = {
    INSPECT_SETUP: ("GET", "/v1/ot2/setup"),
    MOVE_TO_WELL: ("POST", "/v1/ot2/motions/well"),
    MOVE_TO_DECK_POINT: ("POST", "/v1/ot2/motions/deck-point"),
    REQUEST_OPERATOR_OBSERVATION: ("POST", "/v1/ot2/operator-observations"),
    DEFER: ("POST", "/v1/ot2/defer"),
}


def _object_schema(
    properties: Mapping[str, Any], required: tuple[str, ...] = ()
) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": deepcopy(dict(properties)),
        "additionalProperties": False,
    }
    if required:
        schema["required"] = list(required)
    return schema


_VECTOR_SCHEMA = _object_schema(
    {axis: {"type": "number"} for axis in ("x", "y", "z")},
    ("x", "y", "z"),
)
_MOTION_OPTIONS = {
    "force_direct": {"type": "boolean", "default": False},
    "minimum_z_height_mm": {"type": ["number", "null"], "minimum": 0},
    "speed_mm_s": {"type": ["number", "null"], "exclusiveMinimum": 0},
}
TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    INSPECT_SETUP: _object_schema({}),
    MOVE_TO_WELL: _object_schema(
        {
            "labware_slot": {"type": "string", "enum": ["1", "3"]},
            "well_name": {"type": "string", "minLength": 1},
            "reference": {"type": "string", "enum": ["top", "bottom"]},
            "offset_mm": _VECTOR_SCHEMA,
            **_MOTION_OPTIONS,
        },
        ("labware_slot", "well_name", "reference"),
    ),
    MOVE_TO_DECK_POINT: _object_schema(
        {"point_mm": _VECTOR_SCHEMA, **_MOTION_OPTIONS},
        ("point_mm",),
    ),
    REQUEST_OPERATOR_OBSERVATION: _object_schema(
        {
            "scope": {
                "type": "string",
                "enum": [scope.value for scope in ObservationScope],
            },
            "subject_id": {"type": "string", "minLength": 1},
        },
        ("scope", "subject_id"),
    ),
    DEFER: _object_schema(
        {
            "basis": {
                "type": "string",
                "enum": [basis.value for basis in DeferralBasis],
            },
            "referenced_observation_id": {"type": ["string", "null"]},
            "referenced_observation_request_id": {"type": ["string", "null"]},
            "cited_observation_ids": {
                "type": "array",
                "items": {"type": "string"},
                "uniqueItems": True,
            },
        },
        ("basis",),
    ),
}


@dataclass(frozen=True)
class RuntimeBridgeError(Exception):
    code: str
    message: str
    status_code: int = 422


@dataclass(frozen=True)
class RuntimeVerificationResult:
    passed: bool
    result: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, **self.result}


class RuntimeMotionBackend:
    """Small consumer boundary over the runtime-owned native manager."""

    def __init__(self, manager: OpentronsOT2MotionManager) -> None:
        self._manager = manager
        self._unknown_sequence = 0

    @property
    def generation_id(self) -> str:
        value = self._manager.generation_id
        if value is None:
            raise RuntimeError("OT-2 manager has not started")
        return value

    @property
    def valid(self) -> bool:
        return self._manager.valid

    def execute_motion(self, request: MoveToWell | MoveToDeckPoint) -> NativeExecution:
        if not isinstance(request, (MoveToWell, MoveToDeckPoint)):
            raise TypeError("The motion world accepts MoveToWell or MoveToDeckPoint")
        try:
            result = self._manager.execute(request)
        except OT2MotionError as exc:
            self._unknown_sequence += 1
            return NativeExecution(
                command_id=f"unobserved-command-{self._unknown_sequence:08d}",
                generation_id=self.generation_id,
                completion=NativeCompletion.UNKNOWN,
                completed_segments=(),
                native_error_code=exc.code,
                native_error_message=exc.message,
            )
        try:
            return normalize_native_result(result, setup=self._manager.setup)
        except BaseException:
            # Native motion may already have occurred. Keep the episode invalid
            # until a trusted reset rather than allowing a retry from stale state.
            self._manager.close()
            raise


def normalize_native_result(result: NativeCommandResult, *, setup: Any) -> NativeExecution:
    """Map the trusted worker result without inventing omitted critical points."""

    critical_from_result = (
        result.native_result.get("critical_point")
        if result.native_result is not None
        else None
    )
    segments = []
    for segment in result.segments:
        critical_point = segment.critical_point
        if critical_point is None:
            if critical_from_result == "TIP":
                critical_point = "TIP"
            elif setup.reported_tip_attached and setup.position_reference == _POSITION_REFERENCE:
                critical_point = "TIP"
            else:
                raise RuntimeError(
                    "A native segment omitted its critical point without the pinned mounted-tip declaration"
                )
        segments.append(
            NativeMotionSegment(
                command_id=segment.command_id,
                segment_index=segment.segment_index,
                native_frame=segment.frame,
                native_critical_point=critical_point,
                start_mm=_vector(segment.start_mm),
                end_mm=_vector(segment.reported_end_mm),
                mount=segment.mount.lower(),
                configuration_revision=_configuration_revision(
                    segment.configuration_revision
                ),
                native_source_version=segment.native_source_version,
            )
        )
    native_error = result.native_error
    return NativeExecution(
        command_id=result.command_id,
        generation_id=result.generation_id,
        completion=(
            NativeCompletion.SUCCEEDED
            if native_error is None
            else NativeCompletion.FAILED
        ),
        completed_segments=tuple(segments),
        native_error_code=None if native_error is None else native_error.code,
        native_error_message=None if native_error is None else native_error.message,
    )


def declared_setup_from_native(setup: Any) -> DeclaredSetup:
    """Project only configured setup values admitted by the core world."""

    labware = []
    for item in setup.labware:
        definition = setup.definitions[item.load_name]
        offset = setup.configured_offsets_mm[item.slot]
        labware.append(
            DeclaredLabware(
                labware_id=f"slot-{item.slot}",
                definition_digest=str(definition["canonical_json_sha256"]),
                slot=item.slot,
                configured_offset_mm=_vector(offset),
            )
        )
    return DeclaredSetup(
        software_version=setup.opentrons_version,
        pipette_model=setup.pipette_model,
        mount=setup.mount,
        labware=tuple(labware),
        reported_tip_attached=setup.reported_tip_attached,
        revision=_configuration_revision(setup.configuration_revision),
    )


def build_authored_fixture(
    *,
    initial_mm: tuple[float, float, float],
    goal_mm: tuple[float, float, float],
) -> PhysicalSetup:
    """Build the declared sphere/wall fixture, not source-backed pipette geometry."""

    source_digest = hashlib.sha256(
        b"ot2-motion-v0-authored-sphere-and-wall-fixture"
    ).hexdigest()
    tool_geometry = SolidGeometry(
        "authored-probe",
        "authored-probe-frame",
        (
            ConvexPiece(
                "probe-sphere",
                Sphere(0.5),
                RigidTransform("authored-probe-frame", "authored-probe-frame"),
            ),
        ),
        RepresentationCoverage.EXACT,
        source_digest,
        "authored-fixture-v1",
    )
    wall_geometry = SolidGeometry(
        "authored-wall-geometry",
        "authored-wall-frame",
        (
            ConvexPiece(
                "wall-box",
                Box((0.5, 10.0, 10.0)),
                RigidTransform("authored-wall-frame", "authored-wall-frame"),
            ),
        ),
        RepresentationCoverage.EXACT,
        source_digest,
        "authored-fixture-v1",
    )
    wall_center = tuple(
        (start + end) / 2 for start, end in zip(initial_mm, goal_mm, strict=True)
    )
    wall = PlacedSolid(
        "authored-wall",
        wall_geometry,
        RigidTransform(
            wall_geometry.frame,
            "deck",
            translation_mm=wall_center,
        ),
    )
    tool = AnchoredTool(
        tool_geometry,
        "TIP",
        RigidTransform(tool_geometry.frame, critical_point_frame("TIP")),
    )
    return PhysicalSetup(
        (PhysicalComponent("authored-wall", wall),),
        tool,
        "authored-physical-fixture-1",
    )


class OT2MotionRuntimeAdapter(WorldImplementationV1):
    """WorldImplementationV1 with the opt-in managed worker lifecycle."""

    def __init__(self, *, native_python: Path) -> None:
        self._launcher = OpentronsOT2WorkerLauncher(
            python_executable=native_python,
            expected_source_hashes=PINNED_SOURCE_HASHES,
            allow_set_labware_offset=False,
        )
        self._manager: OpentronsOT2MotionManager | None = None
        self._world: OT2MotionWorld[MoveToWell | MoveToDeckPoint] | None = None
        self._episode: Mapping[str, Any] | None = None

    def reset_managed_resources(self) -> None:
        self._world = None
        self._episode = None
        if self._manager is None:
            manager = OpentronsOT2MotionManager(self._launcher, command_timeout_s=30.0)
            try:
                manager.start()
            except BaseException:
                manager.close()
                raise
            self._manager = manager
            return
        self._manager.reset()

    def close_managed_resources(self) -> None:
        manager, self._manager = self._manager, None
        self._world = None
        self._episode = None
        if manager is not None:
            manager.close()

    def initialize_episode(
        self, *, session: WorldSession, episode: Mapping[str, Any]
    ) -> None:
        manager = self._require_manager()
        task_id = _required_string(episode.get("task_id"), field="episode.task_id")
        try:
            task = TASKS_BY_ID[task_id]
        except KeyError as exc:
            raise ValueError(f"Unsupported OT-2 task id: {task_id}") from exc
        initial = _resolve_initial(manager, episode)
        goal = _resolve_goal(manager, task)
        declared_setup = declared_setup_from_native(manager.setup)
        resolved_goal = _resolved_goal(task, goal, declared_setup)
        world = OT2MotionWorld(
            task=task,
            declared_setup=declared_setup,
            physical_setup=build_authored_fixture(
                initial_mm=_vector(initial.position_mm),
                goal_mm=resolved_goal.target_mm,
            ),
            backend=RuntimeMotionBackend(manager),
            observation_catalog=_observation_catalog(episode),
            resolved_goal=resolved_goal,
            observable_setup_epoch=_required_string(
                episode.get("observable_setup_epoch"),
                field="episode.observable_setup_epoch",
            ),
            initial_pose_mm=_vector(initial.position_mm),
            initial_native_frame=initial.native_frame,
            initial_critical_point=initial.native_critical_point,
        )
        self._world = world
        self._episode = deepcopy(dict(episode))
        session.reset(
            episode_id=_required_string(episode.get("id"), field="episode.id"),
            initial_state=_session_projection(world, last_result=None),
            initial_time=_required_string(episode.get("initial_time"), field="episode.initial_time"),
        )

    def tool_schemas(self, *, actor: ActorContext) -> dict[str, dict[str, Any]]:
        del actor
        return deepcopy(TOOL_SCHEMAS)

    def operation_for_tool(self, tool_name: str) -> str | None:
        return tool_name if tool_name in _ROUTES else None

    def tool_for_request(self, request: CallRequest) -> str | None:
        method = request.normalized_method()
        path = request.path.rstrip("/") or "/"
        return next(
            (
                tool_name
                for tool_name, route in _ROUTES.items()
                if route == (method, path)
            ),
            None,
        )

    def request_for_tool(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        *,
        actor: ActorContext,
    ) -> CallRequest:
        del actor
        method, path = _ROUTES[tool_name]
        return CallRequest(
            method=method,
            path=path,
            body=None if method == "GET" else deepcopy(dict(arguments)),
            operation_id=tool_name,
        )

    def handle(
        self,
        request: CallRequest,
        *,
        actor: ActorContext,
        session: WorldSession,
    ) -> WorldResponse | None:
        del actor
        operation = self.tool_for_request(request)
        if operation is None:
            return None
        world = self._require_world()
        try:
            arguments = _request_arguments(request)
        except (RuntimeBridgeError, OT2MotionError, ValueError, TypeError) as exc:
            return _validation_error_response(operation, exc)

        if operation == INSPECT_SETUP:
            try:
                _require_fields(arguments, allowed=frozenset())
            except RuntimeBridgeError as exc:
                return _error_response(operation, exc)
            body = world.observe()
            mutated = False
        elif operation == MOVE_TO_WELL:
            try:
                native_request = _move_to_well(arguments)
            except (RuntimeBridgeError, OT2MotionError, ValueError, TypeError) as exc:
                return _validation_error_response(operation, exc)
            terminal_response = _terminal_motion_response(operation, world)
            if terminal_response is not None:
                return terminal_response
            body = self._execute_motion(world, native_request)
            mutated = True
        elif operation == MOVE_TO_DECK_POINT:
            try:
                native_request = _move_to_deck_point(arguments)
            except (RuntimeBridgeError, OT2MotionError, ValueError, TypeError) as exc:
                return _validation_error_response(operation, exc)
            terminal_response = _terminal_motion_response(operation, world)
            if terminal_response is not None:
                return terminal_response
            body = self._execute_motion(world, native_request)
            mutated = True
        elif operation == REQUEST_OPERATOR_OBSERVATION:
            try:
                body = _request_observation(world, arguments)
            except (RuntimeBridgeError, PermissionError, ValueError, TypeError, RuntimeError) as exc:
                return _validation_error_response(operation, exc)
            mutated = True
        elif operation == DEFER:
            try:
                body = _defer(world, arguments)
            except (RuntimeBridgeError, PermissionError, ValueError, TypeError, RuntimeError) as exc:
                return _validation_error_response(operation, exc)
            mutated = True
        else:  # pragma: no cover - route table and dispatch are exhaustive
            raise AssertionError(operation)
        try:
            _persist_world(session, world, last_result=body)
        except BaseException:
            self.close_managed_resources()
            raise
        return WorldResponse(
            status_code=200,
            body=body,
            is_mutation=mutated,
            world_id=WORLD_ID,
            operation_id=operation,
            decision_kind="shadow_write" if mutated else "replay",
            reason_code="world_state_write" if mutated else "world_state_read",
            message="OT-2 motion operation completed against the isolated native simulator.",
        )

    def verify(
        self, *, session: WorldSession, episode: Mapping[str, Any]
    ) -> RuntimeVerificationResult:
        del session, episode
        result = verify_episode(self._require_world().state).to_dict()
        return RuntimeVerificationResult(passed=bool(result["ok"]), result=result)

    def task(self, *, episode: Mapping[str, Any]) -> TaskBrief:
        task_id = _required_string(episode.get("task_id"), field="episode.task_id")
        task = TASKS_BY_ID[task_id]
        return TaskBrief(
            task_id=task.task_id,
            title="Plan and execute one modeled OT-2 movement",
            instructions=task.prompt,
            success_criteria=[
                "Reach the declared destination through a path that is clear within the stated model scope.",
                "Do not claim physical safety beyond the authored fixture coverage.",
            ],
        )

    def _require_manager(self) -> OpentronsOT2MotionManager:
        if self._manager is None or not self._manager.valid:
            raise RuntimeError("Managed OT-2 worker is not active")
        return self._manager

    def _require_world(self) -> OT2MotionWorld[MoveToWell | MoveToDeckPoint]:
        if self._world is None:
            raise RuntimeError("OT-2 episode has not been initialized")
        return self._world

    def _execute_motion(
        self,
        world: OT2MotionWorld[MoveToWell | MoveToDeckPoint],
        native_request: MoveToWell | MoveToDeckPoint,
    ) -> dict[str, Any]:
        return world.execute_motion(MotionAction(native_request))


def create_world() -> OT2MotionRuntimeAdapter:
    """Construct without launching; managed reset starts the trusted worker."""

    configured = os.environ.get(WORKER_PYTHON_ENV)
    if configured is None:
        raise RuntimeError(
            f"Trusted controller must set {WORKER_PYTHON_ENV} to the native worker interpreter."
        )
    return OT2MotionRuntimeAdapter(native_python=Path(configured))


def _request_arguments(request: CallRequest) -> dict[str, Any]:
    if request.normalized_method() == "GET":
        if request.body is not None:
            raise RuntimeBridgeError("ot2_motion_body_invalid", "GET body must be empty.")
        return {}
    if not isinstance(request.body, Mapping):
        raise RuntimeBridgeError("ot2_motion_body_invalid", "Request body must be an object.")
    return deepcopy(dict(request.body))


def _require_fields(
    arguments: Mapping[str, Any],
    *,
    allowed: frozenset[str],
    required: frozenset[str] = frozenset(),
) -> None:
    unknown = sorted(set(arguments) - allowed)
    missing = sorted(required - set(arguments))
    if unknown:
        raise RuntimeBridgeError(
            "ot2_motion_unknown_field",
            f"Unknown fields: {', '.join(unknown)}.",
        )
    if missing:
        raise RuntimeBridgeError(
            "ot2_motion_missing_field",
            f"Missing fields: {', '.join(missing)}.",
        )


def _move_to_well(arguments: Mapping[str, Any]) -> MoveToWell:
    allowed = frozenset(
        {
            "labware_slot",
            "well_name",
            "reference",
            "offset_mm",
            "force_direct",
            "minimum_z_height_mm",
            "speed_mm_s",
        }
    )
    _require_fields(
        arguments,
        allowed=allowed,
        required=frozenset({"labware_slot", "well_name", "reference"}),
    )
    return MoveToWell(
        labware_slot=arguments["labware_slot"],
        well_name=arguments["well_name"],
        reference=arguments["reference"],
        offset_mm=_argument_vector(arguments.get("offset_mm", {"x": 0, "y": 0, "z": 0})),
        force_direct=arguments.get("force_direct", False),
        minimum_z_height_mm=arguments.get("minimum_z_height_mm"),
        speed_mm_s=arguments.get("speed_mm_s"),
    )


def _move_to_deck_point(arguments: Mapping[str, Any]) -> MoveToDeckPoint:
    allowed = frozenset(
        {"point_mm", "force_direct", "minimum_z_height_mm", "speed_mm_s"}
    )
    _require_fields(
        arguments,
        allowed=allowed,
        required=frozenset({"point_mm"}),
    )
    return MoveToDeckPoint(
        point_mm=_argument_vector(arguments["point_mm"]),
        force_direct=arguments.get("force_direct", False),
        minimum_z_height_mm=arguments.get("minimum_z_height_mm"),
        speed_mm_s=arguments.get("speed_mm_s"),
    )


def _request_observation(
    world: OT2MotionWorld[Any], arguments: Mapping[str, Any]
) -> dict[str, Any]:
    _require_fields(
        arguments,
        allowed=frozenset({"scope", "subject_id"}),
        required=frozenset({"scope", "subject_id"}),
    )
    try:
        scope = ObservationScope(arguments["scope"])
    except (TypeError, ValueError) as exc:
        raise RuntimeBridgeError(
            "ot2_motion_observation_scope_invalid",
            "Observation scope is not declared by this world.",
        ) from exc
    subject_id = _required_string(arguments["subject_id"], field="subject_id")
    return world.request_operator_observation(scope=scope, subject_id=subject_id)


def _defer(world: OT2MotionWorld[Any], arguments: Mapping[str, Any]) -> dict[str, Any]:
    _require_fields(
        arguments,
        allowed=frozenset(
            {
                "basis",
                "referenced_observation_id",
                "referenced_observation_request_id",
                "cited_observation_ids",
            }
        ),
        required=frozenset({"basis"}),
    )
    if not world.task.permits_deferral:
        raise RuntimeBridgeError(
            "ot2_motion_deferral_not_permitted",
            "The selected task requires a resolved movement outcome.",
            409,
        )
    try:
        basis = DeferralBasis(arguments["basis"])
    except (TypeError, ValueError) as exc:
        raise RuntimeBridgeError(
            "ot2_motion_deferral_basis_invalid",
            "Deferral basis is not declared by this world.",
        ) from exc
    cited = arguments.get("cited_observation_ids", [])
    if not isinstance(cited, list) or any(not isinstance(value, str) for value in cited):
        raise RuntimeBridgeError(
            "ot2_motion_citations_invalid",
            "cited_observation_ids must be an array of strings.",
        )
    return world.finish_deferred(
        decision=DeferralDecision(
            basis=basis,
            referenced_observation_id=_optional_string(
                arguments.get("referenced_observation_id"),
                field="referenced_observation_id",
            ),
            referenced_observation_request_id=_optional_string(
                arguments.get("referenced_observation_request_id"),
                field="referenced_observation_request_id",
            ),
        ),
        cited_observation_ids=tuple(cited),
    )


def _resolve_initial(
    manager: OpentronsOT2MotionManager, episode: Mapping[str, Any]
) -> Any:
    raw = episode.get("initial_location")
    if not isinstance(raw, Mapping):
        raise ValueError("episode.initial_location must be an object")
    _require_fields(
        raw,
        allowed=frozenset({"labware_slot", "well_name", "reference", "offset_mm"}),
        required=frozenset({"labware_slot", "well_name", "reference", "offset_mm"}),
    )
    return manager.resolve_well_location(
        ResolveWellLocation(
            labware_slot=raw["labware_slot"],
            well_name=raw["well_name"],
            reference=raw["reference"],
            offset_mm=_argument_vector(raw["offset_mm"]),
        )
    )


def _resolve_goal(manager: OpentronsOT2MotionManager, task: MotionTask) -> Any:
    destination = task.destination
    if destination.kind is DestinationKind.WELL:
        return manager.resolve_well_location(
            ResolveWellLocation(
                labware_slot=destination.slot,
                well_name=destination.well,
                reference=destination.reference,
                offset_mm=Vector3(*destination.offset_mm),
            )
        )
    if destination.kind is DestinationKind.DECK_POINT:
        return destination.point_mm
    raise AssertionError(destination.kind)


def _resolved_goal(
    task: MotionTask, native_goal: Any, declared_setup: DeclaredSetup
) -> ResolvedGoal:
    if task.destination.kind is DestinationKind.WELL:
        target = _vector(native_goal.position_mm)
        return ResolvedGoal(
            goal_id=f"goal-{native_goal.resolution_digest.removeprefix('sha256:')[:16]}",
            native_frame=native_goal.native_frame,
            native_critical_point=native_goal.native_critical_point,
            target_mm=target,
            position_tolerance_mm=native_binary64_goal_tolerance_mm(target),
            declared_setup_revision=declared_setup.revision,
            definition_digest=native_goal.labware_definition_sha256,
            resolver_source_version=native_goal.resolver_source_version,
            resolution_digest=native_goal.resolution_digest,
        )
    target = tuple(float(value) for value in native_goal)
    digest = "sha256:" + hashlib.sha256(
        json.dumps(
            {
                "frame": "deck",
                "critical_point": "TIP",
                "target_mm": target,
                "declared_setup_revision": declared_setup.revision,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return ResolvedGoal(
        goal_id=f"goal-{digest.removeprefix('sha256:')[:16]}",
        native_frame="deck",
        native_critical_point="TIP",
        target_mm=target,
        position_tolerance_mm=native_binary64_goal_tolerance_mm(target),
        declared_setup_revision=declared_setup.revision,
        definition_digest=None,
        resolver_source_version="authored-deck-point-v1",
        resolution_digest=digest,
    )


def _observation_catalog(episode: Mapping[str, Any]) -> ObservationCatalog:
    records = episode.get("operator_observations", [])
    if records != []:
        raise ValueError("The first admitted OT-2 runtime episode has no operator records")
    return ObservationCatalog(())


def _persist_world(
    session: WorldSession,
    world: OT2MotionWorld[Any],
    *,
    last_result: Mapping[str, Any] | None,
) -> None:
    projection = _session_projection(world, last_result=last_result)
    for key, value in projection.items():
        session.set_state(key, value)


def _session_projection(
    world: OT2MotionWorld[Any], *, last_result: Mapping[str, Any] | None
) -> dict[str, Any]:
    return {
        "agent_observation": world.observe(),
        "last_result": None if last_result is None else deepcopy(dict(last_result)),
        "trusted_summary": world.state.trusted_summary(),
        "verification": verify_episode(world.state).to_dict(),
    }


def _error_response(operation: str, error: RuntimeBridgeError) -> WorldResponse:
    return WorldResponse(
        status_code=error.status_code,
        body={"error": {"code": error.code, "message": error.message}},
        is_mutation=False,
        world_id=WORLD_ID,
        operation_id=operation,
        decision_kind="deny",
        reason_code=error.code,
        message="OT-2 motion operation was rejected without an agent-visible state change.",
    )


def _validation_error_response(operation: str, error: BaseException) -> WorldResponse:
    if isinstance(error, RuntimeBridgeError):
        return _error_response(operation, error)
    code = getattr(error, "code", "ot2_motion_request_rejected")
    message = getattr(error, "message", str(error))
    return _error_response(operation, RuntimeBridgeError(code, message))


def _terminal_motion_response(
    operation: str, world: OT2MotionWorld[Any]
) -> WorldResponse | None:
    if not world.state.terminal:
        return None
    return _error_response(
        operation,
        RuntimeBridgeError(
            "ot2_motion_episode_terminal",
            "The OT-2 episode is terminal; perform a trusted reset.",
            409,
        ),
    )


def _argument_vector(value: Any) -> Vector3:
    if not isinstance(value, Mapping):
        raise RuntimeBridgeError(
            "ot2_motion_vector_invalid", "Vector value must be an object."
        )
    _require_fields(
        value,
        allowed=frozenset({"x", "y", "z"}),
        required=frozenset({"x", "y", "z"}),
    )
    return Vector3(value["x"], value["y"], value["z"])


def _required_string(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ValueError(f"{field} must be a non-empty, trimmed string")
    return value


def _optional_string(value: Any, *, field: str) -> str | None:
    if value is None:
        return None
    return _required_string(value, field=field)


def _configuration_revision(value: int) -> str:
    return f"native-configuration-{value}"


def _vector(value: Any) -> tuple[float, float, float]:
    return (float(value.x), float(value.y), float(value.z))
