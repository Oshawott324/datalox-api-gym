"""PyLabRobot-backed lab state for pylabrobot_lab_v0.

Uses PyLabRobot's in-memory Deck, LiquidHandler, and Plate objects
instead of a custom SQLite schema.  The chatterbox backend simulates
all operations — no real hardware is connected.

State is serialised to JSON on disk for episode persistence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _require_pylabrobot():
    """Lazily check that PyLabRobot is installed.  Raises ImportError if not."""
    try:
        import pylabrobot  # noqa: F401
    except ImportError:
        raise ImportError(
            "PyLabRobot is required for the pylabrobot_lab_v0 world. "
            "Install it with: pip install PyLabRobot"
        )


def _plr_resources():
    """Lazy import of pylabrobot.resources."""
    _require_pylabrobot()
    import pylabrobot.resources
    return pylabrobot.resources


def _plr_coordinate():
    _require_pylabrobot()
    from pylabrobot.resources import Coordinate
    return Coordinate


def _plr_deck():
    _require_pylabrobot()
    from pylabrobot.resources import Deck
    return Deck


def _plr_liquid_handler():
    _require_pylabrobot()
    from pylabrobot.liquid_handling import LiquidHandler
    return LiquidHandler


def _plr_chatterbox_backend():
    _require_pylabrobot()
    from pylabrobot.liquid_handling.backends.chatterbox import LiquidHandlerChatterboxBackend
    return LiquidHandlerChatterboxBackend

# ── File names ──────────────────────────────────────────────────────────
STATE_JSON_NAME = "lab_state.json"
RUN_METADATA_NAME = "run.json"
TASK_NAME = "task.json"


def resolve_state_path(run_dir: Path) -> Path:
    """Resolve the lab state JSON file for a sampled run directory."""
    run_dir = run_dir.resolve()
    path = run_dir / STATE_JSON_NAME
    if not path.exists():
        raise FileNotFoundError(f"Missing {STATE_JSON_NAME} in run directory: {run_dir}")
    return path


# Alias for registry compatibility
resolve_state_db_path = resolve_state_path


# ── LabState: in-memory wrapper around PyLabRobot objects ────────────────


@dataclass
class LabState:
    """Holds the complete PyLabRobot deck + instruments for one episode.

    The objects live in memory during the episode.  save() / load()
    persist them to JSON on disk.
    """

    deck: Deck | None = None
    liquid_handler: LiquidHandler | None = None
    plate: Any = None                    # assay plate (PyLabRobot Plate)
    source_plate: Any = None             # source plate
    tip_rack: Any = None                 # tip rack

    # Tracking
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

    def save(self, path: Path) -> None:
        """Persist metadata to JSON.  PLR objects are serialised via their
        built-in serialize() method."""
        data: dict[str, Any] = {
            "setup_done": self.setup_done,
            "tips_used": self.tips_used,
            "transfers": self.transfers,
            "readouts": self.readouts,
            "submissions": self.submissions,
            "notes": self.notes,
            "events": self.events,
            "deck_info": self.deck_info,
            "well_metadata": self.well_metadata,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "LabState":
        """Load metadata from JSON and reconstruct PLR objects."""
        data = json.loads(path.read_text(encoding="utf-8"))
        state = cls()
        state.setup_done = data.get("setup_done", False)
        state.tips_used = data.get("tips_used", 0)
        state.transfers = data.get("transfers", [])
        state.readouts = data.get("readouts", [])
        state.submissions = data.get("submissions", [])
        state.notes = data.get("notes", [])
        state.events = data.get("events", [])
        state.deck_info = data.get("deck_info", {})
        state.well_metadata = data.get("well_metadata", {})
        return state

    def insert_event(self, event_type: str, object_type: str,
                     object_id: str, payload: dict[str, Any],
                     visible_to_agent: bool = True) -> None:
        self.events.append({
            "event_type": event_type,
            "object_type": object_type,
            "object_id": object_id,
            "visible_to_agent": visible_to_agent,
            "payload": payload,
        })


# ── Global state registry ────────────────────────────────────────────────

# The registry's dispatch_tool expects a Path (db_path) signature.
# For the PLR world, we store LabState objects keyed by run_dir and
# resolve them inside dispatch_tool.
_state_registry: dict[str, LabState] = {}


def register_state(run_dir: Path, state: LabState) -> None:
    """Register a LabState for a run directory."""
    _state_registry[str(run_dir.resolve())] = state


def get_state(run_dir: Path) -> LabState:
    """Look up the LabState for a run directory."""
    key = str(run_dir.resolve())
    if key not in _state_registry:
        raise ValueError(f"No LabState registered for {run_dir}")
    return _state_registry[key]


def unregister_state(run_dir: Path) -> None:
    """Remove a LabState registration."""
    key = str(run_dir.resolve())
    _state_registry.pop(key, None)


# ── Deck factory helpers ────────────────────────────────────────────────


def create_deck() -> Any:
    """Create a standard SBS-format deck."""
    Deck = _plr_deck()
    return Deck(size_x=1360.0, size_y=900.0, size_z=0.0, name="lab_deck")


def create_liquid_handler(deck: Any) -> Any:
    """Create a LiquidHandler with chatterbox simulation backend."""
    LiquidHandler = _plr_liquid_handler()
    Chatterbox = _plr_chatterbox_backend()
    return LiquidHandler(backend=Chatterbox(), deck=deck)


def create_plate(name: str) -> Any:
    """Create a standard 96-well flat-bottom plate (Corning 360 uL)."""
    resources = _plr_resources()
    return resources.Cor_96_wellplate_360ul_Fb(name=name)


def create_tip_rack(name: str, with_tips: bool = True) -> Any:
    """Create a 300 uL tip rack (Opentrons format)."""
    resources = _plr_resources()
    return resources.opentrons_96_tiprack_300ul(name=name, with_tips=with_tips)


def setup_deck(lh: Any, plate: Any, source_plate: Any,
               tip_rack: Any) -> None:
    """Place labware on the deck and run setup."""
    Coordinate = _plr_coordinate()
    deck = lh.deck
    deck.assign_child_resource(plate, location=Coordinate(100.0, 100.0, 0.0))
    deck.assign_child_resource(source_plate, location=Coordinate(300.0, 100.0, 0.0))
    deck.assign_child_resource(tip_rack, location=Coordinate(200.0, 300.0, 0.0))
    if hasattr(lh, "setup_sync"):
        lh.setup_sync()


# ── Helpers ─────────────────────────────────────────────────────────────


def get_well(plate: Any, well_name: str) -> Any:
    """Get a single well from a plate by name (e.g. 'A1').

    PyLabRobot's plate[well_name] can return a list when multiple
    wells share the same short name.  We return the first match."""
    result = plate[well_name]
    if isinstance(result, list):
        if not result:
            raise KeyError(f"Well {well_name} not found in plate {plate.name}")
        return result[0]
    return result


def get_well_volume(well: Any) -> float:
    """Get current liquid volume in a well (uL)."""
    if hasattr(well, "tracker") and well.tracker is not None:
        return float(well.tracker.get_used_volume())
    return 0.0


def get_well_max_volume(well: Any) -> float:
    """Get max capacity of a well (uL)."""
    if hasattr(well, "tracker") and well.tracker is not None:
        return float(well.tracker.max_volume)
    return 0.0


def set_well_volume(well: Any, volume_ul: float) -> None:
    """Set the liquid volume in a well (uL).  The caller is responsible
    for ensuring the volume does not exceed max_volume."""
    if hasattr(well, "tracker") and well.tracker is not None:
        well.tracker.set_volume(volume_ul)


def has_tip(tip_spot: Any) -> bool:
    """Check whether a tip spot still has a tip."""
    return getattr(tip_spot, "has_tip", False)


def tip_used_count(tip_rack: Any) -> int:
    """Count tips that have been used (picked up) from the rack."""
    count = 0
    for child in tip_rack.children:
        if not getattr(child, "has_tip", True):
            count += 1
    return count


def deck_summary(lh: LiquidHandler) -> dict[str, Any]:
    """Return a summary of the current deck state."""
    deck = lh.deck
    resources = []
    for child in deck.children:
        res_type = getattr(child, "category", type(child).__name__)
        well_count = len(list(child.children)) if hasattr(child, "children") else 0
        resources.append({
            "name": child.name,
            "type": res_type,
            "location": {
                "x": child.location.x,
                "y": child.location.y,
                "z": child.location.z,
            } if child.location else None,
            "child_count": well_count,
        })

    pipette_state: dict[str, Any] = {"channels": []}
    if hasattr(lh, "head"):
        head = lh.head
        if isinstance(head, dict):
            pipette_state["channels"] = [
                {"name": ch_name, "has_tip": getattr(ch, "has_tip", False)}
                for ch_name, ch in head.items()
            ]
        else:
            pipette_state["channels"] = [
                {"index": i, "has_tip": getattr(ch, "has_tip", False)}
                for i, ch in enumerate(head)
            ]

    return {
        "deck_name": deck.name,
        "resources": resources,
        "pipette": pipette_state,
    }
