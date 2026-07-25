"""OT-2 Simulator + Visualizer backend for pylabrobot_lab_v0.

Replaces ChatterBox with OpentronsOT2Simulator, providing a
browser-based 3D visualisation of every liquid-handling operation.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from typing import Any

from api_gym.worlds.pylabrobot_lab_v0.state import _require_pylabrobot


def _run_async(coro):
    """Run an async coroutine synchronously, even from inside an event loop."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    # We're inside an async context — run in a separate thread
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(asyncio.run, coro)
        return future.result()


def create_ot2_deck() -> Any:
    """Create an OT-2 deck (SBS-style slot layout)."""
    _require_pylabrobot()
    from pylabrobot.resources.opentrons import OTDeck
    return OTDeck()


def create_ot2_liquid_handler(deck: Any) -> Any:
    """Create a LiquidHandler with OT-2 simulator backend."""
    _require_pylabrobot()
    from pylabrobot.liquid_handling import LiquidHandler
    from pylabrobot.liquid_handling.backends import OpentronsOT2Simulator
    return LiquidHandler(backend=OpentronsOT2Simulator(), deck=deck)


def create_ot2_plate(name: str) -> Any:
    """Create a standard 96-well flat-bottom plate for OT-2."""
    _require_pylabrobot()
    from pylabrobot.resources.celltreat import CellTreat_96_wellplate_350ul_Fb
    return CellTreat_96_wellplate_350ul_Fb(name=name)


def create_ot2_tip_rack(name: str, with_tips: bool = True) -> Any:
    """Create a 300 uL tip rack for OT-2."""
    _require_pylabrobot()
    from pylabrobot.resources.opentrons import opentrons_96_tiprack_300ul
    return opentrons_96_tiprack_300ul(name=name, with_tips=with_tips)


def setup_ot2_deck(lh: Any, plate: Any, source_plate: Any,
                   tip_rack: Any) -> None:
    """Place labware on OT-2 deck slots and run setup."""
    from pylabrobot.resources import set_tip_tracking, set_volume_tracking
    set_tip_tracking(True)
    set_volume_tracking(True)

    deck = lh.deck
    deck.assign_child_at_slot(tip_rack, slot=1)
    deck.assign_child_at_slot(source_plate, slot=5)
    deck.assign_child_at_slot(plate, slot=6)

    _run_async(lh.setup())


class OT2VisualizerSession:
    """Manages the OT-2 Visualizer lifecycle for one demo session."""

    def __init__(self, lh: Any):
        self._lh = lh
        self._vis: Any = None

    def start(self) -> None:
        """Start the visualizer server on http://127.0.0.1:1337."""
        _require_pylabrobot()
        import webbrowser
        from pylabrobot.visualizer import Visualizer

        # PyLabRobot's Visualizer._run_file_server calls webbrowser.open()
        # which pops a new browser tab.  Monkey-patch it to a no-op since
        # we embed the visualizer in an iframe inside our own page.
        webbrowser.open = lambda url, *a, **kw: None

        async def _start():
            # Use bright neon cyan liquid color so well volume changes
            # are clearly visible against the dark plate background.
            self._vis = Visualizer(resource=self._lh, liquid_color="00E5FF")
            await self._vis.setup()

        _run_async(_start())
        print("[OT-2 Visualizer] Ready at http://127.0.0.1:1337 (embedded in page).")

    def stop(self) -> None:
        """Stop the visualizer."""
        if self._vis is None:
            return

        async def _stop():
            await self._vis.stop()

        _run_async(_stop())
        self._vis = None
