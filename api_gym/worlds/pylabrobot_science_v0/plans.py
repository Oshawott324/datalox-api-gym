"""Deterministic reference plans used for workflow admission and visual demos."""

from __future__ import annotations

from typing import Any

from .contracts import INCUBATOR_SCENARIO, POWDER_SCENARIO, THERMOCYCLER_SCENARIO


Action = dict[str, Any]


def action(name: str, **arguments: Any) -> Action:
    return {"name": name, "arguments": arguments}


ORACLE_PLANS: dict[str, list[Action]] = {
    THERMOCYCLER_SCENARIO: [
        action("inspect_science_workcell"),
        action("thermocycler_close_lid"),
        action("thermocycler_set_lid_temperature", temperature_c=105.0),
        action("thermocycler_start_protocol"),
        action("thermocycler_advance_time", seconds=120.0),
        action("thermocycler_advance_time", seconds=450.0),
        action("thermocycler_advance_time", seconds=450.0),
        action("thermocycler_advance_time", seconds=450.0),
        action("thermocycler_advance_time", seconds=450.0),
        action("thermocycler_advance_time", seconds=60.0),
        action("thermocycler_get_status"),
        action("qpcr_read_amplification"),
        action("thermocycler_open_lid"),
        action(
            "submit_science_decision",
            decision="accept",
            evidence_id="qpcr-amplification-001",
            rationale="Positive control and both samples amplify while the no-template control remains negative.",
        ),
    ],
    INCUBATOR_SCENARIO: [
        action("inspect_science_workcell"),
        action("reader_measure_od600"),
        action("incubator_set_temperature", temperature_c=30.0),
        action("incubator_start_shaking", rpm=250.0),
        action("incubator_store_plate", slot="S04"),
        action("incubator_advance_time", seconds=7200.0),
        action("incubator_get_status"),
        action("incubator_retrieve_plate"),
        action("reader_measure_od600"),
        action("incubator_store_plate", slot="S04"),
        action("incubator_advance_time", seconds=7200.0),
        action("incubator_retrieve_plate"),
        action("reader_measure_od600"),
        action("incubator_store_plate", slot="S04"),
        action("incubator_advance_time", seconds=7200.0),
        action("incubator_retrieve_plate"),
        action("reader_measure_od600"),
        action("incubator_store_plate", slot="S04"),
        action("incubator_advance_time", seconds=7200.0),
        action("incubator_retrieve_plate"),
        action("reader_measure_od600"),
        action(
            "submit_science_decision",
            decision="accept",
            evidence_id="od600-005",
            rationale="The five timepoints cover eight hours and show a consistent increase across all replicates.",
        ),
    ],
    POWDER_SCENARIO: [
        action("inspect_science_workcell"),
        action("balance_tare"),
        action("formulation_move_vial", destination="powder_dispenser"),
        action("powder_dispense_pulse", amount_mg=150.0),
        action("formulation_move_vial", destination="balance"),
        action("balance_read_mass"),
        action("formulation_move_vial", destination="powder_dispenser"),
        action("powder_dispense_pulse", amount_mg=2.1),
        action("formulation_move_vial", destination="balance"),
        action("balance_read_mass"),
        action(
            "submit_science_decision",
            decision="accept",
            evidence_id="gravimetric-002",
            rationale="The correction pulse brought the measured net mass inside the +/-0.5 mg target band.",
        ),
    ],
}


def run_plan(run_dir: Any, plan: list[Action]) -> list[dict[str, Any]]:
    from .tools import dispatch_tool

    results = []
    for item in plan:
        result = dispatch_tool(run_dir, name=item["name"], arguments=item["arguments"])
        results.append({**item, "result": result})
        if not result["ok"]:
            break
    return results
