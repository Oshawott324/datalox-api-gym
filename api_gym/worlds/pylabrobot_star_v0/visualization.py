"""Public visualization projection for the grounded STAR serial-dilution case."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

from api_gym.worlds.pylabrobot_star_v0.replay import (
    PYLABROBOT_CAPTURE_PACKAGE_VERSION,
    PYLABROBOT_PROTOCOL_VERSION,
    PYLABROBOT_VIEWER_PACKAGE_VERSION,
    read_public_replay_projection,
    run_serial_dilution_qc_replay_case,
    start_public_replay,
    stop_public_replay,
)
from api_gym.worlds.registry import get_world_runtime

VISUALIZATION_RUN_SCHEMA = "datalox_visualization_run_v1"
VISUALIZATION_RENDERER_ID = "pylabrobot_visualizer_v1"


def build_serial_dilution_visualization(
    *,
    operations: list[dict[str, Any]],
    replay: dict[str, Any],
) -> dict[str, Any]:
    """Compose public run context around renderer-native PyLabRobot commands."""

    if len(operations) != 23 or len(replay.get("steps", [])) != 22:
        raise ValueError("serial-dilution visualization expects 23 operations and 22 visual steps")
    steps = [
        _visual_step(index, operation, replay["steps"][index])
        for index, operation in enumerate(operations[:22])
    ]
    steps.append(_submission_step(operations[22], sequence=23))

    source_readout = operations[20]["result"]["data"]
    assay_readout = operations[21]["result"]["data"]
    submission = operations[22]["result"]["data"]
    return {
        "schema_version": VISUALIZATION_RUN_SCHEMA,
        "run_id": "star-serial-dilution-seed-42",
        "world_id": "pylabrobot_star_v0",
        "presentation": {
            "title": "Hamilton STAR serial dilution dry run",
            "summary": (
                "Five fresh-tip 50 uL transfers recorded by PyLabRobot, followed by "
                "two simulated OD600 reads and a protocol submission."
            ),
            "subject": "Scientific workflow dry run",
            "mode": "dry_run",
            "status": "completed",
            "agent": None,
        },
        "workflow": {
            "stages": [
                {
                    "id": "liquid_handling",
                    "label": "Serial dilution",
                    "kind": "lab_automation",
                    "provider": "PyLabRobot",
                    "status": "completed",
                },
                {
                    "id": "measurement",
                    "label": "OD600 read",
                    "kind": "simulated_measurement",
                    "provider": None,
                    "status": "completed",
                },
                {
                    "id": "decision",
                    "label": "Protocol decision",
                    "kind": "workflow_decision",
                    "provider": None,
                    "status": "completed",
                },
            ],
            "edges": [
                {"from": "liquid_handling", "to": "measurement"},
                {"from": "measurement", "to": "decision"},
            ],
        },
        "renderer": {
            "id": VISUALIZATION_RENDERER_ID,
            "protocol_version": PYLABROBOT_PROTOCOL_VERSION,
            "payload": {
                "capture_package_version": PYLABROBOT_CAPTURE_PACKAGE_VERSION,
                "viewer_package_version": PYLABROBOT_VIEWER_PACKAGE_VERSION,
                "initialization": replay["initialization"],
            },
        },
        "resources": _resources(),
        "artifacts": [
            {
                "id": "source-od600",
                "label": "Source plate OD600",
                "type": "simulated_measurement",
                "summary": "Deterministic readout returned by the API Gym world.",
                "data": source_readout,
            },
            {
                "id": "assay-od600",
                "label": "Assay plate OD600",
                "type": "simulated_measurement",
                "summary": "Deterministic readout returned by the API Gym world.",
                "data": assay_readout,
            },
            {
                "id": "protocol-submission",
                "label": "Protocol submission",
                "type": "workflow_decision",
                "summary": "The decision references the assay readout produced after transfer.",
                "data": submission,
            },
        ],
        "steps": steps,
        "outcome": None,
    }


def export_serial_dilution_visualization(destination: Path) -> dict[str, Any]:
    """Run the fixed grounded case and write one portable visualization document."""

    runtime = get_world_runtime("pylabrobot_star_v0")
    with tempfile.TemporaryDirectory(prefix="datalox-star-visualization-") as temporary:
        episode = runtime.sample_episode(
            scenario="serial_dilution_qc",
            seed=42,
            out_dir=Path(temporary) / "run",
        )
        start_public_replay(episode.run_dir)
        try:
            operations = run_serial_dilution_qc_replay_case(episode.run_dir)
            replay = read_public_replay_projection(episode.run_dir)
        finally:
            stop_public_replay(episode.run_dir)
    document = build_serial_dilution_visualization(operations=operations, replay=replay)
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return document


def _visual_step(
    index: int,
    operation: dict[str, Any],
    replay_step: dict[str, Any],
) -> dict[str, Any]:
    name = operation["name"]
    arguments = operation["arguments"]
    result = operation["result"]["data"]
    phase_id = "measurement" if name == "read_absorbance" else "liquid_handling"
    title, description = _operation_copy(name, arguments, result)
    artifact_ids: list[str] = []
    if index == 20:
        artifact_ids = ["source-od600"]
    elif index == 21:
        artifact_ids = ["assay-od600"]
    return {
        "sequence": index + 1,
        "phase_id": phase_id,
        "operation_id": f"{name}-{index + 1}",
        "title": title,
        "description": description,
        "simulated_at": replay_step["simulated_at"],
        "duration_ms": _duration_ms(name),
        "status": "completed",
        "render": {"commands": replay_step["commands"]},
        "facts": _facts(name, arguments, result),
        "state_changes": _state_changes(index, name, arguments, result),
        "artifact_ids": artifact_ids,
    }


def _submission_step(operation: dict[str, Any], *, sequence: int) -> dict[str, Any]:
    result = operation["result"]["data"]
    return {
        "sequence": sequence,
        "phase_id": "decision",
        "operation_id": "submit-protocol-23",
        "title": "Submit the protocol decision",
        "description": "The submission cites the assay readout created after all transfers.",
        "simulated_at": "T+0.000s",
        "duration_ms": 1100,
        "status": "completed",
        "render": {"commands": []},
        "facts": [
            {"label": "Decision", "value": result["decision"], "unit": None, "tone": "success"},
            {
                "label": "Evidence",
                "value": result["evidence_readout_id"],
                "unit": None,
                "tone": "info",
            },
        ],
        "state_changes": [],
        "artifact_ids": ["protocol-submission"],
    }


def _operation_copy(
    name: str,
    arguments: dict[str, Any],
    result: dict[str, Any],
) -> tuple[str, str]:
    if name == "pick_up_tips":
        tip = arguments["tip_refs"][0].split(":", 1)[1]
        return f"Pick up fresh tip {tip}", "Channel 1 mounts a clean tip before the next transfer."
    if name == "aspirate":
        source = arguments["source"].replace(":", " ")
        return f"Aspirate 50 uL from {source}", "The source volume is updated before liquid leaves the well."
    if name == "dispense":
        target = arguments["target"].replace(":", " ")
        return f"Dispense 50 uL into {target}", "The destination well receives one step of the dilution series."
    if name == "discard_tips":
        return "Discard the used tip", "The used tip is removed before the next source contact."
    if name == "read_absorbance":
        wells = ", ".join(result["wells"])
        return f"Read OD600 for {result['plate']}", f"The simulated reader records 600 nm values for {wells}."
    raise ValueError(f"unsupported visualization operation: {name}")


def _facts(
    name: str,
    arguments: dict[str, Any],
    result: dict[str, Any],
) -> list[dict[str, Any]]:
    if name == "pick_up_tips":
        return [
            {"label": "Tip", "value": arguments["tip_refs"][0], "unit": None, "tone": "info"},
            {"label": "Channel", "value": "1", "unit": None, "tone": "neutral"},
        ]
    if name in {"aspirate", "dispense"}:
        location = arguments["source"] if name == "aspirate" else arguments["target"]
        return [
            {"label": "Volume", "value": "50", "unit": "uL", "tone": "info"},
            {"label": "Location", "value": location, "unit": None, "tone": "neutral"},
        ]
    if name == "discard_tips":
        return [{"label": "Tip state", "value": "Discarded", "unit": None, "tone": "success"}]
    return [
        {"label": "Wavelength", "value": str(result["wavelength_nm"]), "unit": "nm", "tone": "info"},
        {"label": "Wells", "value": str(len(result["wells"])), "unit": None, "tone": "neutral"},
    ]


def _state_changes(
    index: int,
    name: str,
    arguments: dict[str, Any],
    result: dict[str, Any],
) -> list[dict[str, Any]]:
    if name == "pick_up_tips":
        transfer_index = index // 4
        return [
            {
                "resource_id": "tip_rack_01",
                "field": "available tips",
                "before": str(96 - transfer_index),
                "after": str(95 - transfer_index),
                "unit": None,
            }
        ]
    if name == "aspirate":
        remaining = float(result["source_remaining_ul"])
        return [
            {
                "resource_id": arguments["source"].replace(":", "."),
                "field": "volume",
                "before": f"{remaining + float(result['volume_ul']):g}",
                "after": f"{remaining:g}",
                "unit": "uL",
            }
        ]
    if name == "dispense":
        return [
            {
                "resource_id": arguments["target"].replace(":", "."),
                "field": "volume",
                "before": f"{float(result['target_volume_before_ul']):g}",
                "after": f"{float(result['target_volume_after_ul']):g}",
                "unit": "uL",
            }
        ]
    if name == "discard_tips":
        return [
            {
                "resource_id": "hamilton_star",
                "field": "channel 1 tip",
                "before": "mounted",
                "after": "empty",
                "unit": None,
            }
        ]
    return []


def _duration_ms(name: str) -> int:
    return {
        "pick_up_tips": 700,
        "aspirate": 900,
        "dispense": 900,
        "discard_tips": 650,
        "read_absorbance": 1200,
    }[name]


def _resources() -> list[dict[str, Any]]:
    resources = [
        {
            "id": "hamilton_star",
            "label": "Hamilton STAR",
            "type": "liquid_handler",
            "status": "ready",
            "summary": "Eight-channel deck rendered from the PyLabRobot resource tree.",
            "attributes": {"channels": 8},
        },
        {
            "id": "tip_rack_01",
            "label": "Hamilton 300 uL tip rack",
            "type": "tip_rack",
            "status": "loaded",
            "summary": "Five distinct clean tips are consumed by this run.",
            "attributes": {"capacity": 96, "tips_used": 5},
        },
        {
            "id": "source_plate.A1",
            "label": "Source plate A1",
            "type": "well",
            "status": "processed",
            "summary": "Stock source for the first transfer.",
            "attributes": {"initial_volume_ul": 200, "final_volume_ul": 150},
        },
    ]
    for index in range(1, 6):
        resources.append(
            {
                "id": f"assay_plate.B{index}",
                "label": f"Assay plate B{index}",
                "type": "well",
                "status": "processed",
                "summary": f"Dilution position {index} of 5.",
                "attributes": {
                    "initial_volume_ul": 50,
                    "final_volume_ul": 100 if index == 5 else 50,
                },
            }
        )
    return resources


def main() -> int:
    parser = argparse.ArgumentParser(description="Export the STAR serial-dilution visualization.")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    export_serial_dilution_visualization(Path(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
