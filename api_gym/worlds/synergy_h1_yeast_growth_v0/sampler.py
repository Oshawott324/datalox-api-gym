"""Sampler for the Synergy H1 20-hour kinetic-growth workflow."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .state import (
    CONTRACT_NAME,
    RUN_METADATA_NAME,
    STATE_DB_NAME,
    TASK_NAME,
    initialize_db,
)


WORLD = "synergy_h1_yeast_growth_v0"
WORLD_ID = "synergy-h1-yeast-growth-v0"
SCENARIO = "yeast_growth_20h_kinetic"
SCENARIOS = {SCENARIO: object()}


@dataclass(frozen=True)
class SampledEpisode:
    run_dir: Path
    state_path: Path
    task_path: Path
    run_metadata_path: Path
    task: dict[str, Any]


CONTRACT: dict[str, Any] = {
    "schema_version": "api_gym.verification_contract.v1",
    "family": SCENARIO,
    "plate_id": "yeast_growth_plate",
    "plate_version": 1,
    "sealed": True,
    "volume_ul": 200.0,
    "replicate_wells": [f"A{i}" for i in range(1, 9)],
    "temperature_c": 30.0,
    "temperature_tolerance_c": 0.5,
    "wavelength_nm": 600,
    "duration_s": 72_000.0,
    "cadence_s": 120.0,
    "cadence_tolerance_s": 5.0,
    "measurement_count": 601,
    "shake_type": "ORBITAL",
    "frequency_setting": 3,
    "source_refs": {
        "assay_protocol": "agilent_app_note",
        "reader_api": "pylabrobot_synergy_h1_docs",
        "reader_specs": "agilent_technical_details",
    },
    "benchmark_defined": {
        "temperature_tolerance_c": 0.5,
        "cadence_tolerance_s": 5.0,
        "measurement_count": "Includes observations at t=0 and t=20h.",
        "temperature_ramp": "Deterministic calibration assumption.",
        "shake_driver_bridge": (
            "PLR frequency setting 3 is documented in the installed driver as about "
            "567 CPM; it is a projection bridge, not an exact encoding of the app "
            "note's 559 CPM / 1 mm setting."
        ),
    },
}


def sample_episode(*, scenario: str, seed: int, out_dir: Path) -> SampledEpisode:
    if scenario != SCENARIO:
        raise ValueError(f"Unsupported {WORLD} scenario: {scenario}")
    out_dir = out_dir.resolve()
    state_path = out_dir / STATE_DB_NAME
    task_path = out_dir / TASK_NAME
    metadata_path = out_dir / RUN_METADATA_NAME
    contract_path = out_dir / CONTRACT_NAME
    if any(path.exists() for path in (state_path, task_path, metadata_path, contract_path)):
        raise FileExistsError(f"Run directory already contains world files: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)
    initialize_db(state_path)
    task = {
        "schema_version": "api_gym.task.v0",
        "world": WORLD,
        "world_id": WORLD_ID,
        "scenario": SCENARIO,
        "seed": seed,
        "objective": "Produce a complete, quality-controlled 20-hour yeast growth series.",
        "prompt": (
            "Run the sealed 96-well yeast plate on the Synergy H1 projection at "
            "30 C. Monitor A1-A8 at 600 nm every 2 minutes for 20 hours while "
            "orbital shaking remains active. Submit accept only when the complete "
            "series is suitable for downstream analysis."
        ),
    }
    task_path.write_text(json.dumps(task, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    contract_path.write_text(
        json.dumps(CONTRACT, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    metadata = {
        "world": WORLD,
        "world_id": WORLD_ID,
        "scenario": SCENARIO,
        "seed": seed,
        "mode": "dry_run",
        "state_db": STATE_DB_NAME,
        "task": TASK_NAME,
        "contract": CONTRACT_NAME,
    }
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return SampledEpisode(out_dir, state_path, task_path, metadata_path, task)
