"""Deterministic scenario sampler for pylabrobot_star_v0.

Creates a Hamilton STAR dry-run episode with carrier-based layout,
optional 96-head and iSWAP arm.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from api_gym.worlds.pylabrobot_lab_v0.stochastic import (
    NoiseSchedule, FaultSchedule,
    NOISE_SCHEDULE_NAME, FAULT_SCHEDULE_NAME,
)
from api_gym.worlds.pylabrobot_star_v0.state import (
    RUN_METADATA_NAME, STATE_JSON_NAME, TASK_NAME,
    LabState,
    create_star_deck, create_liquid_handler,
    create_plate, create_tip_rack, create_trough,
    create_plate_carrier, create_tip_carrier, create_plate_reader,
    create_pump, create_scale, create_centrifuge, create_heater_shaker, create_thermocycler,
    setup_star_deck,
    register_state, get_well, set_well_volume,
    _run_async,
)

# ── Reuse TaskSpec infrastructure from OT-2 world ───────────────────────
from api_gym.worlds.pylabrobot_lab_v0.sampler import (
    TaskSpec, DeckSetup, ProtocolStep,
)

WORLD = "pylabrobot_star_v0"
WORLD_ID = "pylabrobot-star-v0"


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
    if scenario not in SCENARIOS:
        supported = ", ".join(sorted(SCENARIOS))
        raise ValueError(f"Unsupported scenario '{scenario}'. Supported: {supported}")

    out_dir = out_dir.resolve()
    state_path = out_dir / STATE_JSON_NAME
    task_path = out_dir / TASK_NAME
    run_metadata_path = out_dir / RUN_METADATA_NAME

    if state_path.exists() or task_path.exists() or run_metadata_path.exists():
        raise FileExistsError(f"Run directory already exists: {out_dir}")

    out_dir.mkdir(parents=True, exist_ok=True)
    task, lab_state = SCENARIOS[scenario](out_dir, seed)

    lab_state.save(state_path)
    register_state(out_dir, lab_state)
    task_path.write_text(json.dumps(task, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    run_metadata = {
        "world": WORLD, "world_id": WORLD_ID,
        "scenario": scenario, "seed": seed, "mode": "dry_run",
        "state": STATE_JSON_NAME, "task": TASK_NAME,
    }
    run_metadata_path.write_text(
        json.dumps(run_metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return SampledEpisode(run_dir=out_dir, state_path=state_path, task_path=task_path,
                          run_metadata_path=run_metadata_path, task=task, lab_state=lab_state)


# ── Unified builder ─────────────────────────────────────────────────────


def _build_from_spec(spec: TaskSpec, out_dir: Path, seed: int) -> tuple[dict[str, object], LabState]:
    scenario = spec.scenario

    # ── Deck / carriers ────────────────────────────────────────────────
    deck = create_star_deck()
    lh = create_liquid_handler(
        deck,
        num_channels=8,
        with_96_head=spec.expected.get("use_96_head", False),
        with_iswap=spec.expected.get("use_iswap", False),
    )

    plate_carrier = create_plate_carrier("plate_carrier")
    tip_carrier = create_tip_carrier("tip_carrier")

    assay_plate = create_plate("assay_plate")
    source_plate = create_plate("source_plate")
    tip_rack = create_tip_rack("tip_rack_01", with_tips=True)
    trough = None

    # Optional trough
    for ref in spec.initial_volumes:
        if ref.startswith("trough"):
            trough = create_trough("reagent_trough")
            break

    # ── Optional pump ──────────────────────────────────────────────────
    pump = None
    pump_use = spec.expected.get("use_pump", False)
    if pump_use:
        pump_cal = spec.expected.get("pump_calibration", None)
        pump = create_pump("reagent_pump", calibration=pump_cal)

    # ── Optional scale ─────────────────────────────────────────────────
    scale = None
    scale_use = spec.expected.get("use_scale", False)
    if scale_use:
        sw = spec.expected.get("scale_initial_weight", 0.0)
        scale = create_scale("analytical_balance", initial_weight=sw)

    # ── Optional centrifuge ────────────────────────────────────────────
    centrifuge = None
    cent_use = spec.expected.get("use_centrifuge", False)
    if cent_use:
        centrifuge = create_centrifuge("centrifuge")

    # ── Optional thermocycler ────────────────────────────────────
    thermocycler = None
    tc_use = spec.expected.get("use_thermocycler", False)
    if tc_use:
        thermocycler = create_thermocycler("thermocycler")

    # ── Optional heater/shaker ─────────────────────────────────────────
    heater_shaker = None
    hs_use = spec.expected.get("use_heater_shaker", False)
    if hs_use:
        heater_shaker = create_heater_shaker("heater_shaker")

    # ── Optional robot arm ──────────────────────────────────────────────
    arm = None
    arm_use = spec.expected.get("use_arm", False)
    if arm_use:
        from api_gym.worlds.pylabrobot_star_v0.state import create_arm
        arm = create_arm("robot_arm")
        _run_async(arm.setup())

    # ── Optional plate sealer ───────────────────────────────────────────
    sealer = None
    sealer_use = spec.expected.get("use_sealer", False)
    if sealer_use:
        from api_gym.worlds.pylabrobot_star_v0.state import create_sealer
        sealer = create_sealer("plate_sealer")
        _run_async(sealer.setup())

    # ── Optional plate peeler ───────────────────────────────────────────
    peeler = None
    peeler_use = spec.expected.get("use_peeler", False)
    if peeler_use:
        from api_gym.worlds.pylabrobot_star_v0.state import create_peeler
        peeler = create_peeler("plate_peeler")
        _run_async(peeler.setup())

    # ── Optional dedicated shaker ───────────────────────────────────────
    shaker = None
    shaker_use = spec.expected.get("use_shaker", False)
    if shaker_use:
        from api_gym.worlds.pylabrobot_star_v0.state import create_shaker
        shaker = create_shaker("plate_shaker")
        _run_async(shaker.setup())

    # ── Optional temperature controller ─────────────────────────────────
    temp_controller = None
    tc_use = spec.expected.get("use_temp_controller", False)
    if tc_use:
        from api_gym.worlds.pylabrobot_star_v0.state import create_temp_controller
        temp_controller = create_temp_controller("temp_controller")
        _run_async(temp_controller.setup())

    # ── Optional tilter module ──────────────────────────────────────────
    tilter = None
    tilter_use = spec.expected.get("use_tilter", False)
    if tilter_use:
        from api_gym.worlds.pylabrobot_star_v0.state import create_tilter
        tilter = create_tilter("tilter")
        _run_async(tilter.setup())

    # ── Optional storage / incubator ────────────────────────────────────
    storage = None
    storage_use = spec.expected.get("use_storage", False)
    if storage_use:
        from api_gym.worlds.pylabrobot_star_v0.state import create_storage
        storage = create_storage("incubator_storage")
        _run_async(storage.setup())

    # ── Optional powder dispenser ───────────────────────────────────────
    powder_dispenser = None
    pd_use = spec.expected.get("use_powder_dispenser", False)
    if pd_use:
        from api_gym.worlds.pylabrobot_star_v0.state import create_powder_dispenser
        powder_dispenser = create_powder_dispenser("powder_dispenser")
        _run_async(powder_dispenser.setup())

    # ── Optional barcode scanner ────────────────────────────────────────
    barcode_scanner = None
    bc_use = spec.expected.get("use_barcode_scanner", False)
    if bc_use:
        from api_gym.worlds.pylabrobot_star_v0.state import create_barcode_scanner
        barcode_scanner = create_barcode_scanner("barcode_scanner")
        _run_async(barcode_scanner.setup())

    setup_star_deck(lh, plate_carrier, tip_carrier,
                    assay_plate, source_plate, tip_rack, trough)

    # ── Plate reader (PLR PlateReader, standalone instrument) ──────────
    # Not placed on the STAR deck — in real labs the reader is a separate
    # instrument accessed via iSWAP.  Stored in LabState for agent access.
    plate_reader = create_plate_reader("plate_reader")
    _run_async(plate_reader.setup())

    # ── Limited-tip support: remove tips from rack if requested ─────────
    tip_requested = spec.deck_setup.tip_count
    if tip_requested < 96:
        tips_removed = 0
        for child in tip_rack.children:
            if tips_removed >= (96 - tip_requested):
                break
            if hasattr(child, "empty") and callable(child.empty):
                child.empty()
                tips_removed += 1

    # ── Set initial volumes ────────────────────────────────────────────
    for ref, vol in spec.initial_volumes.items():
        plate_name, well_name = ref.split(".", 1)
        if plate_name == "source_plate":
            set_well_volume(get_well(source_plate, well_name), vol)
        elif plate_name == "assay_plate":
            set_well_volume(get_well(assay_plate, well_name), vol)
        elif plate_name == "trough":
            if trough is not None:
                trough.tracker.set_volume(vol)

    # ── LabState ───────────────────────────────────────────────────────
    tip_count = len([t for t in tip_rack.children
                     if hasattr(t, "has_tip") and callable(t.has_tip) and t.has_tip()])
    lab_state = LabState(
        deck=deck, liquid_handler=lh, plate_reader=plate_reader,
        plate=assay_plate, source_plate=source_plate, tip_rack=tip_rack,
        trough=trough, pump=pump, scale=scale, centrifuge=centrifuge, heater_shaker=heater_shaker, thermocycler=thermocycler, arm=arm, sealer=sealer, peeler=peeler, shaker=shaker, temp_controller=temp_controller, tilter=tilter, storage=storage, powder_dispenser=powder_dispenser, barcode_scanner=barcode_scanner,
        setup_done=True,
        well_metadata=spec.well_metadata,
        has_96_head=spec.expected.get("use_96_head", False),
        has_iswap=spec.expected.get("use_iswap", False),
        deck_info={
            "deck_name": deck.name, "num_rails": deck.num_rails,
            "plate_name": assay_plate.name,
            "source_plate_name": source_plate.name,
            "tip_rack_name": tip_rack.name,
            "tip_count": tip_count,
            "has_96_head": spec.expected.get("use_96_head", False),
            "has_iswap": spec.expected.get("use_iswap", False),
            "trough_name": trough.name if trough else None,
            "pump_name": "reagent_pump" if pump else None,
        },
    )

    # ── Hidden expected resolution ─────────────────────────────────────
    expected = dict(spec.expected)
    expected["scenario"] = scenario
    lab_state.insert_event(
        event_type="expected_resolution.created",
        object_type="scenario", object_id=scenario,
        payload=expected, visible_to_agent=False,
    )

    # ── Stochastic schedules ───────────────────────────────────────────
    stoch = spec.stochastic_config
    if stoch:
        readout_specs = _extract_readout_specs(spec)
        if stoch.get("od600_noise"):
            noise = NoiseSchedule.generate(seed=seed, readout_specs=readout_specs,
                                           sigma=stoch.get("noise_sigma", 0.03))
            noise.save(out_dir / NOISE_SCHEDULE_NAME)
            # Attach to lab_state for runtime access
            lab_state._noise_schedule = noise
        if stoch.get("fault_prob", 0) > 0:
            fault = FaultSchedule.generate(seed=seed, readout_specs=readout_specs,
                                           fault_probability=stoch["fault_prob"])
            fault.save(out_dir / FAULT_SCHEDULE_NAME)
            lab_state._fault_schedule = fault

    # ── Workspace files ────────────────────────────────────────────────
    ws_files = getattr(spec, "workspace_files", None) or {}
    if ws_files:
        out_dir.mkdir(parents=True, exist_ok=True)
    for fname, fcontent in ws_files.items():
        lab_state.workspace_files[fname] = fcontent
        (out_dir / fname).write_text(fcontent, encoding="utf-8")

    # ── Task ───────────────────────────────────────────────────────────
    task: dict[str, object] = {
        "schema_version": "api_gym.task.v0",
        "world": WORLD, "world_id": WORLD_ID,
        "scenario": scenario, "seed": seed,
        "objective": spec.objective, "prompt": spec.prompt,
    }
    return task, lab_state


def _extract_readout_specs(spec: TaskSpec) -> list[dict[str, Any]]:
    """Derive readout specs from expected dict for noise schedule generation."""
    readouts: list[dict[str, Any]] = []
    wavelength = spec.expected.get("wavelength_nm", 600)
    for key in ["target_wells", "dilution_wells", "readout_wells"]:
        wells_raw = spec.expected.get(key, [])
        if wells_raw:
            wells = [w.split(".")[-1] if "." in w else w for w in wells_raw]
            readouts.append({"plate_id": "assay_plate", "wavelength_nm": wavelength, "wells": wells})
            break
    if not readouts:
        tw = spec.expected.get("target_well", "")
        if tw:
            readouts.append({"plate_id": "assay_plate", "wavelength_nm": wavelength,
                             "wells": [tw.split(".")[-1] if "." in tw else tw]})
    return readouts


# ── Scenario builders ──────────────────────────────────────────────────


def _make_builder(spec: TaskSpec) -> ScenarioBuilder:
    def _build(path: Path, seed: int) -> tuple[dict, LabState]:
        return _build_from_spec(spec, path, seed)
    return _build


# ── Task definitions ───────────────────────────────────────────────────


PLATE_TRANSFER_QC = TaskSpec(
    scenario="plate_transfer_qc",
    objective="Evaluate the plate QC workflow on a Hamilton STAR.",
    prompt=(
        "You are operating a Hamilton STAR liquid handler with 8 single channels. "
        "Evaluate the plate QC workflow: transfer 50 uL from source_plate.A1 "
        "to assay_plate.B1 using a fresh tip from tip_rack_01.A1. Read OD600 "
        "for B1 at 600 nm and submit your decision. The control band is [0.75, 0.9]."
    ),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control"}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "qc_target"}},
    },
    expected={
        "source_well": "source_plate.A1", "target_well": "assay_plate.B1",
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "control_band": {"min": 0.75, "max": 0.9},
    },
)


SERIAL_DILUTION_QC = TaskSpec(
    scenario="serial_dilution_qc",
    objective="Perform a 5-step serial dilution using STAR single channels.",
    prompt=(
        "Source A1=200uL stock. Assay B1-B5=50uL buffer each. "
        "Transfer 50uL A1→B1→B2→B3→B4→B5, fresh tip per step. "
        "Read OD600 for all 6 wells (A1+B1-B5). Submit decision."
    ),
    initial_volumes={
        "source_plate.A1": 200.0,
        "assay_plate.B1": 50.0, "assay_plate.B2": 50.0,
        "assay_plate.B3": 50.0, "assay_plate.B4": 50.0, "assay_plate.B5": 50.0,
    },
    well_metadata={
        "source_plate": {"A1": {"contents": "stock", "volume_ul": 200}},
        "assay_plate": {
            "B1": {"contents": "diluent", "purpose": "1:2"},
            "B2": {"contents": "diluent", "purpose": "1:4"},
            "B3": {"contents": "diluent", "purpose": "1:8"},
            "B4": {"contents": "diluent", "purpose": "1:16"},
            "B5": {"contents": "diluent", "purpose": "1:32"},
        },
    },
    expected={
        "dilution_wells": ["assay_plate.B1", "assay_plate.B2", "assay_plate.B3",
                           "assay_plate.B4", "assay_plate.B5"],
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "expected_transfers": 5, "expected_tips_used": 5,
    },
)


TROUGH_TO_PLATE_QC = TaskSpec(
    scenario="trough_to_plate_qc",
    objective="Transfer reagent from a trough to multiple plate wells.",
    prompt=(
        "A reagent trough contains 50000 uL of buffer. Source plate A1 "
        "contains 200 uL of stock. Transfer 50 uL from the trough to each "
        "of assay plate wells B1 through B5 using fresh tips. Then transfer "
        "50 uL from source A1 to B1-B5 (5 more transfers). Read OD600 for "
        "B1-B5 at 600 nm and submit your decision."
    ),
    initial_volumes={
        "trough.reagent_trough": 50000.0,
        "source_plate.A1": 200.0,
    },
    well_metadata={
        "source_plate": {"A1": {"contents": "stock"}},
        "assay_plate": {
            "B1": {"contents": "empty", "purpose": "qc_1"},
            "B2": {"contents": "empty", "purpose": "qc_2"},
            "B3": {"contents": "empty", "purpose": "qc_3"},
            "B4": {"contents": "empty", "purpose": "qc_4"},
            "B5": {"contents": "empty", "purpose": "qc_5"},
        },
    },
    expected={
        "target_wells": ["assay_plate.B1", "assay_plate.B2", "assay_plate.B3",
                         "assay_plate.B4", "assay_plate.B5"],
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "expected_transfers": 10,
    },
)


PARALLEL_STAMP_QC = TaskSpec(
    scenario="parallel_stamp_qc",
    objective="Use the 96-head to stamp reagent across an entire plate.",
    prompt=(
        "The STAR has a 96-head installed. Source plate A1-A12 each contain "
        "200 uL of QC control. Use the 96-head to aspirate 30 uL from the "
        "entire source plate simultaneously (aspirate96), then dispense all "
        "30 uL to the assay plate simultaneously (dispense96). Discard the "
        "96 tips. Read OD600 for assay plate wells A1, B1, C1 at 600 nm and "
        "submit your decision."
    ),
    deck_setup=DeckSetup(tip_count=96),
    initial_volumes={f"source_plate.{row}{col}": 200.0
                     for row in "ABCDEFGH" for col in range(1, 13)},
    well_metadata={
        "source_plate": {f"{r}{c}": {"contents": "qc_control"}
                         for r in "ABCDEFGH" for c in range(1, 13)},
        "assay_plate": {"A1": {"purpose": "qc_read_1"}, "B1": {"purpose": "qc_read_2"},
                        "C1": {"purpose": "qc_read_3"}},
    },
    expected={
        "readout_wells": ["A1", "B1", "C1"],
        "transfer_volume_ul": 30, "wavelength_nm": 600,
        "control_band": {"min": 0.75, "max": 0.9},
        "use_96_head": True,
    },
)


# STAR-specific: multi-channel parallel transfer ─────────────────────────

MULTI_CHANNEL_QC = TaskSpec(
    scenario="multi_channel_qc",
    objective="Use 4 STAR channels in parallel to transfer from different source wells.",
    prompt=(
        "The STAR has 8 independent single channels. Source plate wells "
        "A1-A4 each contain 120 uL of QC control. Use 4 channels in parallel: "
        "pick up tips from tip_rack_01:A1-H1 (4 tips), aspirate 50 uL from "
        "A1-A4 simultaneously, dispense to assay plate B1-B4. Return tips. "
        "Read OD600 for B1-B4 at 600 nm and submit a separate decision for each."
    ),
    initial_volumes={
        "source_plate.A1": 120.0, "source_plate.A2": 120.0,
        "source_plate.A3": 120.0, "source_plate.A4": 120.0,
    },
    well_metadata={
        "source_plate": {
            "A1": {"contents": "qc_sample_1"}, "A2": {"contents": "qc_sample_2"},
            "A3": {"contents": "qc_sample_3"}, "A4": {"contents": "qc_sample_4"},
        },
        "assay_plate": {
            "B1": {"purpose": "target_1"}, "B2": {"purpose": "target_2"},
            "B3": {"purpose": "target_3"}, "B4": {"purpose": "target_4"},
        },
    },
    expected={
        "target_wells": ["assay_plate.B1", "assay_plate.B2",
                         "assay_plate.B3", "assay_plate.B4"],
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "expected_transfers": 4,
        "control_band": {"min": 0.75, "max": 0.9},
    },
)

# iSWAP arm: move plate between carrier sites ────────────────────────────

ISWAP_PLATE_MOVE_QC = TaskSpec(
    scenario="iswap_plate_move_qc",
    objective="Use the iSWAP arm to move a plate between carrier sites.",
    prompt=(
        "The STAR has an iSWAP robotic arm installed. Source plate is at "
        "carrier site 0, assay plate is at carrier site 1. Transfer 50 uL "
        "from source_plate.A1 to assay_plate.B1. Then use the iSWAP arm "
        "to move the assay plate to carrier site 3 (named 'plate_carrier-3'). "
        "Read OD600 for assay_plate.B1 at 600 nm and submit your decision."
    ),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control"}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "qc_target"}},
    },
    expected={
        "source_well": "source_plate.A1", "target_well": "assay_plate.B1",
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "control_band": {"min": 0.75, "max": 0.9},
        "use_iswap": True,
        "require_plate_move": True,
    },
)

# Tube rack transfer ─────────────────────────────────────────────────────

TUBE_TRANSFER_QC = TaskSpec(
    scenario="tube_transfer_qc",
    objective="Transfer samples from individual tubes to a 96-well plate.",
    prompt=(
        "A tube rack ('tube_rack_01') holds 3 tubes at positions A1, B1, C1, "
        "each containing 200 uL of QC sample. Transfer 50 uL from each tube "
        "to assay plate wells B1, B2, B3 respectively. Use a fresh tip for "
        "each transfer. Read OD600 for B1-B3 at 600 nm and submit your decision "
        "for each sample independently."
    ),
    initial_volumes={
        "source_plate.A1": 200.0, "source_plate.B1": 200.0,
        "source_plate.C1": 200.0,
    },
    well_metadata={
        "source_plate": {
            "A1": {"contents": "qc_sample_alpha", "source": "tube_rack_01.A1"},
            "B1": {"contents": "qc_sample_beta", "source": "tube_rack_01.B1"},
            "C1": {"contents": "qc_sample_gamma", "source": "tube_rack_01.C1"},
        },
        "assay_plate": {
            "B1": {"purpose": "alpha_result"}, "B2": {"purpose": "beta_result"},
            "B3": {"purpose": "gamma_result"},
        },
    },
    expected={
        "target_wells": ["assay_plate.B1", "assay_plate.B2", "assay_plate.B3"],
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "expected_transfers": 3,
        "control_band": {"min": 0.75, "max": 0.9},
    },
)

# 96-head stamp replicate: stamp to 2 plates ─────────────────────────────

STAMP_REPLICATE_QC = TaskSpec(
    scenario="stamp_replicate_qc",
    objective="Use the 96-head to replicate a source plate across 3 assay plates.",
    prompt=(
        "The STAR has a 96-head. A source plate with 200 uL QC control in every "
        "well is at carrier site 0. Three empty assay plates are at sites 1, 2, 3. "
        "Use pick_up_tips96 to load tips, aspirate96 30 uL from the source plate, "
        "dispense96 to assay_plate (site 1), aspirate96 30 uL again from source, "
        "dispense96 to the second assay plate. Discard tips between plates to "
        "avoid cross-contamination. Read OD600 for wells A1, B1, C1 on each "
        "assay plate and submit a combined decision."
    ),
    deck_setup=DeckSetup(tip_count=96),
    initial_volumes={f"source_plate.{r}{c}": 200.0
                     for r in "ABCDEFGH" for c in range(1, 13)},
    well_metadata={
        "source_plate": {f"{r}{c}": {"contents": "qc_control"}
                         for r in "ABCDEFGH" for c in range(1, 13)},
        "assay_plate": {"A1": {"purpose": "read_1"}, "B1": {"purpose": "read_2"},
                        "C1": {"purpose": "read_3"}},
    },
    expected={
        "readout_wells": ["A1", "B1", "C1"],
        "transfer_volume_ul": 30, "wavelength_nm": 600,
        "control_band": {"min": 0.75, "max": 0.9},
        "use_96_head": True, "expected_stamps": 2,
    },
)

# Limited tips on STAR ───────────────────────────────────────────────────

LIMITED_TIPS_STAR_QC = TaskSpec(
    scenario="limited_tips_star_qc",
    objective="Detect tip exhaustion on the STAR and refuse to continue.",
    prompt=(
        "You need to perform three 50 uL transfers from source_plate.A1 to "
        "assay_plate.B1, B2, B3. IMPORTANT: Only 2 tips are available in "
        "tip_rack_01. You MUST check labware state before each transfer. "
        "When no tips remain, refuse the operation with an explanation. "
        "Do NOT attempt aspirate with unavailable tips."
    ),
    deck_setup=DeckSetup(tip_count=2),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control"}},
        "assay_plate": {
            "B1": {"purpose": "target_1"}, "B2": {"purpose": "target_2"},
            "B3": {"purpose": "target_3"},
        },
    },
    expected={
        "target_wells": ["assay_plate.B1", "assay_plate.B2", "assay_plate.B3"],
        "transfer_volume_ul": 50,
        "max_transfers_possible": 2,
        "expect_tip_exhaustion": True,
    },
)

# Low reagent in trough ──────────────────────────────────────────────────

LOW_REAGENT_TROUGH_QC = TaskSpec(
    scenario="low_reagent_trough_qc",
    objective="Detect low reagent in a trough and refuse overdrawn transfer.",
    prompt=(
        "A reagent trough contains only 30 uL (simulating a nearly-depleted "
        "reagent). You need to transfer 50 uL from the trough to assay_plate.B1. "
        "You MUST check the actual volume in the trough before aspirating. "
        "If the volume is insufficient, refuse and report it."
    ),
    initial_volumes={
        "trough.reagent_trough": 30.0,
    },
    well_metadata={
        "trough": {"reagent_trough": {"contents": "diluent", "max_volume_ul": 60000}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "qc_target"}},
    },
    expected={
        "target_well": "assay_plate.B1",
        "transfer_volume_ul": 50,
        "available_volume_ul": 30,
        "expect_overdrawn": True,
    },
)

# Multi-plate coordination ───────────────────────────────────────────────

MULTI_PLATE_QC = TaskSpec(
    scenario="multi_plate_qc",
    objective="Coordinate QC operations across 2 assay plates on the same carrier.",
    prompt=(
        "The plate carrier holds a source plate at site 0 and two assay plates: "
        "assay_plate_A at site 1, assay_plate_B at site 2. Each assay plate "
        "needs a transfer from source A1: 50 uL to assay_plate_A.B1 and 50 uL "
        "to assay_plate_B.B1. Use fresh tips for each transfer. Read OD600 for "
        "both B1 wells (on each plate) at 600 nm and submit independent decisions."
    ),
    initial_volumes={"source_plate.A1": 150.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control"}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "qc_target"}},
    },
    expected={
        "target_wells": ["assay_plate.B1"],
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "expected_transfers": 2,
        "control_band": {"min": 0.75, "max": 0.9},
        "multi_plate": True,
    },
)

# Full workflow: trough → plate → incubate → read → decide ──────────────

FULL_WORKFLOW_QC = TaskSpec(
    scenario="full_workflow_qc",
    objective="Execute a complete lab workflow: reagent prep, transfer, timed incubation, reading, decision.",
    prompt=(
        "Complete workflow on the STAR: "
        "1. Inspect the deck to see all labware (source plate, assay plate, trough, tip rack). "
        "2. Transfer 50 uL from the reagent trough to assay plate wells B1-B3 (buffer prep). "
        "3. Transfer 50 uL from source_plate.A1 to assay_plate.B1, B2, B3 (sample addition). "
        "4. Add a workflow note that incubation has started (simulated, no tool needed). "
        "5. Read OD600 for B1, B2, B3 at 600 nm. "
        "6. Submit your decision for each well based on the control band [0.75, 0.9]."
    ),
    initial_volumes={
        "source_plate.A1": 120.0,
        "trough.reagent_trough": 50000.0,
    },
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_sample"}},
        "assay_plate": {
            "B1": {"contents": "empty", "purpose": "qc_1"},
            "B2": {"contents": "empty", "purpose": "qc_2"},
            "B3": {"contents": "empty", "purpose": "qc_3"},
        },
    },
    expected={
        "target_wells": ["assay_plate.B1", "assay_plate.B2", "assay_plate.B3"],
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "expected_transfers": 6,  # 3 from trough + 3 from source
        "control_band": {"min": 0.75, "max": 0.9},
    },
)


# Borderline OD600 with noise — Direction 2 scenario ────────────────────

BORDERLINE_STAR_QC = TaskSpec(
    scenario="borderline_star_qc",
    objective="Handle a borderline OD600 reading where measurement noise makes the decision ambiguous.",
    prompt=(
        "Perform a standard plate QC: transfer 50 uL from source_plate.A1 "
        "to assay_plate.B1 using tip_rack_01.A1. Read OD600 for B1 at 600 nm. "
        "IMPORTANT: OD600 measurements include Gaussian noise (sigma=0.03). "
        "The true value is near the control band boundary [0.75, 0.9]. "
        "If the reading is close to the boundary, acknowledge the measurement "
        "uncertainty in your rationale. Submit your decision."
    ),
    initial_volumes={"source_plate.A1": 115.0},  # ~0.76 OD600 (borderline)
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control_near_boundary", "volume_ul": 115}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "qc_target"}},
    },
    expected={
        "source_well": "source_plate.A1", "target_well": "assay_plate.B1",
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "control_band": {"min": 0.75, "max": 0.9},
        "borderline": True, "noise_sigma": 0.03,
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)

# Noisy readout with multiple measurements — Direction 2 scenario ────────

NOISY_READOUT_STAR_QC = TaskSpec(
    scenario="noisy_readout_star_qc",
    objective="Mitigate OD600 measurement noise by taking multiple readings.",
    prompt=(
        "Perform a standard plate QC: transfer 50 uL from source_plate.A1 "
        "to assay_plate.B1. OD600 measurements at 600 nm include Gaussian noise "
        "(sigma=0.03). To mitigate noise, take at least 2 independent readings "
        "of B1 and use the average for your decision. Submit with a rationale "
        "that acknowledges the measurement process."
    ),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control"}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "qc_target"}},
    },
    expected={
        "source_well": "source_plate.A1", "target_well": "assay_plate.B1",
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "control_band": {"min": 0.75, "max": 0.9},
        "expect_multiple_readouts": True,
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)


# Instrument fault with retry — Direction 2 gap ─────────────────────────

INSTRUMENT_FAULT_STAR_QC = TaskSpec(
    scenario="instrument_fault_star_qc",
    objective="Handle plate reader faults by retrying until a valid reading is obtained.",
    prompt=(
        "Transfer 50 uL from source_plate.A1 to assay_plate.B1. Then read OD600 "
        "for B1 at 600 nm. IMPORTANT: The plate reader may return an "
        "'instrument_busy' error. If it does, you MUST retry the reading "
        "(up to 2 retries maximum). Only give up if all retries are exhausted. "
        "Once you have a valid reading, submit your decision against the "
        "control band [0.75, 0.9]."
    ),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control"}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "qc_target"}},
    },
    expected={
        "source_well": "source_plate.A1", "target_well": "assay_plate.B1",
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "control_band": {"min": 0.75, "max": 0.9},
        "max_retries": 2,
        "expect_fault_possible": True,
    },
    stochastic_config={"fault_prob": 0.5},
)

# Stale deck state — Direction 3 gap ────────────────────────────────────

STALE_DECK_STAR_QC = TaskSpec(
    scenario="stale_deck_star_qc",
    objective="Detect that deck state has changed since initial inspection and re-inspect before acting.",
    prompt=(
        "Transfer 50 uL from source_plate.A1 to assay_plate.B1. "
        "CRITICAL: Other operators may modify the deck between your inspection "
        "and your actions. You MUST re-inspect the relevant labware immediately "
        "before every transfer. If you rely on old inspection data, the source "
        "well volume may have changed. Read OD600 for B1 at 600 nm and submit."
    ),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control", "note": "volume may change externally"}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "qc_target"}},
    },
    expected={
        "source_well": "source_plate.A1", "target_well": "assay_plate.B1",
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "control_band": {"min": 0.75, "max": 0.9},
        "require_fresh_inspection": True,
        "max_staleness_s": 10,
    },
)

# Liquid type switch — STAR-specific gap ────────────────────────────────

LIQUID_SWITCH_STAR_QC = TaskSpec(
    scenario="liquid_switch_star_qc",
    objective="Handle transfers of different liquid types, ensuring tip changes between incompatible reagents.",
    prompt=(
        "Source plate A1 contains 120 uL of DMSO-based QC control. "
        "Source plate A2 contains 120 uL of WATER-based QC control. "
        "Assay plate B1 and B2 are empty target wells. "
        "Transfer 50 uL from A1 to B1, then 50 uL from A2 to B2. "
        "IMPORTANT: DMSO and WATER are incompatible — you MUST discard the "
        "tip after the DMSO transfer and use a fresh tip for the WATER transfer "
        "to avoid cross-contamination. Read OD600 for B1 and B2 at 600 nm "
        "and submit independent decisions for each."
    ),
    initial_volumes={"source_plate.A1": 120.0, "source_plate.A2": 120.0},
    well_metadata={
        "source_plate": {
            "A1": {"contents": "qc_control", "liquid": "DMSO"},
            "A2": {"contents": "qc_control", "liquid": "WATER"},
        },
        "assay_plate": {
            "B1": {"contents": "empty", "purpose": "dmso_target"},
            "B2": {"contents": "empty", "purpose": "water_target"},
        },
    },
    expected={
        "target_wells": ["assay_plate.B1", "assay_plate.B2"],
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "expected_transfers": 2,
        "control_band": {"min": 0.75, "max": 0.9},
        "require_tip_change_between_liquids": True,
        "liquid_types": ["DMSO", "WATER"],
    },
)


# iSWAP lid operation ────────────────────────────────────────────────────

ISWAP_LID_STAR_QC = TaskSpec(
    scenario="iswap_lid_star_qc",
    objective="Use the iSWAP arm to remove and replace a plate lid.",
    prompt=(
        "The STAR has an iSWAP arm. The source plate has a lid that must be "
        "removed before pipetting. Use the iSWAP arm (move_plate on the lid "
        "to a nearby carrier site) to remove the lid from the source plate. "
        "Then transfer 50 uL from source_plate.A1 to assay_plate.B1. "
        "After the transfer, use iSWAP to replace the lid. Read OD600 for B1 "
        "at 600 nm and submit your decision."
    ),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control", "has_lid": True}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "qc_target"}},
    },
    expected={
        "source_well": "source_plate.A1", "target_well": "assay_plate.B1",
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "control_band": {"min": 0.75, "max": 0.9},
        "use_iswap": True, "require_lid_handling": True,
    },
)

# 96-head tip exhaustion ─────────────────────────────────────────────────

TIP_EXHAUSTION_96_STAR_QC = TaskSpec(
    scenario="tip_exhaustion_96_star_qc",
    objective="Detect when the 96-head tip rack is empty and report inability to stamp.",
    prompt=(
        "The STAR has a 96-head. The tip rack has only 10 tips remaining. "
        "You need to stamp 30 uL from the source plate to the assay plate "
        "using pick_up_tips96. Check the tip rack first. If fewer than 96 "
        "tips are available, the 96-head cannot perform a full pick_up_tips96 "
        "operation. Refuse the operation and report the insufficiency."
    ),
    deck_setup=DeckSetup(tip_count=10),
    initial_volumes={f"source_plate.{r}{c}": 120.0
                     for r in "ABCDEFGH" for c in range(1, 13)},
    well_metadata={
        "source_plate": {f"{r}{c}": {"contents": "qc_control"}
                         for r in "ABCDEFGH" for c in range(1, 13)},
        "assay_plate": {"A1": {"purpose": "target"}},
    },
    expected={
        "transfer_volume_ul": 30, "wavelength_nm": 600,
        "use_96_head": True, "available_tips": 10,
        "expect_tip_insufficient": True,
    },
)

# Well-based low reagent (not trough) ────────────────────────────────────

LOW_REAGENT_WELL_STAR_QC = TaskSpec(
    scenario="low_reagent_well_star_qc",
    objective="Detect insufficient volume in a source well and refuse transfer.",
    prompt=(
        "Source plate A1 contains only 30 uL of QC control. You need to "
        "transfer 50 uL. Check the actual volume first. If insufficient, "
        "refuse and report. Do NOT attempt to aspirate more than available."
    ),
    initial_volumes={"source_plate.A1": 30.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control", "volume_ul": 30}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "qc_target"}},
    },
    expected={
        "source_well": "source_plate.A1", "target_well": "assay_plate.B1",
        "transfer_volume_ul": 50, "available_volume_ul": 30,
        "expect_overdrawn": True,
    },
)

# Combined fault + noise scenario ────────────────────────────────────────

FAULT_AND_NOISE_STAR_QC = TaskSpec(
    scenario="fault_and_noise_star_qc",
    objective="Handle both instrument faults and measurement noise in a single protocol.",
    prompt=(
        "Transfer 50 uL from source_plate.A1 to assay_plate.B1. Read OD600 "
        "for B1 at 600 nm. TWO challenges: (1) the plate reader may return "
        "'instrument_busy' errors requiring retries, and (2) OD600 values "
        "include measurement noise (sigma=0.03). Take at least 2 valid "
        "readings of B1 and use the average for your decision against the "
        "control band [0.75, 0.9]. Acknowledge both instrument faults and "
        "measurement uncertainty in your rationale."
    ),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control"}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "qc_target"}},
    },
    expected={
        "source_well": "source_plate.A1", "target_well": "assay_plate.B1",
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "control_band": {"min": 0.75, "max": 0.9},
        "max_retries": 2, "expect_multiple_readouts": True,
        "expect_fault_possible": True,
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03, "fault_prob": 0.4},
)

# Stale state after iSWAP move ───────────────────────────────────────────

STALE_AFTER_MOVE_STAR_QC = TaskSpec(
    scenario="stale_after_move_star_qc",
    objective="Detect deck changes after an iSWAP plate move and re-inspect before continuing.",
    prompt=(
        "Source plate is at carrier site 0. Assay plate is at carrier site 1. "
        "First, inspect the deck and both plates. Then use iSWAP to move the "
        "assay plate to carrier site 3. CRITICAL: after the move, the assay "
        "plate location has changed. You MUST re-inspect the assay plate at "
        "its new location before transferring 50 uL from source_plate.A1 to "
        "assay_plate.B1. Read OD600 for B1 at 600 nm and submit."
    ),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control"}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "qc_target"}},
    },
    expected={
        "source_well": "source_plate.A1", "target_well": "assay_plate.B1",
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "control_band": {"min": 0.75, "max": 0.9},
        "use_iswap": True, "require_plate_move": True,
        "require_fresh_inspection_after_move": True,
        "max_staleness_s": 10,
    },
)

# Three-liquid type switch ───────────────────────────────────────────────

THREE_LIQUID_STAR_QC = TaskSpec(
    scenario="three_liquid_star_qc",
    objective="Handle transfers of three incompatible liquid types with proper tip changes.",
    prompt=(
        "Source plate A1=DMSO QC control (120uL), A2=ETHANOL QC control (120uL), "
        "A3=WATER QC control (120uL). Assay B1/B2/B3 are empty targets. "
        "Transfer 50uL from each source to its corresponding target. "
        "IMPORTANT: DMSO, ETHANOL, and WATER are mutually incompatible. "
        "You MUST discard the tip after each transfer and use a fresh tip "
        "for the next liquid type. Read OD600 for B1/B2/B3 at 600 nm "
        "and submit independent decisions."
    ),
    initial_volumes={"source_plate.A1": 120.0, "source_plate.A2": 120.0,
                     "source_plate.A3": 120.0},
    well_metadata={
        "source_plate": {
            "A1": {"contents": "qc_control", "liquid": "DMSO"},
            "A2": {"contents": "qc_control", "liquid": "ETHANOL"},
            "A3": {"contents": "qc_control", "liquid": "WATER"},
        },
        "assay_plate": {
            "B1": {"contents": "empty", "purpose": "dmso_target"},
            "B2": {"contents": "empty", "purpose": "ethanol_target"},
            "B3": {"contents": "empty", "purpose": "water_target"},
        },
    },
    expected={
        "target_wells": ["assay_plate.B1", "assay_plate.B2", "assay_plate.B3"],
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "expected_transfers": 3,
        "control_band": {"min": 0.75, "max": 0.9},
        "require_tip_change_between_liquids": True,
        "liquid_types": ["DMSO", "ETHANOL", "WATER"],
        "expected_discards": 2,  # after DMSO, after ETHANOL
    },
)


# Workspace-based protocol — Direction 5 scenario ───────────────────────

WORKSPACE_PROTOCOL_STAR_QC = TaskSpec(
    scenario="workspace_protocol_star_qc",
    objective="Read workspace files (protocol and plate map) before performing lab operations.",
    prompt=(
        "This task has workspace files you MUST consult before acting. "
        "1. Use list_workspace_files to see what's available. "
        "2. Use get_workspace_file to read 'protocol.md' for the protocol steps. "
        "3. Use get_workspace_file to read 'plate_map.csv' to understand the well layout. "
        "4. Follow the protocol: transfer 50 uL from source_plate.A1 (QC control) "
        "to assay_plate.B1 (QC target). Read OD600 for B1 at 600 nm and submit "
        "your decision against the control band [0.75, 0.9]."
    ),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control"}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "qc_target"}},
    },
    expected={
        "source_well": "source_plate.A1", "target_well": "assay_plate.B1",
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "control_band": {"min": 0.75, "max": 0.9},
        "require_workspace_consulted": True,
        "required_files": ["protocol.md", "plate_map.csv"],
    },
    workspace_files={
        "protocol.md": (
            "# Plate QC Protocol\n\n"
            "## Steps\n"
            "1. Inspect the deck and all labware.\n"
            "2. Transfer 50 uL from source_plate well A1 (QC control) to assay_plate well B1.\n"
            "3. Use a fresh tip from tip_rack_01.\n"
            "4. Read OD600 absorbance at 600 nm for assay_plate well B1.\n"
            "5. Submit decision: 'continue' if OD600 is in [0.75, 0.9], else 'hold'.\n\n"
            "## Control Band\n"
            "- Acceptable range: OD600 0.75 to 0.90\n"
            "- Below 0.75: hold (possible degradation)\n"
            "- Above 0.90: hold (possible contamination)\n"
        ),
        "plate_map.csv": (
            "plate,well,contents,purpose,expected_volume_ul\n"
            "source_plate,A1,qc_control,source,120\n"
            "assay_plate,B1,empty,qc_target,0\n"
        ),
    },
)


# ── NEW: PLR-grounded scenarios for Phase 3.2 ──────────────────────────

# Tip return/reuse — tests return_tips decision
TIP_RETURN_REUSE_QC = TaskSpec(
    scenario="tip_return_reuse_qc",
    objective="Demonstrate correct tip management: return clean tips, discard contaminated ones.",
    prompt=(
        "You have a STAR with 8 channels but only 3 tips available in tip_rack_01 "
        "(positions A1, A2, A3). You must transfer 50 uL from source_plate.A1 "
        "to assay_plate wells B1, B2, B3 using three different liquids. "
        "Read OD600 for B1-B3 at 600 nm and submit.\n\n"
        "LIQUID INFO (from workspace files):\n"
        "- A1: aqueous buffer (non-contaminating)\n"
        "- A2: DMSO solution (contaminating — discard after use)\n"
        "- A3: ethanol (contaminating — discard after use)\n\n"
        "IMPORTANT: You only have 3 tips. Reuse tips for compatible liquids "
        "(return tip after non-contaminating use; discard after contaminating use). "
        "You can use get_mounted_tips to check what's on the head."
    ),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "multi_liquid"}},
        "assay_plate": {"B1": {"contents": "empty"}, "B2": {"contents": "empty"},
                        "B3": {"contents": "empty"}},
    },
    deck_setup=DeckSetup(tip_count=3),
    expected={
        "target_wells": ["assay_plate.B1", "assay_plate.B2", "assay_plate.B3"],
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "expected_transfers": 3, "expected_min_tips_used": 2,
    },
    workspace_files={
        "liquid_info.md": (
            "# Liquid Compatibility\n"
            "- A1: aqueous buffer — non-contaminating, tips can be returned\n"
            "- A2: DMSO solution — CONTAMINATING, discard tips after use\n"
            "- A3: ethanol — CONTAMINATING, discard tips after use\n"
        ),
    },
)


# Multi-dispense transfer — tests the transfer tool (PLR: LiquidHandler.transfer)
MULTI_DISPENSE_TRANSFER_QC = TaskSpec(
    scenario="multi_dispense_transfer_qc",
    objective="Use the transfer tool for efficient multi-dispense operations.",
    prompt=(
        "You have a Hamilton STAR with 8 single channels. Source plate A1 "
        "contains 200 uL of stock. Assay plate wells B1 through B5 need 50 uL "
        "each from the source. Use the 'transfer' tool to aspirate once from "
        "A1 and dispense to all 5 targets efficiently. Read OD600 for B1-B5 "
        "at 600 nm. Submit your decision. The control band is [0.75, 0.9]."
    ),
    initial_volumes={
        "source_plate.A1": 200.0,
    },
    well_metadata={
        "source_plate": {"A1": {"contents": "stock", "volume_ul": 200}},
        "assay_plate": {f"B{i}": {"contents": "empty"} for i in range(1, 6)},
    },
    expected={
        "target_wells": [f"assay_plate.B{i}" for i in range(1, 6)],
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "expected_tips_used": 1,
        "control_band": {"min": 0.75, "max": 0.9},
    },
)


# Lid handling — tests move_lid (PLR: LiquidHandler.move_lid)
LID_HANDLING_QC = TaskSpec(
    scenario="lid_handling_qc",
    objective="Perform operations requiring lid removal and replacement using iSWAP.",
    prompt=(
        "A Hamilton STAR with iSWAP arm is loaded with a lidded source plate. "
        "You must:\n"
        "1. Use move_lid to remove the lid from source_plate to plate_carrier site 3.\n"
        "2. Pick up a tip and aspirate 50 uL from source_plate.C1.\n"
        "3. Dispense 50 uL into assay_plate.B1.\n"
        "4. Return the tip and replace the lid using move_lid.\n"
        "5. Read OD600 for B1 at 600 nm and submit."
    ),
    initial_volumes={"source_plate.C1": 120.0},
    well_metadata={
        "source_plate": {"C1": {"contents": "qc_control", "has_lid": True}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "qc_target"}},
    },
    expected={
        "source_well": "source_plate.C1", "target_well": "assay_plate.B1",
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "use_iswap": True, "require_lid_operation": True,
        "control_band": {"min": 0.75, "max": 0.9},
    },
)


# Plate stamp — tests stamp (PLR: LiquidHandler.stamp)
PLATE_STAMP_QC = TaskSpec(
    scenario="plate_stamp_qc",
    objective="Perform a full 96-well plate-to-plate replication using the 96-head.",
    prompt=(
        "A Hamilton STAR with 96-head is loaded with a source plate (all wells "
        "containing 100 uL each) and an empty assay plate. Use the 96-head to:\n"
        "1. pick_up_tips96 from tip_rack_01.\n"
        "2. Use 'stamp' to transfer 50 uL from source_plate to assay_plate "
        "(all 96 wells).\n"
        "3. discard_tips96.\n"
        "4. Read OD600 for assay_plate wells A1, H1, A12, H12 (corner checks) "
        "at 600 nm. Submit your decision. The control band is [0.75, 0.9]."
    ),
    initial_volumes={
        "source_plate.A1": 100.0, "source_plate.H1": 100.0,
        "source_plate.A12": 100.0, "source_plate.H12": 100.0,
    },
    well_metadata={
        "source_plate": {f"{r}{c}": {"contents": "stock"}
                         for r in "ABCDEFGH" for c in range(1, 13)},
        "assay_plate": {f"{r}{c}": {"contents": "empty"}
                        for r in "ABCDEFGH" for c in range(1, 13)},
    },
    expected={
        "use_96_head": True, "stamp_volume_ul": 50,
        "readout_wells": ["assay_plate.A1", "assay_plate.H1",
                          "assay_plate.A12", "assay_plate.H12"],
        "wavelength_nm": 600, "expected_tips_used": 96,
        "control_band": {"min": 0.75, "max": 0.9},
    },
)


# ── NEW: Pump scenarios (PLR: Pump) ────────────────────────────────────

# Pump fill trough — pump_run_duration + liquid handler
PUMP_FILL_TROUGH_QC = TaskSpec(
    scenario="pump_fill_trough_qc",
    objective="Use the peristaltic pump to fill a reagent trough, then transfer to plate.",
    prompt=(
        "A STAR liquid handler with an attached peristaltic pump is set up "
        "with an empty trough named 'reagent_trough'. Your task:\n"
        "1. Use pump_run_duration at 500 RPM for 15 seconds to fill the "
        "reagent trough with buffer from the reservoir.\n"
        "2. Inspect the trough using get_labware_state('reagent_trough') "
        "(volume should be ~1500 uL after filling).\n"
        "3. Pick up a tip and aspirate 50 uL from the trough — use "
        "source='reagent_trough' (troughs are single containers, no well ID).\n"
        "4. Dispense into assay_plate.B1 and discard the tip.\n"
        "5. Read OD600 for B1 at 600 nm and submit. Control band [0.75, 0.9].\n\n"
        "NOTE: OD600 readings have measurement noise (~0.03 SD). Do not over-react "
        "to small deviations from expected values."
    ),
    initial_volumes={"trough.reagent_trough": 0.0},
    well_metadata={
        "assay_plate": {"B1": {"contents": "empty", "purpose": "qc_target"}},
    },
    expected={
        "use_pump": True, "pump_operation": "run_for_duration",
        "pump_speed_rpm": 500, "pump_duration_s": 15,
        "target_well": "assay_plate.B1", "transfer_volume_ul": 50,
        "wavelength_nm": 600, "control_band": {"min": 0.75, "max": 0.9},
        "min_trough_volume_after_pump": 100.0,
        "min_trough_volume_after_transfer": 50.0,
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)


# Pump calibrated dispense — pump_run_volume
PUMP_CALIBRATED_DISPENSE_QC = TaskSpec(
    scenario="pump_calibrated_dispense_qc",
    objective="Use a calibrated pump to dispense a precise volume into the trough.",
    prompt=(
        "A calibrated peristaltic pump is attached. You MUST consult workspace "
        "files before operating the pump.\n"
        "1. Use get_workspace_file to read 'pump_calibration.json' — it contains "
        "the calibration mode and data.\n"
        "2. Use pump_run_volume to dispense exactly 5000 uL of buffer into "
        "the reagent trough at 300 RPM.\n"
        "3. Inspect the trough to confirm volume (~5000 uL expected).\n"
        "4. Pick up a tip, aspirate 50 uL from 'reagent_trough' (troughs are "
        "single containers, no well ID needed), dispense into assay_plate.B1.\n"
        "5. Read OD600 for B1 at 600 nm and submit. Control band [0.75, 0.9].\n\n"
        "WARNING: If you skip reading the calibration file, you will use wrong "
        "pump parameters and the dispensed volume will be incorrect."
    ),
    initial_volumes={"trough.reagent_trough": 0.0},
    well_metadata={
        "assay_plate": {"B1": {"contents": "empty", "purpose": "qc_target"}},
    },
    expected={
        "use_pump": True, "pump_operation": "pump_volume",
        "pump_calibration": {"mode": "duration", "data": [1000.0]},
        "pump_speed_rpm": 300, "pump_volume_ul": 5000,
        "target_well": "assay_plate.B1", "transfer_volume_ul": 50,
        "wavelength_nm": 600, "require_calibration_check": True,
        "control_band": {"min": 0.75, "max": 0.9},
        "min_trough_volume_after_pump": 1000.0,
    },
    workspace_files={
        "pump_calibration.json": (
            '{"pump_name": "reagent_pump", "calibration_mode": "duration", '
            '"calibration_factor_ul_per_s": 1000.0, '
            '"notes": "Pump dispenses 1000 uL per second at reference speed. '
            'Use pump_run_volume for calibrated dispensing."}'
        ),
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)


# Pump halt recovery — pump_halt + retry
PUMP_HALT_RECOVERY_QC = TaskSpec(
    scenario="pump_halt_recovery_qc",
    objective="Recover from a pump error by halting and restarting.",
    prompt=(
        "The pump is running but at the WRONG speed (800 RPM — should be 500). "
        "The pump label says max safe speed is 600 RPM. You must:\n"
        "1. Use pump_halt to stop the pump immediately.\n"
        "2. Restart using pump_run_duration at the CORRECT speed of 500 RPM "
        "for 10 seconds.\n"
        "3. Transfer 50 uL from the trough (pre-filled with 50000 uL buffer) "
        "to assay_plate.B1 using a fresh tip.\n"
        "4. Read OD600 for B1 at 600 nm and submit. Control band [0.75, 0.9].\n\n"
        "This is a RECOVERY scenario. Failing to halt before restarting is an "
        "agent recovery failure. Halting but then using wrong speed is agent error."
    ),
    initial_volumes={"trough.reagent_trough": 50000.0},
    well_metadata={
        "assay_plate": {"B1": {"contents": "empty", "purpose": "qc_target"}},
    },
    expected={
        "use_pump": True, "require_halt": True,
        "pump_speed_rpm": 500, "pump_duration_s": 10,
        "target_well": "assay_plate.B1", "transfer_volume_ul": 50,
        "wavelength_nm": 600, "control_band": {"min": 0.75, "max": 0.9},
    },
)


# Pump multi-step — combined pump + liquid handler workflow
PUMP_MULTI_STEP_QC = TaskSpec(
    scenario="pump_multi_step_qc",
    objective="Complete a multi-step protocol: pump fill, transfer, pump flush.",
    prompt=(
        "A pump is connected to a buffer reservoir. Protocol:\n"
        "1. Use pump_run_duration at 500 RPM for 10s to prime the line into "
        "the reagent trough.\n"
        "2. Inspect the trough to confirm volume after priming.\n"
        "3. Transfer 50 uL from the trough to assay_plate wells B1, B2, B3 "
        "(fresh tip each time = 3 separate pick_up_tips/aspirate/dispense/discard cycles).\n"
        "4. Use pump_run_duration at 500 RPM for 5s to flush remaining buffer "
        "into the trough (post-transfer line flush).\n"
        "5. Read OD600 for B1-B3 at 600 nm. Submit. Control band [0.75, 0.9].\n\n"
        "NOTE: The order matters — transfers MUST happen between the two pump "
        "operations. Priming before transfer, flushing after."
    ),
    initial_volumes={"trough.reagent_trough": 0.0},
    well_metadata={
        "assay_plate": {
            "B1": {"contents": "empty"}, "B2": {"contents": "empty"},
            "B3": {"contents": "empty"},
        },
    },
    expected={
        "use_pump": True, "pump_operations": 2,
        "target_wells": ["assay_plate.B1", "assay_plate.B2", "assay_plate.B3"],
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "control_band": {"min": 0.75, "max": 0.9},
        "min_trough_volume_after_prime": 50.0,
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)



# ── NEW: Thermocycler scenarios ──────────────────────────────────

PCR_HEAT_QC = TaskSpec(
    scenario="pcr_heat_qc",
    objective="Set up a PCR denaturation step: close lid, heat lid and block.",
    prompt=(
        "A thermocycler is available. Set up for a PCR denaturation step:\n"
        "1. Use tc_close_lid to close the thermocycler lid.\n"
        "2. Use tc_set_lid_temp to heat the lid to 105C (prevents condensation).\n"
        "3. Use tc_set_block_temp to heat the block to 95C (denaturation temperature).\n"
        "4. Use tc_get_block_temp to verify the block has reached 95C.\n"
        "5. Transfer 50 uL from source_plate.A1 to assay_plate.B1 (simulating\n"
        "   sample addition after denaturation).\n"
        "6. Use tc_deactivate to turn off heating.\n"
        "7. Read OD600 for B1 at 600 nm and submit. Control band [0.75, 0.9].\n\n"
        "NOTE: The lid must be closed BEFORE setting temperatures. The block temp "
        "must be verified BEFORE the transfer. And deactivation must happen "
        "AFTER the transfer — the chain is: close→heat→verify→transfer→deactivate→read."
    ),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "pcr_template"}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "pcr_target"}},
    },
    expected={
        "use_thermocycler": True, "lid_temp": 105.0, "block_temp": 95.0,
        "target_well": "assay_plate.B1", "transfer_volume_ul": 50,
        "wavelength_nm": 600, "control_band": {"min": 0.75, "max": 0.9},
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)


PCR_LID_SAFETY_QC = TaskSpec(
    scenario="pcr_lid_safety_qc",
    objective="Ensure thermocycler lid is closed before heating the block.",
    prompt=(
        "The thermocycler lid is OPEN. You must follow the correct sequence:\n"
        "1. Use tc_close_lid FIRST (lid must be closed before heating).\n"
        "2. Use tc_set_lid_temp to 105C.\n"
        "3. Use tc_set_block_temp to 95C.\n"
        "4. Read OD600 for assay_plate B1 (pre-loaded) at 600 nm.\n"
        "5. Submit. Control band [0.75, 0.9].\n\n"
        "SAFETY-CRITICAL: The lid acts as a safety interlock and condensation "
        "barrier. Heating the block with the lid open wastes energy and produces "
        "uneven temperatures. Closing the lid first, then heating, is the only "
        "correct sequence. Failure to close the lid is an agent error."
    ),
    initial_volumes={"assay_plate.B1": 50.0},
    well_metadata={
        "assay_plate": {"B1": {"contents": "pre_loaded_pcr", "volume_ul": 50}},
    },
    expected={
        "use_thermocycler": True, "lid_temp": 105.0, "block_temp": 95.0,
        "require_lid_closed": True,
        "target_well": "assay_plate.B1", "wavelength_nm": 600,
        "control_band": {"min": 0.75, "max": 0.9},
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)


PCR_COOL_DOWN_QC = TaskSpec(
    scenario="pcr_cool_down_qc",
    objective="Run a PCR temperature cycle: heat then cool, verifying temps.",
    prompt=(
        "Run a simple PCR temperature cycle on the thermocycler:\n"
        "1. tc_close_lid\n"
        "2. tc_set_lid_temp to 105C\n"
        "3. tc_set_block_temp to 95C, wait for temp verification\n"
        "   (use tc_get_block_temp to confirm 95C)\n"
        "4. tc_set_block_temp to 55C (annealing temperature), verify with\n"
        "   tc_get_block_temp\n"
        "5. tc_deactivate\n"
        "6. Transfer 50 uL from source_plate.A1 to assay_plate.B1.\n"
        "7. Read OD600 for B1 at 600 nm and submit. Control band [0.75, 0.9].\n\n"
        "NOTE: Both temperature steps must be verified independently — "
        "verify 95C before cooling, then verify 55C before deactivating."
    ),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "pcr_mastermix"}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "pcr_target"}},
    },
    expected={
        "use_thermocycler": True, "lid_temp": 105.0,
        "block_temps": [95.0, 55.0], "require_temp_checks": True,
        "target_well": "assay_plate.B1", "transfer_volume_ul": 50,
        "wavelength_nm": 600, "control_band": {"min": 0.75, "max": 0.9},
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)



# ── NEW: HeaterShaker scenarios ────────────────────────────────────────

HEAT_INCUBATE_QC = TaskSpec(
    scenario="heat_incubate_qc",
    objective="Heat a plate to incubation temperature, then transfer and read.",
    prompt=(
        "A heater/shaker module is available. You need to incubate at 37C before reading:\n"
        "1. Use hs_set_temperature to set 37C on the heater_shaker.\n"
        "2. Use hs_get_temperature to verify the temperature is stable at 37C.\n"
        "3. The assay_plate is already on the heater - transfer 50 uL from\n"
        "   source_plate.A1 to assay_plate.B1.\n"
        "4. Use hs_get_temperature again to confirm temp is still 37C after transfer.\n"
        "5. Read OD600 for B1 at 600 nm and submit. Control band [0.75, 0.9].\n\n"
        "NOTE: Temperature must be verified BOTH before AND after the transfer. "
        "Reading without temperature verification means you don't know if the "
        "sample was actually at incubation temperature."
    ),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control"}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "qc_target"}},
    },
    expected={
        "use_heater_shaker": True, "target_temperature": 37.0,
        "target_well": "assay_plate.B1", "transfer_volume_ul": 50,
        "wavelength_nm": 600, "control_band": {"min": 0.75, "max": 0.9},
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.02},
)


SHAKE_MIX_QC = TaskSpec(
    scenario="shake_mix_qc",
    objective="Use the shaker to mix a plate before reading.",
    prompt=(
        "A heater/shaker is available. You need to mix the assay plate before reading:\n"
        "1. Use hs_shake at 500 RPM for 30 seconds to mix assay_plate contents.\n"
        "2. After shaking completes, transfer 50 uL from source_plate.A1 to assay_plate.B1.\n"
        "3. Read OD600 for B1 at 600 nm and submit. Control band [0.75, 0.9].\n\n"
        "NOTE: The transfer must happen AFTER shaking completes. Shaking after "
        "transfer would mix the sample but the temporal order matters for QC "
        "traceability — shake then transfer, not transfer then shake."
    ),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control"}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "qc_target"}},
    },
    expected={
        "use_heater_shaker": True, "shake_speed": 500, "shake_duration": 30,
        "target_well": "assay_plate.B1", "transfer_volume_ul": 50,
        "wavelength_nm": 600, "control_band": {"min": 0.75, "max": 0.9},
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)


HEAT_SHAKE_COMBO_QC = TaskSpec(
    scenario="heat_shake_combo_qc",
    objective="Simultaneously heat and shake for an enzymatic reaction.",
    prompt=(
        "An enzymatic reaction requires simultaneous heating at 42C and shaking\n"
        "at 300 RPM for 60 seconds on the heater/shaker:\n"
        "1. Use hs_set_temperature to 42C.\n"
        "2. Use hs_shake at 300 RPM for 60 seconds.\n"
        "3. Use hs_get_temperature to verify 42C.\n"
        "4. Transfer 50 uL from source_plate.A1 to assay_plate.B1.\n"
        "5. Use hs_deactivate to stop heating and shaking.\n"
        "6. Read OD600 for B1 at 600 nm and submit. Control band [0.75, 0.9].\n\n"
        "NOTE: Both heating AND shaking must be active simultaneously for the "
        "reaction to work. Setting temperature alone or shaking alone is "
        "insufficient. And deactivation must happen after the transfer — leaving "
        "the heater on after the protocol is a safety issue."
    ),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "enzyme_substrate"}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "reaction_target"}},
    },
    expected={
        "use_heater_shaker": True, "target_temperature": 42.0,
        "shake_speed": 300, "shake_duration": 60,
        "require_deactivate": True,
        "target_well": "assay_plate.B1", "transfer_volume_ul": 50,
        "wavelength_nm": 600, "control_band": {"min": 0.75, "max": 0.9},
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)



# ── NEW: Centrifuge scenarios ──────────────────────────────────────────

# Basic spin cycle
SPIN_DOWN_QC = TaskSpec(
    scenario="spin_down_qc",
    objective="Perform a centrifugation spin-down of a sample plate.",
    prompt=(
        "A centrifuge with two buckets is available. You need to spin down "
        "a sample plate in bucket 1:\n"
        "1. Use centrifuge_go_to_bucket1 to present bucket 1.\n"
        "2. The assay_plate is already loaded. Lock it with centrifuge_lock_bucket.\n"
        "3. Use centrifuge_close_door, then centrifuge_lock_door.\n"
        "4. Spin at 2000 g for 60 seconds with centrifuge_spin.\n"
        "5. Use centrifuge_open_door to retrieve the plate.\n"
        "6. Read OD600 for assay_plate B1 at 600 nm. Submit. Control band [0.75, 0.9].\n\n"
        "SAFETY: The door MUST be closed and locked BEFORE spinning. "
        "Spinning with the door open will cause an error. "
        "The sequence order is: bucket → lock_bucket → close → lock_door → spin → open."
    ),
    initial_volumes={"assay_plate.B1": 50.0},
    well_metadata={
        "assay_plate": {"B1": {"contents": "spun_sample", "volume_ul": 50}},
    },
    expected={
        "use_centrifuge": True, "g_force": 2000, "duration_s": 60,
        "target_well": "assay_plate.B1", "wavelength_nm": 600,
        "require_door_close": True, "require_lock": True, "require_spin": True,
        "control_band": {"min": 0.75, "max": 0.9},
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)


# Balanced load — both buckets
BALANCED_LOAD_QC = TaskSpec(
    scenario="balanced_load_qc",
    objective="Load both centrifuge buckets for balanced operation.",
    prompt=(
        "A centrifuge requires balanced loading — both buckets must have "
        "equal weight before spinning. Unbalanced loads can damage the centrifuge.\n"
        "1. centrifuge_go_to_bucket1 → lock bucket 1 (with source_plate).\n"
        "2. centrifuge_go_to_bucket2 → lock bucket 2 (with assay_plate).\n"
        "3. Transfer 50 uL from source_plate.A1 to assay_plate.B1 (this is "
        "the QC sample you will read after spinning).\n"
        "4. Close door → lock door → spin at 3000 g for 120 s.\n"
        "5. Open door, read OD600 for assay_plate B1 at 600 nm. Submit.\n"
        "Control band [0.75, 0.9].\n\n"
        "IMPORTANT: Both buckets must be locked BEFORE door close + spin. "
        "Loading only one bucket is an unbalanced load and will cause spin failure."
    ),
    initial_volumes={"source_plate.A1": 200.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "stock", "volume_ul": 200}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "qc_target"}},
    },
    expected={
        "use_centrifuge": True, "g_force": 3000, "duration_s": 120,
        "target_well": "assay_plate.B1", "transfer_volume_ul": 50,
        "wavelength_nm": 600, "require_both_buckets": True,
        "control_band": {"min": 0.75, "max": 0.9},
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)


# Door safety — must lock before spin
DOOR_SAFETY_QC = TaskSpec(
    scenario="door_safety_qc",
    objective="Follow centrifuge safety protocol: close and lock door before spinning.",
    prompt=(
        "The centrifuge door is open. A plate is loaded in bucket 1. "
        "You must follow the correct safety sequence:\n"
        "1. centrifuge_close_door → centrifuge_lock_door.\n"
        "2. Spin at 1500 g for 30 s.\n"
        "WARNING: Attempting to spin before closing+latching the door will "
        "fail with a safety interlock error. You must recover by locking "
        "the door and retrying.\n"
        "3. After spin, centrifuge_open_door.\n"
        "4. Read OD600 for assay_plate B1 (pre-loaded with 50 uL sample) "
        "at 600 nm. Submit. Control band [0.75, 0.9].\n\n"
        "This is a SAFETY-CRITICAL scenario. Skipping the lock step is an "
        "agent recovery failure. Correctly locking before spinning is "
        "success_despite_fault (the initial door-open state was the fault)."
    ),
    initial_volumes={"assay_plate.B1": 50.0},
    well_metadata={
        "assay_plate": {"B1": {"contents": "pre_loaded_qc", "volume_ul": 50}},
    },
    expected={
        "use_centrifuge": True, "g_force": 1500, "duration_s": 30,
        "target_well": "assay_plate.B1", "wavelength_nm": 600,
        "require_door_close": True, "require_lock": True, "require_spin": True,
        "control_band": {"min": 0.75, "max": 0.9},
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)


# ── NEW: Scale scenarios ───────────────────────────────────────────────

# Gravimetric verification — weigh plate before/after transfer
GRAVIMETRIC_QC = TaskSpec(
    scenario="gravimetric_qc",
    objective="Use an analytical balance to gravimetrically verify a liquid transfer.",
    prompt=(
        "An analytical balance ('analytical_balance') is available. "
        "You must verify a 50 uL transfer gravimetrically:\n"
        "1. First, zero the scale with scale_zero.\n"
        "2. Tare the empty assay plate with scale_tare.\n"
        "3. Read the empty weight with scale_get_weight (should be ~0.0 g after tare).\n"
        "4. Pick up a tip, aspirate 50 uL from source_plate.A1, dispense into "
        "assay_plate.B1, discard the tip.\n"
        "5. Read the weight again with scale_get_weight.\n"
        "6. Submit: 'continue' if weight gain > 0.04 g (~50 uL water = 0.05 g).\n"
        "   Otherwise 'hold'.\n\n"
        "NOTE: The ORDER matters — zero before tare, weigh before AND after transfer. "
        "Skipping the pre-transfer weigh makes gravimetric verification impossible."
    ),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control"}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "qc_target"}},
    },
    expected={
        "use_scale": True, "scale_initial_weight": 125.0,
        "target_well": "assay_plate.B1", "transfer_volume_ul": 50,
        "require_zero": True, "require_tare": True,
        "expected_weight_gain_g": 0.05,
    },
)


# Tare before sample — tests tare specifically
TARE_WEIGH_QC = TaskSpec(
    scenario="tare_weigh_qc",
    objective="Tare the balance before weighing to get net sample weight.",
    prompt=(
        "A tube rack containing sample tubes is on the analytical balance "
        "(initial reading: 250.0 g — gross weight including rack). "
        "You need the net weight of just the sample:\n"
        "1. Use scale_tare to zero out the rack weight.\n"
        "2. Use scale_get_weight to read the net sample weight (should be ~0.0 g).\n"
        "3. Transfer 50 uL from source_plate.A1 to assay_plate.B1.\n"
        "4. Read OD600 for B1 at 600 nm and submit. Control band [0.75, 0.9].\n\n"
        "WARNING: Without tare, scale_get_weight returns GROSS weight (250+ g). "
        "Only after tare does it return net sample weight. Failing to tare "
        "means you cannot verify the actual sample mass."
    ),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control"}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "qc_target"}},
    },
    expected={
        "use_scale": True, "scale_initial_weight": 250.0,
        "target_well": "assay_plate.B1", "transfer_volume_ul": 50,
        "wavelength_nm": 600, "require_tare": True,
        "control_band": {"min": 0.75, "max": 0.9},
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.02},
)


# Zero at session start — tests zero vs tare distinction
ZERO_SCALE_QC = TaskSpec(
    scenario="zero_scale_qc",
    objective="Correctly zero the scale at session start, then tare before sample.",
    prompt=(
        "You are starting a new weighing session. The scale currently reads "
        "0.5 g (drift from last session). Protocol requires:\n"
        "1. Use scale_zero to reset to absolute zero.\n"
        "2. Use scale_tare to tare the empty container.\n"
        "3. Verify weight is ~0.0 g with scale_get_weight.\n"
        "(Note: zero is for session start; tare is per-container. "
        "They are DIFFERENT operations — do not confuse them.)\n"
        "4. Then transfer 50 uL from source_plate.A1 to assay_plate.B1.\n"
        "5. Read OD600 for B1 at 600 nm and submit. Control band [0.75, 0.9].\n\n"
        "NOTE: Using tare without zero first leaves calibration drift uncorrected. "
        "Using zero when you meant tare resets the absolute reference incorrectly."
    ),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control"}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "qc_target"}},
    },
    expected={
        "use_scale": True, "scale_initial_weight": 0.5,
        "target_well": "assay_plate.B1", "transfer_volume_ul": 50,
        "wavelength_nm": 600, "require_zero": True, "require_tare": True,
        "control_band": {"min": 0.75, "max": 0.9},
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)


# ── NEW: PlateReader extended scenarios ────────────────────────────────

# Fluorescence read — tests read_fluorescence
FLUORESCENCE_QC = TaskSpec(
    scenario="fluorescence_qc",
    objective="Perform a fluorescence measurement on a QC sample.",
    prompt=(
        "A STAR with plate reader is set up. You need to measure fluorescence "
        "on assay plate well B1 after transferring sample:\n"
        "1. Pick up a tip, aspirate 50 uL from source_plate.A1 (contains GFP-tagged QC control).\n"
        "2. Dispense into assay_plate.B1 and return the tip.\n"
        "3. Use read_fluorescence with excitation=485 nm, emission=535 nm, "
        "focal_height_mm=10.0 on assay_plate well B1.\n"
        "4. Submit: 'continue' if fluorescence > 5.0, else 'hold'. "
        "(Note: fluorescence values are ~10× absorbance scale.)"
    ),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "gfp_qc_control"}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "fluor_target"}},
    },
    expected={
        "target_well": "assay_plate.B1", "transfer_volume_ul": 50,
        "read_mode": "fluorescence",
        "excitation_nm": 485, "emission_nm": 535, "focal_height_mm": 10.0,
    },
)


# Luminescence read — tests read_luminescence
LUMINESCENCE_QC = TaskSpec(
    scenario="luminescence_qc",
    objective="Perform an ATP luminescence assay measurement.",
    prompt=(
        "An ATP detection reagent has been added to source_plate.A1 which "
        "produces luminescence proportional to ATP concentration.\n"
        "1. Pick up a tip, aspirate 50 uL from source_plate.A1.\n"
        "2. Dispense into assay_plate.B1 and discard the tip (reagent is "
        "light-sensitive — work quickly).\n"
        "3. Use read_luminescence with focal_height_mm=10.0 on assay_plate B1.\n"
        "4. Submit: 'continue' if luminescence > 50.0, else 'hold'. "
        "(Note: luminescence values are ~100× absorbance scale.)"
    ),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "atp_reagent", "light_sensitive": True}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "lum_target"}},
    },
    expected={
        "target_well": "assay_plate.B1", "transfer_volume_ul": 50,
        "read_mode": "luminescence",
        "focal_height_mm": 10.0,
    },
)


# Reader door control — tests plate_reader_open + plate_reader_close
READER_DOOR_QC = TaskSpec(
    scenario="reader_door_qc",
    objective="Properly operate the plate reader door before and after reading.",
    prompt=(
        "The plate reader is loaded with assay_plate already inside but the "
        "door is open. You must follow the correct reader protocol:\n"
        "1. Use plate_reader_close to close the reader door.\n"
        "2. Use read_absorbance at 600 nm on assay_plate well B1.\n"
        "3. Use plate_reader_open to open the reader door.\n"
        "4. Submit your QC decision. Control band [0.75, 0.9].\n\n"
        "IMPORTANT: Never read while the door is open. Always close before "
        "reading and open after to remove the plate."
    ),
    initial_volumes={"source_plate.A1": 0.0, "assay_plate.B1": 50.0},
    well_metadata={
        "assay_plate": {"B1": {"contents": "qc_sample", "volume_ul": 50}},
    },
    expected={
        "target_well": "assay_plate.B1", "wavelength_nm": 600,
        "require_door_close": True, "require_door_open": True,
        "plate_preloaded": True,
        "control_band": {"min": 0.75, "max": 0.9},
    },
)


# Multi-mode read — tests absorbance + fluorescence combo
MULTI_MODE_QC = TaskSpec(
    scenario="multi_mode_qc",
    objective="Read both absorbance and fluorescence on the same sample.",
    prompt=(
        "A dual-mode QC sample in source_plate.A1 needs both absorbance and "
        "fluorescence measurement:\n"
        "1. Transfer 50 uL from source_plate.A1 to assay_plate.B1 (fresh tip).\n"
        "2. Read absorbance at 600 nm on assay_plate B1.\n"
        "3. Read fluorescence at ex=485 nm, em=535 nm, focal_height=10.0 mm "
        "on assay_plate B1.\n"
        "4. Submit: 'continue' if both absorbance in [0.75, 0.9] AND "
        "fluorescence > 5.0. Otherwise 'hold'."
    ),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "dual_mode_qc"}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "dual_target"}},
    },
    expected={
        "target_well": "assay_plate.B1", "transfer_volume_ul": 50,
        "read_modes": ["absorbance", "fluorescence"],
        "wavelength_nm": 600, "excitation_nm": 485, "emission_nm": 535,
        "control_band": {"min": 0.75, "max": 0.9},
    },
)


# Mounted tips query — tests get_mounted_tips
MOUNTED_TIPS_QUERY_QC = TaskSpec(
    scenario="mounted_tips_query_qc",
    objective="Use get_mounted_tips to verify tip state during a protocol.",
    prompt=(
        "You are operating a STAR with 8 channels. Before starting a transfer "
        "protocol, you must verify the pipetting head state.\n"
        "1. Use get_mounted_tips to confirm no tips are on the head.\n"
        "2. Pick up a tip from tip_rack_01.A1.\n"
        "3. Use get_mounted_tips to confirm the tip is on channel 0.\n"
        "4. Aspirate 50 uL from source_plate.A1.\n"
        "5. Dispense 50 uL into assay_plate.B1.\n"
        "6. Return the tip.\n"
        "7. Use get_mounted_tips to confirm the head is empty again.\n"
        "8. Read OD600 for B1 at 600 nm. Submit your decision against [0.75, 0.9]."
    ),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control"}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "qc_target"}},
    },
    expected={
        "source_well": "source_plate.A1", "target_well": "assay_plate.B1",
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "require_head_state_checks": True,
        "control_band": {"min": 0.75, "max": 0.9},
    },
)


# ── NEW: Robot arm scenarios ──────────────────────────────────────────


# Arm plate transfer — pick and place plate from carrier to reader
ARM_PLATE_TRANSFER_QC = TaskSpec(
    scenario="arm_plate_transfer_qc",
    objective="Use the robot arm to pick up a plate from the carrier and place it into the plate reader.",
    prompt=(
        "A robot arm (PreciseFlex SCARA) is available alongside the STAR deck. "
        "Your task is to move the assay_plate from its carrier position to the "
        "plate_reader for OD600 reading:\n\n"
        "== Arm sequence ==\n"
        "1. arm_home — home the arm first (required before any motion).\n"
        "2. arm_open_gripper(width_mm=80.0) — open the gripper to receive the plate.\n"
        "3. arm_move_to(x=100, y=200, z=100) — move above the carrier.\n"
        "4. arm_approach(x=100, y=200, z=30, access='vertical') — approach the plate.\n"
        "5. arm_close_gripper(width_mm=85.0) — grip the plate (SBS standard width).\n"
        "6. arm_pick_up_resource(x=100, y=200, z=30, plate_width_mm=85.0) — lift plate.\n"
        "7. arm_move_to(x=300, y=100, z=100) — transport to reader area.\n"
        "8. arm_approach(x=300, y=100, z=30, access='vertical') — approach reader tray.\n"
        "9. arm_drop_resource(x=300, y=100, z=30) — place plate in reader.\n"
        "10. arm_move_to_safe — retract arm to safe position before reading.\n\n"
        "== Readout ==\n"
        "11. plate_reader_open → read_absorbance(assay_plate, 600 nm, wells=['B1']).\n"
        "12. Submit decision against control band [0.75, 0.9].\n\n"
        "SAFETY WARNING: Trying to pick_up with a closed gripper will fail "
        "with a 'gripper_already_closed' error. Trying to drop with an open "
        "gripper will fail with 'gripper_already_open' error. Recover by "
        "opening/closing the gripper and retrying — but do NOT skip arm_move_to_safe "
        "at the end or the arm will remain over the reader, risking collision."
    ),
    initial_volumes={"assay_plate.B1": 50.0},
    well_metadata={
        "assay_plate": {"B1": {"contents": "pre_loaded_sample", "volume_ul": 50}},
    },
    expected={
        "use_arm": True,
        "target_well": "assay_plate.B1", "wavelength_nm": 600,
        "require_home": True, "require_pickup": True, "require_drop": True,
        "require_safe_move": True, "require_reader_access": True,
        "control_band": {"min": 0.75, "max": 0.9},
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)


# Arm halt recovery — halt during motion, verify position, recover
ARM_HALT_RECOVERY_QC = TaskSpec(
    scenario="arm_halt_recovery_qc",
    objective="Handle an arm emergency stop: halt during motion, verify position, and recover.",
    prompt=(
        "A robot arm is available. During a routine plate transfer operation, "
        "a potential collision is detected. You must:\n\n"
        "1. Home the arm with arm_home.\n"
        "2. Start moving toward the plate: arm_move_to(x=100, y=200, z=80).\n"
        "3. Use arm_get_position to verify the current position.\n"
        "4. Before reaching the destination, issue arm_halt for safety.\n"
        "5. Check current position again with arm_get_position.\n"
        "6. Check gripper state with arm_get_gripper_state.\n"
        "7. Move to safe position: arm_move_to_safe.\n"
        "8. Now, transfer 50 uL from source_plate.A1 to assay_plate.B1 using "
        "the liquid handler (pick_up from tip_rack_01.A1, aspirate, dispense, "
        "return tip).\n"
        "9. Read OD600 for assay_plate B1 at 600 nm. Submit against [0.75, 0.9].\n\n"
        "This tests the agent's ability to handle emergency stops and verify "
        "arm state during fault recovery."
    ),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control"}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "qc_target"}},
    },
    expected={
        "use_arm": True,
        "source_well": "source_plate.A1", "target_well": "assay_plate.B1",
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "require_home": True, "require_halt": True,
        "require_position_check": True, "require_safe_move": True,
        "control_band": {"min": 0.75, "max": 0.9},
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)


# Arm position verify — safety inspection of arm state
ARM_POSITION_VERIFY_QC = TaskSpec(
    scenario="arm_position_verify_qc",
    objective="Verify the robot arm position and gripper state before and after operations.",
    prompt=(
        "A robot arm is available. Before performing any plate manipulation, "
        "you must verify the arm is in a safe state:\n\n"
        "1. Home the arm with arm_home.\n"
        "2. Check position with arm_get_position — should be at home (0, 0, ~150).\n"
        "3. Check gripper state with arm_get_gripper_state — should be open.\n"
        "4. Open gripper to 80 mm: arm_open_gripper(width_mm=80.0) for safety.\n"
        "5. Move arm to pick-up position: arm_move_to(x=100, y=200, z=100).\n"
        "6. Approach: arm_approach(x=100, y=200, z=30).\n"
        "7. Close gripper: arm_close_gripper(width_mm=85.0).\n"
        "8. Check gripper state again — should show closed.\n"
        "9. Pick up plate: arm_pick_up_resource(x=100, y=200, z=30, plate_width_mm=85.0).\n"
        "10. Check position again with arm_get_position.\n"
        "11. Move to safe: arm_move_to_safe.\n"
        "12. Drop the resource (it was just a drill): arm_open_gripper(width_mm=80.0).\n"
        "13. Now, using the liquid handler, transfer 50 uL from source_plate.A1 "
        "to assay_plate.B1 (pick_up from tip_rack_01.A1, aspirate, dispense, "
        "return tip).\n"
        "14. Read OD600 for assay_plate B1 at 600 nm. Submit against [0.75, 0.9].\n\n"
        "This tests state inspection and position/gripper verification in a "
        "safety-critical workflow."
    ),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control"}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "qc_target"}},
    },
    expected={
        "use_arm": True,
        "source_well": "source_plate.A1", "target_well": "assay_plate.B1",
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "require_home": True, "require_state_checks": True,
        "require_pickup": True, "require_safe_move": True,
        "control_band": {"min": 0.75, "max": 0.9},
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)


# ── NEW: Plate sealer scenarios ────────────────────────────────────────


# Basic seal plate — set temp, verify, seal, transfer, read
SEAL_PLATE_QC = TaskSpec(
    scenario="seal_plate_qc",
    objective="Heat-seal a sample plate before incubation: set temperature, verify, seal.",
    prompt=(
        "A plate sealer is available for heat-sealing microplates. The "
        "assay_plate (pre-loaded with sample in B1) needs to be sealed "
        "before incubation:\n\n"
        "== Sealer sequence ==\n"
        "1. sealer_set_temperature(temperature=170.0) — set sealing temp to 170°C.\n"
        "2. sealer_get_temperature — verify the sealer has reached 170°C.\n"
        "3. sealer_close — close the sealer door (the plate is already loaded).\n"
        "4. sealer_seal(temperature=170, duration_s=3.0) — heat-seal for 3 seconds.\n"
        "5. sealer_open — open the door to retrieve the sealed plate.\n\n"
        "== Verification ==\n"
        "6. Transfer 50 uL from source_plate.A1 to the sealed assay_plate.B1 "
        "using the liquid handler (pick_up from tip_rack_01.A1, aspirate, "
        "dispense, return tip). The seal should not interfere with pipetting.\n"
        "7. Read OD600 for assay_plate B1 at 600 nm. Submit against [0.75, 0.9].\n\n"
        "IMPORTANT: The sealer door MUST be closed before invoking sealer_seal. "
        "Trying to seal with the door open returns a 'door_open' error. "
        "The sequence order is: set_temp→verify→close→seal→open."
    ),
    initial_volumes={"source_plate.A1": 120.0, "assay_plate.B1": 50.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control"}},
        "assay_plate": {"B1": {"contents": "pre_loaded_sample", "volume_ul": 50}},
    },
    expected={
        "use_sealer": True,
        "source_well": "source_plate.A1", "target_well": "assay_plate.B1",
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "seal_temperature": 170, "seal_duration_s": 3.0,
        "require_temp_verify": True, "require_seal": True,
        "control_band": {"min": 0.75, "max": 0.9},
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)


# Temperature verification — must reach target before sealing
SEAL_TEMP_VERIFY_QC = TaskSpec(
    scenario="seal_temp_verify_qc",
    objective="Verify the sealer reaches target temperature before initiating the seal cycle.",
    prompt=(
        "A plate sealer is available. Before sealing, the sealer must reach "
        "the target temperature of 165°C. You must verify this:\n\n"
        "1. sealer_set_temperature(temperature=165.0).\n"
        "2. Query sealer_get_temperature to read current temperature.\n"
        "3. The dry-run sealer reaches temperature instantly, but you should "
        "still verify it BEFORE closing the door and sealing.\n"
        "4. sealer_close — close the door.\n"
        "5. sealer_seal(temperature=165, duration_s=2.5).\n"
        "6. sealer_open — open the door.\n\n"
        "== Post-seal verification ==\n"
        "7. Transfer 50 uL from source_plate.A1 to assay_plate.B1 using "
        "the liquid handler (pick_up from tip_rack_01.A1, aspirate, "
        "dispense, return tip).\n"
        "8. Read OD600 for assay_plate B1 at 600 nm. Submit against [0.75, 0.9].\n\n"
        "CRITICAL: The temperature must be verified BEFORE the seal. "
        "Sealing at the wrong temperature will compromise plate integrity. "
        "A sequence of: set_temp→read_temp→close→seal→open is expected. "
        "Skipping the temperature read is a protocol deviation."
    ),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control"}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "qc_target"}},
    },
    expected={
        "use_sealer": True,
        "source_well": "source_plate.A1", "target_well": "assay_plate.B1",
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "seal_temperature": 165, "seal_duration_s": 2.5,
        "require_temp_verify": True, "require_seal": True,
        "control_band": {"min": 0.75, "max": 0.9},
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)


# Door safety — must close before seal, seal with open door fails
SEAL_DOOR_SAFETY_QC = TaskSpec(
    scenario="seal_door_safety_qc",
    objective="Follow sealer door safety protocol: close before seal, recover from door errors.",
    prompt=(
        "The plate sealer door is initially OPEN. You must seal the "
        "assay_plate (pre-loaded with sample in B1) following the correct "
        "safety sequence:\n\n"
        "1. sealer_set_temperature(temperature=175.0).\n"
        "2. sealer_get_temperature — verify temperature.\n"
        "3. sealer_close — close the door.\n"
        "4. sealer_seal(temperature=175, duration_s=3.0).\n"
        "WARNING: Attempting to seal before closing the door will fail with "
        "a 'door_open' error. If this happens, you must close the door and "
        "retry the seal. The seal success counts even if you hit the error "
        "once (as long as you recover).\n"
        "5. sealer_open.\n\n"
        "== Readout ==\n"
        "6. Read OD600 for assay_plate B1 (which already has 50 uL sample) "
        "at 600 nm. Submit against [0.75, 0.9].\n\n"
        "SAFETY-CRITICAL: Skipping the door close and sealing with the door "
        "open is a protocol violation. Correctly closing before sealing "
        "is the expected behavior."
    ),
    initial_volumes={"assay_plate.B1": 50.0},
    well_metadata={
        "assay_plate": {"B1": {"contents": "pre_loaded_sample", "volume_ul": 50}},
    },
    expected={
        "use_sealer": True,
        "target_well": "assay_plate.B1", "wavelength_nm": 600,
        "seal_temperature": 175, "seal_duration_s": 3.0,
        "require_door_close": True, "require_seal": True,
        "require_door_open_after": True,
        "control_band": {"min": 0.75, "max": 0.9},
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)


# ── NEW: Plate peeler/de-sealer scenarios ──────────────────────────────


# Basic peel — check seal, peel, verify removal, transfer, read
PEEL_PLATE_QC = TaskSpec(
    scenario="peel_plate_qc",
    objective="Remove the seal from a plate using the peeler: check, peel, verify.",
    prompt=(
        "A plate peeler/de-sealer (XPeel) is available. The assay_plate "
        "has a seal that needs to be removed before pipetting:\n\n"
        "== Peeler sequence ==\n"
        "1. peeler_move_conveyor_in — load the plate into the peeler.\n"
        "2. peeler_move_elevator_up — raise plate to peel position.\n"
        "3. peeler_seal_check — verify the seal is detected.\n"
        "4. peeler_peel(begin_location=0, fast=false, adhere_time=2.5) — peel.\n"
        "5. peeler_seal_check — verify the seal is now gone (should return 'no_seal').\n"
        "6. peeler_move_elevator_down — lower the plate.\n"
        "7. peeler_move_conveyor_out — unload.\n\n"
        "== Post-peel verification ==\n"
        "8. Transfer 50 uL from source_plate.A1 to assay_plate.B1 using "
        "the liquid handler (pick_up from tip_rack_01.A1, aspirate, "
        "dispense, return tip). With the seal removed, pipetting should work.\n"
        "9. Read OD600 for assay_plate B1 at 600 nm. Submit against [0.75, 0.9].\n\n"
        "IMPORTANT: Trying to peel without a seal present returns a 'no_seal' "
        "error. Always check with peeler_seal_check before peeling. "
        "The sequence order is: in→up→check→peel→check→down→out."
    ),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control"}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "qc_target"}},
    },
    expected={
        "use_peeler": True,
        "source_well": "source_plate.A1", "target_well": "assay_plate.B1",
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "require_seal_check_before": True, "require_peel": True,
        "require_seal_check_after": True, "require_conveyor_in_out": True,
        "control_band": {"min": 0.75, "max": 0.9},
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)


# Peeler tape + status — monitor consumable and device state
PEEL_TAPE_MONITOR_QC = TaskSpec(
    scenario="peel_tape_monitor_qc",
    objective="Monitor tape remaining and device status before and after peeling.",
    prompt=(
        "A plate peeler is available. Before peeling, you must verify "
        "consumable levels and device health:\n\n"
        "1. peeler_get_status — check device has no errors.\n"
        "2. peeler_get_tape_remaining — check there is enough adhesive tape.\n"
        "3. peeler_move_conveyor_in → peeler_move_elevator_up.\n"
        "4. peeler_seal_check — confirm seal detected.\n"
        "5. peeler_advance_tape — advance to a clean tape segment.\n"
        "6. peeler_peel(begin_location=0, adhere_time=2.5).\n"
        "7. peeler_get_tape_remaining — verify tape decreased after peel.\n"
        "8. peeler_get_status — verify device still healthy.\n"
        "9. peeler_move_elevator_down → peeler_move_conveyor_out.\n\n"
        "== Post-peel transfer ==\n"
        "10. Transfer 50 uL from source_plate.A1 to assay_plate.B1.\n"
        "11. Read OD600 for assay_plate B1 at 600 nm. Submit against [0.75, 0.9].\n\n"
        "CRITICAL: Tape remaining should decrease after peeling (~1% per peel). "
        "If tape is below 5%, the peeler should not be used without replacement. "
        "Always check status before and after critical operations."
    ),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control"}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "qc_target"}},
    },
    expected={
        "use_peeler": True,
        "source_well": "source_plate.A1", "target_well": "assay_plate.B1",
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "require_tape_check_before": True, "require_peel": True,
        "require_tape_check_after": True, "require_status_checks": True,
        "control_band": {"min": 0.75, "max": 0.9},
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)


# No-seal error recovery — handle missing seal gracefully
PEEL_NO_SEAL_QC = TaskSpec(
    scenario="peel_no_seal_qc",
    objective="Handle the case where no seal is detected: verify, report, skip peel.",
    prompt=(
        "A plate peeler is available. The assay_plate may ALREADY have its "
        "seal removed (the seal sensor may report 'no_seal'). You must:\n\n"
        "1. peeler_move_conveyor_in → peeler_move_elevator_up.\n"
        "2. peeler_seal_check — check the seal status.\n"
        "If 'no_seal' is returned:\n"
        "   - The plate is already unsealed. Do NOT attempt to peel — it will "
        "     fail with a 'no_seal' error.\n"
        "   - Proceed directly to step 3.\n"
        "If 'seal_detected' is returned:\n"
        "   - Use peeler_peel(begin_location=0, adhere_time=2.5) to remove it.\n"
        "   - Then peeler_seal_check again to verify 'no_seal'.\n"
        "3. peeler_move_elevator_down → peeler_move_conveyor_out.\n\n"
        "== Post-peel verification ==\n"
        "4. Transfer 50 uL from source_plate.A1 to assay_plate.B1.\n"
        "5. Read OD600 for assay_plate B1 at 600 nm. Submit against [0.75, 0.9].\n\n"
        "CRITICAL: The key test is whether the agent correctly handles the "
        "'no_seal' response. Forcing an unnecessary peel is an agent_error. "
        "The correct response to 'no_seal' is to skip peeling and proceed."
    ),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control"}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "qc_target"}},
    },
    expected={
        "use_peeler": True,
        "source_well": "source_plate.A1", "target_well": "assay_plate.B1",
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "require_seal_check": True,
        "control_band": {"min": 0.75, "max": 0.9},
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)


# ── NEW: Dedicated shaker scenarios ─────────────────────────────────────


# Basic shaker mix — lock→shake→stop→unlock→transfer→read
SHAKER_MIX_QC = TaskSpec(
    scenario="shaker_mix_qc",
    objective="Mix a plate on the dedicated shaker: lock, shake, stop, unlock.",
    prompt=(
        "A dedicated plate shaker (no heating) is available. You need to "
        "mix the assay_plate before reading:\n\n"
        "== Shaker sequence ==\n"
        "1. shaker_lock_plate — lock the plate onto the shaker.\n"
        "2. shaker_shake(speed_rpm=800, duration_s=10.0) — shake at 800 RPM for 10 seconds.\n"
        "3. shaker_stop_shaking — stop (even though timed shake auto-stops, "
        "   good practice to explicitly stop).\n"
        "4. shaker_unlock_plate — unlock the plate.\n\n"
        "== Transfer ==\n"
        "5. Transfer 50 uL from source_plate.A1 to assay_plate.B1 using "
        "the liquid handler (pick_up from tip_rack_01.A1, aspirate, "
        "dispense, return tip).\n"
        "6. Read OD600 for assay_plate B1 at 600 nm. Submit against [0.75, 0.9].\n\n"
        "IMPORTANT: The plate MUST be locked before shaking. "
        "Trying to shake without locking returns a 'plate_not_locked' error. "
        "The sequence order is: lock→shake→stop→unlock."
    ),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control"}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "qc_target"}},
    },
    expected={
        "use_shaker": True,
        "source_well": "source_plate.A1", "target_well": "assay_plate.B1",
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "shake_speed_rpm": 800, "shake_duration_s": 10.0,
        "require_lock": True, "require_unlock": True,
        "control_band": {"min": 0.75, "max": 0.9},
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)


# Lock safety — must lock before shake, auto-stop on unlock
SHAKER_LOCK_SAFETY_QC = TaskSpec(
    scenario="shaker_lock_safety_qc",
    objective="Follow shaker lock safety protocol: lock before shake, verify auto-stop on unlock.",
    prompt=(
        "The shaker plate lock is initially OPEN. You must follow the "
        "correct safety sequence:\n\n"
        "1. shaker_lock_plate — lock the plate.\n"
        "2. shaker_shake(speed_rpm=600, duration_s=5.0) — shake at 600 RPM for 5 seconds.\n"
        "WARNING: Attempting to shake before locking will fail with a "
        "'plate_not_locked' error. If this happens, lock the plate and retry.\n"
        "3. shaker_unlock_plate — unlock (automatically stops shaking if still active).\n\n"
        "== Verification ==\n"
        "4. Transfer 50 uL from source_plate.A1 to assay_plate.B1.\n"
        "5. Read OD600 for assay_plate B1 at 600 nm. Submit against [0.75, 0.9].\n\n"
        "SAFETY-CRITICAL: An unlocked plate during shaking can fly off the "
        "shaker. The lock interlock must be respected. Correctly locking "
        "before shaking is success_despite_fault (the initial unlocked state "
        "is the fault condition)."
    ),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control"}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "qc_target"}},
    },
    expected={
        "use_shaker": True,
        "source_well": "source_plate.A1", "target_well": "assay_plate.B1",
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "shake_speed_rpm": 600, "shake_duration_s": 5.0,
        "require_lock": True, "require_unlock": True,
        "control_band": {"min": 0.75, "max": 0.9},
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)


# Continuous shake with manual stop — shake without duration, stop manually
SHAKER_CONTINUOUS_QC = TaskSpec(
    scenario="shaker_continuous_qc",
    objective="Run a continuous shake (no duration) and manually stop it.",
    prompt=(
        "A dedicated shaker is available. You need to run a continuous "
        "shake (indefinite duration) and manually stop it:\n\n"
        "1. shaker_lock_plate.\n"
        "2. shaker_shake(speed_rpm=500) — start continuous shaking (no duration specified).\n"
        "3. The shaker is now running indefinitely. After a few seconds "
        "(the clock advances), call shaker_stop_shaking to stop.\n"
        "4. shaker_unlock_plate.\n\n"
        "== Post-shake transfer ==\n"
        "5. Transfer 50 uL from source_plate.A1 to assay_plate.B1.\n"
        "6. Read OD600 for assay_plate B1 at 600 nm. Submit against [0.75, 0.9].\n\n"
        "KEY DISTINCTION: This tests continuous shaking (no duration argument). "
        "The agent must remember to call shaker_stop_shaking before unlocking — "
        "unlocking auto-stops but explicit stop is better practice. "
        "Forgetting to stop before unlock is acceptable (auto-stop covers it), "
        "but forgetting to lock before shake is a hard error."
    ),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control"}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "qc_target"}},
    },
    expected={
        "use_shaker": True,
        "source_well": "source_plate.A1", "target_well": "assay_plate.B1",
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "shake_speed_rpm": 500,
        "require_lock": True, "require_unlock": True,
        "control_band": {"min": 0.75, "max": 0.9},
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)


# ── NEW: Temperature controller scenarios ──────────────────────────────


# Temp control incubate — set temp → wait → verify → hold → deactivate
TEMP_CONTROL_INCUBATE_QC = TaskSpec(
    scenario="temp_control_incubate_qc",
    objective="Incubate a plate at a set temperature: set, wait, verify, deactivate.",
    prompt=(
        "A dedicated temperature controller (no shaking) is available. "
        "You need to incubate the assay_plate at 37°C before reading:\n\n"
        "== Temperature control sequence ==\n"
        "1. temp_controller_set_temperature(temperature=37.0) — set target to 37°C.\n"
        "2. temp_controller_wait_for_temperature(timeout=60.0, tolerance=0.5) — "
        "   wait until the temperature stabilizes at 37±0.5°C.\n"
        "3. temp_controller_get_temperature — verify the current temperature is at 37°C.\n"
        "4. temp_controller_deactivate — turn off heating after incubation.\n\n"
        "== Transfer ==\n"
        "5. Transfer 50 uL from source_plate.A1 to assay_plate.B1.\n"
        "6. Read OD600 for assay_plate B1 at 600 nm. Submit against [0.75, 0.9].\n\n"
        "IMPORTANT: The sequence must be: set→wait→verify→deactivate. "
        "Skipping wait_for_temperature means the plate may incubate at the wrong "
        "temperature. Deactivating before verifying is wasteful (heat lost)."
    ),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control"}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "qc_target"}},
    },
    expected={
        "use_temp_controller": True,
        "source_well": "source_plate.A1", "target_well": "assay_plate.B1",
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "target_temperature": 37.0,
        "require_wait": True, "require_verify": True, "require_deactivate": True,
        "control_band": {"min": 0.75, "max": 0.9},
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)


# Multi-point temp verify — check before, during, after transfer
TEMP_CONTROL_VERIFY_QC = TaskSpec(
    scenario="temp_control_verify_qc",
    objective="Verify temperature at multiple checkpoints: before and after transfer.",
    prompt=(
        "A temperature controller is available. You need to pre-warm the "
        "assay_plate to 42°C and verify the temperature at multiple points:\n\n"
        "1. temp_controller_set_temperature(temperature=42.0).\n"
        "2. temp_controller_wait_for_temperature(timeout=60.0, tolerance=0.5).\n"
        "3. temp_controller_get_temperature — verify BEFORE transfer.\n"
        "4. Transfer 50 uL from source_plate.A1 to assay_plate.B1.\n"
        "5. temp_controller_get_temperature — verify AFTER transfer "
        "(temp should still be 42°C).\n"
        "6. temp_controller_deactivate.\n"
        "7. Read OD600 for assay_plate B1 at 600 nm. Submit against [0.75, 0.9].\n\n"
        "CRITICAL: Temperature must be verified at BOTH checkpoints (before "
        "and after transfer). A single temperature check is insufficient — "
        "the transfer step could have disturbed the thermal equilibrium."
    ),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control"}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "qc_target"}},
    },
    expected={
        "use_temp_controller": True,
        "source_well": "source_plate.A1", "target_well": "assay_plate.B1",
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "target_temperature": 42.0,
        "require_double_verify": True, "require_deactivate": True,
        "control_band": {"min": 0.75, "max": 0.9},
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)


# Temp timeout handling — agent must handle temp wait timeout gracefully
TEMP_CONTROL_TIMEOUT_QC = TaskSpec(
    scenario="temp_control_timeout_qc",
    objective="Handle a temperature wait timeout: detect failure, retry or proceed.",
    prompt=(
        "A temperature controller is available. You need to set it to 60°C — "
        "a high temperature that may take time to reach:\n\n"
        "1. temp_controller_set_temperature(temperature=60.0).\n"
        "2. temp_controller_wait_for_temperature(timeout=5.0, tolerance=0.5) — "
        "   use a SHORT timeout (5 seconds). In dry-run mode this will succeed, "
        "   but you should still check the result.\n"
        "3. temp_controller_get_temperature — verify the temperature was reached.\n"
        "4. If the temperature was reached, proceed to transfer.\n"
        "   If wait_for_temperature timed out, you should check temperature "
        "   anyway — it might be close enough. If still not at 60°C, you may "
        "   retry with a longer timeout.\n"
        "5. Transfer 50 uL from source_plate.A1 to assay_plate.B1.\n"
        "6. temp_controller_deactivate.\n"
        "7. Read OD600 for assay_plate B1 at 600 nm. Submit against [0.75, 0.9].\n\n"
        "KEY TEST: The agent must CHECK the temperature after the wait, "
        "regardless of whether the wait reported success or timeout. "
        "Blindly trusting wait_for_temperature without verifying is "
        "an agent_error."
    ),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control"}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "qc_target"}},
    },
    expected={
        "use_temp_controller": True,
        "source_well": "source_plate.A1", "target_well": "assay_plate.B1",
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "target_temperature": 60.0,
        "require_verify_after_wait": True, "require_deactivate": True,
        "control_band": {"min": 0.75, "max": 0.9},
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)


# ── NEW: Tilter module scenarios ──────────────────────────────────────


# Basic tilt — set angle → verify → return to level → transfer → read
TILTER_DRAIN_QC = TaskSpec(
    scenario="tilter_drain_qc",
    objective="Tilt a plate for draining: set angle, verify, return to level.",
    prompt=(
        "A plate tilter module (Hamilton Tilt Module) is available. You need "
        "to tilt the assay_plate to 15° for draining, then return it to "
        "level before pipetting:\n\n"
        "== Tilter sequence ==\n"
        "1. tilter_set_angle(angle=15.0) — tilt the plate to 15°.\n"
        "2. tilter_get_angle — verify the angle is 15°.\n"
        "3. (Wait for drain — the plate is tilted, liquid settles to low side.)\n"
        "4. tilter_return_to_level — return to 0° (flat) before pipetting.\n"
        "5. tilter_get_angle — verify returned to 0°.\n\n"
        "== Transfer ==\n"
        "6. Transfer 50 uL from source_plate.A1 to assay_plate.B1.\n"
        "7. Read OD600 for assay_plate B1 at 600 nm. Submit against [0.75, 0.9].\n\n"
        "IMPORTANT: The tilter MUST be returned to level (0°) before the "
        "liquid handler pipettes. Pipetting on a tilted plate will cause "
        "inaccurate aspiration. The sequence is: tilt→verify→drain→level→verify→transfer."
    ),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control"}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "qc_target"}},
    },
    expected={
        "use_tilter": True,
        "source_well": "source_plate.A1", "target_well": "assay_plate.B1",
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "tilt_angle": 15.0,
        "require_return_to_level": True, "require_verify": True,
        "control_band": {"min": 0.75, "max": 0.9},
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)


# Multi-angle tilt — set multiple angles, verify each step
TILTER_MULTI_ANGLE_QC = TaskSpec(
    scenario="tilter_multi_angle_qc",
    objective="Test multiple tilt angles in sequence: 10°, 20°, return to level.",
    prompt=(
        "A tilter module is available. Test multiple tilt angles to find the "
        "optimal drain angle:\n\n"
        "1. tilter_set_angle(angle=10.0) → tilter_get_angle to verify.\n"
        "2. tilter_tilt(relative_angle=10.0) — tilt +10° more (should reach 20°).\n"
        "3. tilter_get_angle — verify at 20°.\n"
        "4. tilter_return_to_level — return to 0°.\n"
        "5. tilter_get_angle — verify at 0°.\n\n"
        "== Transfer ==\n"
        "6. Transfer 50 uL from source_plate.A1 to assay_plate.B1.\n"
        "7. Read OD600 for assay_plate B1 at 600 nm. Submit against [0.75, 0.9].\n\n"
        "KEY TEST: Uses BOTH tilter_set_angle (absolute) and tilter_tilt "
        "(relative). The agent must understand the difference: set_angle(10) "
        "→ tilt(+10) should reach 20°, not 10°."
    ),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control"}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "qc_target"}},
    },
    expected={
        "use_tilter": True,
        "source_well": "source_plate.A1", "target_well": "assay_plate.B1",
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "require_relative_tilt": True, "require_return_to_level": True,
        "control_band": {"min": 0.75, "max": 0.9},
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)


# Tilter safety — extreme angle protection, must return to level
TILTER_SAFETY_QC = TaskSpec(
    scenario="tilter_safety_qc",
    objective="Follow tilter safety protocol: avoid extreme angles, always return to level.",
    prompt=(
        "A tilter module is available. Safety rules apply:\n"
        "1. The tilter has a ±45° safety limit. Angles beyond this are rejected.\n"
        "2. Always return to level (0°) after use.\n\n"
        "== Protocol ==\n"
        "1. tilter_set_angle(angle=30.0) — tilt to 30° (safe).\n"
        "2. tilter_get_angle — verify 30°.\n"
        "3. tilter_return_to_level.\n"
        "4. tilter_get_angle — verify returned to 0°.\n"
        "WARNING: If you attempt tilter_set_angle(angle=50), the tilter will "
        "return an 'angle_too_extreme' error (safety limit is ±45°). If this "
        "happens, use a smaller angle and retry.\n\n"
        "5. Transfer 50 uL from source_plate.A1 to assay_plate.B1.\n"
        "6. Read OD600 for assay_plate B1 at 600 nm. Submit against [0.75, 0.9].\n\n"
        "SAFETY-CRITICAL: Leaving the tilter at a non-zero angle can cause "
        "pipetting errors. The agent MUST return to level before transfer. "
        "Attempting extreme angles (>45°) is a safety violation."
    ),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control"}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "qc_target"}},
    },
    expected={
        "use_tilter": True,
        "source_well": "source_plate.A1", "target_well": "assay_plate.B1",
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "tilt_angle": 30.0,
        "require_return_to_level": True, "max_angle": 45.0,
        "control_band": {"min": 0.75, "max": 0.9},
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)


# ── NEW: Storage / incubator scenarios ────────────────────────────────


# Store & retrieve — store plate, incubate, retrieve, transfer, read
STORAGE_STORE_RETRIEVE_QC = TaskSpec(
    scenario="storage_store_retrieve_qc",
    objective="Store a plate in the incubator, incubate, then retrieve it for reading.",
    prompt=(
        "An incubator/storage unit (20 free sites) is available. You need "
        "to store the assay_plate, incubate it, then retrieve it:\n\n"
        "== Storage sequence ==\n"
        "1. storage_get_free_sites — check available capacity.\n"
        "2. storage_open_door — open the incubator door.\n"
        "3. storage_store_plate(plate_name='assay_plate') — store the plate.\n"
        "4. storage_close_door — close the door.\n"
        "5. storage_set_temperature(temperature=37.0) — set incubation temp.\n"
        "6. storage_get_temperature — verify 37°C reached.\n"
        "7. (Incubation period — clock advances.)\n"
        "8. storage_open_door — open to retrieve.\n"
        "9. storage_retrieve_plate(plate_name='assay_plate') — retrieve plate.\n"
        "10. storage_close_door.\n\n"
        "== Transfer ==\n"
        "11. Transfer 50 uL from source_plate.A1 to assay_plate.B1.\n"
        "12. Read OD600 for assay_plate B1 at 600 nm. Submit against [0.75, 0.9].\n\n"
        "IMPORTANT: The sequence is: check_capacity→open→store→close→set_temp→"
        "verify→incubate→open→retrieve→close."
    ),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control"}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "qc_target"}},
    },
    expected={
        "use_storage": True,
        "source_well": "source_plate.A1", "target_well": "assay_plate.B1",
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "incubation_temp": 37.0,
        "require_store": True, "require_retrieve": True,
        "control_band": {"min": 0.75, "max": 0.9},
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)


# Storage environment monitoring — temp + shaking + capacity
STORAGE_ENV_MONITOR_QC = TaskSpec(
    scenario="storage_env_monitor_qc",
    objective="Monitor storage environment: set temp, start shaking, verify, stop, check capacity.",
    prompt=(
        "An incubator/storage unit is available. Monitor its environment:\n\n"
        "1. storage_open_door → storage_store_plate(plate_name='assay_plate') → "
        "   storage_close_door.\n"
        "2. storage_set_temperature(temperature=30.0).\n"
        "3. storage_get_temperature — verify BEFORE shaking.\n"
        "4. storage_start_shaking(frequency=2.0) — start gentle shaking.\n"
        "5. storage_get_temperature — verify DURING shaking (temp should hold).\n"
        "6. storage_stop_shaking — stop shaking.\n"
        "7. storage_get_temperature — verify AFTER shaking stopped.\n"
        "8. storage_get_free_sites — check how many sites remain.\n"
        "9. storage_open_door → storage_retrieve_plate(plate_name='assay_plate') "
        "   → storage_close_door.\n\n"
        "== Transfer ==\n"
        "10. Transfer 50 uL from source_plate.A1 to assay_plate.B1.\n"
        "11. Read OD600 for assay_plate B1 at 600 nm. Submit against [0.75, 0.9].\n\n"
        "CRITICAL: Temperature must be verified at THREE points: before shaking, "
        "during shaking, and after stopping. Shaking should not affect temperature "
        "stability. Free site count should decrease after storing and increase "
        "after retrieving."
    ),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control"}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "qc_target"}},
    },
    expected={
        "use_storage": True,
        "source_well": "source_plate.A1", "target_well": "assay_plate.B1",
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "incubation_temp": 30.0,
        "require_triple_temp_verify": True, "require_shaking": True,
        "control_band": {"min": 0.75, "max": 0.9},
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)


# Storage capacity — check capacity before storing, handle full storage
STORAGE_CAPACITY_QC = TaskSpec(
    scenario="storage_capacity_qc",
    objective="Check storage capacity before storing a plate — ensure there is space.",
    prompt=(
        "An incubator/storage unit is available. Before storing the assay_plate, "
        "always check available capacity:\n\n"
        "1. storage_get_free_sites — check how many sites are free.\n"
        "   (There are 20 free sites in the dry-run storage, plenty of space.)\n"
        "2. If free_sites > 0: storage_open_door → storage_store_plate(plate_name='assay_plate') "
        "   → storage_close_door.\n"
        "   If free_sites == 0: storage is FULL. You cannot store. Proceed without storing.\n"
        "3. storage_set_temperature(temperature=37.0).\n"
        "4. storage_get_free_sites — should show 19 free (one less after storing).\n"
        "5. storage_open_door → storage_retrieve_plate(plate_name='assay_plate') "
        "   → storage_close_door.\n"
        "6. storage_get_free_sites — should show 20 again (freed after retrieval).\n\n"
        "== Transfer ==\n"
        "7. Transfer 50 uL from source_plate.A1 to assay_plate.B1.\n"
        "8. Read OD600 for assay_plate B1 at 600 nm. Submit against [0.75, 0.9].\n\n"
        "KEY TEST: The agent MUST check capacity before storing. Blindly storing "
        "when the incubator is full (free_sites == 0) will fail. The capacity "
        "should decrease after storing and increase after retrieving."
    ),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control"}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "qc_target"}},
    },
    expected={
        "use_storage": True,
        "source_well": "source_plate.A1", "target_well": "assay_plate.B1",
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "require_capacity_check": True,
        "control_band": {"min": 0.75, "max": 0.9},
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)


# ── NEW: Powder dispenser scenarios ──────────────────────────────────


# Basic powder dispense — dispense single powder, then add liquid, read
POWDER_DISPENSE_QC = TaskSpec(
    scenario="powder_dispense_qc",
    objective="Dispense a powder reagent into a well, then add liquid for reading.",
    prompt=(
        "A powder dispenser is available. You need to dispense reagent powder "
        "into the assay plate before adding liquid:\n\n"
        "== Powder dispensing ==\n"
        "1. powder_dispense(powder_name='reagent_a', amount_mg=50.0, "
        "   target_well='assay_plate:B1') — dispense 50 mg of reagent_a into B1.\n\n"
        "== Liquid addition ==\n"
        "2. Transfer 50 uL from source_plate.A1 to assay_plate.B1 using "
        "the liquid handler (pick_up from tip_rack_01.A1, aspirate, "
        "dispense, return tip). The liquid will dissolve the powder.\n"
        "3. Read OD600 for assay_plate B1 at 600 nm. Submit against [0.75, 0.9].\n\n"
        "IMPORTANT: Amount must be positive and ≤1000 mg per dispense. "
        "Exceeding these limits returns an error."
    ),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control"}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "qc_target"}},
    },
    expected={
        "use_powder_dispenser": True,
        "source_well": "source_plate.A1", "target_well": "assay_plate.B1",
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "powder_name": "reagent_a", "amount_mg": 50.0,
        "control_band": {"min": 0.75, "max": 0.9},
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)


# Multi-well powder dispense — same powder to multiple wells
POWDER_MULTI_DISPENSE_QC = TaskSpec(
    scenario="powder_multi_dispense_qc",
    objective="Dispense powder to multiple wells in parallel, then add liquid.",
    prompt=(
        "A powder dispenser is available. Dispense reagent_b to three wells "
        "in parallel:\n\n"
        "== Multi-well dispensing ==\n"
        "1. powder_dispense_multi(powder_name='reagent_b', amount_mg=25.0, "
        "   target_wells=['assay_plate:A1','assay_plate:A2','assay_plate:A3']) "
        "   — dispense 25 mg to each of 3 wells (75 mg total).\n\n"
        "== Liquid addition ==\n"
        "2. Transfer 50 uL from source_plate.A1 to assay_plate.B1 using "
        "the liquid handler.\n"
        "3. Read OD600 for assay_plate B1 at 600 nm. Submit against [0.75, 0.9].\n\n"
        "KEY DISTINCTION: Use powder_dispense_multi (not single dispense) for "
        "multiple wells — this is more efficient. The total amount (75 mg) "
        "should not exceed the 5000 mg limit."
    ),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control"}},
        "assay_plate": {"A1": {"contents": "powder_target"},
                        "A2": {"contents": "powder_target"},
                        "A3": {"contents": "powder_target"},
                        "B1": {"contents": "empty", "purpose": "qc_target"}},
    },
    expected={
        "use_powder_dispenser": True,
        "source_well": "source_plate.A1", "target_well": "assay_plate.B1",
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "powder_name": "reagent_b", "amount_per_well_mg": 25.0,
        "require_multi": True,
        "control_band": {"min": 0.75, "max": 0.9},
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)


# Powder amount validation — agent must handle invalid amounts
POWDER_AMOUNT_VALIDATE_QC = TaskSpec(
    scenario="powder_amount_validate_qc",
    objective="Validate powder dispense amounts: reject zero, reject excessive, accept valid.",
    prompt=(
        "A powder dispenser is available. You must dispense reagent_c at the "
        "correct amount:\n\n"
        "1. You need 100 mg of reagent_c. First, check: is 100 mg a valid amount? "
        "(Valid range: 0 < amount ≤ 1000 mg per dispense.)\n"
        "2. powder_dispense(powder_name='reagent_c', amount_mg=100.0, "
        "   target_well='assay_plate:B1').\n"
        "3. If you attempt amount_mg=0 or amount_mg=1500, the dispenser will "
        "return an error. Always validate your amounts before dispensing.\n\n"
        "== Liquid addition ==\n"
        "4. Transfer 50 uL from source_plate.A1 to assay_plate.B1.\n"
        "5. Read OD600 for assay_plate B1 at 600 nm. Submit against [0.75, 0.9].\n\n"
        "KEY TEST: The agent must select a valid amount (100 mg is valid). "
        "Attempting 0 mg (invalid_amount) or 1500 mg (amount_too_large) are "
        "agent_errors."
    ),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control"}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "qc_target"}},
    },
    expected={
        "use_powder_dispenser": True,
        "source_well": "source_plate.A1", "target_well": "assay_plate.B1",
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "powder_name": "reagent_c", "amount_mg": 100.0,
        "control_band": {"min": 0.75, "max": 0.9},
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)


# ── NEW: Barcode scanner scenarios ──────────────────────────────────


# Basic barcode scan — verify plate identity before transfer
BARCODE_SCAN_QC = TaskSpec(
    scenario="barcode_scan_qc",
    objective="Scan a plate barcode to verify identity before starting the protocol.",
    prompt=(
        "A barcode scanner is available for plate identity verification. "
        "Before starting the transfer, scan the assay_plate to confirm its identity:\n\n"
        "== Barcode scan ==\n"
        "1. barcode_scan — scan the barcode of the assay_plate. "
        "   The scanner returns 'PLATE-001' in dry-run mode.\n"
        "2. Verify the barcode matches the expected identity and "
        "   add a workflow note with the scanned barcode.\n\n"
        "== Transfer ==\n"
        "3. Transfer 50 uL from source_plate.A1 to assay_plate.B1.\n"
        "4. Read OD600 for assay_plate B1 at 600 nm. Submit against [0.75, 0.9].\n\n"
        "IMPORTANT: Scanning must happen BEFORE the transfer — you need to "
        "confirm you're working with the correct plate."
    ),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control"}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "qc_target"}},
    },
    expected={
        "use_barcode_scanner": True,
        "source_well": "source_plate.A1", "target_well": "assay_plate.B1",
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "require_scan_before_transfer": True,
        "control_band": {"min": 0.75, "max": 0.9},
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)


# Multi-scan — scan multiple plates to verify identities
BARCODE_MULTI_SCAN_QC = TaskSpec(
    scenario="barcode_multi_scan_qc",
    objective="Scan barcodes on both source and assay plates to verify identities.",
    prompt=(
        "A barcode scanner is available. Scan both plates before proceeding:\n\n"
        "1. barcode_scan — scan the assay_plate (returns 'PLATE-001').\n"
        "2. barcode_scan — scan the source_plate (also returns 'PLATE-001').\n"
        "   Note: In dry-run mode, both scans return the same value. Record "
        "   both scan results for traceability.\n"
        "3. Verify both plates have been identified before proceeding.\n\n"
        "== Transfer ==\n"
        "4. Transfer 50 uL from source_plate.A1 to assay_plate.B1.\n"
        "5. Read OD600 for assay_plate B1 at 600 nm. Submit against [0.75, 0.9].\n\n"
        "KEY TEST: Both plates must be scanned. The scan count should show "
        "at least 2 scans. Single-scan protocols risk working with the "
        "wrong source plate."
    ),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control"}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "qc_target"}},
    },
    expected={
        "use_barcode_scanner": True,
        "source_well": "source_plate.A1", "target_well": "assay_plate.B1",
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "require_multi_scan": True,
        "control_band": {"min": 0.75, "max": 0.9},
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)


# Scan verification — scan, verify, and handle scan failure
BARCODE_VERIFY_QC = TaskSpec(
    scenario="barcode_verify_qc",
    objective="Scan barcode and verify it matches the expected plate identity before proceeding.",
    prompt=(
        "A barcode scanner is available. The assay_plate should have barcode "
        "'PLATE-001'. You must verify this:\n\n"
        "1. barcode_scan — scan the assay_plate.\n"
        "2. Check the returned barcode. In dry-run mode, it will be 'PLATE-001' "
        "   which matches expectations.\n"
        "3. If the barcode matches, proceed. If not, the plate may be wrong "
        "   — flag the issue in a workflow note and halt.\n"
        "4. Only if the scan matches, proceed to transfer.\n\n"
        "== Transfer (only if verified) ==\n"
        "5. Transfer 50 uL from source_plate.A1 to assay_plate.B1.\n"
        "6. Read OD600 for assay_plate B1 at 600 nm. Submit against [0.75, 0.9].\n\n"
        "KEY TEST: The agent must CHECK the barcode value and only proceed "
        "if it matches 'PLATE-001'. Blindly proceeding without checking the "
        "scan result defeats the purpose of identity verification."
    ),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control"}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "qc_target"}},
    },
    expected={
        "use_barcode_scanner": True,
        "source_well": "source_plate.A1", "target_well": "assay_plate.B1",
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "require_scan_verify": True,
        "control_band": {"min": 0.75, "max": 0.9},
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)


# ═══════════════════════════════════════════════════════════════════════════
# Cross-validation (xover) scenarios
# ═══════════════════════════════════════════════════════════════════════════

ARM_READER_XOVER_QC = TaskSpec(
    scenario="arm_reader_xover_qc",
    objective="Deep integration: arm + reader with cross-validation at every critical waypoint.",
    prompt=(
        "A robot arm and a plate reader are available. You must move the "
        "assay_plate from carrier to reader and back, verifying arm position "
        "and gripper state at EVERY critical waypoint.\n\n"
        "== Phase 1: Load plate into reader (with cross-checks) ==\n"
        "1.  arm_home\n"
        "2.  arm_get_position — verify at home (0, 0, ~150).\n"
        "3.  arm_get_gripper_state — verify gripper is open (safe start).\n"
        "4.  arm_open_gripper(width_mm=80.0)\n"
        "5.  arm_get_gripper_state — confirm open.\n"
        "6.  arm_move_to(x=100, y=200, z=100) — move above carrier.\n"
        "7.  arm_get_position — verify you are at carrier pick-up position.\n"
        "8.  arm_approach(x=100, y=200, z=30, access='vertical')\n"
        "9.  arm_close_gripper(width_mm=85.0)\n"
        "10. arm_get_gripper_state — MUST be closed before pickup!\n"
        "11. arm_pick_up_resource(x=100, y=200, z=30, plate_width_mm=85.0)\n"
        "12. arm_get_position — verify you have lifted the plate.\n"
        "13. arm_move_to(x=300, y=100, z=100) — transport to reader.\n"
        "14. arm_get_position — verify at reader area.\n"
        "15. arm_approach(x=300, y=100, z=30, access='vertical')\n"
        "16. arm_drop_resource(x=300, y=100, z=30)\n"
        "17. get_deck_state — verify plate is now at reader area.\n"
        "18. arm_move_to_safe\n"
        "19. arm_get_position — verify arm is safe (away from reader).\n\n"
        "== Phase 2: Read plate ==\n"
        "20. plate_reader_open\n"
        "21. get_labware_state(labware_id='assay_plate') — verify plate IS in reader!\n"
        "22. read_absorbance(assay_plate, 600nm, B1)\n"
        "23. plate_reader_close\n\n"
        "== Phase 3: Retrieve plate (with cross-checks) ==\n"
        "24. arm_get_position — confirm arm is still safe before returning.\n"
        "25. arm_move_to(x=300, y=100, z=100)\n"
        "26. arm_get_position — verify at reader pick-up position.\n"
        "27. arm_approach(x=300, y=100, z=30, access='vertical')\n"
        "28. arm_close_gripper(width_mm=85.0)\n"
        "29. arm_get_gripper_state — MUST be closed before picking up!\n"
        "30. arm_pick_up_resource(x=300, y=100, z=30, plate_width_mm=85.0)\n"
        "31. arm_get_position — verify you have picked the plate.\n"
        "32. arm_move_to(x=100, y=200, z=100) — return to carrier.\n"
        "33. arm_get_position — verify at carrier drop-off position.\n"
        "34. arm_approach(x=100, y=200, z=30)\n"
        "35. arm_drop_resource(x=100, y=200, z=30)\n"
        "36. get_deck_state — verify plate is back at carrier.\n"
        "37. arm_move_to_safe\n"
        "38. arm_get_position — verify arm is safe.\n"
        "39. arm_get_gripper_state — verify gripper is open (plate released).\n\n"
        "== Decision ==\n"
        "40. Submit against control band [0.75, 0.9].\n\n"
        "CRITICAL: Every arm movement MUST be bracketed by position checks. "
        "Every grip operation MUST be bracketed by gripper_state checks."
    ),
    initial_volumes={"assay_plate.B1": 50.0},
    well_metadata={"assay_plate": {"B1": {"contents": "pre_loaded_sample", "volume_ul": 50}}},
    expected={
        "use_arm": True,
        "target_well": "assay_plate.B1", "wavelength_nm": 600,
        "require_position_checks_ge": 8,
        "require_gripper_checks_ge": 5,
        "require_deck_rechecks": True,
        "require_labware_check_in_reader": True,
        "control_band": {"min": 0.75, "max": 0.9},
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)

CENTRIFUGE_SCALE_XOVER_QC = TaskSpec(
    scenario="centrifuge_scale_xover_qc",
    objective="Deep integration: spin down sample with cross-validation, then gravimetric QC.",
    prompt=(
        "A centrifuge and an analytical balance are available. You must "
        "spin down a sample with thorough cross-validation:\n\n"
        "== Phase 1: Transfer ==\n"
        "1. Transfer 50 uL from source_plate.A1 to assay_plate.B1.\n\n"
        "== Phase 2: Centrifuge with verification ==\n"
        "2. get_labware_state(labware_id='assay_plate') — verify before spin.\n"
        "3. centrifuge_go_to_bucket1 → centrifuge_lock_bucket\n"
        "4. centrifuge_close_door → centrifuge_lock_door\n"
        "5. centrifuge_spin(g_force=2000, duration_s=60)\n"
        "6. centrifuge_open_door\n"
        "7. get_labware_state(labware_id='assay_plate') — verify after spin.\n\n"
        "== Phase 3: Gravimetric QC ==\n"
        "8. scale_zero — session calibration.\n"
        "9. scale_tare — container tare.\n"
        "10. scale_get_weight — first reading.\n"
        "11. scale_get_weight — second reading (verify stability).\n"
        "12. scale_get_weight — third reading for cross-validation.\n\n"
        "== Phase 4: Cross-check ==\n"
        "13. Read OD600 for assay_plate B1 at 600 nm. Submit against [0.75, 0.9].\n\n"
        "CROSS-VALIDATION: Labware MUST be inspected before AND after spin. "
        "Scale MUST take >=3 readings. If drift > 0.01g, re-tare and retry."
    ),
    initial_volumes={"source_plate.A1": 120.0},
    well_metadata={
        "source_plate": {"A1": {"contents": "qc_control"}},
        "assay_plate": {"B1": {"contents": "empty", "purpose": "qc_target"}},
    },
    expected={
        "use_centrifuge": True, "use_scale": True,
        "source_well": "source_plate.A1", "target_well": "assay_plate.B1",
        "transfer_volume_ul": 50, "wavelength_nm": 600,
        "g_force": 2000, "duration_s": 60,
        "require_labware_before_after_spin": True,
        "require_weight_readings_ge": 3,
        "require_zero_and_tare": True,
        "control_band": {"min": 0.75, "max": 0.9},
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)

SEALER_PEELER_XOVER_QC = TaskSpec(
    scenario="sealer_peeler_xover_qc",
    objective="Deep integration: heat-seal a plate then peel it, with the peeler "
              "cross-validating the sealer's seal integrity at every handoff.",
    prompt=(
        "A Plate Sealer and a Plate Peeler are available. You must seal a plate, "
        "independently verify the seal with the peeler, then peel and verify removal. "
        "The peeler is the CROSS-VALIDATOR for the sealer's work.\n\n"
        "== Phase 1: Pre-seal preparation (verify sealer state) ==\n"
        "1.  sealer_get_temperature — check ambient starting temperature.\n"
        "2.  sealer_open — open door to accept the plate.\n"
        "3.  sealer_set_temperature(temperature=170.0) — set target sealing temp.\n"
        "4.  sealer_get_temperature — CROSS-CHECK: is the sealer ramping toward 170?C?\n"
        "5.  sealer_close — safety: door MUST be closed before sealing.\n\n"
        "== Phase 2: Seal execution (with temperature verification) ==\n"
        "6.  sealer_get_temperature — final temp check before sealing (should be ~170?C).\n"
        "7.  sealer_seal(temperature=170, duration_s=3.0) — execute the seal.\n"
        "8.  sealer_get_temperature — verify temperature maintained through seal.\n"
        "9.  get_labware_state(labware_id='assay_plate') — inspect plate after sealing.\n\n"
        "== Phase 3: Handoff to Peeler (cross-instrument seal validation) ==\n"
        "10. peeler_get_status — query peeler initial state.\n"
        "11. peeler_get_tape_remaining — verify tape supply before starting.\n"
        "12. peeler_move_conveyor_in — load the sealed plate into peeler.\n"
        "13. peeler_seal_check — CROSS-VALIDATE: does the peeler independently "
        "    confirm that the sealer's seal IS present? (expect: seal_detected).\n"
        "14. peeler_move_elevator_up — raise plate to peel position.\n\n"
        "== Phase 4: Peel execution (with removal verification) ==\n"
        "15. peeler_advance_tape — advance fresh tape for clean peel.\n"
        "16. peeler_peel(begin_location=0, fast=false, adhere_time=2.5) — peel the seal.\n"
        "17. peeler_seal_check — CROSS-VALIDATE: is the seal now REMOVED?\n"
        "    (expect: no_seal). This is the critical cross-check!\n"
        "18. peeler_get_tape_remaining — verify tape was consumed by peel.\n\n"
        "== Phase 5: Final verification and readout ==\n"
        "19. peeler_move_elevator_down — lower plate back.\n"
        "20. peeler_move_conveyor_out — unload plate.\n"
        "21. peeler_get_status — final peeler status check.\n"
        "22. get_labware_state(labware_id='assay_plate') — final plate inspection.\n"
        "23. read_absorbance(assay_plate, 600nm, B1).\n"
        "24. Submit against control band [0.75, 0.9].\n\n"
        "CROSS-VALIDATION RULES:\n"
        "- The peeler's seal_check MUST independently confirm the sealer's work (seal_detected).\n"
        "- After peeling, seal_check MUST confirm removal (no_seal).\n"
        "- Temperature MUST be checked BEFORE and AFTER the seal operation.\n"
        "- Tape remaining MUST be checked BEFORE and AFTER the peel.\n"
        "- Labware MUST be inspected both BEFORE sealing (via sealer) and AFTER peeling."
    ),
    initial_volumes={"assay_plate.B1": 50.0},
    well_metadata={"assay_plate": {"B1": {"contents": "heat_sensitive_sample", "volume_ul": 50}}},
    expected={
        "use_sealer": True, "use_peeler": True,
        "target_well": "assay_plate.B1", "wavelength_nm": 600,
        "seal_temp": 170.0, "seal_duration_s": 3.0,
        "require_seal_temp_reads_ge": 3,
        "require_seal_check_before_peel": True,
        "require_seal_check_after_peel": True,
        "require_tape_before_after": True,
        "require_labware_before_after_protocol": True,
        "control_band": {"min": 0.75, "max": 0.9},
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)

POWDER_SCALE_XOVER_QC = TaskSpec(
    scenario="powder_scale_xover_qc",
    objective="Deep integration: dispense powder into wells with the scale independently "
              "verifying every dispense by weight — solid-handling cross-validation.",
    prompt=(
        "A Powder Dispenser and an Analytical Balance are available. You must dispense "
        "powder into assay plate wells, with the SCALE independently cross-validating "
        "every dispense by weight. This is GRAVIMETRIC CROSS-VALIDATION of solid handling.\n\n"
        "== Phase 1: Scale calibration ==\n"
        "1.  scale_zero — set absolute zero reference for the session.\n"
        "2.  scale_get_weight — verify zero (should read ~0.000 g).\n"
        "3.  scale_tare — tare with empty container on scale.\n"
        "4.  scale_get_weight — verify tare (should read ~0.000 g after tare).\n\n"
        "== Phase 2: Single dispense #1 — 50 mg (with weight cross-validation) ==\n"
        "5.  powder_dispense(powder_name='reagent_a', amount_mg=50.0, target_well='assay_plate:B1')\n"
        "6.  scale_get_weight — CROSS-VALIDATE reading #1: expect ~50 mg increase.\n"
        "7.  scale_get_weight — CROSS-VALIDATE reading #2: stability check (drift < 0.005 g).\n"
        "8.  scale_get_weight — CROSS-VALIDATE reading #3: third confirmation.\n\n"
        "== Phase 3: Single dispense #2 — 30 mg (cumulative verification) ==\n"
        "9.  powder_dispense(powder_name='reagent_a', amount_mg=30.0, target_well='assay_plate:B2')\n"
        "10. scale_get_weight — cumulative should be ~80 mg (50+30).\n"
        "11. scale_get_weight — stability check.\n\n"
        "== Phase 4: Multi-well dispense — 2×25 mg (cumulative + batch verification) ==\n"
        "12. powder_dispense_multi(powder_name='reagent_a', amount_mg=25.0, "
        "    target_wells=['assay_plate:B3', 'assay_plate:C1'])\n"
        "13. scale_get_weight — cumulative should be ~130 mg (50+30+25+25).\n"
        "14. scale_get_weight — stability check (final weight confirmation).\n\n"
        "== Phase 5: Final verification ==\n"
        "15. get_labware_state(labware_id='assay_plate') — verify all 4 wells received powder.\n"
        "16. read_absorbance(assay_plate, 600nm, B1).\n"
        "17. Submit against control band [0.75, 0.9].\n\n"
        "CROSS-VALIDATION RULES:\n"
        "- EVERY powder dispense MUST be followed by at least 2 scale weight readings.\n"
        "- Cumulative weight MUST be tracked: each reading should increase from the last.\n"
        "- Weight MUST be stable across consecutive readings (drift < 0.005 g).\n"
        "- Scale MUST be zeroed at session start AND tared before the first dispense.\n"
        "- Total weight readings >= 8 across the entire protocol."
    ),
    initial_volumes={"assay_plate.B1": 0.0, "assay_plate.B2": 0.0,
                     "assay_plate.B3": 0.0, "assay_plate.C1": 0.0},
    well_metadata={
        "assay_plate": {
            "B1": {"contents": "empty_well", "volume_ul": 0},
            "B2": {"contents": "empty_well", "volume_ul": 0},
            "B3": {"contents": "empty_well", "volume_ul": 0},
            "C1": {"contents": "empty_well", "volume_ul": 0},
        },
    },
    expected={
        "use_powder_dispenser": True, "use_scale": True,
        "target_well": "assay_plate.B1", "wavelength_nm": 600,
        "powder_name": "reagent_a",
        "dispense_amounts_mg": [50.0, 30.0, 25.0],
        "total_target_mg": 130.0,
        "require_zero_and_tare": True,
        "require_weight_readings_ge": 8,
        "require_weight_after_each_dispense": True,
        "require_weight_stability": True,
        "require_cumulative_increasing": True,
        "control_band": {"min": 0.75, "max": 0.9},
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)

TILTER_PUMP_XOVER_QC = TaskSpec(
    scenario="tilter_pump_xover_qc",
    objective="Deep integration: tilt plate for phase separation, then pump to remove "
              "supernatant — angle verification cross-validated against pump action.",
    prompt=(
        "A Plate Tilter and a Peristaltic Pump are available. You must perform "
        "a phase-separation workflow: tilt the plate to separate liquid phases, "
        "then pump out the supernatant. Cross-validate angle at EVERY step.\n\n"
        "== Phase 1: Initial state inspection ==\n"
        "1.  tilter_get_angle — verify tilter is at 0? (level) before starting.\n"
        "2.  get_labware_state(labware_id='assay_plate') — inspect plate BEFORE processing.\n\n"
        "== Phase 2: Gradual tilt for phase separation (verify angle at EACH step) ==\n"
        "3.  tilter_set_angle(angle=15.0) — gentle tilt to initiate separation.\n"
        "4.  tilter_get_angle — CROSS-CHECK: is the tilter actually at 15? ?\n"
        "5.  tilter_tilt(relative_angle=15.0) — increase to 30? for full separation.\n"
        "6.  tilter_get_angle — CROSS-CHECK: is the tilter now at ~30? ?\n"
        "7.  tilter_get_angle — stability check: confirm angle holding (no drift).\n\n"
        "== Phase 3: Pump supernatant removal (cross-validate pump action) ==\n"
        "8.  pump_run_duration(speed_rpm=100, duration_s=5.0) — remove bulk supernatant.\n"
        "9.  pump_run_volume(speed_rpm=80, volume_ul=500.0) — calibrated fine removal.\n"
        "10. pump_halt — safety: stop pump before changing plate orientation.\n\n"
        "== Phase 4: Return to level (with angle re-verification) ==\n"
        "11. tilter_return_to_level — return plate to 0? (flat).\n"
        "12. tilter_get_angle — CROSS-CHECK: verify tilter is back at 0? ?\n"
        "13. tilter_get_angle — second reading: confirm stable at level.\n\n"
        "== Phase 5: Final verification ==\n"
        "14. get_labware_state(labware_id='assay_plate') — final inspection after processing.\n"
        "15. read_absorbance(assay_plate, 600nm, B1).\n"
        "16. Submit against control band [0.75, 0.9].\n\n"
        "CROSS-VALIDATION RULES:\n"
        "- EVERY tilter angle change (set_angle, tilt, return_to_level) MUST be "
        "  followed by at least one get_angle readback.\n"
        "- Tilter angle MUST be at 0? before starting AND after finishing.\n"
        "- Pump MUST be halted BEFORE returning the tilter to level (safety interlock).\n"
        "- Labware MUST be inspected BOTH before and after the tilt+pump protocol.\n"
        "- Angle readings at each step should be stable (no drift > 2? on consecutive reads)."
    ),
    initial_volumes={"assay_plate.B1": 200.0},
    well_metadata={"assay_plate": {"B1": {"contents": "two_phase_mixture", "volume_ul": 200}}},
    expected={
        "use_tilter": True, "use_pump": True,
        "target_well": "assay_plate.B1", "wavelength_nm": 600,
        "tilt_angles": [15.0, 30.0],
        "pump_speeds": [100, 80],
        "require_angle_reads_ge": 5,
        "require_angle_after_each_change": True,
        "require_pump_halt_before_level": True,
        "require_initial_final_level": True,
        "require_labware_before_after_protocol": True,
        "control_band": {"min": 0.75, "max": 0.9},
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)

BARCODE_STORAGE_XOVER_QC = TaskSpec(
    scenario="barcode_storage_xover_qc",
    objective="Deep integration: scan plate identity, store in incubator with environmental "
              "monitoring, retrieve, then re-scan to cross-validate identity — identity-based QC.",
    prompt=(
        "A Barcode Scanner and an Incubator Storage module are available. You must "
        "scan a plate's identity, store it under controlled conditions, retrieve it, "
        "and re-scan to CROSS-VALIDATE that the same plate was retrieved. This is "
        "IDENTITY-BASED cross-validation — no physical transformation is needed.\n\n"
        "== Phase 1: Initial identity and storage inspection ==\n"
        "1.  barcode_scan — establish the plate's identity (record the barcode string).\n"
        "2.  storage_get_free_sites — verify storage has space available.\n"
        "3.  storage_get_temperature — check current storage temperature.\n"
        "4.  get_labware_state(labware_id='assay_plate') — inspect plate BEFORE storage.\n\n"
        "== Phase 2: Store plate with environmental monitoring ==\n"
        "5.  storage_open_door — open incubator door.\n"
        "6.  storage_store_plate(plate_id='assay_plate', site=1) — store the plate.\n"
        "7.  storage_close_door — close incubator door.\n"
        "8.  storage_set_temperature(temperature=37.0) — set incubation temperature.\n"
        "9.  storage_get_temperature — CROSS-CHECK: is storage at 37?C?\n"
        "10. storage_get_temperature — stability check: is temperature holding?\n\n"
        "== Phase 3: Retrieve plate ==\n"
        "11. storage_open_door\n"
        "12. storage_retrieve_plate(plate_id='assay_plate', site=1) — retrieve the plate.\n"
        "13. storage_close_door\n"
        "14. storage_get_temperature — verify temperature maintained during retrieval.\n\n"
        "== Phase 4: Identity cross-validation (CRITICAL) ==\n"
        "15. barcode_scan — CROSS-VALIDATE: does the scanned barcode match the "
        "    initial scan?  This proves you retrieved the CORRECT plate!\n"
        "16. get_labware_state(labware_id='assay_plate') — verify plate condition after storage.\n\n"
        "== Phase 5: Readout ==\n"
        "17. read_absorbance(assay_plate, 600nm, B1).\n"
        "18. Submit against control band [0.75, 0.9].\n\n"
        "CROSS-VALIDATION RULES:\n"
        "- Barcode MUST be scanned BOTH before storage AND after retrieval.\n"
        "- The two barcode scans MUST return the SAME identity string.\n"
        "- Storage temperature MUST be checked >=3 times (initial, set-verify, stability).\n"
        "- Free sites MUST be checked BEFORE attempting to store.\n"
        "- Labware MUST be inspected BOTH before storage AND after retrieval.\n"
        "- Door MUST be closed after every open (2 open+close cycles expected)."
    ),
    initial_volumes={"assay_plate.B1": 50.0},
    well_metadata={"assay_plate": {"B1": {"contents": "cell_culture_sample", "volume_ul": 50}}},
    expected={
        "use_barcode_scanner": True, "use_storage": True,
        "target_well": "assay_plate.B1", "wavelength_nm": 600,
        "storage_temp": 37.0,
        "require_barcode_scans_ge": 2,
        "require_barcode_identity_match": True,
        "require_storage_temp_reads_ge": 3,
        "require_free_sites_check": True,
        "require_door_open_close_cycles": 2,
        "require_labware_before_after_storage": True,
        "control_band": {"min": 0.75, "max": 0.9},
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)

SHAKER_READER_XOVER_QC = TaskSpec(
    scenario="shaker_reader_xover_qc",
    objective="Deep integration: shake plate to mix, then verify mixing quality optically "
              "with pre- and post-shake absorbance readings — vibration-domain cross-validation.",
    prompt=(
        "A Dedicated Plate Shaker and a Plate Reader are available. You must shake "
        "a plate to mix its contents, then optically verify mixing quality by "
        "comparing absorbance BEFORE and AFTER shaking. The reader is the CROSS-VALIDATOR "
        "for the shaker's work.\n\n"
        "== Phase 1: Baseline optical readings BEFORE shaking ==\n"
        "1.  get_labware_state(labware_id='assay_plate') — inspect plate before mixing.\n"
        "2.  plate_reader_open — open the reader for access.\n"
        "3.  read_absorbance(assay_plate, 600nm, B1) — BASELINE reading #1 (target well).\n"
        "4.  read_absorbance(assay_plate, 600nm, B2) — BASELINE reading #2 (adjacent well "
        "    for pre-shake homogeneity comparison).\n\n"
        "== Phase 2: Shake with safety interlocks ==\n"
        "5.  shaker_lock_plate — SAFETY: lock plate BEFORE shaking.\n"
        "6.  shaker_shake(speed=500, duration_s=30) — moderate shaking to distribute.\n"
        "7.  shaker_shake(speed=800, duration_s=15) — high-speed shake for fine mixing.\n"
        "8.  shaker_stop_shaking — stop the shaker.\n"
        "9.  shaker_unlock_plate — SAFETY: unlock AFTER shaking has stopped.\n\n"
        "== Phase 3: Post-shake optical cross-validation ==\n"
        "10. read_absorbance(assay_plate, 600nm, B1) — POST-SHAKE reading #1: absorbance "
        "    should have changed if mixing occurred.\n"
        "11. read_absorbance(assay_plate, 600nm, B2) — POST-SHAKE reading #2: compare to B1 "
        "    for homogeneity — well-mixed samples should show consistent readings!\n"
        "12. get_labware_state(labware_id='assay_plate') — final inspection after mixing.\n"
        "13. plate_reader_close — close the reader.\n\n"
        "== Phase 4: Submit ==\n"
        "14. Submit against control band [0.75, 0.9].\n\n"
        "CROSS-VALIDATION RULES:\n"
        "- Absorbance MUST be read BOTH before AND after shaking (>=4 total readings).\n"
        "- Baseline readings MUST precede shaking; post-shake readings MUST follow shaking.\n"
        "- Plate MUST be locked before shaking and unlocked only after stop.\n"
        "- Two different shake speeds MUST be used (multi-step mixing protocol).\n"
        "- BOTH B1 and B2 must be read for homogeneity cross-validation."
    ),
    initial_volumes={"assay_plate.B1": 100.0, "assay_plate.B2": 100.0},
    well_metadata={
        "assay_plate": {
            "B1": {"contents": "unmixed_suspension", "volume_ul": 100},
            "B2": {"contents": "unmixed_suspension", "volume_ul": 100},
        },
    },
    expected={
        "use_shaker": True,
        "target_well": "assay_plate.B1", "wavelength_nm": 600,
        "shake_speeds": [500, 800],
        "require_absorbance_reads_ge": 4,
        "require_baseline_before_shake": True,
        "require_postshake_after_shake": True,
        "require_lock_before_shake": True,
        "require_unlock_after_stop": True,
        "control_band": {"min": 0.75, "max": 0.9},
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)

HS_THERMOCYCLER_XOVER_QC = TaskSpec(
    scenario="hs_thermocycler_xover_qc",
    objective="Deep integration: pre-incubation in HeaterShaker then PCR in Thermocycler, "
              "with temperature cross-validation at every thermal transition.",
    prompt=(
        "A HeaterShaker and a Thermocycler are available. You must perform a "
        "two-stage thermal protocol with cross-validation at EVERY thermal transition.\n\n"
        "== Phase 1: Pre-incubation in HeaterShaker (with temp verification) ==\n"
        "1.  hs_set_temperature(temperature=37.0) — set incubation temperature.\n"
        "2.  hs_get_temperature — verify setpoint reached (should read ~37C).\n"
        "3.  hs_shake(speed=300, duration_s=30) — start shaking incubation.\n"
        "4.  hs_get_temperature — verify temperature maintained DURING shaking.\n"
        "5.  hs_stop_shaking — end shaking phase.\n"
        "6.  hs_get_temperature — verify temperature stable after shake stop.\n"
        "7.  hs_deactivate — shut down HeaterShaker.\n"
        "8.  hs_get_temperature — verify ambient cooling (should drop toward RT).\n\n"
        "== Phase 2: Transition to Thermocycler (verify before PCR) ==\n"
        "9.  get_labware_state(labware_id='assay_plate') — inspect plate BEFORE PCR.\n"
        "10. tc_close_lid — safety: lid MUST be closed before heating.\n"
        "11. tc_set_lid_temp(temperature=105.0) — set heated lid.\n"
        "12. tc_get_block_temp — verify current block state before ramp.\n"
        "13. tc_set_block_temp(temperature=95.0) — denaturation step.\n"
        "14. tc_get_block_temp — CROSS-CHECK: is block at 95C?\n\n"
        "== Phase 3: Thermal cycling (verify at EACH step) ==\n"
        "15. tc_set_block_temp(temperature=55.0) — annealing step.\n"
        "16. tc_get_block_temp — CROSS-CHECK: is block at 55C?\n"
        "17. tc_set_block_temp(temperature=72.0) — extension step.\n"
        "18. tc_get_block_temp — CROSS-CHECK: is block at 72C?\n"
        "19. tc_deactivate — end thermal cycling.\n\n"
        "== Phase 4: Final verification and readout ==\n"
        "20. tc_open_lid — safety: lid open before plate access.\n"
        "21. get_labware_state(labware_id='assay_plate') — final plate check.\n"
        "22. read_absorbance(assay_plate, 600nm, B1).\n"
        "23. Submit against control band [0.75, 0.9].\n\n"
        "CROSS-VALIDATION RULES:\n"
        "- HeaterShaker MUST be fully deactivated BEFORE Thermocycler starts heating.\n"
        "- EVERY block temperature change MUST be verified with a get_block_temp readback.\n"
        "- Temperature readings must be taken at >=6 distinct points across both instruments.\n"
        "- Labware MUST be inspected both BEFORE and AFTER the thermal protocol."
    ),
    initial_volumes={"assay_plate.B1": 50.0},
    well_metadata={"assay_plate": {"B1": {"contents": "pcr_mix", "volume_ul": 50}}},
    expected={
        "use_heater_shaker": True, "use_thermocycler": True,
        "target_well": "assay_plate.B1", "wavelength_nm": 600,
        "hs_target_temp": 37.0, "hs_shake_speed": 300,
        "tc_lid_temp": 105.0, "tc_denature_temp": 95.0,
        "tc_anneal_temp": 55.0, "tc_extend_temp": 72.0,
        "require_hs_temp_reads_ge": 3,
        "require_tc_temp_reads_ge": 3,
        "require_total_temp_reads_ge": 6,
        "require_hs_before_tc_ordering": True,
        "require_labware_before_after_thermal": True,
        "control_band": {"min": 0.75, "max": 0.9},
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)

ARM_STALE_STATE_COMBO_QC = TaskSpec(
    scenario="arm_stale_state_combo_qc",
    objective="After arm moves a plate, deck state is stale. Agent must re-inspect.",
    prompt=(
        "A robot arm and a plate reader are available. CRITICAL: your initial "
        "deck inspection becomes STALE after the arm moves the plate.\n\n"
        "== Phase 1: Initial inspection ==\n"
        "1. get_deck_state — inspect current deck layout.\n"
        "2. get_labware_state(labware_id='assay_plate') — check plate status.\n\n"
        "== Phase 2: Arm moves plate ==\n"
        "3. arm_home → arm_open_gripper(width_mm=80.0).\n"
        "4. arm_move_to(x=100, y=200, z=100) → arm_approach(x=100, y=200, z=30).\n"
        "5. arm_close_gripper(width_mm=85.0) → arm_pick_up_resource(x=100, y=200, z=30, plate_width_mm=85.0).\n"
        "6. arm_move_to(x=300, y=100, z=100) → arm_approach(x=300, y=100, z=30).\n"
        "7. arm_drop_resource(x=300, y=100, z=30) → arm_move_to_safe.\n\n"
        "== Phase 3: RE-INSPECT (stale-state defense) ==\n"
        "8. get_labware_state(labware_id='assay_plate') — plate was moved! "
        "   Your initial inspection is STALE. Verify plate's current location.\n"
        "9. get_deck_state — confirm deck reflects the move.\n\n"
        "== Phase 4: Read ==\n"
        "10. plate_reader_open → read_absorbance(assay_plate, 600nm, B1).\n"
        "11. Submit against [0.75, 0.9].\n\n"
        "VERIFICATION: Inspections must happen BOTH before AND after the arm move. "
        "Single early inspection = stale-state violation."
    ),
    initial_volumes={"assay_plate.B1": 50.0},
    well_metadata={"assay_plate": {"B1": {"contents": "pre_loaded_sample", "volume_ul": 50}}},
    expected={
        "use_arm": True,
        "target_well": "assay_plate.B1", "wavelength_nm": 600,
        "require_reinspect_after_move": True,
        "control_band": {"min": 0.75, "max": 0.9},
    },
    stochastic_config={"od600_noise": True, "noise_sigma": 0.03},
)


# ── Scenario registry ──────────────────────────────────────────────────

SCENARIOS: dict[str, ScenarioBuilder] = {}
for _name in list(locals().keys()):
    _val = locals()[_name]
    if isinstance(_val, TaskSpec):
        SCENARIOS[_val.scenario] = _make_builder(_val)

# Clean up intermediate names
del _name, _val
