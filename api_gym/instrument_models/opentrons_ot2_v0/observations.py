"""Allowlisted agent observations for the OT-2 motion model."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from math import isfinite
from string import hexdigits
from typing import Any, Protocol, Sequence


class DeclaredLabwareLike(Protocol):
    labware_id: str
    definition_digest: str
    slot: str
    configured_offset_mm: Sequence[float]


class DeclaredSetupLike(Protocol):
    software_version: str
    pipette_model: str
    mount: str
    labware: Sequence[DeclaredLabwareLike]
    reported_tip_attached: bool
    revision: str


class ObservationScope(str, Enum):
    """Narrow operator facts that this world can deliver."""

    LABWARE_SEATED = "labware_seated"
    OFFSET_LABEL_MATCHES_DECLARATION = "offset_label_matches_declaration"
    MOUNTED_TIP_CONFIRMED = "mounted_tip_confirmed"
    DIMENSION_MM = "dimension_mm"


class GeometryCoverage(str, Enum):
    """Public claim boundary for the geometry used by an episode."""

    AUTHORED_FIXTURE_ONLY = "authored_fixture_only"


@dataclass(frozen=True)
class ModelDisclosure:
    """Agent-visible scope statement; never an identifier for hidden geometry."""

    fixture_label: str
    geometry_coverage: GeometryCoverage
    moving_body_coverage: str
    static_body_coverage: str
    physical_validation: str = "not_performed"

    def __post_init__(self) -> None:
        for name in ("fixture_label", "moving_body_coverage", "static_body_coverage"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must be non-empty")
        if self.physical_validation != "not_performed":
            raise ValueError("The offline OT-2 world has no physical validation record")


@dataclass(frozen=True)
class DimensionObservation:
    dimension_id: str
    value_mm: float
    uncertainty_mm: float

    def __post_init__(self) -> None:
        if not self.dimension_id.strip():
            raise ValueError("dimension_id must be non-empty")
        if not isfinite(self.value_mm):
            raise ValueError("value_mm must be finite")
        if not isfinite(self.uncertainty_mm) or self.uncertainty_mm < 0:
            raise ValueError("uncertainty_mm must be finite and non-negative")


ObservationValue = bool | DimensionObservation


@dataclass(frozen=True)
class OperatorEvidence:
    """One authored or measured fact with an explicit subject and setup scope."""

    observation_id: str
    subject_id: str
    scope: ObservationScope
    value: ObservationValue
    method: str
    observed_at: str
    observed_setup_epoch: str
    evidence_reference: str

    def __post_init__(self) -> None:
        for name in (
            "observation_id",
            "subject_id",
            "method",
            "observed_setup_epoch",
            "evidence_reference",
        ):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must be non-empty")
        if not self.observation_id.startswith("obs_") or any(
            character not in hexdigits for character in self.observation_id[4:]
        ):
            raise ValueError("observation_id must be an opaque obs_<hex> identifier")
        if len(self.observation_id) < 12:
            raise ValueError("observation_id must contain at least eight hexadecimal characters")
        if not self.evidence_reference.startswith("sha256:") or len(
            self.evidence_reference.removeprefix("sha256:")
        ) != 64 or any(
            character not in hexdigits
            for character in self.evidence_reference.removeprefix("sha256:")
        ):
            raise ValueError("evidence_reference must be an opaque sha256:<digest> reference")
        try:
            datetime.fromisoformat(self.observed_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("observed_at must be an ISO-8601 timestamp") from exc
        if self.scope is ObservationScope.DIMENSION_MM:
            if not isinstance(self.value, DimensionObservation):
                raise TypeError("dimension_mm observations require DimensionObservation")
        elif type(self.value) is not bool:
            raise TypeError(f"{self.scope.value} observations require a boolean value")


@dataclass(frozen=True)
class ObservationCatalog:
    """Trusted finite evidence catalog queried by exact scope and subject."""

    records: tuple[OperatorEvidence, ...]

    def __post_init__(self) -> None:
        if len({record.observation_id for record in self.records}) != len(self.records):
            raise ValueError("Operator observation IDs must be unique")

    def request(
        self,
        *,
        scope: ObservationScope,
        subject_id: str,
        allowed_scopes: frozenset[ObservationScope],
        observable_setup_epoch: str,
    ) -> OperatorEvidence:
        if scope not in allowed_scopes:
            raise PermissionError(f"Observation scope is not allowed: {scope.value}")
        matches = [
            record
            for record in self.records
            if record.scope is scope
            and record.subject_id == subject_id
            and record.observed_setup_epoch == observable_setup_epoch
        ]
        if len(matches) != 1:
            raise LookupError(
                f"Expected one supplied {scope.value} observation for {subject_id!r}; "
                f"found {len(matches)}"
            )
        return matches[0]


def project_declared_setup(setup: DeclaredSetupLike) -> dict[str, Any]:
    """Serialize only configured properties explicitly admitted for the agent."""

    labware = []
    for item in setup.labware:
        offset = tuple(float(value) for value in item.configured_offset_mm)
        if len(offset) != 3 or not all(isfinite(value) for value in offset):
            raise ValueError("Configured labware offsets must be finite XYZ vectors")
        labware.append(
            {
                "labware_id": item.labware_id,
                "definition_digest": item.definition_digest,
                "slot": str(item.slot),
                "configured_offset_mm": list(offset),
            }
        )
    return {
        "software_version": setup.software_version,
        "pipette_model": setup.pipette_model,
        "mount": setup.mount,
        "labware": sorted(labware, key=lambda item: item["labware_id"]),
        "reported_tip_attached": bool(setup.reported_tip_attached),
        "setup_revision": setup.revision,
    }


def project_operator_evidence(
    evidence: OperatorEvidence,
    *,
    current_observable_setup_epoch: str,
) -> dict[str, Any]:
    """Project a delivered fact and mark its revision validity explicitly."""

    value: bool | dict[str, Any]
    if isinstance(evidence.value, DimensionObservation):
        value = asdict(evidence.value)
    else:
        value = evidence.value
    return {
        "observation_id": evidence.observation_id,
        "subject_id": evidence.subject_id,
        "scope": evidence.scope.value,
        "value": value,
        "method": evidence.method,
        "observed_at": evidence.observed_at,
        "applicability_basis": "visible_setup_epoch",
        "observed_setup_epoch": evidence.observed_setup_epoch,
        "evidence_reference": evidence.evidence_reference,
        "stale": evidence.observed_setup_epoch != current_observable_setup_epoch,
    }


def project_pre_action_observation(
    setup: DeclaredSetupLike,
    *,
    model: ModelDisclosure,
    observable_setup_epoch: str,
    delivered_evidence: Sequence[OperatorEvidence] = (),
) -> dict[str, Any]:
    """Build the complete pre-action JSON from public inputs only."""

    setup_projection = project_declared_setup(setup)
    return {
        "schema_version": "api_gym.observation.ot2_motion_v0.v1",
        "declared_setup": setup_projection,
        "model_scope": {
            "fixture_label": model.fixture_label,
            "geometry_coverage": model.geometry_coverage.value,
            "moving_body_coverage": model.moving_body_coverage,
            "static_body_coverage": model.static_body_coverage,
            "physical_validation": model.physical_validation,
        },
        "operator_evidence": [
            project_operator_evidence(
                evidence,
                current_observable_setup_epoch=observable_setup_epoch,
            )
            for evidence in delivered_evidence
        ],
    }
