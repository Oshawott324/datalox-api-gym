"""Authored engineering-control tasks for the OT-2 motion world."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import dist, isfinite, sqrt, ulp
from string import hexdigits
from typing import Any

from api_gym.instrument_models.opentrons_ot2_v0.observations import (
    GeometryCoverage,
    ModelDisclosure,
    ObservationScope,
)


class DestinationKind(str, Enum):
    WELL = "well"
    DECK_POINT = "deck_point"


class CoverageRequirement(str, Enum):
    DECLARED_AUTHORED_FIXTURE = "declared_authored_fixture"
    COMPLETE_RELEVANT_GEOMETRY = "complete_relevant_geometry"


@dataclass(frozen=True)
class ObservationRequirement:
    scope: ObservationScope
    subject_id: str

    def __post_init__(self) -> None:
        if not self.subject_id.strip():
            raise ValueError("Observation prerequisite subject must be non-empty")


@dataclass(frozen=True)
class MotionDestination:
    kind: DestinationKind
    slot: str | None = None
    well: str | None = None
    reference: str | None = None
    offset_mm: tuple[float, float, float] = (0.0, 0.0, 0.0)
    point_mm: tuple[float, float, float] | None = None

    def __post_init__(self) -> None:
        if len(self.offset_mm) != 3 or not all(isfinite(value) for value in self.offset_mm):
            raise ValueError("offset_mm must contain three finite values")
        if self.kind is DestinationKind.WELL:
            if not self.slot or not self.well or self.reference not in {"top", "bottom"}:
                raise ValueError("Well destinations require slot, well, and top/bottom reference")
            if self.point_mm is not None:
                raise ValueError("Well destinations cannot also contain a deck point")
        elif self.kind is DestinationKind.DECK_POINT:
            if self.point_mm is None or len(self.point_mm) != 3:
                raise ValueError("Deck-point destinations require a finite XYZ point")
            if not all(isfinite(value) for value in self.point_mm):
                raise ValueError("Deck-point coordinates must be finite")
            if any(value is not None for value in (self.slot, self.well, self.reference)):
                raise ValueError("Deck-point destinations cannot contain a well reference")

    def to_dict(self) -> dict[str, Any]:
        if self.kind is DestinationKind.WELL:
            return {
                "kind": self.kind.value,
                "slot": self.slot,
                "well": self.well,
                "reference": self.reference,
                "offset_mm": list(self.offset_mm),
            }
        return {"kind": self.kind.value, "point_mm": list(self.point_mm or ())}


@dataclass(frozen=True)
class ResolvedGoal:
    """Trusted goal pose resolved independently from a command result."""

    goal_id: str
    native_frame: str
    native_critical_point: str
    target_mm: tuple[float, float, float]
    position_tolerance_mm: float
    declared_setup_revision: str
    definition_digest: str | None
    resolver_source_version: str
    resolution_digest: str

    def __post_init__(self) -> None:
        for name in (
            "goal_id",
            "native_frame",
            "native_critical_point",
            "declared_setup_revision",
            "resolver_source_version",
            "resolution_digest",
        ):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must be non-empty")
        if len(self.target_mm) != 3 or not all(isfinite(value) for value in self.target_mm):
            raise ValueError("Resolved goal position must be a finite XYZ vector")
        if not isfinite(self.position_tolerance_mm) or self.position_tolerance_mm < 0:
            raise ValueError("Resolved goal tolerance must be finite and non-negative")
        if self.definition_digest is not None and (
            len(self.definition_digest) != 64
            or any(character not in hexdigits for character in self.definition_digest)
        ):
            raise ValueError("definition_digest must be a 64-character hexadecimal digest")
        resolution_digest = self.resolution_digest.removeprefix("sha256:")
        if len(resolution_digest) != 64 or any(
            character not in hexdigits for character in resolution_digest
        ):
            raise ValueError("resolution_digest must contain a SHA-256 digest")

    def contains(self, position_mm: tuple[float, float, float]) -> bool:
        return dist(self.target_mm, position_mm) <= self.position_tolerance_mm


def native_binary64_goal_tolerance_mm(
    target_mm: tuple[float, float, float],
) -> float:
    """Bound one binary64 representation step per native coordinate."""

    if len(target_mm) != 3 or not all(isfinite(value) for value in target_mm):
        raise ValueError("Native goal target must be a finite XYZ vector")
    return sqrt(sum(ulp(component) ** 2 for component in target_mm))


@dataclass(frozen=True)
class MotionTask:
    task_id: str
    prompt: str
    destination: MotionDestination
    required_geometry_coverage: CoverageRequirement
    permits_deferral: bool
    allowed_observation_scopes: frozenset[ObservationScope]
    observation_prerequisites: frozenset[ObservationRequirement]
    offset_edit_authorized: bool
    model_disclosure: ModelDisclosure

    def __post_init__(self) -> None:
        if not self.task_id.strip() or not self.prompt.strip():
            raise ValueError("Task ID and prompt must be non-empty")
        if any(
            requirement.scope not in self.allowed_observation_scopes
            for requirement in self.observation_prerequisites
        ):
            raise ValueError("Observation prerequisites must use an allowed scope")
        if self.observation_prerequisites and not self.permits_deferral:
            raise ValueError("Tasks with unresolved prerequisites must permit deferral")

    def agent_payload(self) -> dict[str, Any]:
        """Return only objective and declared policy, never control-case truth."""

        return {
            "schema_version": "api_gym.task.ot2_motion_v0.v1",
            "task_id": self.task_id,
            "objective": self.prompt,
            "destination": self.destination.to_dict(),
            "required_geometry_coverage": self.required_geometry_coverage.value,
            "permits_deferral": self.permits_deferral,
            "allowed_observation_scopes": sorted(
                scope.value for scope in self.allowed_observation_scopes
            ),
            "observation_prerequisites": [
                {"scope": requirement.scope.value, "subject_id": requirement.subject_id}
                for requirement in sorted(
                    self.observation_prerequisites,
                    key=lambda item: (item.scope.value, item.subject_id),
                )
            ],
            "offset_edit_authorized": self.offset_edit_authorized,
        }


_FIXTURE_MODEL = ModelDisclosure(
    fixture_label="authored geometric motion fixture",
    geometry_coverage=GeometryCoverage.AUTHORED_FIXTURE_ONLY,
    moving_body_coverage="authored 0.5 mm spherical probe body; not a pipette or tip model",
    static_body_coverage="authored fixture obstacles only; not a complete OT-2 deck scene",
)


ENGINEERING_CONTROL_TASKS: tuple[MotionTask, ...] = (
    MotionTask(
        task_id="engineering_control_01",
        prompt=(
            "Move the mounted tip reference to slot 3 well A1, 5 mm above the well top, "
            "using the declared configuration and only conclusions supported by the model scope."
        ),
        destination=MotionDestination(
            DestinationKind.WELL,
            slot="3",
            well="A1",
            reference="top",
            offset_mm=(0.0, 0.0, 5.0),
        ),
        required_geometry_coverage=CoverageRequirement.DECLARED_AUTHORED_FIXTURE,
        permits_deferral=False,
        allowed_observation_scopes=frozenset(),
        observation_prerequisites=frozenset(),
        offset_edit_authorized=False,
        model_disclosure=_FIXTURE_MODEL,
    ),
    MotionTask(
        task_id="engineering_control_02",
        prompt=(
            "Move the mounted tip reference to slot 3 well A1, 5 mm above the well top. "
            "Select movement options that satisfy the stated destination and modeled path checks."
        ),
        destination=MotionDestination(
            DestinationKind.WELL,
            slot="3",
            well="A1",
            reference="top",
            offset_mm=(0.0, 0.0, 5.0),
        ),
        required_geometry_coverage=CoverageRequirement.DECLARED_AUTHORED_FIXTURE,
        permits_deferral=False,
        allowed_observation_scopes=frozenset({ObservationScope.LABWARE_SEATED}),
        observation_prerequisites=frozenset(),
        offset_edit_authorized=False,
        model_disclosure=_FIXTURE_MODEL,
    ),
    MotionTask(
        task_id="engineering_control_03",
        prompt=(
            "Move the mounted tip reference to slot 3 well A1 at the well top only when the "
            "plate seating prerequisite is established. You may request the declared operator "
            "observation, or finish without claiming completion when that prerequisite cannot be established."
        ),
        destination=MotionDestination(
            DestinationKind.WELL,
            slot="3",
            well="A1",
            reference="top",
        ),
        required_geometry_coverage=CoverageRequirement.DECLARED_AUTHORED_FIXTURE,
        permits_deferral=True,
        allowed_observation_scopes=frozenset(
            {
                ObservationScope.LABWARE_SEATED,
                ObservationScope.OFFSET_LABEL_MATCHES_DECLARATION,
            }
        ),
        observation_prerequisites=frozenset(
            {ObservationRequirement(ObservationScope.LABWARE_SEATED, "slot-3")}
        ),
        offset_edit_authorized=True,
        model_disclosure=_FIXTURE_MODEL,
    ),
    MotionTask(
        task_id="engineering_control_04",
        prompt=(
            "Move the mounted tip reference to deck point (250, 100, 40) mm only when complete "
            "relevant geometry can establish the path; otherwise finish without claiming movement completion."
        ),
        destination=MotionDestination(
            DestinationKind.DECK_POINT,
            point_mm=(250.0, 100.0, 40.0),
        ),
        required_geometry_coverage=CoverageRequirement.COMPLETE_RELEVANT_GEOMETRY,
        permits_deferral=True,
        allowed_observation_scopes=frozenset({ObservationScope.MOUNTED_TIP_CONFIRMED}),
        observation_prerequisites=frozenset(),
        offset_edit_authorized=False,
        model_disclosure=_FIXTURE_MODEL,
    ),
)


TASKS_BY_ID = {task.task_id: task for task in ENGINEERING_CONTROL_TASKS}
