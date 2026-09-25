"""Observe native motion planning in a dedicated, device-free probe process.

This is reference instrumentation, not an agent adapter or a replacement motion
planner. Every recorded move delegates to the unchanged official simulator.
The private hook and cleanup boundary are pinned to Opentrons 9.1.1.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import os
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory


def run_reference() -> dict:
    if version("opentrons") != "9.1.1" or version("opentrons-shared-data") != "9.1.1":
        raise RuntimeError("Reference instrumentation requires Opentrons and shared-data 9.1.1")
    # Configuration is selected before importing the vendor package. This probe
    # runs in its own process, so it never changes a concurrent session's config.
    import sys
    if "opentrons" in sys.modules:
        raise RuntimeError("Run the reference probe in a fresh process")

    with TemporaryDirectory(prefix="ot2-motion-config-") as config_dir:
        os.environ["OT_API_CONFIG_DIR"] = config_dir
        from opentrons import simulate, types
        from opentrons.hardware_control import API, ThreadManager
        from opentrons_shared_data.labware import load_definition

        records: list[dict] = []
        active_case: str | None = None

        class RecordingSimulator(API):
            async def move_to(self, mount, abs_position, **kwargs):
                if not self.is_simulator:
                    raise RuntimeError("Reference probe requires the official simulator backend")
                critical_point = kwargs.get("critical_point")
                start = await self.gantry_position(mount, critical_point=critical_point)
                await super().move_to(mount, abs_position, **kwargs)
                end = await self.gantry_position(mount, critical_point=critical_point)
                if active_case is not None:
                    records.append({
                        "case": active_case,
                        "mount": mount.name,
                        "critical_point": critical_point.name if critical_point else None,
                        "start_mm": list(start),
                        "requested_end_mm": list(abs_position),
                        "reported_end_mm": list(end),
                        "speed_mm_s": kwargs.get("speed"),
                    })

        hardware = ThreadManager(
            RecordingSimulator.build_hardware_simulator,
            attached_instruments={types.Mount.LEFT: {"model": "p300_single_v2.1", "id": "simulation-only"}},
            strict_attached_instruments=True,
        )
        context = None
        cases = []
        try:
            context = simulate.get_protocol_api(
                "2.26", robot_type="OT-2", use_virtual_hardware=False,
                extra_labware={}, hardware_simulator=hardware,
            )
            if not context.is_simulating() or not hardware.sync.is_simulator:
                raise RuntimeError("A non-simulator reference is forbidden")
            first = context.load_labware("corning_96_wellplate_360ul_flat", 1, version=1)
            second = context.load_labware("corning_96_wellplate_360ul_flat", 3, version=1)
            rack = context.load_labware("opentrons_96_tiprack_300ul", 5, version=1)
            pipette = context.load_instrument("p300_single_gen2", "left", tip_racks=[rack])
            # Setup only: pickup contact mechanics are outside this experiment.
            pipette.pick_up_tip(rack["A1"])
            pipette.move_to(first["A1"].top(z=5))
            instrument = hardware.sync.attached_instruments[types.Mount.LEFT]
            setup = {
                "robot_type": "OT-2", "api_level": "2.26", "mount": "left",
                "pipette_model": instrument["model"], "tip_length_mm": instrument["tip_length"],
                "position_frame": "deck",
                "position_units": "mm",
                "position_reference": "native critical point; tip end for this mounted-tip setup",
                "slots": {"1": first.load_name, "3": second.load_name, "5": rack.load_name},
                "calibration": "official nominal defaults; no physical calibration supplied",
                "pickup": "official simulated setup only; contact behavior not validated",
            }

            def move(case, destination, **kwargs):
                nonlocal active_case
                active_case = case
                before = len(records)
                try:
                    pipette.move_to(destination, **kwargs)
                finally:
                    active_case = None
                cases.append({"id": case, "segments": records[before:]})

            move("raised_cross_plate", second["A1"].top(z=5))
            move("direct_cross_plate", first["A1"].top(z=5), force_direct=True)
            move("minimum_height", second["A1"].top(z=5), minimum_z_height=100)
            second.set_offset(x=1, y=-2, z=0.5)
            move("labware_offset", second["A1"].top(z=5), force_direct=True)
            move("same_position", second["A1"].top(z=5), force_direct=True)

            definitions = {}
            for name in (first.load_name, rack.load_name):
                definition = load_definition(name, 1)
                serialized = json.dumps(definition, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
                definitions[name] = {
                    "namespace": definition["namespace"], "version": definition["version"],
                    "canonical_json_sha256": hashlib.sha256(serialized).hexdigest(),
                    "dimensions": definition["dimensions"],
                }
            source_files = {}
            for cls in (API,):
                path = Path(inspect.getfile(cls))
                source_files["opentrons/hardware_control/api.py"] = hashlib.sha256(path.read_bytes()).hexdigest()
            return {
                "opentrons_version": version("opentrons"), "setup": setup,
                "source_files_sha256": source_files, "definitions": definitions, "cases": cases,
                "claim": "native simulator movement segments, not measured hardware trajectories",
            }
        finally:
            if context is not None:
                context.cleanup()
            # The 9.1.1 interactive API retains engine contexts in this stack.
            # Close the engine while its hardware thread is still available.
            try:
                simulate._LIVE_PROTOCOL_ENGINE_CONTEXTS.close()
            finally:
                hardware.clean_up()


if __name__ == "__main__":
    print(json.dumps(run_reference(), sort_keys=True, allow_nan=False))
