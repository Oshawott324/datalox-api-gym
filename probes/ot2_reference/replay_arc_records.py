"""Replay the five recorded arc attempts in the official OT-2 motion planner.

Every recorded attempt was a ``moveToAddressableAreaForDropTip`` to the fixed
trash, issued at the start of each script call, before that call picked up a
tip (see robot-exports-20261012/run_records.md in the reference repository). Run ``ac20a023`` served the
slot-3 and then the slot-7 calls, so the slot-7 attempt started with the tip
from the slot-3 call still attached; run ``ee3a249b`` (slot 6) was a new run.

``protocol_api.drop_tip()`` takes no ``minimum_z_height``, so the drop-tip move
is sent to the engine directly, as the host-side script did. This is a tool for
reproducing the records, not a protocol, and needs an opentrons release that
still accepts OT-2 protocols (PyPI 8.8.2 is the newest)::

    runs/ot2-analysis-8.8.2/bin/python probes/ot2_reference/replay_arc_records.py
    runs/ot2-analysis-8.8.2/bin/python probes/ot2_reference/replay_arc_records.py --tip-length-mm 30.85
"""

from __future__ import annotations

import argparse
import copy
import inspect
import os
import tempfile

RECORDED = [
    # (run, slot, minimum_z_height, recorded outcome, tip attached in the engine at that moment)
    ("ac20a023", "3", 180.0, "rejected", False),
    ("ac20a023", "3", 150.0, "accepted", False),
    ("ac20a023", "7", 150.0, "rejected", True),
    ("ac20a023", "7", 130.0, "accepted", True),
    ("ee3a249b", "6", 130.0, "accepted", False),
]


def _context(with_tip: bool, tip_length_mm: float | None):
    from opentrons import simulate
    from opentrons_shared_data.labware import load_definition

    ctx = simulate.get_protocol_api("2.16", robot_type="OT-2")
    definition = copy.deepcopy(load_definition("opentrons_96_tiprack_20ul", 1))
    if tip_length_mm is not None:
        # Effective tip length = tipLength - tipOverlap; set it to the calibrated value.
        definition["parameters"]["tipLength"] = tip_length_mm + definition["parameters"]["tipOverlap"]
        definition["parameters"]["loadName"] = "opentrons_96_tiprack_20ul_calibrated"
        definition["namespace"] = "custom_beta"
    tips = ctx.load_labware_from_definition(definition, 2)
    pipette = ctx.load_instrument("p20_single_gen2", "left", tip_racks=[tips])
    ctx.home()
    if with_tip:
        pipette.pick_up_tip()
    return ctx, pipette


def _trash_move(ctx, pipette, minimum_z: float) -> str:
    from opentrons.protocol_engine import commands as cmd
    from opentrons.protocol_engine.types import AddressableOffsetVector

    params = cmd.MoveToAddressableAreaForDropTipParams(
        pipetteId=pipette._core.pipette_id,
        addressableAreaName="fixedTrash",
        offset=AddressableOffsetVector(x=0, y=0, z=0),
        ignoreTipConfiguration=True,
        minimumZHeight=minimum_z,
    )
    client = ctx._core._engine_client
    try:
        if "command_annotations" in inspect.signature(client.execute_command).parameters:
            client.execute_command(params, command_annotations=[])
        else:
            client.execute_command(params)
        return "accepted"
    except Exception as error:  # noqa: BLE001 - classify planner errors
        if "out of bounds" in str(error).lower():
            return "rejected"
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tip-length-mm", type=float, default=None,
                        help="calibrated effective tip length; default uses the labware definition")
    args = parser.parse_args()
    os.environ.setdefault("OT_API_CONFIG_DIR", tempfile.mkdtemp(prefix="ot2-default-config-"))

    import opentrons

    label = "definition" if args.tip_length_mm is None else f"{args.tip_length_mm} mm"
    print(f"opentrons {opentrons.__version__}, tip length: {label}")
    matches = 0
    for run, slot, minimum_z, recorded, with_tip in RECORDED:
        ctx, pipette = _context(with_tip, args.tip_length_mm)
        predicted = _trash_move(ctx, pipette, minimum_z)
        matches += predicted == recorded
        tip = "tip attached" if with_tip else "no tip"
        print(f"{run} slot {slot} {minimum_z:5.0f} mm, {tip:12s} recorded {recorded:8s} predicted {predicted:8s}"
              f" {'match' if predicted == recorded else 'MISMATCH'}")
    print(f"{matches}/{len(RECORDED)} recorded outcomes reproduced")
    for with_tip in (False, True):
        low, high = 100.0, 200.0
        while high - low > 0.02:
            middle = (low + high) / 2
            ctx, pipette = _context(with_tip, args.tip_length_mm)
            low, high = (middle, high) if _trash_move(ctx, pipette, middle) == "accepted" else (low, middle)
        print(f"highest accepted minimum_z_height, {'tip attached' if with_tip else 'no tip'}: {low:.2f} mm")


if __name__ == "__main__":
    main()
