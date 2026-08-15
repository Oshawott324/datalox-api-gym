from __future__ import annotations

import json
from pathlib import Path

from pylabrobot.visualizer import Visualizer

from api_gym.worlds.pylabrobot_star_v0.replay import (
    PUBLIC_REPLAY_PROJECTION_NAME,
    PYLABROBOT_CAPTURE_PACKAGE_VERSION,
    PYLABROBOT_VIEWER_PACKAGE_VERSION,
    read_public_replay_projection,
    run_serial_dilution_qc_replay_case,
    start_public_replay,
    stop_public_replay,
)
from api_gym.worlds.pylabrobot_star_v0.state import get_state
from api_gym.worlds.registry import get_world_runtime


def test_star_world_records_upstream_visualizer_commands_per_tool(tmp_path: Path) -> None:
    runtime = get_world_runtime("pylabrobot_star_v0")
    episode = runtime.sample_episode(
        scenario="plate_transfer_qc",
        seed=42,
        out_dir=tmp_path / "run",
    )
    start_public_replay(episode.run_dir)
    try:
        assert runtime.dispatch_tool(
            episode.run_dir,
            name="pick_up_tips",
            arguments={"tip_refs": ["tip_rack_01:A1"], "channels": [0]},
        )["ok"]
        assert runtime.dispatch_tool(
            episode.run_dir,
            name="aspirate",
            arguments={"source": "source_plate:A1", "volume_ul": 50, "channel": 0},
        )["ok"]
        assert runtime.dispatch_tool(
            episode.run_dir,
            name="dispense",
            arguments={"target": "assay_plate:B1", "volume_ul": 50, "channel": 0},
        )["ok"]
        assert runtime.dispatch_tool(
            episode.run_dir,
            name="return_tips",
            arguments={"channels": [0]},
        )["ok"]

        replay = read_public_replay_projection(episode.run_dir)
    finally:
        stop_public_replay(episode.run_dir)

    assert (episode.run_dir / PUBLIC_REPLAY_PROJECTION_NAME).is_file()
    assert replay["schema_version"] == "datalox_world_replay_projection_v1"
    assert replay["renderer"] == {
        "id": "pylabrobot_visualizer",
        "capture_package_version": PYLABROBOT_CAPTURE_PACKAGE_VERSION,
        "viewer_package_version": PYLABROBOT_VIEWER_PACKAGE_VERSION,
        "protocol_version": "0.1.0",
    }
    assert [command["event"] for command in replay["initialization"]] == [
        "set_root_resource",
        "set_state",
        "show_machine_tools",
    ]
    assert [step["operation_id"] for step in replay["steps"]] == [
        "pick_up_tips",
        "aspirate",
        "dispense",
        "return_tips",
    ]
    assert all(step["commands"] for step in replay["steps"])
    assert all(
        command["event"] == "set_state"
        for step in replay["steps"]
        for command in step["commands"]
    )
    assert replay["steps"][1]["label"] == "Aspirate 50 uL from source_plate:A1"
    assert replay["steps"][2]["label"] == "Dispense 50 uL into assay_plate:B1"


def test_serial_dilution_replay_uses_upstream_commands_and_populated_frame_zero(
    tmp_path: Path,
    monkeypatch,
) -> None:
    assembled_commands: list[dict] = []
    upstream_assemble_command = Visualizer._assemble_command

    def capture_upstream_command(self, event, data):
        serialized, command_id = upstream_assemble_command(self, event, data)
        command = json.loads(serialized)
        assembled_commands.append({"event": command["event"], "data": command["data"]})
        return serialized, command_id

    monkeypatch.setattr(Visualizer, "_assemble_command", capture_upstream_command)

    runtime = get_world_runtime("pylabrobot_star_v0")
    episode = runtime.sample_episode(
        scenario="serial_dilution_qc",
        seed=42,
        out_dir=tmp_path / "serial-dilution-run",
    )
    recorder = start_public_replay(episode.run_dir)
    try:
        assert isinstance(recorder, Visualizer)
        operations = run_serial_dilution_qc_replay_case(episode.run_dir)
        replay = read_public_replay_projection(episode.run_dir)
    finally:
        stop_public_replay(episode.run_dir)

    projected_commands = replay["initialization"] + [
        command
        for step in replay["steps"]
        for command in step["commands"]
    ]
    assert projected_commands == assembled_commands

    initialization = {command["event"]: command["data"] for command in replay["initialization"]}
    root = initialization["set_root_resource"]["resource"]
    resource_names = _resource_names(root)
    assert {"deck", "tip_rack_01", "source_plate", "assay_plate"}.issubset(resource_names)
    assert _resource_by_name(root, "deck")["type"] == "HamiltonSTARDeck"

    initial_state = initialization["set_state"]
    assert initial_state["source_plate_well_A1"]["volume"] == 200.0
    for well in ("B1", "B2", "B3", "B4", "B5"):
        assert initial_state[f"assay_plate_well_{well}"]["volume"] == 50.0
    for tip in ("A1", "A2", "A3", "A4", "A5"):
        assert initial_state[f"tip_rack_01_tipspot_{tip}"]["tip"]["type"] == "HamiltonTip"

    expected_transfers = [
        ("source_plate:A1", "assay_plate:B1", "tip_rack_01:A1"),
        ("assay_plate:B1", "assay_plate:B2", "tip_rack_01:A2"),
        ("assay_plate:B2", "assay_plate:B3", "tip_rack_01:A3"),
        ("assay_plate:B3", "assay_plate:B4", "tip_rack_01:A4"),
        ("assay_plate:B4", "assay_plate:B5", "tip_rack_01:A5"),
    ]
    expected_transfer_operations: list[str] = []
    for index, (source, target, tip_ref) in enumerate(expected_transfers):
        expected_transfer_operations.extend(
            ["pick_up_tips", "aspirate", "dispense", "discard_tips"]
        )
        operation_offset = index * 4
        assert operations[operation_offset]["arguments"]["tip_refs"] == [tip_ref]
        assert operations[operation_offset + 1]["arguments"] == {
            "source": source,
            "volume_ul": 50,
            "channel": 0,
        }
        assert operations[operation_offset + 2]["arguments"] == {
            "target": target,
            "volume_ul": 50,
            "channel": 0,
        }
    assert [operation["name"] for operation in operations[:20]] == expected_transfer_operations
    assert [operation["name"] for operation in operations[20:]] == [
        "read_absorbance",
        "read_absorbance",
        "submit_protocol",
    ]

    replay_operation_ids = [step["operation_id"] for step in replay["steps"]]
    assert replay_operation_ids[:20] == expected_transfer_operations
    assert replay_operation_ids[20:] == ["read_absorbance", "read_absorbance"]
    assert len(replay["steps"]) == 22
    assert len(replay["steps"]) > 4 * 4
    assert all(step["commands"] for step in replay["steps"])

    state = get_state(episode.run_dir)
    assert state.tips_used == 5
    assert [
        transfer["target_well"]
        for transfer in state.transfers
        if transfer["type"] == "dispense"
    ] == [target for _, target, _ in expected_transfers]
    assert [readout["plate"] for readout in state.readouts] == [
        "source_plate",
        "assay_plate",
    ]
    assert state.readouts[1]["wells"] == ["B1", "B2", "B3", "B4", "B5"]
    assert state.submissions[-1]["evidence_readout_id"] == state.readouts[1]["readout_id"]
    assert state.submissions[-1]["target_well"] == "assay_plate:B5"


def _resource_names(resource: dict) -> set[str]:
    names = {resource["name"]}
    for child in resource.get("children", []):
        names.update(_resource_names(child))
    return names


def _resource_by_name(resource: dict, name: str) -> dict:
    if resource["name"] == name:
        return resource
    for child in resource.get("children", []):
        try:
            return _resource_by_name(child, name)
        except KeyError:
            continue
    raise KeyError(name)
