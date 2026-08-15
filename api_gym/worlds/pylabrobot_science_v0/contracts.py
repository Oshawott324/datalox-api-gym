"""Public task contracts for the instrument-rich science workflows."""

from __future__ import annotations

from typing import Any


THERMOCYCLER_SCENARIO = "qpcr_amplification_qc"
INCUBATOR_SCENARIO = "incubator_growth_campaign"
POWDER_SCENARIO = "gravimetric_powder_formulation"

SCENARIO_CONTRACTS: dict[str, dict[str, Any]] = {
    THERMOCYCLER_SCENARIO: {
        "family": "thermocycler",
        "objective": "Run a qPCR thermal program and accept only a control-valid amplification result.",
        "prompt": (
            "Run the loaded qPCR plate with the specified heated-lid profile. Complete the "
            "thermal program, inspect the amplification result, and submit whether the run is "
            "usable. A usable run requires amplification of the positive control and both samples, "
            "with no amplification in the no-template control."
        ),
        "plate_id": "qpcr_plate_01",
        "lid_temperature_c": 105.0,
        "block_max_volume_ul": 25.0,
        "protocol": [
            {
                "label": "initial_denaturation",
                "repeats": 1,
                "steps": [{"label": "denature", "temperature_c": 95.0, "hold_seconds": 120.0}],
            },
            {
                "label": "amplification",
                "repeats": 40,
                "steps": [
                    {"label": "denature", "temperature_c": 95.0, "hold_seconds": 15.0},
                    {"label": "anneal_extend", "temperature_c": 60.0, "hold_seconds": 30.0},
                ],
            },
            {
                "label": "final_extension",
                "repeats": 1,
                "steps": [{"label": "extend", "temperature_c": 72.0, "hold_seconds": 60.0}],
            },
        ],
        "amplification_wells": {
            "A1": {"role": "positive_control", "ct": 22.8},
            "A2": {"role": "no_template_control", "ct": None},
            "B1": {"role": "sample_1", "ct": 27.4},
            "B2": {"role": "sample_2", "ct": 29.1},
        },
        "projection_notes": {
            "thermal_program": "Executed through the installed PyLabRobot Thermocycler.run_protocol interface.",
            "logical_time": "Benchmark-defined acceleration of a fire-and-forget thermal program.",
            "amplification": "Deterministic benchmark artifact; generic PyLabRobot thermocyclers do not expose qPCR fluorescence.",
        },
    },
    INCUBATOR_SCENARIO: {
        "family": "incubator_shaker",
        "objective": "Run an eight-hour shaking-incubation campaign with complete OD600 timepoints.",
        "prompt": (
            "Track culture plate CULTURE-BC-1042 from baseline through eight hours. Incubate at "
            "30 C with orbital shaking at 250 rpm, measure OD600 at 0, 2, 4, 6, and 8 hours, "
            "and submit the final growth-series decision using the last measurement as evidence."
        ),
        "plate_id": "culture_plate_01",
        "barcode": "CULTURE-BC-1042",
        "storage_slot": "S04",
        "temperature_c": 30.0,
        "temperature_tolerance_c": 0.5,
        "temperature_ramp_c_per_s": 0.02,
        "shake_rpm": 250.0,
        "measurement_times_s": [0.0, 7200.0, 14400.0, 21600.0, 28800.0],
        "cadence_tolerance_s": 90.0,
        "minimum_conditioned_exposure_s": 28200.0,
        "measurement_duration_s": 45.0,
        "projection_notes": {
            "incubator_controls": "Temperature and shaking use installed PyLabRobot Incubator interfaces.",
            "storage_and_clock": "Slot inventory, transfer time, and accelerated logical time are benchmark-defined.",
            "measurements": "OD600 values are deterministic growth-shaped benchmark artifacts from a separate reader surface.",
        },
    },
    POWDER_SCENARIO: {
        "family": "powder_balance",
        "objective": "Formulate one vial to a gravimetrically verified powder target.",
        "prompt": (
            "Prepare formulation vial FORM-001 with 150.0 mg of L-leucine. Tare the analytical "
            "balance, use one or more powder-dispense pulses, reweigh after dosing, and accept only "
            "when the measured net mass is within +/-0.5 mg of target."
        ),
        "vial_id": "FORM-001",
        "powder": "L-leucine",
        "target_mass_mg": 150.0,
        "tolerance_mg": 0.5,
        "empty_vial_mass_g": 12.4832,
        "max_pulse_mg": 150.0,
        "projection_notes": {
            "dispense_interface": "Each pulse calls the installed PyLabRobot PowderDispenser.dispense interface.",
            "balance_interface": "Tare and weight reads call the installed PyLabRobot Scale interface.",
            "delivery_error": "Pulse delivery and balance noise are deterministic benchmark-defined dynamics, not vendor accuracy claims.",
        },
    },
}

