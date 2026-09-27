"""Separate visible software configuration from trusted physical geometry."""

from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
from string import hexdigits
from typing import Iterable

from api_gym.instrument_models.geometry.frames import RigidTransform, Vec3, vector_mm
from api_gym.instrument_models.geometry.solids import PlacedSolid

from .motion import AnchoredTool, Mount


def _name(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _digest(value: str, field_name: str) -> str:
    if len(value) != 64 or any(character not in hexdigits for character in value):
        raise ValueError(f"{field_name} must be a 64-character hexadecimal digest")
    return value.lower()


def _hash(values: Iterable[str]) -> str:
    result = sha256()
    for value in values:
        encoded = value.encode("utf-8")
        result.update(len(encoded).to_bytes(8, "big"))
        result.update(encoded)
    return result.hexdigest()


@dataclass(frozen=True)
class DeclaredLabware:
    labware_id: str
    definition_digest: str
    slot: str
    configured_offset_mm: Vec3 = (0.0, 0.0, 0.0)

    def __post_init__(self) -> None:
        object.__setattr__(self, "labware_id", _name(self.labware_id, "labware_id"))
        object.__setattr__(
            self,
            "definition_digest",
            _digest(self.definition_digest, "definition_digest"),
        )
        object.__setattr__(self, "slot", _name(self.slot, "slot"))
        object.__setattr__(self, "configured_offset_mm", vector_mm(self.configured_offset_mm))


@dataclass(frozen=True)
class DeclaredSetup:
    """Software-reported setup suitable for an explicit agent projection."""

    software_version: str
    pipette_model: str
    mount: Mount
    labware: tuple[DeclaredLabware, ...]
    reported_tip_attached: bool
    revision: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "software_version", _name(self.software_version, "software_version"))
        object.__setattr__(self, "pipette_model", _name(self.pipette_model, "pipette_model"))
        if self.mount not in ("left", "right"):
            raise ValueError("mount must be 'left' or 'right'")
        labware = tuple(self.labware)
        if not all(isinstance(item, DeclaredLabware) for item in labware):
            raise TypeError("labware must contain DeclaredLabware records")
        if len({item.labware_id for item in labware}) != len(labware):
            raise ValueError("Declared labware IDs must be unique")
        if len({item.slot for item in labware}) != len(labware):
            raise ValueError("Declared labware slots must be unique")
        if type(self.reported_tip_attached) is not bool:
            raise TypeError("reported_tip_attached must be a bool")
        object.__setattr__(self, "labware", labware)
        object.__setattr__(self, "revision", _name(self.revision, "revision"))

    @property
    def configuration_digest(self) -> str:
        values = [
            "ot2-declared-setup-v1",
            self.software_version,
            self.pipette_model,
            self.mount,
            str(self.reported_tip_attached),
            self.revision,
        ]
        for item in self.labware:
            values.extend(
                (
                    item.labware_id,
                    item.definition_digest,
                    item.slot,
                    *(component.hex() for component in item.configured_offset_mm),
                )
            )
        return _hash(values)

    def with_labware_offset(
        self,
        labware_id: str,
        offset_mm: Vec3,
        *,
        revision: str,
    ) -> DeclaredSetup:
        offset = vector_mm(offset_mm)
        next_revision = _name(revision, "revision")
        found = False
        changed = False
        updated = []
        for item in self.labware:
            if item.labware_id == labware_id:
                changed = item.configured_offset_mm != offset
                item = replace(item, configured_offset_mm=offset)
                found = True
            updated.append(item)
        if not found:
            raise KeyError(f"Unknown declared labware {labware_id!r}")
        if changed and next_revision == self.revision:
            raise ValueError("Changing a declared offset requires a new setup revision")
        return replace(self, labware=tuple(updated), revision=next_revision)


@dataclass(frozen=True)
class PhysicalComponent:
    """Trusted modeled material, or an explicit missing-geometry record."""

    component_id: str
    solid: PlacedSolid | None
    missing_geometry_reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "component_id", _name(self.component_id, "component_id"))
        if self.solid is not None and not isinstance(self.solid, PlacedSolid):
            raise TypeError("Physical component solid must be a PlacedSolid or None")
        if self.solid is None:
            if self.missing_geometry_reason is None:
                raise ValueError("A component without a solid needs a missing-geometry reason")
            object.__setattr__(
                self,
                "missing_geometry_reason",
                _name(self.missing_geometry_reason, "missing_geometry_reason"),
            )
        elif self.missing_geometry_reason is not None:
            raise ValueError("A modeled component cannot also be marked missing")
        elif self.solid.instance_id != self.component_id:
            raise ValueError("Physical component ID must match its placed-solid instance ID")


@dataclass(frozen=True)
class PhysicalSetup:
    """Trusted actual placement and collision coverage, never agent-visible."""

    static_components: tuple[PhysicalComponent, ...]
    moving_tool: AnchoredTool | None
    revision: str

    def __post_init__(self) -> None:
        components = tuple(self.static_components)
        if not all(isinstance(component, PhysicalComponent) for component in components):
            raise TypeError("static_components must contain PhysicalComponent records")
        if self.moving_tool is not None and not isinstance(self.moving_tool, AnchoredTool):
            raise TypeError("moving_tool must be an AnchoredTool or None")
        if len({component.component_id for component in components}) != len(components):
            raise ValueError("Physical component IDs must be unique")
        object.__setattr__(self, "static_components", components)
        object.__setattr__(self, "revision", _name(self.revision, "revision"))

    @property
    def physical_digest(self) -> str:
        values = ["ot2-physical-setup-v1", self.revision]
        if self.moving_tool is None:
            values.append("missing-moving-tool")
        else:
            values.extend(
                (
                    self.moving_tool.geometry.geometry_digest,
                    self.moving_tool.native_critical_point,
                    self.moving_tool.critical_from_geometry.digest,
                )
            )
        for component in self.static_components:
            values.extend(
                (
                    component.component_id,
                    component.solid.placement_digest if component.solid else "missing",
                    component.missing_geometry_reason or "",
                )
            )
        return _hash(values)

    def with_component_pose(
        self,
        component_id: str,
        pose: RigidTransform,
        *,
        revision: str,
    ) -> PhysicalSetup:
        next_revision = _name(revision, "revision")
        found = False
        changed = False
        updated = []
        for component in self.static_components:
            if component.component_id == component_id:
                if component.solid is None:
                    raise ValueError(f"Cannot place missing geometry {component_id!r}")
                changed = component.solid.pose != pose
                component = replace(component, solid=component.solid.with_pose(pose))
                found = True
            updated.append(component)
        if not found:
            raise KeyError(f"Unknown physical component {component_id!r}")
        if changed and next_revision == self.revision:
            raise ValueError("Changing a physical placement requires a new setup revision")
        return replace(self, static_components=tuple(updated), revision=next_revision)
