"""Deterministic scenario sampler for pylabrobot_lab_v0.

Creates a PyLabRobot-backed dry-run episode: a Deck with LiquidHandler,
plates, tip rack, and a pipette — all simulated via chatterbox backends.
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass, field
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


# ── TaskSpec: declarative task definition ──────────────────────────────────


@dataclass
class DeckSetup:
    """Physical layout of the OT-2 deck."""
    tip_count: int = 96
    tip_slot: int = 1
    source_slot: int = 5
    assay_slot: int = 6


@dataclass
class ProtocolStep:
    """One step in the expected protocol (for documentation / verifier ref)."""
    type: str          # "transfer" | "read" | "submit"
    source: str = ""   # e.g. "source_plate.A1"
    target: str = ""   # e.g. "assay_plate.B1"
    volume_ul: float = 50.0
    tip: str = ""      # e.g. "tip_rack_01.A1"


@dataclass
class TaskSpec:
    """Declarative specification for one benchmark task."""
    scenario: str
    objective: str
    prompt: str
    deck_setup: DeckSetup = field(default_factory=DeckSetup)
    initial_volumes: dict[str, float] = field(default_factory=dict)
    well_metadata: dict[str, dict[str, Any]] = field(default_factory=dict)
    protocol: list[ProtocolStep] = field(default_factory=list)
    expected: dict[str, Any] = field(default_factory=dict)
    stochastic_config: dict[str, Any] | None = None  # {"od600_noise": True, "fault_prob": 0.15}


def _stable_prefix(scenario: str, seed: int) -> str:
    digest = hashlib.sha256(f"{WORLD}:{scenario}:{seed}".encode("utf-8")).hexdigest()
    return digest[:10]


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


# ── Unified builder ────────────────────────────────────────────────────────


def _build_from_spec(spec: TaskSpec, out_dir: Path, seed: int,
                     backend: str = "chatterbox") -> tuple[dict[str, object], LabState]:
    """Build a complete episode from a TaskSpec definition.

    *backend* is "chatterbox" for the standard simulator or "ot2" for the
    OT-2 Visualizer backend.
    """
    scenario = spec.scenario

    # ── Create deck / labware ──────────────────────────────────────────
    if backend == "ot2":
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
    else:
        deck = create_deck()
        lh = create_liquid_handler(deck)
        assay_plate = create_plate("assay_plate")
        source_plate = create_plate("source_plate")
        tip_rack = create_tip_rack("tip_rack_01", with_tips=True)
        setup_deck(lh, assay_plate, source_plate, tip_rack)

    # ── Limited-tip support: remove tips from rack if requested ─────────
    tip_count = spec.deck_setup.tip_count
    if tip_count < 96:
        tips_removed = 0
        for child in tip_rack.children:
            if tips_removed >= (96 - tip_count):
                break
            if hasattr(child, "empty") and callable(child.empty):
                child.empty()
                tips_removed += 1

    # ── Set initial well volumes ────────────────────────────────────────
    for ref, vol in spec.initial_volumes.items():
        plate_name, well_name = ref.split(".", 1)
        plate = source_plate if plate_name == "source_plate" else assay_plate
        set_well_volume(get_well(plate, well_name), vol)

    # ── Build LabState ──────────────────────────────────────────────────
    active_tip_count = len([t for t in tip_rack.children if _tip_has_tip(t)])
    lab_state = LabState(
        deck=deck, liquid_handler=lh,
        plate=assay_plate, source_plate=source_plate, tip_rack=tip_rack,
        setup_done=True,
        well_metadata=spec.well_metadata,
        deck_info={
            "deck_name": deck.name,
            "plate_name": assay_plate.name,
            "plate_wells": len(list(assay_plate.children)),
            "source_plate_name": source_plate.name,
            "tip_rack_name": tip_rack.name,
            "tip_count": active_tip_count,
        },
    )

    # ── Hidden expected resolution ──────────────────────────────────────
    expected = dict(spec.expected)
    expected["scenario"] = scenario
    lab_state.insert_event(
        event_type="expected_resolution.created",
        object_type="scenario", object_id=scenario,
        payload=expected, visible_to_agent=False,
    )

    # ── Stochastic schedules ────────────────────────────────────────────
    stoch = spec.stochastic_config
    if stoch:
        from api_gym.worlds.pylabrobot_lab_v0.stochastic import (
            NoiseSchedule, FaultSchedule,
            NOISE_SCHEDULE_NAME, FAULT_SCHEDULE_NAME,
        )
        readout_specs = _extract_readout_specs(spec)
        if stoch.get("od600_noise"):
            noise = NoiseSchedule.generate(
                seed=seed, readout_specs=readout_specs,
                sigma=stoch.get("noise_sigma", 0.03),
            )
            noise.save(out_dir / NOISE_SCHEDULE_NAME)
        if stoch.get("fault_prob", 0) > 0:
            fault = FaultSchedule.generate(
                seed=seed, readout_specs=readout_specs,
                fault_probability=stoch["fault_prob"],
            )
            fault.save(out_dir / FAULT_SCHEDULE_NAME)

    # ── Task dict ───────────────────────────────────────────────────────
    task: dict[str, object] = {
        "schema_version": "api_gym.task.v0",
        "world": WORLD, "world_id": WORLD_ID,
        "scenario": scenario, "seed": seed,
        "objective": spec.objective,
        "prompt": spec.prompt,
    }

    return task, lab_state


def _tip_has_tip(tip_spot: Any) -> bool:
    """Check whether a tip spot currently has a tip.

    PyLabRobot TipSpot stores this in a TipTracker and via the ``has_tip``
    method.  We try both the tracker attribute and the callable method.
    """
    if hasattr(tip_spot, "tracker") and tip_spot.tracker is not None:
        return bool(tip_spot.tracker.has_tip)
    if hasattr(tip_spot, "has_tip") and callable(tip_spot.has_tip):
        return tip_spot.has_tip()
    return bool(getattr(tip_spot, "has_tip", False))


def _extract_readout_specs(spec: TaskSpec) -> list[dict[str, Any]]:
    """Pull readout specs for stochastic schedule generation.

    Derives from protocol steps if present, otherwise from expected dict.
    """
    readouts: list[dict[str, Any]] = []

    # First try explicit protocol steps
    read_steps = [s for s in spec.protocol if s.type == "read"]
    for step in read_steps:
        well = step.target.split(".")[-1] if "." in step.target else step.target
        readouts.append({
            "plate_id": step.target.split(".")[0] if "." in step.target else "assay_plate",
            "wavelength_nm": spec.expected.get("wavelength_nm", 600),
            "wells": [well],
        })

    # Fallback: derive from expected dict
    if not readouts:
        wavelength = spec.expected.get("wavelength_nm", 600)
        target_wells = spec.expected.get("readout_wells", [])
        if not target_wells:
            target_well = spec.expected.get("target_well", "")
            if target_well:
                target_wells = [target_well.split(".")[-1] if "." in target_well else target_well]
        if not target_wells:
            dilution_wells = spec.expected.get("dilution_wells", [])
            target_wells = [w.split(".")[-1] if "." in w else w for w in dilution_wells]
        if not target_wells:
            target_wells_list = spec.expected.get("target_wells", [])
            target_wells = [w.split(".")[-1] if "." in w else w for w in target_wells_list]
        if target_wells:
            readouts.append({
                "plate_id": "assay_plate",
                "wavelength_nm": wavelength,
                "wells": target_wells,
            })

    return readouts


# ── Scenario builders (delegating to _build_from_spec) ─────────────────────


def _build_plate_transfer_qc(db_path: Path, seed: int) -> tuple[dict[str, object], LabState]:
    return _build_from_spec(PLATE_TRANSFER_QC, db_path, seed, backend="chatterbox")


def _build_plate_transfer_qc_ot2(db_path: Path, seed: int) -> tuple[dict[str, object], LabState]:
    return _build_from_spec(PLATE_TRANSFER_QC, db_path, seed, backend="ot2")


def _build_serial_dilution_qc(db_path: Path, seed: int) -> tuple[dict[str, object], LabState]:
    return _build_from_spec(SERIAL_DILUTION_QC, db_path, seed, backend="chatterbox")


def _build_serial_dilution_qc_ot2(db_path: Path, seed: int) -> tuple[dict[str, object], LabState]:
    return _build_from_spec(SERIAL_DILUTION_QC, db_path, seed, backend="ot2")


def _build_multi_sample_qc(db_path: Path, seed: int) -> tuple[dict[str, object], LabState]:
    return _build_from_spec(MULTI_SAMPLE_QC, db_path, seed, backend="chatterbox")


def _build_multi_sample_qc_ot2(db_path: Path, seed: int) -> tuple[dict[str, object], LabState]:
    return _build_from_spec(MULTI_SAMPLE_QC, db_path, seed, backend="ot2")


def _build_concentration_gradient_qc(db_path: Path, seed: int) -> tuple[dict[str, object], LabState]:
    return _build_from_spec(CONCENTRATION_GRADIENT_QC, db_path, seed, backend="chatterbox")


def _build_concentration_gradient_qc_ot2(db_path: Path, seed: int) -> tuple[dict[str, object], LabState]:
    return _build_from_spec(CONCENTRATION_GRADIENT_QC, db_path, seed, backend="ot2")


def _build_limited_tips_qc(db_path: Path, seed: int) -> tuple[dict[str, object], LabState]:
    return _build_from_spec(LIMITED_TIPS_QC, db_path, seed, backend="chatterbox")


def _build_limited_tips_qc_ot2(db_path: Path, seed: int) -> tuple[dict[str, object], LabState]:
    return _build_from_spec(LIMITED_TIPS_QC, db_path, seed, backend="ot2")


def _build_low_reagent_qc(db_path: Path, seed: int) -> tuple[dict[str, object], LabState]:
    return _build_from_spec(LOW_REAGENT_QC, db_path, seed, backend="chatterbox")


def _build_low_reagent_qc_ot2(db_path: Path, seed: int) -> tuple[dict[str, object], LabState]:
    return _build_from_spec(LOW_REAGENT_QC, db_path, seed, backend="ot2")


def _build_instrument_busy_qc(db_path: Path, seed: int) -> tuple[dict[str, object], LabState]:
    return _build_from_spec(INSTRUMENT_BUSY_QC, db_path, seed, backend="chatterbox")


def _build_instrument_busy_qc_ot2(db_path: Path, seed: int) -> tuple[dict[str, object], LabState]:
    return _build_from_spec(INSTRUMENT_BUSY_QC, db_path, seed, backend="ot2")


def _build_stale_deck_qc(db_path: Path, seed: int) -> tuple[dict[str, object], LabState]:
    return _build_from_spec(STALE_DECK_QC, db_path, seed, backend="chatterbox")


def _build_stale_deck_qc_ot2(db_path: Path, seed: int) -> tuple[dict[str, object], LabState]:
    return _build_from_spec(STALE_DECK_QC, db_path, seed, backend="ot2")


def _build_borderline_qc(db_path: Path, seed: int) -> tuple[dict[str, object], LabState]:
    return _build_from_spec(BORDERLINE_QC, db_path, seed, backend="chatterbox")


def _build_borderline_qc_ot2(db_path: Path, seed: int) -> tuple[dict[str, object], LabState]:
    return _build_from_spec(BORDERLINE_QC, db_path, seed, backend="ot2")


def _build_cross_contamination_qc(db_path: Path, seed: int) -> tuple[dict[str, object], LabState]:
    return _build_from_spec(CROSS_CONTAMINATION_QC, db_path, seed, backend="chatterbox")


def _build_cross_contamination_qc_ot2(db_path: Path, seed: int) -> tuple[dict[str, object], LabState]:
    return _build_from_spec(CROSS_CONTAMINATION_QC, db_path, seed, backend="ot2")


# ── Task definitions ───────────────────────────────────────────────────────


PLATE_TRANSFER_QC = TaskSpec(
    scenario="plate_transfer_qc",
    objective="Evaluate whether the plate QC workflow should continue.",
    prompt=(
        "Evaluate whether the plate QC workflow should continue. Inspect the dry-run "
        "deck state and labware state, use the available lab tools to gather evidence, "
        "and submit a final protocol decision with the supporting readout evidence."
    ),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control"}},
        "assay_plate": {"B1": {"contents": "empty_assay_well", "purpose": "qc_target"}},
    },
    expected={
        "source_well": "source_plate.A1",
        "target_well": "assay_plate.B1",
        "transfer_volume_ul": 50,
        "wavelength_nm": 600,
        "control_band": {"min": 0.75, "max": 0.9},
        "expected_readout_value": 0.82,
        "expected_decision": "continue",
    },
)


SERIAL_DILUTION_QC = TaskSpec(
    scenario="serial_dilution_qc",
    objective="Perform a 5-step serial dilution and verify the dilution curve.",
    prompt=(
        "Perform a 5-step serial dilution. The source plate well A1 contains 200 uL of "
        "concentrated stock. The assay plate wells B1 through B5 each contain 50 uL of "
        "diluent/buffer. Transfer 50 uL from the stock (A1) to B1 (1:2), then 50 uL from "
        "B1 to B2 (1:4), B2 to B3 (1:8), B3 to B4 (1:16), B4 to B5 (1:32). Use a fresh "
        "tip for each transfer step to avoid cross-contamination. Mix each well after "
        "dispensing. After all transfers, read OD600 of all 6 wells (A1 and B1-B5) and "
        "submit your decision on whether the dilution curve is valid."
    ),
    initial_volumes={
        "source_plate.A1": 200.0,
        "assay_plate.B1": 50.0, "assay_plate.B2": 50.0,
        "assay_plate.B3": 50.0, "assay_plate.B4": 50.0, "assay_plate.B5": 50.0,
    },
    well_metadata={
        "source_plate": {"A1": {"contents": "concentrated_stock", "volume_ul": 200}},
        "assay_plate": {
            "B1": {"contents": "diluent", "purpose": "dilution_1_2", "initial_volume_ul": 50},
            "B2": {"contents": "diluent", "purpose": "dilution_1_4", "initial_volume_ul": 50},
            "B3": {"contents": "diluent", "purpose": "dilution_1_8", "initial_volume_ul": 50},
            "B4": {"contents": "diluent", "purpose": "dilution_1_16", "initial_volume_ul": 50},
            "B5": {"contents": "diluent", "purpose": "dilution_1_32", "initial_volume_ul": 50},
        },
    },
    expected={
        "source_well": "source_plate.A1",
        "dilution_wells": ["assay_plate.B1", "assay_plate.B2", "assay_plate.B3",
                           "assay_plate.B4", "assay_plate.B5"],
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "expected_transfers": 5, "expected_tips_used": 5,
        "expected_od600_order": "decreasing",
    },
)


MULTI_SAMPLE_QC = TaskSpec(
    scenario="multi_sample_qc",
    objective="Evaluate three independent QC samples in parallel.",
    prompt=(
        "Three QC control samples are located in source plate wells A1, A2, and A3 "
        "(120 uL each). Transfer 50 uL from each source well to the corresponding "
        "assay plate well (A1→B1, A2→B2, A3→B3). Use a fresh tip for each transfer. "
        "Read OD600 for B1, B2, and B3 at 600 nm. Submit a separate continue/hold "
        "decision for each well based on the control band [0.75, 0.9]."
    ),
    initial_volumes={
        "source_plate.A1": 120.0, "source_plate.A2": 120.0, "source_plate.A3": 120.0,
    },
    well_metadata={
        "source_plate": {
            "A1": {"contents": "qc_control_sample_1"},
            "A2": {"contents": "qc_control_sample_2"},
            "A3": {"contents": "qc_control_sample_3"},
        },
        "assay_plate": {
            "B1": {"contents": "empty_assay_well", "purpose": "qc_target_1"},
            "B2": {"contents": "empty_assay_well", "purpose": "qc_target_2"},
            "B3": {"contents": "empty_assay_well", "purpose": "qc_target_3"},
        },
    },
    expected={
        "source_wells": ["source_plate.A1", "source_plate.A2", "source_plate.A3"],
        "target_wells": ["assay_plate.B1", "assay_plate.B2", "assay_plate.B3"],
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "control_band": {"min": 0.75, "max": 0.9},
        "expected_transfers": 3,
    },
)


CONCENTRATION_GRADIENT_QC = TaskSpec(
    scenario="concentration_gradient_qc",
    objective="Verify that OD600 readings are linearly related to buffer dilution.",
    prompt=(
        "Source plate A1 contains 200 uL of concentrated stock. Assay plate wells "
        "B1-B5 contain increasing amounts of buffer: B1=0, B2=25, B3=50, B4=75, B5=100 uL. "
        "Transfer 50 uL of stock into each of B1-B5 using fresh tips. Read OD600 for all "
        "5 wells at 600 nm. Verify that OD600 decreases as buffer volume increases "
        "(linear relationship expected). Submit your decision on whether the gradient "
        "is valid."
    ),
    initial_volumes={
        "source_plate.A1": 200.0,
        "assay_plate.B1": 0.0, "assay_plate.B2": 25.0,
        "assay_plate.B3": 50.0, "assay_plate.B4": 75.0, "assay_plate.B5": 100.0,
    },
    well_metadata={
        "source_plate": {"A1": {"contents": "concentrated_stock"}},
        "assay_plate": {
            "B1": {"contents": "buffer", "buffer_vol_ul": 0, "purpose": "gradient_0"},
            "B2": {"contents": "buffer", "buffer_vol_ul": 25, "purpose": "gradient_25"},
            "B3": {"contents": "buffer", "buffer_vol_ul": 50, "purpose": "gradient_50"},
            "B4": {"contents": "buffer", "buffer_vol_ul": 75, "purpose": "gradient_75"},
            "B5": {"contents": "buffer", "buffer_vol_ul": 100, "purpose": "gradient_100"},
        },
    },
    expected={
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "expected_transfers": 5, "expected_tips_used": 5,
        "expected_od600_order": "decreasing",
    },
)


LIMITED_TIPS_QC = TaskSpec(
    scenario="limited_tips_qc",
    objective="Detect tip exhaustion and refuse to proceed when tips run out.",
    prompt=(
        "You need to perform three 50 uL transfers: source_plate.A1→assay_plate.B1, "
        "source_plate.A1→assay_plate.B2, source_plate.A1→assay_plate.B3. "
        "IMPORTANT: The tip rack has only 2 tips available. You MUST inspect the "
        "tip rack before each transfer. If no tips are available, you must refuse "
        "the operation and report that the protocol cannot be completed due to "
        "tip exhaustion. Do NOT attempt to aspirate without a tip."
    ),
    deck_setup=DeckSetup(tip_count=2),
    initial_volumes={
        "source_plate.A1": 120.0,
    },
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control"}},
        "assay_plate": {
            "B1": {"contents": "empty_assay_well", "purpose": "qc_target_1"},
            "B2": {"contents": "empty_assay_well", "purpose": "qc_target_2"},
            "B3": {"contents": "empty_assay_well", "purpose": "qc_target_3"},
        },
    },
    expected={
        "source_well": "source_plate.A1",
        "target_wells": ["assay_plate.B1", "assay_plate.B2", "assay_plate.B3"],
        "transfer_volume_ul": 50,
        "max_transfers_possible": 2,
        "expect_tip_exhaustion": True,
    },
)


LOW_REAGENT_QC = TaskSpec(
    scenario="low_reagent_qc",
    objective="Detect insufficient source volume and refuse to proceed.",
    prompt=(
        "You are asked to transfer 50 uL from source_plate.A1 to assay_plate.B1 "
        "for a QC check. IMPORTANT: The source well may have insufficient volume. "
        "You MUST check the actual volume in source_plate.A1 before aspirating. "
        "If the volume is less than 50 uL, refuse the operation and report that "
        "the protocol cannot proceed due to insufficient reagent. Do NOT attempt "
        "to aspirate more than is available."
    ),
    initial_volumes={"source_plate.A1": 30.0},  # Only 30 uL, not enough for 50
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control", "volume_ul": 30}},
        "assay_plate": {"B1": {"contents": "empty_assay_well", "purpose": "qc_target"}},
    },
    expected={
        "source_well": "source_plate.A1",
        "target_well": "assay_plate.B1",
        "transfer_volume_ul": 50,
        "available_volume_ul": 30,
        "expect_overdrawn": True,
    },
)


INSTRUMENT_BUSY_QC = TaskSpec(
    scenario="instrument_busy_qc",
    objective="Handle an instrument fault during reading and retry to get a valid measurement.",
    prompt=(
        "Perform a standard plate QC: transfer 50 uL from source_plate.A1 to "
        "assay_plate.B1, then read OD600 for B1 at 600 nm. The plate reader may "
        "occasionally return an 'instrument_busy' error — if it does, you must "
        "retry the reading (up to 2 retries). Once you have a valid reading, "
        "submit your decision. Do NOT give up after a single fault."
    ),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control"}},
        "assay_plate": {"B1": {"contents": "empty_assay_well", "purpose": "qc_target"}},
    },
    expected={
        "source_well": "source_plate.A1",
        "target_well": "assay_plate.B1",
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "control_band": {"min": 0.75, "max": 0.9},
        "max_retries": 2,
    },
    stochastic_config={"fault_prob": 0.3},
)


STALE_DECK_QC = TaskSpec(
    scenario="stale_deck_qc",
    objective="Detect that the deck state has changed and re-inspect before acting.",
    prompt=(
        "You are asked to transfer 50 uL from source_plate.A1 to assay_plate.B1. "
        "IMPORTANT: The deck state may change between your initial inspection and "
        "your action. You should re-inspect the relevant labware immediately before "
        "each transfer operation. If you rely on stale inspection data, you may "
        "attempt to aspirate from a well that has been changed."
    ),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control"}},
        "assay_plate": {"B1": {"contents": "empty_assay_well", "purpose": "qc_target"}},
    },
    expected={
        "source_well": "source_plate.A1",
        "target_well": "assay_plate.B1",
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "control_band": {"min": 0.75, "max": 0.9},
        "require_fresh_inspection": True,
        "max_staleness_s": 5,
    },
)


BORDERLINE_QC = TaskSpec(
    scenario="borderline_qc",
    objective="Make a QC decision when the OD600 reading is near the control band boundary.",
    prompt=(
        "Perform a standard plate QC: transfer 50 uL from source_plate.A1 to "
        "assay_plate.B1, then read OD600 for B1 at 600 nm. The control band is "
        "[0.75, 0.9]. NOTE: The OD600 reading includes measurement noise (±0.03). "
        "If the reading is very close to the band boundary, consider the "
        "uncertainty in your decision rationale. Submit your decision with a "
        "justification that addresses the measurement uncertainty."
    ),
    initial_volumes={"source_plate.A1": 115.0},  # Tuned so true OD600 ≈ 0.76 (borderline)
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control", "note": "near-boundary concentration"}},
        "assay_plate": {"B1": {"contents": "empty_assay_well", "purpose": "qc_target"}},
    },
    expected={
        "source_well": "source_plate.A1",
        "target_well": "assay_plate.B1",
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "control_band": {"min": 0.75, "max": 0.9},
        "borderline": True,
        "require_uncertainty_rationale": True,
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)


CROSS_CONTAMINATION_QC = TaskSpec(
    scenario="cross_contamination_qc",
    objective="Avoid cross-contamination by using a fresh tip for each transfer.",
    prompt=(
        "You need to perform two transfers: source_plate.A1→assay_plate.B1 (50 uL) "
        "and assay_plate.B1→assay_plate.B2 (50 uL). IMPORTANT: You MUST use a "
        "fresh tip for each transfer. Reusing a tip across different wells will "
        "cause cross-contamination and invalidate the results. After both transfers, "
        "read OD600 for B1 and B2 at 600 nm and submit your decision."
    ),
    initial_volumes={
        "source_plate.A1": 120.0,
        "assay_plate.B1": 50.0,  # diluent
    },
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control"}},
        "assay_plate": {
            "B1": {"contents": "diluent", "purpose": "first_transfer_target"},
            "B2": {"contents": "empty_assay_well", "purpose": "second_transfer_target"},
        },
    },
    expected={
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "expected_transfers": 2,
        "require_fresh_tip_per_transfer": True,
        "expected_tips_used": 2,
    },
)


# ── Scenario registry ──────────────────────────────────────────────────────


SCENARIOS: dict[str, ScenarioBuilder] = {
    "plate_transfer_qc": _build_plate_transfer_qc,
    "plate_transfer_qc_ot2": _build_plate_transfer_qc_ot2,
    "serial_dilution_qc": _build_serial_dilution_qc,
    "serial_dilution_qc_ot2": _build_serial_dilution_qc_ot2,
    "multi_sample_qc": _build_multi_sample_qc,
    "multi_sample_qc_ot2": _build_multi_sample_qc_ot2,
    "concentration_gradient_qc": _build_concentration_gradient_qc,
    "concentration_gradient_qc_ot2": _build_concentration_gradient_qc_ot2,
    "limited_tips_qc": _build_limited_tips_qc,
    "limited_tips_qc_ot2": _build_limited_tips_qc_ot2,
    "low_reagent_qc": _build_low_reagent_qc,
    "low_reagent_qc_ot2": _build_low_reagent_qc_ot2,
    "instrument_busy_qc": _build_instrument_busy_qc,
    "instrument_busy_qc_ot2": _build_instrument_busy_qc_ot2,
    "stale_deck_qc": _build_stale_deck_qc,
    "stale_deck_qc_ot2": _build_stale_deck_qc_ot2,
    "borderline_qc": _build_borderline_qc,
    "borderline_qc_ot2": _build_borderline_qc_ot2,
    "cross_contamination_qc": _build_cross_contamination_qc,
    "cross_contamination_qc_ot2": _build_cross_contamination_qc_ot2,
}
