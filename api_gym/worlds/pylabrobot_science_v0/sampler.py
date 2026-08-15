"""Episode sampler for instrument-rich PyLabRobot science workflows."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .backends import ThermocyclerProgramBackend
from .contracts import SCENARIO_CONTRACTS
from .state import CONTRACT_NAME, RUN_METADATA_NAME, STATE_DB_NAME, TASK_NAME, initialize_db


WORLD = "pylabrobot_science_v0"
WORLD_ID = "pylabrobot-science-v0"
SCENARIOS = {name: object() for name in SCENARIO_CONTRACTS}


@dataclass(frozen=True)
class SampledEpisode:
    run_dir: Path
    state_path: Path
    task_path: Path
    run_metadata_path: Path
    task: dict[str, Any]


def sample_episode(*, scenario: str, seed: int, out_dir: Path) -> SampledEpisode:
    contract = SCENARIO_CONTRACTS.get(scenario)
    if contract is None:
        raise ValueError(f"Unsupported {WORLD} scenario: {scenario}")
    out_dir = out_dir.resolve()
    paths = {
        "state": out_dir / STATE_DB_NAME,
        "task": out_dir / TASK_NAME,
        "metadata": out_dir / RUN_METADATA_NAME,
        "contract": out_dir / CONTRACT_NAME,
    }
    if any(path.exists() for path in paths.values()):
        raise FileExistsError(f"Run directory already contains world files: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)
    initialize_db(paths["state"], _initial_state(scenario, contract))
    task = {
        "schema_version": "api_gym.task.v0",
        "world": WORLD,
        "world_id": WORLD_ID,
        "scenario": scenario,
        "seed": seed,
        "objective": contract["objective"],
        "prompt": contract["prompt"],
    }
    paths["task"].write_text(json.dumps(task, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    paths["contract"].write_text(
        json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    metadata = {
        "world": WORLD,
        "world_id": WORLD_ID,
        "scenario": scenario,
        "seed": seed,
        "mode": "dry_run",
        "state_db": STATE_DB_NAME,
        "task": TASK_NAME,
        "contract": CONTRACT_NAME,
    }
    paths["metadata"].write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return SampledEpisode(paths["state"].parent, paths["state"], paths["task"], paths["metadata"], task)


def _initial_state(scenario: str, contract: dict[str, Any]) -> dict[str, Any]:
    family = str(contract["family"])
    base: dict[str, Any] = {"scenario": scenario, "family": family, "clock_s": 0.0}
    if family == "thermocycler":
        base.update(
            {
                "plate": {"plate_id": contract["plate_id"], "loaded": True},
                "thermocycler": ThermocyclerProgramBackend().serialize(),
            }
        )
    elif family == "incubator_shaker":
        base.update(
            {
                "plate": {
                    "plate_id": contract["plate_id"],
                    "barcode": contract["barcode"],
                    "location": "loading_tray",
                    "version": 1,
                },
                "incubator": {
                    "door_open": False,
                    "slots": {f"S{i:02d}": None for i in range(1, 9)},
                    "target_temperature_c": None,
                    "current_temperature_c": 22.0,
                    "shaking": False,
                    "shake_rpm": 0.0,
                    "conditioned_exposure_s": 0.0,
                },
                "reader": {"busy": False},
                "measurement_count": 0,
            }
        )
    elif family == "powder_balance":
        base.update(
            {
                "vial": {
                    "vial_id": contract["vial_id"],
                    "powder": contract["powder"],
                    "empty_mass_g": contract["empty_vial_mass_g"],
                    "powder_mass_mg": 0.0,
                    "on_balance": True,
                },
                "balance": {"tare_offset_g": 0.0, "tared": False, "read_count": 0},
                "powder_dispenser": {"pulse_count": 0},
            }
        )
    else:
        raise ValueError(f"Unsupported workflow family: {family}")
    return base

