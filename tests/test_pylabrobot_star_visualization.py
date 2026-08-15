from __future__ import annotations

from pathlib import Path

from api_gym.worlds.pylabrobot_star_v0.visualization import (
    export_serial_dilution_visualization,
)


def test_serial_dilution_visualization_is_public_and_synchronized(tmp_path: Path) -> None:
    destination = tmp_path / "star-serial-dilution.json"
    document = export_serial_dilution_visualization(destination)

    assert destination.is_file()
    assert document["schema_version"] == "datalox_visualization_run_v1"
    assert document["presentation"]["mode"] == "dry_run"
    assert document["presentation"]["agent"] is None
    assert len(document["steps"]) == 23
    assert [step["phase_id"] for step in document["steps"][-3:]] == [
        "measurement",
        "measurement",
        "decision",
    ]
    assert document["steps"][2]["state_changes"] == [
        {
            "resource_id": "assay_plate.B1",
            "field": "volume",
            "before": "50",
            "after": "100",
            "unit": "uL",
        }
    ]
    assert document["steps"][-1]["render"]["commands"] == []
    assert document["steps"][-1]["artifact_ids"] == ["protocol-submission"]
    assert document["outcome"] is None
    assert "/Users/" not in destination.read_text(encoding="utf-8")
