"""Deterministic scenario sampler for unitelabs_plate_qc_v0."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from api_gym.worlds.unitelabs_plate_qc_v0.state import (
    RUN_METADATA_NAME,
    STATE_DB_NAME,
    TASK_NAME,
    connect,
    dumps_json,
    initialize_db,
    insert_event,
)

WORLD = "unitelabs_plate_qc_v0"
WORLD_ID = "unitelabs-plate-qc-v0"
BASE_TIME = datetime(2026, 6, 11, 9, 0, tzinfo=timezone.utc)


@dataclass(frozen=True)
class SampledEpisode:
    run_dir: Path
    db_path: Path
    task_path: Path
    run_metadata_path: Path
    task: dict[str, object]


ScenarioBuilder = Callable[[Path, int], dict[str, object]]


def sample_episode(*, scenario: str, seed: int, out_dir: Path) -> SampledEpisode:
    """Create one deterministic SQLite-backed episode run."""
    if scenario not in SCENARIOS:
        supported = ", ".join(sorted(SCENARIOS))
        raise ValueError(f"Unsupported unitelabs_plate_qc_v0 scenario '{scenario}'. Supported: {supported}")

    out_dir = out_dir.resolve()
    db_path = out_dir / STATE_DB_NAME
    task_path = out_dir / TASK_NAME
    run_metadata_path = out_dir / RUN_METADATA_NAME

    if db_path.exists() or task_path.exists() or run_metadata_path.exists():
        raise FileExistsError(f"Run directory already contains API Gym state files: {out_dir}")

    initialize_db(db_path)
    task = SCENARIOS[scenario](db_path, seed)

    out_dir.mkdir(parents=True, exist_ok=True)
    task_path.write_text(json.dumps(task, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    run_metadata = {
        "world": WORLD,
        "world_id": WORLD_ID,
        "scenario": scenario,
        "seed": seed,
        "mode": "dry_run",
        "state_db": STATE_DB_NAME,
        "task": TASK_NAME,
    }
    run_metadata_path.write_text(json.dumps(run_metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return SampledEpisode(
        run_dir=out_dir,
        db_path=db_path,
        task_path=task_path,
        run_metadata_path=run_metadata_path,
        task=task,
    )


def _iso(minutes: int = 0) -> str:
    return (BASE_TIME + timedelta(minutes=minutes)).isoformat().replace("+00:00", "Z")


def _build_plate_transfer_qc(db_path: Path, seed: int) -> dict[str, object]:
    scenario = "plate_transfer_qc"
    created_at = _iso()
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO deck (id, mode, dry_run, loaded_labware_json, metadata_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "deck_1",
                "dry_run",
                1,
                dumps_json(["source_plate", "assay_plate", "tip_rack_1"]),
                dumps_json({"operator": "agent", "seed": seed}),
            ),
        )
        conn.executemany(
            """
            INSERT INTO labware (id, kind, display_name, metadata_json)
            VALUES (?, ?, ?, ?)
            """,
            [
                ("source_plate", "plate", "Source Plate", dumps_json({"format": "96_well"})),
                ("assay_plate", "plate", "Assay Plate", dumps_json({"format": "96_well"})),
                ("tip_rack_1", "tip_rack", "Tip Rack 1", dumps_json({"format": "96_tip"})),
            ],
        )
        conn.executemany(
            """
            INSERT INTO wells (labware_id, well_id, volume_ul, metadata_json)
            VALUES (?, ?, ?, ?)
            """,
            [
                ("source_plate", "A1", 120.0, dumps_json({"contents": "qc_control"})),
                ("assay_plate", "B1", 0.0, dumps_json({"contents": "empty_assay_well"})),
            ],
        )
        conn.execute(
            "INSERT INTO tips (rack_id, well_id, status) VALUES (?, ?, ?)",
            ("tip_rack_1", "A1", "available"),
        )
        conn.execute(
            """
            INSERT INTO pipette_state (
              id, tip, aspirated_volume_ul, source_labware_id, source_well_id
            ) VALUES (?, ?, ?, ?, ?)
            """,
            ("p300_single", None, 0.0, None, None),
        )
        conn.execute(
            """
            INSERT INTO control_bands (
              id, plate_id, well_id, wavelength_nm, min_value, max_value, expected_value, required_dispense_ul
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("control_band_assay_b1_od600", "assay_plate", "B1", 600, 0.75, 0.9, 0.82, 50.0),
        )
        insert_event(
            conn,
            event_type="expected_resolution.created",
            object_type="scenario",
            object_id=scenario,
            payload={
                "scenario": scenario,
                "source": "source_plate:A1",
                "target": "assay_plate:B1",
                "tip": "tip_rack_1:A1",
                "transfer_volume_ul": 50,
                "wavelength_nm": 600,
                "control_band": {"min": 0.75, "max": 0.9},
                "expected_readout_value": 0.82,
                "expected_decision": "continue",
            },
            created_at=created_at,
            visible_to_agent=False,
        )

    return {
        "schema_version": "api_gym.task.v0",
        "world": WORLD,
        "world_id": WORLD_ID,
        "scenario": scenario,
        "seed": seed,
        "objective": "Evaluate whether the plate QC workflow should continue.",
        "prompt": (
            "Evaluate whether the plate QC workflow should continue. Inspect the dry-run deck state and "
            "labware state, use the available lab tools to gather evidence, and submit a final protocol "
            "decision with the supporting readout evidence."
        ),
    }


SCENARIOS: dict[str, ScenarioBuilder] = {
    "plate_transfer_qc": _build_plate_transfer_qc,
}
