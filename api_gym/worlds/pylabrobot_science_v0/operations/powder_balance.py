"""Powder-dispenser and analytical-balance operations."""

from __future__ import annotations

from typing import Any

from pylabrobot.powder_dispensing import PowderDispenser
from pylabrobot.resources import Resource
from pylabrobot.resources.powder import Powder
from pylabrobot.scales import Scale

from ..backends import BalanceProjectionBackend, PowderPulseBackend
from ..dynamics import balance_noise_g, powder_delivery
from ..state import insert_artifact, insert_event, load_state, save_state
from .common import Handler, error, ok, require_family, run_async, tool_definition


TOOL_DEFINITIONS = [
    tool_definition(
        "balance_tare",
        "Tare the vial through PyLabRobot Scale.tare().",
        {},
        [],
    ),
    tool_definition(
        "formulation_move_vial",
        "Move the formulation vial between the balance and powder dispenser stations.",
        {
            "destination": {
                "type": "string",
                "enum": ["balance", "powder_dispenser"],
            }
        },
        ["destination"],
    ),
    tool_definition(
        "powder_dispense_pulse",
        "Request one powder dose through PyLabRobot PowderDispenser.dispense().",
        {
            "amount_mg": {
                "type": "number",
                "exclusiveMinimum": 0,
                "maximum": 150,
            }
        },
        ["amount_mg"],
    ),
    tool_definition(
        "balance_read_mass",
        "Read net vial mass through PyLabRobot Scale.get_weight().",
        {},
        [],
    ),
]


def _balance(
    state: dict[str, Any],
) -> tuple[Scale, BalanceProjectionBackend]:
    gross_mass_g = (
        float(state["vial"]["empty_mass_g"])
        + float(state["vial"]["powder_mass_mg"]) / 1000.0
    )
    backend = BalanceProjectionBackend(
        gross_mass_g=gross_mass_g,
        tare_offset_g=float(state["balance"]["tare_offset_g"]),
    )
    scale = Scale(
        name="analytical_balance",
        size_x=200,
        size_y=300,
        size_z=150,
        backend=backend,
    )
    run_async(scale.setup())
    return scale, backend


def _tare(
    conn: Any,
    _arguments: dict[str, Any],
    _contract: dict[str, Any],
) -> dict[str, Any]:
    state = load_state(conn)
    invalid = require_family(state, "powder_balance")
    if invalid:
        return invalid
    if not state["vial"]["on_balance"]:
        return error(
            "vial_not_on_balance",
            "Move the vial to the balance before taring.",
        )
    scale, backend = _balance(state)
    run_async(scale.tare())
    state["balance"]["tare_offset_g"] = backend.tare_offset_g
    state["balance"]["tared"] = True
    save_state(conn, state)
    payload = {"tared": True, "tare_offset_g": round(backend.tare_offset_g, 4)}
    insert_event(
        conn,
        operation="balance.tared",
        time_s=state["clock_s"],
        payload=payload,
    )
    return ok(payload)


def _move_vial(
    conn: Any,
    arguments: dict[str, Any],
    _contract: dict[str, Any],
) -> dict[str, Any]:
    state = load_state(conn)
    invalid = require_family(state, "powder_balance")
    if invalid:
        return invalid
    destination = str(arguments["destination"])
    if destination not in {"balance", "powder_dispenser"}:
        return error(
            "unknown_formulation_station",
            "Destination must be balance or powder_dispenser.",
        )
    current = "balance" if state["vial"]["on_balance"] else "powder_dispenser"
    if current == destination:
        return error(
            "vial_already_at_station",
            "The vial is already at the requested station.",
            station=current,
        )
    state["vial"]["on_balance"] = destination == "balance"
    state["clock_s"] += 3.0
    save_state(conn, state)
    payload = {
        "vial_id": state["vial"]["vial_id"],
        "from": current,
        "to": destination,
    }
    insert_event(
        conn,
        operation="formulation.vial_moved",
        time_s=state["clock_s"],
        payload=payload,
    )
    return ok(payload)


def _dispense_pulse(
    conn: Any,
    arguments: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    state = load_state(conn)
    invalid = require_family(state, "powder_balance")
    if invalid:
        return invalid
    if state["vial"]["on_balance"]:
        return error(
            "vial_not_at_dispenser",
            "Move the vial to the powder dispenser before dosing.",
        )
    if not state["balance"]["tared"]:
        return error(
            "balance_not_tared",
            "Tare the empty vial before the first powder pulse.",
        )
    requested = float(arguments["amount_mg"])
    if requested <= 0 or requested > float(contract["max_pulse_mg"]):
        return error(
            "invalid_powder_pulse",
            "Requested pulse is outside the configured range.",
        )
    pulse_index = int(state["powder_dispenser"]["pulse_count"]) + 1
    actual = powder_delivery(requested_mg=requested, pulse_index=pulse_index)
    backend = PowderPulseBackend(actual)
    dispenser = PowderDispenser(backend=backend)
    run_async(dispenser.setup())
    target = Resource(
        name=state["vial"]["vial_id"],
        size_x=20,
        size_y=20,
        size_z=40,
    )
    results = run_async(
        dispenser.dispense(
            resources=target,
            powders=Powder(name=state["vial"]["powder"]),
            amounts=float(requested),
        )
    )
    delivered = float(results[0]["actual_amount"])
    state["vial"]["powder_mass_mg"] = round(
        float(state["vial"]["powder_mass_mg"]) + delivered,
        3,
    )
    state["powder_dispenser"]["pulse_count"] = pulse_index
    state["clock_s"] += 2.0
    save_state(conn, state)
    payload = {
        "pulse_index": pulse_index,
        "powder": state["vial"]["powder"],
        "requested_mg": requested,
        "actual_amount_mg": delivered,
        "cumulative_amount_mg": state["vial"]["powder_mass_mg"],
        "grounding": "pylabrobot_powder_dispense_with_benchmark_delivery_projection",
    }
    insert_event(
        conn,
        operation="powder.pulse_dispensed",
        time_s=state["clock_s"],
        payload=payload,
    )
    return ok(payload)


def _read_mass(
    conn: Any,
    _arguments: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    state = load_state(conn)
    invalid = require_family(state, "powder_balance")
    if invalid:
        return invalid
    if not state["vial"]["on_balance"]:
        return error(
            "vial_not_on_balance",
            "Move the vial to the balance before weighing.",
        )
    if not state["balance"]["tared"]:
        return error(
            "balance_not_tared",
            "Tare the balance before reading net powder mass.",
        )
    scale, _backend = _balance(state)
    weight_g = float(run_async(scale.get_weight()))
    state["balance"]["read_count"] += 1
    read_index = int(state["balance"]["read_count"])
    measured_g = weight_g + balance_noise_g(read_index=read_index)
    measured_mg = round(measured_g * 1000.0, 3)
    error_mg = round(measured_mg - float(contract["target_mass_mg"]), 3)
    within_tolerance = abs(error_mg) <= float(contract["tolerance_mg"])
    state["clock_s"] += 1.0
    save_state(conn, state)
    artifact_id = f"gravimetric-{read_index:03d}"
    payload = {
        "artifact_id": artifact_id,
        "vial_id": state["vial"]["vial_id"],
        "powder": state["vial"]["powder"],
        "measured_mass_mg": measured_mg,
        "target_mass_mg": contract["target_mass_mg"],
        "tolerance_mg": contract["tolerance_mg"],
        "error_mg": error_mg,
        "within_tolerance": within_tolerance,
        "grounding": "pylabrobot_scale_with_benchmark_noise_projection",
    }
    insert_artifact(
        conn,
        artifact_id=artifact_id,
        kind="gravimetric_measurement",
        time_s=state["clock_s"],
        payload=payload,
    )
    insert_event(
        conn,
        operation="balance.mass_read",
        time_s=state["clock_s"],
        payload={"artifact_id": artifact_id, **payload},
    )
    return ok(payload)


HANDLERS: dict[str, Handler] = {
    "balance_tare": _tare,
    "formulation_move_vial": _move_vial,
    "powder_dispense_pulse": _dispense_pulse,
    "balance_read_mass": _read_mass,
}
