"""Deterministic scenario sampler for pylabrobot_lab_v0.

Creates a PyLabRobot-backed dry-run episode: a Deck with LiquidHandler,
plates, tip rack, and a pipette — all simulated via chatterbox backends.
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from api_gym.worlds.pylabrobot_lab_v0.state import (
    RUN_METADATA_NAME,
    STATE_JSON_NAME,
    TASK_NAME,
    LabState,
    create_deck,
    register_state,
    create_liquid_handler,
    create_plate,
    create_tip_rack,
    get_well,
    set_well_volume,
    setup_deck,
)

WORLD = "pylabrobot_lab_v0"
WORLD_ID = "pylabrobot-lab-v0"


@dataclass(frozen=True)
class SampledEpisode:
    run_dir: Path
    state_path: Path
    task_path: Path
    run_metadata_path: Path
    task: dict[str, object]
    lab_state: LabState


ScenarioBuilder = Callable[[Path, int], tuple[dict[str, object], LabState]]


def sample_episode(*, scenario: str, seed: int, out_dir: Path) -> SampledEpisode:
    """Create one deterministic PyLabRobot-backed episode run."""
    if scenario not in SCENARIOS:
        supported = ", ".join(sorted(SCENARIOS))
        raise ValueError(
            f"Unsupported pylabrobot_lab_v0 scenario '{scenario}'. Supported: {supported}"
        )

    out_dir = out_dir.resolve()
    state_path = out_dir / STATE_JSON_NAME
    task_path = out_dir / TASK_NAME
    run_metadata_path = out_dir / RUN_METADATA_NAME

    if state_path.exists() or task_path.exists() or run_metadata_path.exists():
        raise FileExistsError(
            f"Run directory already contains API Gym state files: {out_dir}"
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    task, lab_state = SCENARIOS[scenario](out_dir, seed)

    # Persist and register
    lab_state.save(state_path)
    register_state(out_dir, lab_state)
    task_path.write_text(json.dumps(task, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    run_metadata = {
        "world": WORLD,
        "world_id": WORLD_ID,
        "scenario": scenario,
        "seed": seed,
        "mode": "dry_run",
        "state": STATE_JSON_NAME,
        "task": TASK_NAME,
    }
    run_metadata_path.write_text(
        json.dumps(run_metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    return SampledEpisode(
        run_dir=out_dir,
        state_path=state_path,
        task_path=task_path,
        run_metadata_path=run_metadata_path,
        task=task,
        lab_state=lab_state,
    )


def _stable_prefix(scenario: str, seed: int) -> str:
    digest = hashlib.sha256(f"{WORLD}:{scenario}:{seed}".encode("utf-8")).hexdigest()
    return digest[:10]


def _build_plate_transfer_qc(db_path: Path, seed: int) -> tuple[dict[str, object], LabState]:
    """Build a plate QC scenario: transfer 50 uL, read OD600, submit decision."""
    scenario = "plate_transfer_qc"
    prefix = _stable_prefix(scenario, seed)

    # ── Build PyLabRobot objects ────────────────────────────────────────
    deck = create_deck()
    lh = create_liquid_handler(deck)

    assay_plate = create_plate("assay_plate")
    source_plate = create_plate("source_plate")
    tip_rack = create_tip_rack("tip_rack_01", with_tips=True)

    setup_deck(lh, assay_plate, source_plate, tip_rack)

    # Fill source well A1 with 120 uL QC control
    src_well = get_well(source_plate, "A1")
    set_well_volume(src_well, 120.0)

    # Assay plate B1 is the intended target (empty, 0 uL by default)
    # Mark B1 with metadata so the LLM can identify the correct target well
    tgt_well = get_well(assay_plate, "B1")
    well_metadata: dict[str, dict[str, Any]] = {
        "source_plate": {"A1": {"contents": "qc_control"}},
        "assay_plate": {"B1": {"contents": "empty_assay_well", "purpose": "qc_target"}},
    }

    # ── Build LabState ─────────────────────────────────────────────────
    lab_state = LabState(
        deck=deck,
        liquid_handler=lh,
        plate=assay_plate,
        source_plate=source_plate,
        tip_rack=tip_rack,
        setup_done=True,
        well_metadata=well_metadata,
        deck_info={
            "deck_name": deck.name,
            "plate_name": assay_plate.name,
            "plate_wells": len(list(assay_plate.children)),
            "source_plate_name": source_plate.name,
            "tip_rack_name": tip_rack.name,
            "tip_count": len([t for t in tip_rack.children if getattr(t, "has_tip", False)]),
            "pipette_channels": len(lh.head) if hasattr(lh, "head") else 0,
        },
    )

    # Hidden expected resolution
    expected = {
        "scenario": scenario,
        "source_well": "source_plate.A1",
        "target_well": "assay_plate.B1",
        "transfer_volume_ul": 50,
        "wavelength_nm": 600,
        "control_band": {"min": 0.75, "max": 0.9},
        "expected_readout_value": 0.82,
        "expected_decision": "continue",
    }
    lab_state.insert_event(
        event_type="expected_resolution.created",
        object_type="scenario",
        object_id=scenario,
        payload=expected,
        visible_to_agent=False,
    )

    task: dict[str, object] = {
        "schema_version": "api_gym.task.v0",
        "world": WORLD,
        "world_id": WORLD_ID,
        "scenario": scenario,
        "seed": seed,
        "objective": "Evaluate whether the plate QC workflow should continue.",
        "prompt": (
            "Evaluate whether the plate QC workflow should continue. Inspect the dry-run "
            "deck state and labware state, use the available lab tools to gather evidence, "
            "and submit a final protocol decision with the supporting readout evidence."
        ),
    }

    return task, lab_state


def _build_plate_transfer_qc_ot2(db_path: Path, seed: int) -> tuple[dict[str, object], LabState]:
    """Build a plate QC scenario using OT-2 Simulator + Visualizer backend."""
    scenario = "plate_transfer_qc"
    prefix = _stable_prefix(scenario, seed)

    from api_gym.worlds.pylabrobot_lab_v0.state_ot2 import (
        create_ot2_deck,
        create_ot2_liquid_handler,
        create_ot2_plate,
        create_ot2_tip_rack,
        setup_ot2_deck,
    )

    deck = create_ot2_deck()
    lh = create_ot2_liquid_handler(deck)

    assay_plate = create_ot2_plate("assay_plate")
    source_plate = create_ot2_plate("source_plate")
    tip_rack = create_ot2_tip_rack("tip_rack_01", with_tips=True)

    setup_ot2_deck(lh, assay_plate, source_plate, tip_rack)

    # Fill source well A1 with 120 uL
    from api_gym.worlds.pylabrobot_lab_v0.state import get_well, set_well_volume
    src_well = get_well(source_plate, "A1")
    set_well_volume(src_well, 120.0)

    well_metadata: dict[str, dict[str, Any]] = {
        "source_plate": {"A1": {"contents": "qc_control"}},
        "assay_plate": {"B1": {"contents": "empty_assay_well", "purpose": "qc_target"}},
    }

    lab_state = LabState(
        deck=deck, liquid_handler=lh,
        plate=assay_plate, source_plate=source_plate, tip_rack=tip_rack,
        setup_done=True,
        well_metadata=well_metadata,
        deck_info={
            "deck_name": deck.name,
            "plate_name": assay_plate.name,
            "plate_wells": len(list(assay_plate.children)),
            "source_plate_name": source_plate.name,
            "tip_rack_name": tip_rack.name,
            "tip_count": len([t for t in tip_rack.children if getattr(t, "has_tip", False)]),
        },
    )

    expected = {
        "scenario": scenario, "source_well": "source_plate.A1",
        "target_well": "assay_plate.B1", "transfer_volume_ul": 50,
        "wavelength_nm": 600,
        "control_band": {"min": 0.75, "max": 0.9},
        "expected_readout_value": 0.82, "expected_decision": "continue",
    }
    lab_state.insert_event(
        event_type="expected_resolution.created",
        object_type="scenario", object_id=scenario,
        payload=expected, visible_to_agent=False,
    )

    task: dict[str, object] = {
        "schema_version": "api_gym.task.v0", "world": WORLD, "world_id": WORLD_ID,
        "scenario": scenario, "seed": seed,
        "objective": "Evaluate whether the plate QC workflow should continue.",
        "prompt": (
            "Evaluate whether the plate QC workflow should continue. Inspect the dry-run "
            "deck state and labware state, use the available lab tools to gather evidence, "
            "and submit a final protocol decision with the supporting readout evidence."
        ),
    }
    return task, lab_state


def _build_serial_dilution_qc(db_path: Path, seed: int) -> tuple[dict[str, object], LabState]:
    """Serial dilution: A1 stock → B1→B2→B3→B4→B5, read OD600, verify curve."""
    scenario = "serial_dilution_qc"
    prefix = _stable_prefix(scenario, seed)

    deck = create_deck()
    lh = create_liquid_handler(deck)

    assay_plate = create_plate("assay_plate")
    source_plate = create_plate("source_plate")
    tip_rack = create_tip_rack("tip_rack_01", with_tips=True)

    setup_deck(lh, assay_plate, source_plate, tip_rack)

    # Source A1: 200 uL concentrated stock
    from api_gym.worlds.pylabrobot_lab_v0.state import get_well, set_well_volume
    src_well = get_well(source_plate, "A1")
    set_well_volume(src_well, 200.0)

    # Assay B1-B5: each 50 uL buffer (diluent)
    diluent_wells = ["B1", "B2", "B3", "B4", "B5"]
    for well_name in diluent_wells:
        well = get_well(assay_plate, well_name)
        set_well_volume(well, 50.0)

    well_metadata: dict[str, dict[str, Any]] = {
        "source_plate": {"A1": {"contents": "concentrated_stock", "volume_ul": 200}},
        "assay_plate": {
            "B1": {"contents": "diluent", "purpose": "dilution_1_2", "initial_volume_ul": 50},
            "B2": {"contents": "diluent", "purpose": "dilution_1_4", "initial_volume_ul": 50},
            "B3": {"contents": "diluent", "purpose": "dilution_1_8", "initial_volume_ul": 50},
            "B4": {"contents": "diluent", "purpose": "dilution_1_16", "initial_volume_ul": 50},
            "B5": {"contents": "diluent", "purpose": "dilution_1_32", "initial_volume_ul": 50},
        },
    }

    lab_state = LabState(
        deck=deck, liquid_handler=lh,
        plate=assay_plate, source_plate=source_plate, tip_rack=tip_rack,
        setup_done=True,
        well_metadata=well_metadata,
        deck_info={
            "deck_name": deck.name,
            "plate_name": assay_plate.name, "plate_wells": len(list(assay_plate.children)),
            "source_plate_name": source_plate.name,
            "tip_rack_name": tip_rack.name,
            "tip_count": len([t for t in tip_rack.children if getattr(t, "has_tip", False)]),
        },
    )

    expected = {
        "scenario": scenario,
        "source_well": "source_plate.A1",
        "dilution_wells": ["assay_plate.B1", "assay_plate.B2", "assay_plate.B3",
                           "assay_plate.B4", "assay_plate.B5"],
        "transfer_volume_ul": 50,
        "wavelength_nm": 600,
        "dilution_chain": ["A1", "B1", "B2", "B3", "B4", "B5"],
        "expected_transfers": 5,
        "expected_tips_used": 5,
        # OD600 should decrease: stock > 1:2 > 1:4 > ... > 1:32
        "expected_od600_order": "decreasing",
    }
    lab_state.insert_event(
        event_type="expected_resolution.created",
        object_type="scenario", object_id=scenario,
        payload=expected, visible_to_agent=False,
    )

    task: dict[str, object] = {
        "schema_version": "api_gym.task.v0", "world": WORLD, "world_id": WORLD_ID,
        "scenario": scenario, "seed": seed,
        "objective": "Perform a 5-step serial dilution and verify the dilution curve.",
        "prompt": (
            "Perform a 5-step serial dilution. The source plate well A1 contains 200 uL of "
            "concentrated stock. The assay plate wells B1 through B5 each contain 50 uL of "
            "diluent/buffer. Transfer 50 uL from the stock (A1) to B1 (1:2), then 50 uL from "
            "B1 to B2 (1:4), B2 to B3 (1:8), B3 to B4 (1:16), B4 to B5 (1:32). Use a fresh "
            "tip for each transfer step to avoid cross-contamination. Mix each well after "
            "dispensing. After all transfers, read OD600 of all 6 wells (A1 and B1-B5) and "
            "submit your decision on whether the dilution curve is valid."
        ),
    }
    return task, lab_state


def _build_serial_dilution_qc_ot2(db_path: Path, seed: int) -> tuple[dict[str, object], LabState]:
    """Serial dilution for OT-2 Visualizer."""
    scenario = "serial_dilution_qc"
    prefix = _stable_prefix(scenario, seed)

    from api_gym.worlds.pylabrobot_lab_v0.state_ot2 import (
        create_ot2_deck, create_ot2_liquid_handler,
        create_ot2_plate, create_ot2_tip_rack, setup_ot2_deck,
    )

    deck = create_ot2_deck()
    lh = create_ot2_liquid_handler(deck)
    assay_plate = create_ot2_plate("assay_plate")
    source_plate = create_ot2_plate("source_plate")
    tip_rack = create_ot2_tip_rack("tip_rack_01", with_tips=True)
    setup_ot2_deck(lh, assay_plate, source_plate, tip_rack)

    from api_gym.worlds.pylabrobot_lab_v0.state import get_well, set_well_volume
    set_well_volume(get_well(source_plate, "A1"), 200.0)
    for w in ["B1", "B2", "B3", "B4", "B5"]:
        set_well_volume(get_well(assay_plate, w), 50.0)

    well_metadata: dict[str, dict[str, Any]] = {
        "source_plate": {"A1": {"contents": "concentrated_stock", "volume_ul": 200}},
        "assay_plate": {
            "B1": {"contents": "diluent", "purpose": "dilution_1_2", "initial_volume_ul": 50},
            "B2": {"contents": "diluent", "purpose": "dilution_1_4", "initial_volume_ul": 50},
            "B3": {"contents": "diluent", "purpose": "dilution_1_8", "initial_volume_ul": 50},
            "B4": {"contents": "diluent", "purpose": "dilution_1_16", "initial_volume_ul": 50},
            "B5": {"contents": "diluent", "purpose": "dilution_1_32", "initial_volume_ul": 50},
        },
    }

    lab_state = LabState(
        deck=deck, liquid_handler=lh,
        plate=assay_plate, source_plate=source_plate, tip_rack=tip_rack,
        setup_done=True, well_metadata=well_metadata,
        deck_info={
            "deck_name": deck.name, "plate_name": assay_plate.name,
            "plate_wells": len(list(assay_plate.children)),
            "source_plate_name": source_plate.name,
            "tip_rack_name": tip_rack.name,
            "tip_count": len([t for t in tip_rack.children if getattr(t, "has_tip", False)]),
        },
    )

    expected = {
        "scenario": scenario,
        "source_well": "source_plate.A1",
        "dilution_wells": ["assay_plate.B1", "assay_plate.B2", "assay_plate.B3",
                           "assay_plate.B4", "assay_plate.B5"],
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "expected_transfers": 5, "expected_tips_used": 5,
        "expected_od600_order": "decreasing",
    }
    lab_state.insert_event(
        event_type="expected_resolution.created",
        object_type="scenario", object_id=scenario,
        payload=expected, visible_to_agent=False,
    )

    task: dict[str, object] = {
        "schema_version": "api_gym.task.v0", "world": WORLD, "world_id": WORLD_ID,
        "scenario": scenario, "seed": seed,
        "objective": "Perform a 5-step serial dilution and verify the dilution curve.",
        "prompt": (
            "Perform a 5-step serial dilution. The source plate well A1 contains 200 uL of "
            "concentrated stock. The assay plate wells B1 through B5 each contain 50 uL of "
            "diluent/buffer. Transfer 50 uL from the stock (A1) to B1 (1:2), then 50 uL from "
            "B1 to B2 (1:4), B2 to B3 (1:8), B3 to B4 (1:16), B4 to B5 (1:32). Use a fresh "
            "tip for each transfer step to avoid cross-contamination. Mix each well after "
            "dispensing. After all transfers, read OD600 of all 6 wells (A1 and B1-B5) and "
            "submit your decision on whether the dilution curve is valid."
        ),
    }
    return task, lab_state


SCENARIOS: dict[str, ScenarioBuilder] = {
    "plate_transfer_qc": _build_plate_transfer_qc,
    "plate_transfer_qc_ot2": _build_plate_transfer_qc_ot2,
    "serial_dilution_qc": _build_serial_dilution_qc,
    "serial_dilution_qc_ot2": _build_serial_dilution_qc_ot2,
}
