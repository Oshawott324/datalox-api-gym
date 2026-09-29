"""Agent-visible Phase 3 assignment without a hidden solution sequence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .defaults import MAX_ASSAY_PLATES, MAX_LOGICAL_TIME_S, MAX_PLATE_TRANSFERS
from .scenarios import ScenarioDefinition


@dataclass(frozen=True)
class AssayTask:
    task_id: str
    title: str
    instructions: str
    success_criteria: tuple[str, ...]
    public_resources: dict[str, Any]


def task_for_scenario(scenario: ScenarioDefinition) -> AssayTask:
    context = " ".join(scenario.public_context)
    return AssayTask(
        task_id=scenario.scenario_id,
        title=scenario.public_title,
        instructions=(
            "Prepare SAMPLE-A, the matched BLANK, and REF-AP from the declared stocks. "
            "Request operator-confirmed transfer of the identified plate, acquire modeled "
            "405 nm observations at 37 degC, and report a supported blank-corrected relative "
            "rate or an evidence-backed unresolved disposition. "
            f"{context}"
        ),
        success_criteria=(
            "Use confirmed native liquid actions and no more than 2 assay plates, 2 operator transfers, and 900 logical seconds.",
            "Use at least four acquired numeric observations spanning at least 90 seconds for each fitted well.",
            "Every cited absorbance must be within the modeled linear-analysis interval from 0.02 through 1.5; if no valid window remains, use a fresh reaction rather than spent material.",
            "Cite sample, matched blank, and REF-AP measurements from the same plate revision and reader settings.",
            "Fit each cited well by unweighted ordinary least squares against its actual timestamps; subtract the blank slope, convert seconds to minutes, and apply the lineage dilution factor.",
            "Combine sample and blank slope standard errors in quadrature and apply the same time and dilution factors.",
            "Apply only the dilution factor supported by preparation lineage and report delta_absorbance_per_minute.",
            "A usable result requires a blank-corrected REF-AP rate from 0.01 through 0.08 delta_absorbance_per_minute and relative standard error no greater than 0.25.",
            "Do not replace missing or overrange observations with numeric values.",
            "Report submission is terminal; validate the selected evidence and complete any fresh-reaction recovery before submitting exactly one report.",
        ),
        public_resources={
            "sample_ids": ["SAMPLE-A"],
            "control_ids": ["BLANK", "REF-AP"],
            "preparation_constraints": {
                "reaction_volume_interval_ul": [80.0, 200.0],
                "substrate_stock_fraction_of_final_reaction": 0.5,
                "standard_reaction_composition_ul": {
                    "SAMPLE-A": {"SAMPLE-A-stock": 50.0, "substrate-stock": 50.0},
                    "BLANK": {"assay-buffer": 50.0, "substrate-stock": 50.0},
                    "REF-AP": {"REF-AP-stock": 50.0, "substrate-stock": 50.0},
                },
                "standard_sample_reporting_dilution_factor": 1.0,
                "dilution_interpretation": (
                    "The 1:1 assay-reagent mixture is the declared undiluted baseline, so "
                    "50 uL SAMPLE-A-stock plus 50 uL substrate-stock has reporting dilution "
                    "factor 1. Added assay buffer that replaces SAMPLE-A-stock increases the "
                    "factor according to preparation lineage."
                ),
                "fresh_diluted_sample_example_ul": {
                    "SAMPLE-A-stock": 25.0,
                    "assay-buffer": 25.0,
                    "substrate-stock": 50.0,
                    "supported_dilution_factor": 2.0,
                },
            },
            "usable_absorbance_interval": [0.02, 1.5],
            "assay_plates": MAX_ASSAY_PLATES,
            "maximum_logical_time_s": MAX_LOGICAL_TIME_S,
            "plate_transfers": MAX_PLATE_TRANSFERS,
            "reporting_units": ["delta_absorbance_per_minute"],
        },
    )


__all__ = ["AssayTask", "task_for_scenario"]
