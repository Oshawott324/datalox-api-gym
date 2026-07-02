"""Dry-run STAR backend for LabLongRun-Bench.

Extends ``LiquidHandlerChatterboxBackend`` (the brand-agnostic dry-run
backend) with configurable STAR-specific features: 96-head and iSWAP arm.

All liquid-handling, tip, and resource-movement backend methods are
inherited as no-op print statements from the chatterbox base.
``LiquidHandler``'s high-level VolumeTracker and TipTracker updates
execute independently of the backend, so full state tracking works
correctly in dry-run mode.
"""

from __future__ import annotations

from pylabrobot.liquid_handling.backends.chatterbox import (
    LiquidHandlerChatterboxBackend,
)


class STARDryRunBackend(LiquidHandlerChatterboxBackend):
    """Configurable STAR dry-run backend.

    All operations are no-ops (print-only).  Volume / tip tracking is
    handled by ``LiquidHandler`` at the high-level API layer.
    """

    def __init__(
        self,
        num_channels: int = 8,
        with_96_head: bool = False,
        with_iswap: bool = False,
    ):
        super().__init__(num_channels=num_channels)
        self._head96_installed = with_96_head
        self._num_arms = 1 if with_iswap else 0
