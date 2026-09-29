"""Frozen Phase 3 scenario catalogue for enzyme activity v0.

Scenario definitions deliberately keep the agent-visible assignment separate
from trusted initial conditions and fault scheduling.  The latter are consumed
only by the world implementation and verifier fixtures.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True)
class ScenarioDefinition:
    scenario_id: str
    family: str
    seed: int
    public_title: str
    public_context: tuple[str, ...]
    private_initial_conditions: Mapping[str, Any]
    private_events: Mapping[str, Any]
    expected_mutant_failure_code: str
    usable_result_feasible: bool

    def __post_init__(self) -> None:
        if not self.scenario_id or not self.family or type(self.seed) is not int:
            raise ValueError("scenario identity, family, and integer seed are required")
        if not self.public_title or not self.public_context:
            raise ValueError("agent-visible scenario material is required")
        object.__setattr__(
            self,
            "private_initial_conditions",
            MappingProxyType(dict(self.private_initial_conditions)),
        )
        object.__setattr__(
            self, "private_events", MappingProxyType(dict(self.private_events))
        )


_COMMON_INITIAL = {
    "sample_enzyme_concentration_mM": 0.002,
    "reference_enzyme_concentration_mM": 0.0015,
    "blank_drift_abs_per_s": 0.00001,
}


SCENARIOS: tuple[ScenarioDefinition, ...] = (
    ScenarioDefinition(
        scenario_id="enzyme-activity-nominal-01",
        family="nominal_measurement",
        seed=1729,
        public_title="Measure modeled enzyme activity",
        public_context=(
            "A second fresh assay plate and transfer are available when the first reaction is unsuitable.",
        ),
        private_initial_conditions=_COMMON_INITIAL,
        private_events={"transfer_delay_s": 5.0, "missing_measurement_indices": ()},
        expected_mutant_failure_code="fit_window_invalid",
        usable_result_feasible=True,
    ),
    ScenarioDefinition(
        scenario_id="enzyme-activity-high-01",
        family="high_activity_unsuitable_range",
        seed=1730,
        public_title="Measure modeled enzyme activity",
        public_context=(
            "Inspect the full kinetic trace before choosing a fit window.",
        ),
        private_initial_conditions={
            **_COMMON_INITIAL,
            "sample_enzyme_concentration_mM": 0.06,
        },
        private_events={"transfer_delay_s": 5.0, "missing_measurement_indices": ()},
        expected_mutant_failure_code="fit_window_invalid",
        usable_result_feasible=True,
    ),
    ScenarioDefinition(
        scenario_id="enzyme-activity-delayed-01",
        family="delayed_acquisition",
        seed=1731,
        public_title="Measure modeled enzyme activity",
        public_context=("Operator transfers and reader access can take logical time.",),
        private_initial_conditions=_COMMON_INITIAL,
        private_events={"transfer_delay_s": 125.0, "missing_measurement_indices": ()},
        expected_mutant_failure_code="fit_window_invalid",
        usable_result_feasible=True,
    ),
    ScenarioDefinition(
        scenario_id="enzyme-activity-interrupted-01",
        family="interrupted_series",
        seed=1732,
        public_title="Measure modeled enzyme activity",
        public_context=("Acquisition status must be checked before analysis.",),
        private_initial_conditions=_COMMON_INITIAL,
        private_events={
            "transfer_delay_s": 5.0,
            "missing_measurement_indices": (3, 7),
        },
        expected_mutant_failure_code="measurement_reference_invalid",
        usable_result_feasible=True,
    ),
    ScenarioDefinition(
        scenario_id="enzyme-activity-background-01",
        family="reagent_background",
        seed=1733,
        public_title="Measure modeled enzyme activity",
        public_context=(
            "Matched blank and reference-control wells are supplied by the SOP.",
        ),
        private_initial_conditions={
            **_COMMON_INITIAL,
            "blank_drift_abs_per_s": 0.0004,
        },
        private_events={"transfer_delay_s": 5.0, "missing_measurement_indices": ()},
        expected_mutant_failure_code="blank_evidence_missing",
        usable_result_feasible=True,
    ),
    ScenarioDefinition(
        scenario_id="enzyme-activity-lineage-01",
        family="sample_plate_lineage",
        seed=1734,
        public_title="Measure modeled enzyme activity",
        public_context=(
            "Plate identity and revision are confirmed at transfer and acquisition.",
        ),
        private_initial_conditions=_COMMON_INITIAL,
        private_events={
            "transfer_delay_s": 5.0,
            "missing_measurement_indices": (),
            "observed_transfer_plate_id": "assay-plate-unexpected",
        },
        expected_mutant_failure_code="plate_lineage_mismatch",
        usable_result_feasible=True,
    ),
)

_BY_ID = {scenario.scenario_id: scenario for scenario in SCENARIOS}


def scenario_for_id(scenario_id: str) -> ScenarioDefinition:
    try:
        return _BY_ID[scenario_id]
    except KeyError as exc:
        raise ValueError(f"unknown enzyme activity scenario {scenario_id!r}") from exc


__all__ = ["SCENARIOS", "ScenarioDefinition", "scenario_for_id"]
