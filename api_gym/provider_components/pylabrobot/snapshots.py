"""Selected JSON snapshots from actual PyLabRobot resource and tracker objects."""

from __future__ import annotations

from typing import Any

from pylabrobot.liquid_handling import LiquidHandler
from pylabrobot.plate_reading import PlateReader
from pylabrobot.resources import Plate, TipRack
from pylabrobot.storage import Incubator


def ot2_snapshot(
    liquid_handler: LiquidHandler,
    *,
    tip_rack: TipRack,
    source_plate: Plate,
    target_plate: Plate,
    tracked_wells: tuple[str, ...] = ("A1", "A2"),
) -> dict[str, Any]:
    backend = liquid_handler.backend
    return {
        "backend": {
            "class": _class_path(backend),
            "left_pipette": _pipette_name(getattr(backend, "left_pipette", None)),
            "left_pipette_has_tip": bool(
                getattr(backend, "left_pipette_has_tip", False)
            ),
            "right_pipette": _pipette_name(getattr(backend, "right_pipette", None)),
            "right_pipette_has_tip": bool(
                getattr(backend, "right_pipette_has_tip", False)
            ),
        },
        "channels": {
            str(channel): _tip_tracker_snapshot(tracker)
            for channel, tracker in sorted(liquid_handler.head.items())
        },
        "deck": [
            {
                "resource": resource.name,
                "slot": liquid_handler.deck.get_slot(resource),
            }
            for resource in (tip_rack, source_plate, target_plate)
        ],
        "tip_spots": {
            name: {"has_tip": tip_rack.get_item(name).tracker.has_tip}
            for name in tracked_wells
        },
        "wells": {
            f"{plate.name}:{name}": _volume_tracker_snapshot(
                plate.get_item(name).tracker
            )
            for plate in (source_plate, target_plate)
            for name in tracked_wells
        },
    }


def incubator_snapshot(incubator: Incubator) -> dict[str, Any]:
    return {
        "backend": {"class": _class_path(incubator.backend)},
        "loading_tray": _resource_name(incubator.loading_tray.resource),
        "sites": {
            site.name: _resource_name(site.resource)
            for rack in incubator.racks
            for _, site in sorted(rack.sites.items())
        },
    }


def plate_reader_snapshot(reader: PlateReader) -> dict[str, Any]:
    return {
        "backend": {"class": _class_path(reader.backend)},
        "plate": _resource_name(reader.get_plate()) if reader.children else None,
    }


def _tip_tracker_snapshot(tracker: Any) -> dict[str, Any]:
    if not tracker.has_tip:
        return {"has_tip": False, "tip": None}
    tip = tracker.get_tip()
    return {
        "has_tip": True,
        "tip": {
            "max_volume_ul": tip.maximal_volume,
            "volume": _volume_tracker_snapshot(tip.tracker),
        },
    }


def _volume_tracker_snapshot(tracker: Any) -> dict[str, float]:
    return {
        "max_volume_ul": float(tracker.max_volume),
        "pending_volume_ul": float(tracker.pending_volume),
        "volume_ul": float(tracker.volume),
    }


def _class_path(value: Any) -> str:
    return f"{type(value).__module__}.{type(value).__name__}"


def _resource_name(value: Any) -> str | None:
    return value.name if value is not None else None


def _pipette_name(value: Any) -> str | None:
    return value.get("name") if isinstance(value, dict) else None
