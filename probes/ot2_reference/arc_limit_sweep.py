"""Measure the official OT-2 arc limit and compare it with recorded robot outcomes.

Run with an interpreter that has the OT-2-capable ``opentrons`` package
(8.8.2 is the newest PyPI release whose analyzer still accepts OT-2
protocols)::

    runs/ot2-analysis-8.8.2/bin/python probes/ot2_reference/arc_limit_sweep.py \
        --reference worlds/ot2_protocol_v0/reference_v0.json \
        --out runs/ot2_reference/arc_limit_sweep

The sweep uses default robot settings and calibration. It measures, by
bisection on ``minimum_z_height``, the highest arc the official motion planner
accepts for a cross-slot ``moveToWell`` and for the drop-tip move to the fixed
trash, then checks how that limit moves with effective tip length. It also
writes the approximate slot-3 labware definition used by the task world.
"""

from __future__ import annotations

import argparse
import copy
import inspect
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable

STANDARD_RACK = "opentrons_24_tuberack_eppendorf_2ml_safelock_snapcap"
SLOT3_LOAD_NAME = "custom_24_tuberack_eppendorf_2ml_slot3_pitch19p69"
SLOT3_PITCH_MM = 19.69
API_LEVEL = "2.16"
PIPETTES = {
    "p20": {"name": "p20_single_gen2", "mount": "left", "tip_rack": "opentrons_96_tiprack_20ul", "slot": 2},
    "p300": {"name": "p300_single_gen2", "mount": "right", "tip_rack": "opentrons_96_tiprack_300ul", "slot": 5},
}
TARGET_SLOTS = (3, 6, 7, 8)
RESOLUTION_MM = 0.05


def slot3_definition() -> dict[str, Any]:
    """Standard 24-tube rack with the measured 19.69 mm column pitch."""
    from opentrons_shared_data.labware import load_definition

    base = copy.deepcopy(load_definition(STANDARD_RACK, 1))
    first_x = base["wells"]["A1"]["x"]
    for name, well in base["wells"].items():
        column = int(name[1:]) - 1
        well["x"] = round(first_x + column * SLOT3_PITCH_MM, 3)
    base["namespace"] = "custom_beta"
    base["version"] = 1
    base["parameters"]["loadName"] = SLOT3_LOAD_NAME
    base["metadata"]["displayName"] = "Custom 24 tube rack, 2 mL Eppendorf, 19.69 mm column pitch (approximation)"
    base["brand"] = {"brand": "custom", "brandId": []}
    return base


def _context(pipette_key: str, target_slot: int, tip_length_delta_mm: float = 0.0):
    from opentrons import simulate
    from opentrons_shared_data.labware import load_definition

    spec = PIPETTES[pipette_key]
    ctx = simulate.get_protocol_api(API_LEVEL, robot_type="OT-2")
    if tip_length_delta_mm:
        tip_def = copy.deepcopy(load_definition(spec["tip_rack"], 1))
        tip_def["parameters"]["tipLength"] += tip_length_delta_mm
        sign = "plus" if tip_length_delta_mm > 0 else "minus"
        tip_def["parameters"]["loadName"] = f"{spec['tip_rack']}_len_{sign}_{abs(tip_length_delta_mm):.1f}".replace(".", "p")
        tip_def["namespace"] = "custom_beta"
        tips = ctx.load_labware_from_definition(tip_def, spec["slot"])
    else:
        tips = ctx.load_labware(spec["tip_rack"], spec["slot"])
    if target_slot == 3:
        rack = ctx.load_labware_from_definition(slot3_definition(), 3)
    else:
        rack = ctx.load_labware(STANDARD_RACK, target_slot)
    pipette = ctx.load_instrument(spec["name"], spec["mount"], tip_racks=[tips])
    ctx.home()
    pipette.pick_up_tip()
    return ctx, pipette, rack


def _is_arc_rejection(error: Exception) -> bool:
    return "out of bounds" in str(error).lower()


def _move_to_well(pipette_key: str, slot: int, tip_delta: float) -> Callable[[float], bool]:
    def attempt(min_z: float) -> bool:
        _, pipette, rack = _context(pipette_key, slot, tip_delta)
        try:
            pipette.move_to(rack["A1"].top(), minimum_z_height=min_z)
            return True
        except Exception as error:  # noqa: BLE001 - classify official planner errors
            if _is_arc_rejection(error):
                return False
            raise

    return attempt


def _trash_move(pipette_key: str, tip_delta: float) -> Callable[[float], bool]:
    from opentrons.protocol_engine import commands as cmd
    from opentrons.protocol_engine.types import AddressableOffsetVector

    def attempt(min_z: float) -> bool:
        ctx, pipette, _ = _context(pipette_key, 7, tip_delta)
        params = cmd.MoveToAddressableAreaForDropTipParams(
            pipetteId=pipette._core.pipette_id,
            addressableAreaName="fixedTrash",
            offset=AddressableOffsetVector(x=0, y=0, z=0),
            minimumZHeight=min_z,
        )
        client = ctx._core._engine_client
        # The command_annotations argument exists only in newer engine clients.
        takes_annotations = "command_annotations" in inspect.signature(client.execute_command).parameters
        try:
            if takes_annotations:
                client.execute_command(params, command_annotations=[])
            else:
                client.execute_command(params)
            return True
        except Exception as error:  # noqa: BLE001
            if _is_arc_rejection(error):
                return False
            raise

    return attempt


def _bisect_limit(accepts: Callable[[float], bool], low: float = 100.0, high: float = 200.0) -> float:
    if not accepts(low):
        raise RuntimeError(f"Lower bound {low} mm was rejected; widen the search range")
    if accepts(high):
        return high
    while high - low > RESOLUTION_MM:
        middle = (low + high) / 2
        if accepts(middle):
            low = middle
        else:
            high = middle
    return round(low, 2)


def _max_height(pipette_key: str) -> float:
    ctx, pipette, _ = _context(pipette_key, 7)
    return float(ctx._core._engine_client.state.pipettes.get_instrument_max_height_ot2(pipette._core.pipette_id))


def run(reference: dict[str, Any]) -> dict[str, Any]:
    import opentrons

    limits: dict[str, Any] = {}
    for key in PIPETTES:
        per_slot = {str(slot): _bisect_limit(_move_to_well(key, slot, 0.0)) for slot in TARGET_SLOTS}
        limits[key] = {
            "instrument_max_height_mm": _max_height(key),
            "move_to_well_limit_by_slot_mm": per_slot,
            "trash_drop_tip_move_limit_mm": _bisect_limit(_trash_move(key, 0.0)),
            "tip_length_sensitivity": {
                f"{delta:+.1f}": _bisect_limit(_move_to_well(key, 7, delta)) for delta in (-2.0, -1.0, 1.0, 2.0)
            },
        }

    p20 = limits["p20"]
    comparisons = []
    for outcome in reference["real_arc_outcomes"]:
        slot = outcome["slot"]
        min_z = float(outcome["minimum_z_height_mm"])
        failing = outcome.get("failing_command")
        if failing == "moveToAddressableAreaForDropTip":
            limit = p20["trash_drop_tip_move_limit_mm"]
            command = "drop-tip move to trash"
        else:
            limit = p20["move_to_well_limit_by_slot_mm"][slot]
            command = "moveToWell" if failing is None else "moveToWell (failing command not recorded)"
        predicted = "accepted" if min_z <= limit else "rejected"
        comparisons.append(
            {**outcome, "compared_command": command, "default_limit_mm": limit,
             "default_prediction": predicted, "matches_robot": predicted == outcome["outcome"]}
        )

    accepted_slot3 = [c for c in comparisons if c["slot"] == "3" and c["outcome"] == "accepted"]
    required_shift = None
    if accepted_slot3:
        highest_accepted = max(c["minimum_z_height_mm"] for c in accepted_slot3)
        required_shift = round(highest_accepted - p20["move_to_well_limit_by_slot_mm"]["3"], 2)

    return {
        "opentrons_version": opentrons.__version__,
        "api_level": API_LEVEL,
        "configuration": "default robot settings, default deck and pipette calibration, nominal tip length",
        "limits": limits,
        "real_outcome_comparison": comparisons,
        "robot_limit_must_exceed_default_by_at_least_mm": required_shift,
    }


def _markdown(result: dict[str, Any]) -> str:
    p20 = result["limits"]["p20"]
    p300 = result["limits"]["p300"]
    lines = [
        "# OT-2 arc-limit sweep",
        "",
        f"Official `opentrons` {result['opentrons_version']}, API level {result['api_level']}, {result['configuration']}.",
        "",
        "| Pipette | Instrument max height (mm) | moveToWell limit, slots 3/6/7/8 (mm) | Trash drop-tip move limit (mm) |",
        "| --- | ---: | --- | ---: |",
    ]
    for name, data in (("p20 + 20 uL tips", p20), ("p300 + 300 uL tips", p300)):
        per_slot = ", ".join(f"{v:.2f}" for v in data["move_to_well_limit_by_slot_mm"].values())
        lines.append(
            f"| {name} | {data['instrument_max_height_mm']:.2f} | {per_slot} | {data['trash_drop_tip_move_limit_mm']:.2f} |"
        )
    lines += ["", "Tip-length sensitivity (p20, slot 7):", ""]
    for delta, limit in p20["tip_length_sensitivity"].items():
        lines.append(f"- tip length {delta} mm: limit {limit:.2f} mm")
    lines += ["", "| Recorded outcome | Compared command | Default limit (mm) | Default prediction | Matches robot |",
              "| --- | --- | ---: | --- | --- |"]
    for item in result["real_outcome_comparison"]:
        lines.append(
            f"| slot {item['slot']}, {item['minimum_z_height_mm']:.0f} mm, {item['outcome']} | {item['compared_command']} | "
            f"{item['default_limit_mm']:.2f} | {item['default_prediction']} | {'yes' if item['matches_robot'] else 'no'} |"
        )
    shift = result["robot_limit_must_exceed_default_by_at_least_mm"]
    if shift is not None:
        lines += ["", f"The robot accepted a slot-3 arc {shift:.2f} mm above the default limit."]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--write-slot3-labware", type=Path, default=None)
    args = parser.parse_args()

    os.environ.setdefault("OT_API_CONFIG_DIR", tempfile.mkdtemp(prefix="ot2-default-config-"))
    if args.write_slot3_labware:
        args.write_slot3_labware.parent.mkdir(parents=True, exist_ok=True)
        args.write_slot3_labware.write_text(json.dumps(slot3_definition(), indent=2, sort_keys=True) + "\n")

    result = run(json.loads(args.reference.read_text()))
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "arc_limit_sweep.json").write_text(json.dumps(result, indent=2) + "\n")
    (args.out / "arc_limit_sweep.md").write_text(_markdown(result))
    print(_markdown(result))


if __name__ == "__main__":
    main()
