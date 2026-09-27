from __future__ import annotations

import json

import pytest

from api_gym.instrument_models.opentrons_ot2_v0.configuration import (
    DeclaredLabware,
    DeclaredSetup,
)
from api_gym.instrument_models.opentrons_ot2_v0.observations import (
    GeometryCoverage,
    ModelDisclosure,
    ObservationCatalog,
    ObservationScope,
    OperatorEvidence,
    project_operator_evidence,
    project_pre_action_observation,
)


def _setup(revision: str = "configuration-1") -> DeclaredSetup:
    return DeclaredSetup(
        software_version="9.1.1",
        pipette_model="p300_single_v2.1",
        mount="left",
        labware=(
            DeclaredLabware("plate", "a" * 64, "1", (1.0, -2.0, 0.5)),
            DeclaredLabware("tiprack", "b" * 64, "5"),
        ),
        reported_tip_attached=True,
        revision=revision,
    )


def _model() -> ModelDisclosure:
    return ModelDisclosure(
        fixture_label="authored geometric motion fixture",
        geometry_coverage=GeometryCoverage.AUTHORED_FIXTURE_ONLY,
        moving_body_coverage="authored sphere; not pipette geometry",
        static_body_coverage="authored obstacles; incomplete instrument scene",
    )


def _evidence(*, epoch: str = "visible-epoch-1", value: bool = True) -> OperatorEvidence:
    return OperatorEvidence(
        observation_id="obs_0123456789abcdef",
        subject_id="plate",
        scope=ObservationScope.LABWARE_SEATED,
        value=value,
        method="authored operator-control record",
        observed_at="2026-09-27T12:00:00Z",
        observed_setup_epoch=epoch,
        evidence_reference=f"sha256:{'c' * 64}",
    )


def test_declared_setup_projection_is_an_explicit_allowlist() -> None:
    projected = project_pre_action_observation(
        _setup(),
        model=_model(),
        observable_setup_epoch="visible-epoch-1",
    )
    assert set(projected) == {
        "schema_version",
        "declared_setup",
        "model_scope",
        "operator_evidence",
    }
    assert set(projected["declared_setup"]) == {
        "software_version",
        "pipette_model",
        "mount",
        "labware",
        "reported_tip_attached",
        "setup_revision",
    }
    serialized = json.dumps(projected, sort_keys=True)
    for forbidden in (
        '"family"',
        '"scene_digest"',
        '"physical_setup_revision"',
        '"actual_transform"',
        '"path_check"',
        '"oracle"',
    ):
        assert forbidden not in serialized
    assert projected["model_scope"]["geometry_coverage"] == "authored_fixture_only"
    assert "not pipette geometry" in projected["model_scope"]["moving_body_coverage"]


def test_visible_setup_epoch_controls_staleness_not_hidden_physical_revision() -> None:
    evidence = _evidence(epoch="visible-epoch-1")
    current = project_operator_evidence(
        evidence,
        current_observable_setup_epoch="visible-epoch-1",
    )
    stale = project_operator_evidence(
        evidence,
        current_observable_setup_epoch="visible-epoch-2",
    )
    assert current["stale"] is False
    assert stale["stale"] is True
    assert current["applicability_basis"] == "visible_setup_epoch"
    assert "physical" not in json.dumps(current)


def test_observation_catalog_allows_only_exact_task_scopes_and_subjects() -> None:
    catalog = ObservationCatalog((_evidence(),))
    delivered = catalog.request(
        scope=ObservationScope.LABWARE_SEATED,
        subject_id="plate",
        allowed_scopes=frozenset({ObservationScope.LABWARE_SEATED}),
        observable_setup_epoch="visible-epoch-1",
    )
    assert delivered.observation_id == "obs_0123456789abcdef"
    with pytest.raises(PermissionError):
        catalog.request(
            scope=ObservationScope.DIMENSION_MM,
            subject_id="plate",
            allowed_scopes=frozenset({ObservationScope.LABWARE_SEATED}),
            observable_setup_epoch="visible-epoch-1",
        )
    with pytest.raises(LookupError):
        catalog.request(
            scope=ObservationScope.LABWARE_SEATED,
            subject_id="unknown-labware",
            allowed_scopes=frozenset({ObservationScope.LABWARE_SEATED}),
            observable_setup_epoch="visible-epoch-1",
        )


def test_observation_catalog_does_not_deliver_future_epoch_records() -> None:
    future = _evidence(epoch="visible-epoch-2")
    catalog = ObservationCatalog((future,))
    with pytest.raises(LookupError):
        catalog.request(
            scope=ObservationScope.LABWARE_SEATED,
            subject_id="plate",
            allowed_scopes=frozenset({ObservationScope.LABWARE_SEATED}),
            observable_setup_epoch="visible-epoch-1",
        )


@pytest.mark.parametrize(
    ("observation_id", "reference"),
    [
        ("hazard-route", f"sha256:{'d' * 64}"),
        ("obs_0123456789abcdef", "task-family-unsafe"),
    ],
)
def test_operator_evidence_identifiers_are_opaque(observation_id: str, reference: str) -> None:
    with pytest.raises(ValueError):
        OperatorEvidence(
            observation_id=observation_id,
            subject_id="plate",
            scope=ObservationScope.LABWARE_SEATED,
            value=True,
            method="authored operator-control record",
            observed_at="2026-09-27T12:00:00Z",
            observed_setup_epoch="visible-epoch-1",
            evidence_reference=reference,
        )
