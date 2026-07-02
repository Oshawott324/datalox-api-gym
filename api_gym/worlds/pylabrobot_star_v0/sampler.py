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
    create_plate_carrier, create_tip_carrier,
    setup_star_deck,
    register_state, get_well, set_well_volume,
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

    setup_star_deck(lh, plate_carrier, tip_carrier,
                    assay_plate, source_plate, tip_rack, trough)

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
        deck=deck, liquid_handler=lh,
        plate=assay_plate, source_plate=source_plate, tip_rack=tip_rack,
        trough=trough,
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


# ── Scenario registry ──────────────────────────────────────────────────

SCENARIOS: dict[str, ScenarioBuilder] = {}
for _name in list(locals().keys()):
    _val = locals()[_name]
    if isinstance(_val, TaskSpec):
        SCENARIOS[_val.scenario] = _make_builder(_val)

# Clean up intermediate names
del _name, _val
