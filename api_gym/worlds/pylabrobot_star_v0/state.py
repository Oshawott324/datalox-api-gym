"""Hamilton STAR-backed lab state for pylabrobot_star_v0.

Uses PyLabRobot's STARChatterboxBackend to simulate a full STAR(let) deck
with 8-channel pipetting, optional 96-head and iSWAP arm.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ── Reuse LabClock from OT-2 world ──────────────────────────────────────
from api_gym.worlds.pylabrobot_lab_v0.state import LabClock

# ── File names ──────────────────────────────────────────────────────────
STATE_JSON_NAME = "lab_state.json"
RUN_METADATA_NAME = "run.json"
TASK_NAME = "task.json"


def resolve_state_path(run_dir: Path) -> Path:
    run_dir = run_dir.resolve()
    path = run_dir / STATE_JSON_NAME
    if not path.exists():
        raise FileNotFoundError(f"Missing {STATE_JSON_NAME} in run directory: {run_dir}")
    return path


resolve_state_db_path = resolve_state_path


# ── LabState ────────────────────────────────────────────────────────────


@dataclass
class LabState:
    """Holds the complete STAR deck + instruments for one episode."""

    deck: Any = None
    liquid_handler: Any = None       # LiquidHandler with STAR backend
    plate: Any = None                # assay plate
    source_plate: Any = None         # source plate
    tip_rack: Any = None             # tip rack (96)
    trough: Any = None               # reagent trough (optional)
    tube_rack: Any = None            # tube rack (optional)

    # Tracking
    clock: LabClock = field(default_factory=LabClock)
    setup_done: bool = False
    tips_used: int = 0
    transfers: list[dict[str, Any]] = field(default_factory=list)
    readouts: list[dict[str, Any]] = field(default_factory=list)
    submissions: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)

    # Agent-visible metadata
    deck_info: dict[str, Any] = field(default_factory=dict)
    well_metadata: dict[str, dict[str, Any]] = field(default_factory=dict)

    # STAR-specific config
    has_96_head: bool = False
    has_iswap: bool = False

    def save(self, path: Path) -> None:
        data: dict[str, Any] = {
            "clock_time": self.clock.current_time,
            "setup_done": self.setup_done,
            "tips_used": self.tips_used,
            "transfers": self.transfers,
            "readouts": self.readouts,
            "submissions": self.submissions,
            "notes": self.notes,
            "events": self.events,
            "deck_info": self.deck_info,
            "well_metadata": self.well_metadata,
            "has_96_head": self.has_96_head,
            "has_iswap": self.has_iswap,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "LabState":
        data = json.loads(path.read_text(encoding="utf-8"))
        state = cls()
        state.clock.current_time = data.get("clock_time", 0.0)
        state.setup_done = data.get("setup_done", False)
        state.tips_used = data.get("tips_used", 0)
        state.transfers = data.get("transfers", [])
        state.readouts = data.get("readouts", [])
        state.submissions = data.get("submissions", [])
        state.notes = data.get("notes", [])
        state.events = data.get("events", [])
        state.deck_info = data.get("deck_info", {})
        state.well_metadata = data.get("well_metadata", {})
        state.has_96_head = data.get("has_96_head", False)
        state.has_iswap = data.get("has_iswap", False)
        return state

    def insert_event(self, event_type: str, object_type: str,
                     object_id: str, payload: dict[str, Any],
                     visible_to_agent: bool = True) -> None:
        self.events.append({
            "event_type": event_type,
            "object_type": object_type,
            "object_id": object_id,
            "visible_to_agent": visible_to_agent,
            "clock_time": self.clock.current_time,
            "payload": payload,
        })


# ── Global state registry ───────────────────────────────────────────────

_state_registry: dict[str, LabState] = {}


def register_state(run_dir: Path, state: LabState) -> None:
    _state_registry[str(run_dir.resolve())] = state


def get_state(run_dir: Path) -> LabState:
    key = str(run_dir.resolve())
    if key not in _state_registry:
        raise ValueError(f"No LabState registered for {run_dir}")
    return _state_registry[key]


def unregister_state(run_dir: Path) -> None:
    _state_registry.pop(str(run_dir.resolve()), None)


# ── Deck / labware factories ────────────────────────────────────────────


def create_star_deck() -> Any:
    """Create a STARLet deck (32 rails)."""
    from pylabrobot.resources.hamilton import STARLetDeck
    return STARLetDeck()


def create_liquid_handler(deck: Any, num_channels: int = 8,
                          with_96_head: bool = False,
                          with_iswap: bool = False) -> Any:
    """Create a LiquidHandler with STARChatterboxBackend."""
    from pylabrobot.liquid_handling import LiquidHandler
    from pylabrobot.liquid_handling.backends.hamilton.STAR_chatterbox import (
        STARChatterboxBackend,
    )
    backend = STARChatterboxBackend(
        num_channels=num_channels,
        core96_head_installed=with_96_head,
        iswap_installed=with_iswap,
    )
    return LiquidHandler(backend=backend, deck=deck)


def create_plate(name: str) -> Any:
    """Create a standard 96-well plate (Corning 360uL flat-bottom).

    Uses the same factory as the OT-2 world for compatibility.
    """
    # Use known-working plate factory from pylabrobot_lab_v0
    from api_gym.worlds.pylabrobot_lab_v0.state import create_plate as _cp
    return _cp(name)


def create_tip_rack(name: str, tip_volume_ul: int = 300,
                    with_tips: bool = True) -> Any:
    """Create a tip rack.

    Uses the OT-2 tip rack factory for broad compatibility.
    Hamilton-specific tip racks (hamilton_96_tiprack_300uL, etc.) can
    be used when STARChatterboxBackend is available.
    """
    from api_gym.worlds.pylabrobot_lab_v0.state import create_tip_rack as _ctr
    return _ctr(name, with_tips=with_tips)


def create_trough(name: str, volume_ml: int = 60) -> Any:
    """Create a Hamilton reagent trough."""
    from pylabrobot.resources.hamilton.troughs import (
        hamilton_1_trough_60mL_Vb,
        hamilton_1_trough_120mL_Vb,
        hamilton_1_trough_200mL_Vb,
    )
    if volume_ml <= 60:
        return hamilton_1_trough_60mL_Vb(name=name)
    elif volume_ml <= 120:
        return hamilton_1_trough_120mL_Vb(name=name)
    else:
        return hamilton_1_trough_200mL_Vb(name=name)


def create_plate_carrier(name: str) -> Any:
    """Create a 5-position plate carrier."""
    from pylabrobot.resources.hamilton import PLT_CAR_L5AC_A00
    return PLT_CAR_L5AC_A00(name=name)


def create_tip_carrier(name: str) -> Any:
    """Create a tip carrier (96 positions, standard)."""
    from pylabrobot.resources.hamilton.tip_carriers import TIP_CAR_480_A00
    return TIP_CAR_480_A00(name=name)


def setup_star_deck(lh: Any, plate_carrier: Any, tip_carrier: Any,
                    plate: Any, source_plate: Any, tip_rack: Any,
                    trough: Any = None) -> None:
    """Place carriers on the STAR deck, assign labware, and run setup."""
    from pylabrobot.resources import set_tip_tracking, set_volume_tracking
    set_tip_tracking(True)
    set_volume_tracking(True)

    deck = lh.deck

    # Place carriers at specific rails
    deck.assign_child_resource(tip_carrier, rails=1)
    deck.assign_child_resource(plate_carrier, rails=15)

    # Assign labware to carrier sites
    plate_carrier.assign_resource_to_site(source_plate, spot=0)
    plate_carrier.assign_resource_to_site(plate, spot=1)
    if trough is not None:
        plate_carrier.assign_resource_to_site(trough, spot=2)

    tip_carrier.assign_resource_to_site(tip_rack, spot=0)

    _run_async(lh.setup())


# ── Helpers (reused from OT-2 world) ────────────────────────────────────

from api_gym.worlds.pylabrobot_lab_v0.state import (
    _require_pylabrobot,
    get_well,
    get_well_volume,
    get_well_max_volume,
    set_well_volume,
    has_tip,
    tip_used_count,
    deck_summary,
)


def _run_async(coro: Any) -> Any:
    """Run an async coroutine synchronously."""
    import asyncio
    import concurrent.futures
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, coro).result()
