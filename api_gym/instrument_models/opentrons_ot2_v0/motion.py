"""Native OT-2 motion records and critical-point geometry anchoring."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from api_gym.instrument_models.geometry.frames import RigidTransform, Vec3, vector_mm
from api_gym.instrument_models.geometry.solids import PlacedSolid, SolidGeometry

Mount = Literal["left", "right"]


def _name(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _mount(value: str) -> Mount:
    if value not in ("left", "right"):
        raise ValueError("mount must be 'left' or 'right'")
    return value


def critical_point_frame(native_critical_point: str) -> str:
    return f"native-critical-point:{_name(native_critical_point, 'native_critical_point')}"


@dataclass(frozen=True)
class NativeMotionSegment:
    """One ordered native path segment in final, already-offset coordinates."""

    command_id: str
    segment_index: int
    native_frame: str
    native_critical_point: str
    start_mm: Vec3
    end_mm: Vec3
    mount: Mount
    configuration_revision: str
    native_source_version: str
    motion_kind: str = "translation"

    def __post_init__(self) -> None:
        object.__setattr__(self, "command_id", _name(self.command_id, "command_id"))
        if type(self.segment_index) is not int or self.segment_index < 0:
            raise ValueError("segment_index must be a non-negative integer")
        object.__setattr__(self, "native_frame", _name(self.native_frame, "native_frame"))
        object.__setattr__(
            self,
            "native_critical_point",
            _name(self.native_critical_point, "native_critical_point"),
        )
        object.__setattr__(self, "start_mm", vector_mm(self.start_mm))
        object.__setattr__(self, "end_mm", vector_mm(self.end_mm))
        object.__setattr__(self, "mount", _mount(self.mount))
        object.__setattr__(
            self,
            "configuration_revision",
            _name(self.configuration_revision, "configuration_revision"),
        )
        object.__setattr__(
            self,
            "native_source_version",
            _name(self.native_source_version, "native_source_version"),
        )
        object.__setattr__(self, "motion_kind", _name(self.motion_kind, "motion_kind"))


@dataclass(frozen=True)
class AnchoredTool:
    """Tool material located relative to one native critical point."""

    geometry: SolidGeometry
    native_critical_point: str
    critical_from_geometry: RigidTransform

    def __post_init__(self) -> None:
        if not isinstance(self.geometry, SolidGeometry):
            raise TypeError("Anchored tool geometry must be a SolidGeometry")
        if not isinstance(self.critical_from_geometry, RigidTransform):
            raise TypeError("Critical-point anchor must be a RigidTransform")
        object.__setattr__(
            self,
            "native_critical_point",
            _name(self.native_critical_point, "native_critical_point"),
        )
        if self.critical_from_geometry.source_frame != self.geometry.frame:
            raise ValueError("Critical-point anchor must start in the tool geometry frame")
        expected_frame = critical_point_frame(self.native_critical_point)
        if self.critical_from_geometry.target_frame != expected_frame:
            raise ValueError(f"Critical-point anchor must target {expected_frame!r}")


@dataclass(frozen=True)
class SolidMotion:
    geometry: SolidGeometry
    start_pose: RigidTransform
    end_pose: RigidTransform

    def __post_init__(self) -> None:
        if not isinstance(self.geometry, SolidGeometry):
            raise TypeError("Motion geometry must be a SolidGeometry")
        if not isinstance(self.start_pose, RigidTransform) or not isinstance(
            self.end_pose, RigidTransform
        ):
            raise TypeError("Motion endpoint poses must be RigidTransform records")
        if self.start_pose.source_frame != self.geometry.frame:
            raise ValueError("Motion start pose must start in the tool geometry frame")
        if self.end_pose.source_frame != self.geometry.frame:
            raise ValueError("Motion end pose must start in the tool geometry frame")
        if self.start_pose.target_frame != self.end_pose.target_frame:
            raise ValueError("Motion endpoint poses must target the same native frame")

    @property
    def start_solid(self) -> PlacedSolid:
        return PlacedSolid(self.geometry.geometry_id, self.geometry, self.start_pose)


def motion_for_segment(segment: NativeMotionSegment, tool: AnchoredTool) -> SolidMotion:
    """Anchor tool geometry to a native path without applying software offsets.

    The native start and end are treated as authoritative critical-point
    coordinates in ``segment.native_frame``. Configured offsets have already
    affected those coordinates upstream and are intentionally not accepted by
    this function.
    """
    if segment.native_critical_point != tool.native_critical_point:
        raise ValueError("Native segment and tool anchor use different critical points")
    critical_frame = critical_point_frame(segment.native_critical_point)
    start = RigidTransform(
        critical_frame,
        segment.native_frame,
        translation_mm=segment.start_mm,
    ).compose(tool.critical_from_geometry)
    end = RigidTransform(
        critical_frame,
        segment.native_frame,
        translation_mm=segment.end_mm,
    ).compose(tool.critical_from_geometry)
    return SolidMotion(tool.geometry, start, end)
