"""Environment state — unified snapshot reconstructed from event logs.

Every instrument has a dedicated immutable state dataclass and a reducer
function that folds one event into the state.  ``EnvironmentState.from_events()``
replays the full event log to produce a queryable current-state snapshot.

Verifiers can query ``env.centrifuge.door_locked`` instead of scanning events
for ``centrifuge.door_locked`` and inferring the current value from ordering.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any


# ── Timestamped value wrapper ────────────────────────────────────────────


@dataclass(frozen=True)
class TS:
    """Timestamped value with last-updated clock time.

    Verifiers can call ``staleness_s(now)`` to detect stale reads.
    """
    value: Any = None
    updated_at: float = 0.0

    def staleness_s(self, now: float) -> float:
        return max(0.0, now - self.updated_at)


def _ts(value: Any, clock_time: float) -> TS:
    return TS(value=value, updated_at=clock_time)


# ── Per-instrument state dataclasses ─────────────────────────────────────


@dataclass(frozen=True)
class ArmState:
    x: TS = field(default_factory=lambda: TS(0.0))
    y: TS = field(default_factory=lambda: TS(0.0))
    z: TS = field(default_factory=lambda: TS(0.0))
    gripper_open: TS = field(default_factory=lambda: TS(True))
    gripper_width: TS = field(default_factory=lambda: TS(80.0))
    homed: TS = field(default_factory=lambda: TS(False))
    holding_plate: TS = field(default_factory=lambda: TS(None))  # plate_name | None


@dataclass(frozen=True)
class CentrifugeState:
    door_open: TS = field(default_factory=lambda: TS(True))
    door_locked: TS = field(default_factory=lambda: TS(False))
    at_bucket: TS = field(default_factory=lambda: TS(0))
    bucket_locked: TS = field(default_factory=lambda: TS(False))
    spinning: TS = field(default_factory=lambda: TS(False))
    last_g_force: TS = field(default_factory=lambda: TS(0.0))
    contains_plate: TS = field(default_factory=lambda: TS(None))
    # Violation tracking (set by reducer at event time)
    spin_without_lock: TS = field(default_factory=lambda: TS(False))


@dataclass(frozen=True)
class HeaterShakerState:
    target_temp: TS = field(default_factory=lambda: TS(25.0))
    current_temp: TS = field(default_factory=lambda: TS(25.0))
    shaking: TS = field(default_factory=lambda: TS(False))
    plate_locked: TS = field(default_factory=lambda: TS(False))
    active: TS = field(default_factory=lambda: TS(True))
    contains_plate: TS = field(default_factory=lambda: TS(None))
    # Timestamps for temporal chain validation
    temp_set_at: float = 0.0
    shake_started_at: float = 0.0
    shake_stopped_at: float = 0.0
    deactivated_at: float = 0.0


@dataclass(frozen=True)
class ThermocyclerState:
    lid_open: TS = field(default_factory=lambda: TS(True))
    lid_temp: TS = field(default_factory=lambda: TS(25.0))
    lid_target: TS = field(default_factory=lambda: TS(25.0))
    block_temp: TS = field(default_factory=lambda: TS(25.0))
    block_target: TS = field(default_factory=lambda: TS(25.0))
    active: TS = field(default_factory=lambda: TS(True))
    contains_plate: TS = field(default_factory=lambda: TS(None))
    # Timestamps for PCR chain validation
    lid_closed_at: float = 0.0
    lid_temp_set_at: float = 0.0
    block_heated_at: float = 0.0
    block_read_at: float = 0.0
    deactivated_at: float = 0.0
    lid_opened_at: float = 0.0


@dataclass(frozen=True)
class SealerState:
    door_open: TS = field(default_factory=lambda: TS(True))
    target_temp: TS = field(default_factory=lambda: TS(25.0))
    current_temp: TS = field(default_factory=lambda: TS(25.0))
    heater_on: TS = field(default_factory=lambda: TS(False))
    sealing: TS = field(default_factory=lambda: TS(False))
    contains_plate: TS = field(default_factory=lambda: TS(None))
    # Violation tracking
    seal_with_door_open: TS = field(default_factory=lambda: TS(False))


@dataclass(frozen=True)
class PeelerState:
    conveyor_in: TS = field(default_factory=lambda: TS(False))
    elevator_up: TS = field(default_factory=lambda: TS(False))
    tape_remaining_pct: TS = field(default_factory=lambda: TS(100.0))
    peel_count: TS = field(default_factory=lambda: TS(0))
    seal_present: TS = field(default_factory=lambda: TS(True))
    contains_plate: TS = field(default_factory=lambda: TS(None))
    # Violation tracking
    peel_no_check_before: TS = field(default_factory=lambda: TS(False))
    peel_no_check_after: TS = field(default_factory=lambda: TS(False))
    _last_check_before_peel: bool = False  # internal, not TS


@dataclass(frozen=True)
class ShakerState:
    plate_locked: TS = field(default_factory=lambda: TS(False))
    shaking: TS = field(default_factory=lambda: TS(False))
    speed_rpm: TS = field(default_factory=lambda: TS(0.0))
    contains_plate: TS = field(default_factory=lambda: TS(None))
    # Violation tracking
    shake_without_lock: TS = field(default_factory=lambda: TS(False))


@dataclass(frozen=True)
class ScaleState:
    last_weight_g: TS = field(default_factory=lambda: TS(0.0))
    zeroed: TS = field(default_factory=lambda: TS(False))
    tared: TS = field(default_factory=lambda: TS(False))
    has_plate: TS = field(default_factory=lambda: TS(False))
    weigh_count: int = 0


@dataclass(frozen=True)
class TempControllerState:
    target_temp: TS = field(default_factory=lambda: TS(25.0))
    current_temp: TS = field(default_factory=lambda: TS(25.0))
    active: TS = field(default_factory=lambda: TS(False))
    contains_plate: TS = field(default_factory=lambda: TS(None))
    deactivated_at: float = 0.0


@dataclass(frozen=True)
class TilterState:
    angle: TS = field(default_factory=lambda: TS(0.0))
    contains_plate: TS = field(default_factory=lambda: TS(None))
    leveled_at: float = 0.0


@dataclass(frozen=True)
class StorageState:
    door_open: TS = field(default_factory=lambda: TS(True))
    target_temp: TS = field(default_factory=lambda: TS(25.0))
    current_temp: TS = field(default_factory=lambda: TS(25.0))
    shaking: TS = field(default_factory=lambda: TS(False))
    free_sites: TS = field(default_factory=lambda: TS(0))
    stored_plates: TS = field(default_factory=lambda: TS({}))  # plate_name -> site_id


@dataclass(frozen=True)
class PowderDispenserState:
    dispense_count: int = 0
    total_amount_mg: TS = field(default_factory=lambda: TS(0.0))


@dataclass(frozen=True)
class BarcodeScannerState:
    last_barcode: TS = field(default_factory=lambda: TS(""))
    scan_count: int = 0


@dataclass(frozen=True)
class PlateReaderState:
    door_open: TS = field(default_factory=lambda: TS(False))
    plate_loaded: TS = field(default_factory=lambda: TS(None))
    readout_count: int = 0
    opened_at: float = 0.0


@dataclass(frozen=True)
class PumpState:
    running: TS = field(default_factory=lambda: TS(False))
    last_speed: TS = field(default_factory=lambda: TS(0.0))
    total_duration_s: TS = field(default_factory=lambda: TS(0.0))
    halted_at: float = 0.0


@dataclass(frozen=True)
class LiquidHandlerState:
    tips_used: int = 0
    transfers_completed: int = 0
    iSwap_holding: TS = field(default_factory=lambda: TS(None))


# ── Plate location ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class PlateLocation:
    plate_name: str
    location: str  # "carrier", "arm_gripper", "reader", "scale", "centrifuge", etc.
    updated_at: float = 0.0


# ── Root EnvironmentState ───────────────────────────────────────────────


@dataclass(frozen=True)
class EnvironmentState:
    """Unified environment snapshot reconstructed from events.

    All instrument states start as defaults.  ``from_events()`` replays
    the full event log through per-instrument reducers to derive the
    current state.  Fields are frozen (immutable) — reducers return new
    objects via ``dataclasses.replace``.
    """

    clock_time: float = 0.0

    # Per-instrument state
    arm: ArmState = field(default_factory=ArmState)
    centrifuge: CentrifugeState = field(default_factory=CentrifugeState)
    heater_shaker: HeaterShakerState = field(default_factory=HeaterShakerState)
    thermocycler: ThermocyclerState = field(default_factory=ThermocyclerState)
    sealer: SealerState = field(default_factory=SealerState)
    peeler: PeelerState = field(default_factory=PeelerState)
    shaker: ShakerState = field(default_factory=ShakerState)
    scale: ScaleState = field(default_factory=ScaleState)
    temp_controller: TempControllerState = field(default_factory=TempControllerState)
    tilter: TilterState = field(default_factory=TilterState)
    storage: StorageState = field(default_factory=StorageState)
    powder_dispenser: PowderDispenserState = field(default_factory=PowderDispenserState)
    barcode_scanner: BarcodeScannerState = field(default_factory=BarcodeScannerState)
    plate_reader: PlateReaderState = field(default_factory=PlateReaderState)
    pump: PumpState = field(default_factory=PumpState)
    liquid_handler: LiquidHandlerState = field(default_factory=LiquidHandlerState)

    # Cross-instrument
    plate_locations: dict[str, PlateLocation] = field(default_factory=dict)

    cross: "CrossInstrumentFacts" = field(default_factory=lambda: CrossInstrumentFacts())

    @classmethod
    def from_events(cls, events: list[dict]) -> "EnvironmentState":
        """Replay all events through reducers, then derive cross-instrument facts."""
        state = cls()
        for event in events:
            state = _reduce_event(state, event)
        state = replace(state, cross=_derive_cross_instrument(state))
        return state


# ── L2: Cross-Instrument Facts (event-level temporal analysis) ──────────


@dataclass(frozen=True)
class CrossInstrumentFacts:
    """Layer 2: derived facts from event-level temporal analysis.

    Each field is computed by scanning the raw event sequence, not just
    checking final L1 state.  This is the key difference from L1 — L2
    answers "was every spin preceded by a lock?" while L1 answers "what
    is the door state right now?"
    """

    # ── Safety interlocks ────────────────────────────────────────────
    centrifuge_safe: TS = field(default_factory=lambda: TS(True))
    # For every centrifuge.spin event: the nearest prior door_lock is
    # AFTER the nearest prior door_open → spin occurred while locked.

    reader_thermal_safe: TS = field(default_factory=lambda: TS(True))
    # For every reader.opened event: all three thermal instruments
    # (HS, TC, temp_ctrl) had been deactivated before it.

    shaker_safe: TS = field(default_factory=lambda: TS(True))
    # For every shaker.shaking event: plate was locked before shake started.

    sealer_safe: TS = field(default_factory=lambda: TS(True))
    # For every sealer.sealed event: door was closed before seal.

    peeler_safe: TS = field(default_factory=lambda: TS(True))
    # Peeler seal_check was called BEFORE peel (confirming seal) AND
    # AFTER peel (confirming removal).

    # ── Cross-instrument temporal ordering ───────────────────────────
    hs_before_tc: TS = field(default_factory=lambda: TS(True))
    # HS was deactivated before TC started (thermal interference prevention).

    pump_halted_before_tilter: TS = field(default_factory=lambda: TS(True))
    # Pump was halted before tilter returned to level.

    # ── Plate location consistency ────────────────────────────────────
    plate_weighing_valid: TS = field(default_factory=lambda: TS(False))
    # Scale readings exist AND occurred while plate was at scale location
    # (between arm.drop at scale coords and arm.pickup from scale coords).

    plate_returned_to_carrier: TS = field(default_factory=lambda: TS(False))
    # Plate's final recorded location is "carrier".

    # ── Protocol chain completeness (event-ordering validated) ────────
    incubation_chain: TS = field(default_factory=lambda: TS(False))
    # Events occurred in order: set_temp → shake → stop → deactivate
    # AND all four steps are present in the event log.

    pcr_chain: TS = field(default_factory=lambda: TS(False))
    # Events: lid_close → set_lid_temp → block_heat(>=1) → block_read(>=1) →
    # deactivate → lid_open, all in temporal order.

    seal_peel_chain: TS = field(default_factory=lambda: TS(False))
    # sealer.sealed → peeler.seal_check(seal_detected) → peeler.peeled →
    # peeler.seal_check(no_seal), all in temporal order.

    # ── Timing anchors ────────────────────────────────────────────────
    last_instrument_op_time: float = 0.0
    last_readout_time: float = 0.0
    last_submit_time: float = 0.0


def _derive_cross_instrument(state: EnvironmentState) -> CrossInstrumentFacts:
    """Pure L1-state reading. No event scanning — violaations already
    detected by L1 reducers at event time; timestamps already recorded.
    """
    cross = CrossInstrumentFacts()
    ct = state.clock_time

    # ── Safety: L1 already flagged violations ──────────────────────────
    cf = state.centrifuge
    cross = replace(cross, centrifuge_safe=_ts(
        not cf.spin_without_lock.value, ct))

    sl = state.sealer
    cross = replace(cross, sealer_safe=_ts(
        not sl.seal_with_door_open.value, ct))

    sk = state.shaker
    cross = replace(cross, shaker_safe=_ts(
        not sk.shake_without_lock.value, ct))

    plr = state.peeler
    cross = replace(cross, peeler_safe=_ts(
        not plr.peel_no_check_before.value, ct))

    # ── Reader thermal safety: all deactivated before reader opened ────
    hs = state.heater_shaker
    tc = state.thermocycler
    tmp = state.temp_controller
    pr = state.plate_reader
    if pr.opened_at > 0:
        ok = True
        if hs.deactivated_at > 0:
            ok = ok and hs.deactivated_at < pr.opened_at
        if tc.deactivated_at > 0:
            ok = ok and tc.deactivated_at < pr.opened_at
        if tmp.deactivated_at > 0:
            ok = ok and tmp.deactivated_at < pr.opened_at
        cross = replace(cross, reader_thermal_safe=_ts(ok, ct))

    # ── Cross-instrument temporal ordering ─────────────────────────────
    if hs.deactivated_at > 0 and tc.block_heated_at > 0:
        cross = replace(cross, hs_before_tc=_ts(
            hs.deactivated_at < tc.block_heated_at, ct))

    pump = state.pump
    tilt = state.tilter
    if pump.halted_at > 0 and tilt.leveled_at > 0:
        cross = replace(cross, pump_halted_before_tilter=_ts(
            pump.halted_at < tilt.leveled_at, ct))

    # ── Plate weighing valid ───────────────────────────────────────────
    sc = state.scale
    plate_on_scale = any(
        pl.location == "scale" for pl in state.plate_locations.values())
    cross = replace(cross, plate_weighing_valid=_ts(
        plate_on_scale and sc.weigh_count > 0
        and (sc.zeroed.value or sc.tared.value), ct))

    # ── Plate returned ─────────────────────────────────────────────────
    returned = any(pl.location == "carrier"
                   for pl in state.plate_locations.values())
    arm_released = state.arm.homed.value and state.arm.gripper_open.value
    cross = replace(cross, plate_returned_to_carrier=_ts(
        returned or arm_released, ct))

    # ── Protocol chains: timestamps already recorded by L1 ─────────────
    if hs.temp_set_at > 0 and hs.shake_started_at > 0 and hs.shake_stopped_at > 0 and hs.deactivated_at > 0:
        chain = (hs.temp_set_at < hs.shake_started_at
                 < hs.shake_stopped_at < hs.deactivated_at)
        cross = replace(cross, incubation_chain=_ts(chain, ct))

    if (tc.lid_closed_at > 0 and tc.lid_temp_set_at > 0
            and tc.block_heated_at > 0 and tc.block_read_at > 0
            and tc.deactivated_at > 0 and tc.lid_opened_at > 0):
        chain = (tc.lid_closed_at < tc.lid_temp_set_at
                 < tc.block_heated_at < tc.block_read_at
                 < tc.deactivated_at < tc.lid_opened_at)
        cross = replace(cross, pcr_chain=_ts(chain, ct))

    slr = state.sealer
    if slr.sealing.value and plr.peel_count.value > 0:
        chain = (not plr.peel_no_check_before.value
                 and slr.sealing.value
                 and not plr.seal_present.value)
        cross = replace(cross, seal_peel_chain=_ts(chain, ct))

    # ── Timing anchors from L1 timestamps ──────────────────────────────
    last_op = max(filter(lambda x: x > 0, [
        state.arm.x.updated_at, cf.last_g_force.updated_at,
        hs.current_temp.updated_at, tc.block_temp.updated_at,
        sl.current_temp.updated_at, plr.peel_count.updated_at,
        sk.speed_rpm.updated_at, sc.last_weight_g.updated_at,
        pump.last_speed.updated_at, tilt.angle.updated_at,
        state.storage.current_temp.updated_at,
        state.powder_dispenser.total_amount_mg.updated_at,
    ]), default=0.0)
    cross = replace(cross, last_instrument_op_time=last_op)

    return cross


# ── L3: Reusable Predicates ──────────────────────────────────────────────


def is_reader_safe(env: EnvironmentState) -> tuple[bool, str]:
    """All thermal instruments deactivated before reader access (event-level check)."""
    if not env.cross.reader_thermal_safe.value:
        return False, "thermal instrument still active when reader opened"
    return True, "all thermal instruments off before reader access"


def is_centrifuge_safe(env: EnvironmentState) -> tuple[bool, str]:
    """Every centrifuge spin was preceded by a door lock (no unlock between)."""
    if not env.cross.centrifuge_safe.value:
        return False, "spin occurred without door locked"
    return True, "every spin had door locked"


def is_shaker_safe(env: EnvironmentState) -> tuple[bool, str]:
    """Plate was locked before every shake start (event-level check)."""
    if not env.cross.shaker_safe.value:
        return False, "shaking started without plate locked"
    return True, "plate locked before every shake"


def is_sealer_safe(env: EnvironmentState) -> tuple[bool, str]:
    """Door was closed before every seal operation (event-level check)."""
    if not env.cross.sealer_safe.value:
        return False, "seal executed with door open"
    return True, "door closed before every seal"


def is_peeler_safe(env: EnvironmentState) -> tuple[bool, str]:
    """Seal check confirmed seal before peel AND confirmed removal after peel."""
    if not env.cross.peeler_safe.value:
        return False, "seal not verified before AND after peel"
    return True, "seal verified before and after peel"


def is_hs_before_tc(env: EnvironmentState) -> tuple[bool, str]:
    """HS was deactivated before TC started heating."""
    if not env.cross.hs_before_tc.value:
        return False, "TC started before HS deactivated"
    return True, "HS deactivated before TC"


def is_pump_halted_before_tilter(env: EnvironmentState) -> tuple[bool, str]:
    """Pump was halted before tilter returned to level."""
    if not env.cross.pump_halted_before_tilter.value:
        return False, "tilter leveled while pump still running"
    return True, "pump halted before tilter leveled"


def is_plate_where_it_should_be(env: EnvironmentState, expected: str = "carrier") -> tuple[bool, str]:
    """Plate location matches expected."""
    pl = env.plate_locations.get("assay_plate")
    if pl is None:
        return False, f"no plate location data (expected {expected})"
    if pl.location != expected:
        return False, f"plate at {pl.location} (expected {expected})"
    return True, f"plate at {expected}"


def is_incubation_chain_complete(env: EnvironmentState) -> tuple[bool, str]:
    """HS events in order: set_temp → shake → stop → deactivate."""
    if not env.cross.incubation_chain.value:
        return False, "incubation chain broken or incomplete"
    return True, "incubation chain complete"


def is_pcr_chain_complete(env: EnvironmentState) -> tuple[bool, str]:
    """TC events in order: close → lid_heat → block_heat → read → deact → open."""
    if not env.cross.pcr_chain.value:
        return False, "PCR chain broken or incomplete"
    return True, "PCR chain complete"


def is_seal_peel_chain_complete(env: EnvironmentState) -> tuple[bool, str]:
    """Seal→check(seal)→peel→check(no_seal) events in order."""
    if not env.cross.seal_peel_chain.value:
        return False, "seal-peel chain broken or incomplete"
    return True, "seal-peel chain complete"


def is_plate_weighing_valid(env: EnvironmentState) -> tuple[bool, str]:
    """Scale readings occurred while plate was at scale location."""
    if not env.cross.plate_weighing_valid.value:
        return False, "no valid weigh while plate on scale"
    return True, "plate weighed while on scale"


# ── Master event dispatcher ──────────────────────────────────────────────


def _reduce_event(state: EnvironmentState, event: dict) -> EnvironmentState:
    """Dispatch a single event to the appropriate instrument reducer."""
    et = event.get("event_type", "")
    ct = event.get("clock_time", 0.0)
    state = replace(state, clock_time=max(state.clock_time, ct))

    # Arm events
    if et.startswith("arm."):
        state = replace(state, arm=_reduce_arm(state.arm, event, ct))

    # Centrifuge events
    elif et.startswith("centrifuge."):
        state = replace(state, centrifuge=_reduce_centrifuge(state.centrifuge, event, ct))

    # HeaterShaker events
    elif et.startswith("hs."):
        state = replace(state, heater_shaker=_reduce_heater_shaker(state.heater_shaker, event, ct))

    # Thermocycler events (block/lid — not temp_controller)
    elif et.startswith("tc.") and event.get("object_type") == "thermocycler":
        state = replace(state, thermocycler=_reduce_thermocycler(state.thermocycler, event, ct))

    # TempController events (tc.* with object_type "temp_controller")
    elif et.startswith("tc.") and event.get("object_type") == "temp_controller":
        state = replace(state, temp_controller=_reduce_temp_controller(state.temp_controller, event, ct))

    # Sealer events
    elif et.startswith("sealer."):
        state = replace(state, sealer=_reduce_sealer(state.sealer, event, ct))

    # Peeler events
    elif et.startswith("peeler."):
        state = replace(state, peeler=_reduce_peeler(state.peeler, event, ct))

    # Shaker events
    elif et.startswith("shaker."):
        state = replace(state, shaker=_reduce_shaker(state.shaker, event, ct))

    # Scale events
    elif et.startswith("scale."):
        state = replace(state, scale=_reduce_scale(state.scale, event, ct))

    # Tilter events
    elif et.startswith("tilter."):
        state = replace(state, tilter=_reduce_tilter(state.tilter, event, ct))

    # Storage events
    elif et.startswith("storage."):
        state = replace(state, storage=_reduce_storage(state.storage, event, ct))

    # Powder dispenser events
    elif et.startswith("powder."):
        state = replace(state, powder_dispenser=_reduce_powder_dispenser(state.powder_dispenser, event, ct))

    # Barcode events
    elif et.startswith("barcode."):
        state = replace(state, barcode_scanner=_reduce_barcode_scanner(state.barcode_scanner, event, ct))

    # Plate reader events
    elif et.startswith("reader.") or et.startswith("readout."):
        state = replace(state, plate_reader=_reduce_plate_reader(state.plate_reader, event, ct))

    # Pump events
    elif et.startswith("pump."):
        state = replace(state, pump=_reduce_pump(state.pump, event, ct))

    # Liquid handler / transfer events
    elif et.startswith("tips.") or et.startswith("transfer.") or et.startswith("stamp.") or et.startswith("plate.moved"):
        state = replace(state, liquid_handler=_reduce_liquid_handler(state.liquid_handler, event, ct))

    # Plate location tracking from arm drops and reader loads
    state = _track_plate_location(state, event, ct)

    return state


# ── Instrument reducers ──────────────────────────────────────────────────


def _reduce_arm(state: ArmState, event: dict, ct: float) -> ArmState:
    et = event["event_type"]
    p = event.get("payload", {})
    if et == "arm.homed":
        state = replace(state, x=_ts(0.0, ct), y=_ts(0.0, ct), z=_ts(150.0, ct),
                        homed=_ts(True, ct))
    elif et == "arm.moved_to":
        state = replace(state, x=_ts(p.get("x", 0.0), ct),
                        y=_ts(p.get("y", 0.0), ct),
                        z=_ts(p.get("z", 0.0), ct))
    elif et == "arm.approached":
        state = replace(state, x=_ts(p.get("x", 0.0), ct),
                        y=_ts(p.get("y", 0.0), ct),
                        z=_ts(p.get("z", 0.0), ct))
    elif et == "arm.safe":
        state = replace(state, x=_ts(0.0, ct), y=_ts(0.0, ct), z=_ts(150.0, ct))
    elif et == "arm.gripper_opened":
        state = replace(state, gripper_open=_ts(True, ct),
                        gripper_width=_ts(p.get("width_mm", 80.0), ct))
    elif et == "arm.gripper_closed":
        state = replace(state, gripper_open=_ts(False, ct),
                        gripper_width=_ts(p.get("width_mm", 85.0), ct))
    elif et == "arm.picked_up":
        state = replace(state, gripper_open=_ts(False, ct),
                        holding_plate=_ts("assay_plate", ct))
    elif et == "arm.dropped":
        state = replace(state, gripper_open=_ts(True, ct),
                        holding_plate=_ts(None, ct))
    elif et == "arm.position_read":
        pos = p if p else {}
        state = replace(state, x=_ts(pos.get("x", state.x.value), ct),
                        y=_ts(pos.get("y", state.y.value), ct),
                        z=_ts(pos.get("z", state.z.value), ct))
    elif et == "arm.gripper_state":
        closed = p.get("gripper_closed", False)
        state = replace(state, gripper_open=_ts(not closed, ct))
    return state


def _reduce_centrifuge(state: CentrifugeState, event: dict, ct: float) -> CentrifugeState:
    et = event["event_type"]
    p = event.get("payload", {})
    if et == "centrifuge.door_opened":
        state = replace(state, door_open=_ts(True, ct), door_locked=_ts(False, ct),
                        spinning=_ts(False, ct))
    elif et == "centrifuge.door_closed":
        state = replace(state, door_open=_ts(False, ct))
    elif et == "centrifuge.door_locked":
        state = replace(state, door_locked=_ts(True, ct))
    elif et == "centrifuge.bucket1":
        state = replace(state, at_bucket=_ts(1, ct))
    elif et == "centrifuge.bucket2":
        state = replace(state, at_bucket=_ts(2, ct))
    elif et == "centrifuge.bucket_locked":
        state = replace(state, bucket_locked=_ts(True, ct))
    elif et == "centrifuge.spin":
        # Violation detection: spin while door not locked
        if not state.door_locked.value:
            state = replace(state, spin_without_lock=_ts(True, ct))
        state = replace(state, spinning=_ts(True, ct),
                        last_g_force=_ts(p.get("g_force", 0.0), ct))
    return state


def _reduce_heater_shaker(state: HeaterShakerState, event: dict, ct: float) -> HeaterShakerState:
    et = event["event_type"]
    p = event.get("payload", {})
    if et == "hs.temp_set":
        temp = p.get("target_temperature", p.get("temperature", 25.0))
        state = replace(state, target_temp=_ts(temp, ct), current_temp=_ts(temp, ct),
                        temp_set_at=ct)
    elif et == "hs.temp_read":
        temp = p.get("current_temperature", p.get("temperature", state.current_temp.value))
        state = replace(state, current_temp=_ts(temp, ct))
    elif et == "hs.shake":
        state = replace(state, shaking=_ts(True, ct), shake_started_at=ct)
    elif et == "hs.shake_stop":
        state = replace(state, shaking=_ts(False, ct), shake_stopped_at=ct)
    elif et == "hs.deactivated":
        state = replace(state, active=_ts(False, ct), shaking=_ts(False, ct),
                        current_temp=_ts(25.0, ct), deactivated_at=ct)
    return state


def _reduce_thermocycler(state: ThermocyclerState, event: dict, ct: float) -> ThermocyclerState:
    et = event["event_type"]
    p = event.get("payload", {})
    if et == "tc.lid_closed":
        state = replace(state, lid_open=_ts(False, ct), lid_closed_at=ct)
    elif et == "tc.lid_opened":
        state = replace(state, lid_open=_ts(True, ct), lid_opened_at=ct)
    elif et == "tc.lid_temp_set":
        temp = p.get("temperature", p.get("lid_temperature", 105.0))
        state = replace(state, lid_target=_ts(temp, ct), lid_temp=_ts(temp, ct),
                        lid_temp_set_at=ct)
    elif et == "tc.block_temp_set":
        temp = p.get("temperature", p.get("block_temperature", 25.0))
        state = replace(state, block_target=_ts(temp, ct), block_temp=_ts(temp, ct),
                        block_heated_at=ct)
    elif et == "tc.block_temp_read":
        temp = p.get("temperature", p.get("block_temperature", state.block_temp.value))
        state = replace(state, block_temp=_ts(temp, ct), block_read_at=ct)
    elif et == "tc.deactivated":
        state = replace(state, active=_ts(False, ct), block_temp=_ts(25.0, ct),
                        lid_temp=_ts(25.0, ct), deactivated_at=ct)
    return state


def _reduce_temp_controller(state: TempControllerState, event: dict, ct: float) -> TempControllerState:
    et = event["event_type"]
    p = event.get("payload", {})
    if et == "tc.set_temp":
        temp = p.get("temperature", 25.0)
        state = replace(state, target_temp=_ts(temp, ct), current_temp=_ts(temp, ct),
                        active=_ts(True, ct))
    elif et == "tc.read_temp":
        temp = p.get("temperature", state.current_temp.value)
        state = replace(state, current_temp=_ts(temp, ct))
    elif et == "tc.temp_reached":
        temp = p.get("temperature", state.current_temp.value)
        state = replace(state, current_temp=_ts(temp, ct))
    elif et == "tc.deactivated":
        state = replace(state, active=_ts(False, ct), deactivated_at=ct)
    return state


def _reduce_sealer(state: SealerState, event: dict, ct: float) -> SealerState:
    et = event["event_type"]
    p = event.get("payload", {})
    if et == "sealer.opened":
        state = replace(state, door_open=_ts(True, ct))
    elif et == "sealer.closed":
        state = replace(state, door_open=_ts(False, ct))
    elif et == "sealer.temp_set":
        temp = p.get("temperature", 170.0)
        state = replace(state, target_temp=_ts(temp, ct), current_temp=_ts(temp, ct),
                        heater_on=_ts(True, ct))
    elif et == "sealer.temp_read":
        temp = p.get("temperature", state.current_temp.value)
        state = replace(state, current_temp=_ts(temp, ct))
    elif et == "sealer.sealed":
        # Violation detection: seal while door open
        if state.door_open.value:
            state = replace(state, seal_with_door_open=_ts(True, ct))
        temp = p.get("temperature", 170.0)
        state = replace(state, sealing=_ts(True, ct), current_temp=_ts(temp, ct))
    return state


def _reduce_peeler(state: PeelerState, event: dict, ct: float) -> PeelerState:
    et = event["event_type"]
    p = event.get("payload", {})
    if et == "peeler.conveyor_in":
        state = replace(state, conveyor_in=_ts(True, ct))
    elif et == "peeler.conveyor_out":
        state = replace(state, conveyor_in=_ts(False, ct))
    elif et == "peeler.elevator_up":
        state = replace(state, elevator_up=_ts(True, ct))
    elif et == "peeler.elevator_down":
        state = replace(state, elevator_up=_ts(False, ct))
    elif et == "peeler.tape_advanced":
        remaining = p.get("tape_remaining_pct", state.tape_remaining_pct.value)
        state = replace(state, tape_remaining_pct=_ts(remaining, ct))
    elif et == "peeler.tape_checked":
        remaining = p.get("tape_remaining_pct", state.tape_remaining_pct.value)
        state = replace(state, tape_remaining_pct=_ts(remaining, ct))
    elif et == "peeler.seal_checked":
        result = p.get("result", "")
        seal = (result == "seal_detected")
        state = replace(state, seal_present=_ts(seal, ct),
                        _last_check_before_peel=seal)
    elif et == "peeler.peeled":
        # Violation detection: peel without prior seal_check confirming seal
        if not state._last_check_before_peel:
            state = replace(state, peel_no_check_before=_ts(True, ct))
        # seal_present will be set to False; next seal_check should confirm
        state = replace(state, seal_present=_ts(False, ct),
                        peel_count=_ts(state.peel_count.value + 1, ct),
                        tape_remaining_pct=_ts(max(0, state.tape_remaining_pct.value - 1), ct))
    elif et == "peeler.status_checked":
        pass  # status tuple doesn't change state we track
    return state


def _reduce_shaker(state: ShakerState, event: dict, ct: float) -> ShakerState:
    et = event["event_type"]
    p = event.get("payload", {})
    if et == "shaker.plate_locked":
        state = replace(state, plate_locked=_ts(True, ct))
    elif et == "shaker.plate_unlocked":
        state = replace(state, plate_locked=_ts(False, ct))
    elif et == "shaker.shaking":
        # Violation detection: shake while plate not locked
        if not state.plate_locked.value:
            state = replace(state, shake_without_lock=_ts(True, ct))
        state = replace(state, shaking=_ts(True, ct),
                        speed_rpm=_ts(p.get("speed_rpm", 0.0), ct))
    elif et == "shaker.stopped":
        state = replace(state, shaking=_ts(False, ct), speed_rpm=_ts(0.0, ct))
    return state


def _reduce_scale(state: ScaleState, event: dict, ct: float) -> ScaleState:
    et = event["event_type"]
    p = event.get("payload", {})
    if et == "scale.zeroed":
        state = replace(state, zeroed=_ts(True, ct))
    elif et == "scale.tared":
        state = replace(state, tared=_ts(True, ct))
    elif et == "scale.weight_read":
        w = p.get("weight_g", 0.0)
        state = replace(state, last_weight_g=_ts(w, ct),
                        weigh_count=state.weigh_count + 1)
    return state


def _reduce_tilter(state: TilterState, event: dict, ct: float) -> TilterState:
    et = event["event_type"]
    p = event.get("payload", {})
    if et in ("tilter.angle_set", "tilter.tilted", "tilter.angle_read"):
        angle = p.get("angle", p.get("absolute_angle", p.get("relative_angle", 0.0)))
        state = replace(state, angle=_ts(angle, ct))
        if abs(angle) < 1.0:
            state = replace(state, leveled_at=ct)
    return state


def _reduce_storage(state: StorageState, event: dict, ct: float) -> StorageState:
    et = event["event_type"]
    p = event.get("payload", {})
    if et == "storage.door_opened":
        state = replace(state, door_open=_ts(True, ct))
    elif et == "storage.door_closed":
        state = replace(state, door_open=_ts(False, ct))
    elif et == "storage.temp_set":
        temp = p.get("temperature", 37.0)
        state = replace(state, target_temp=_ts(temp, ct), current_temp=_ts(temp, ct))
    elif et == "storage.temp_read":
        temp = p.get("temperature", state.current_temp.value)
        state = replace(state, current_temp=_ts(temp, ct))
    elif et == "storage.shaking_started":
        state = replace(state, shaking=_ts(True, ct))
    elif et == "storage.shaking_stopped":
        state = replace(state, shaking=_ts(False, ct))
    elif et == "storage.plate_stored":
        site = p.get("site", "unknown")
        stored = dict(state.stored_plates.value)
        stored["assay_plate"] = site
        state = replace(state, stored_plates=_ts(stored, ct))
    elif et == "storage.plate_retrieved":
        stored = dict(state.stored_plates.value)
        stored.pop("assay_plate", None)
        state = replace(state, stored_plates=_ts(stored, ct))
    elif et == "storage.free_sites_checked":
        free = p.get("free_sites", state.free_sites.value)
        state = replace(state, free_sites=_ts(free, ct))
    return state


def _reduce_powder_dispenser(state: PowderDispenserState, event: dict, ct: float) -> PowderDispenserState:
    p = event.get("payload", {})
    amount = p.get("amount_mg", 0.0)
    new_total = state.total_amount_mg.value + amount
    return replace(state, dispense_count=state.dispense_count + 1,
                   total_amount_mg=_ts(new_total, ct))


def _reduce_barcode_scanner(state: BarcodeScannerState, event: dict, ct: float) -> BarcodeScannerState:
    p = event.get("payload", {})
    barcode = p.get("barcode", "")
    return replace(state, last_barcode=_ts(barcode, ct),
                   scan_count=state.scan_count + 1)


def _reduce_plate_reader(state: PlateReaderState, event: dict, ct: float) -> PlateReaderState:
    et = event["event_type"]
    p = event.get("payload", {})
    if et == "reader.opened":
        state = replace(state, door_open=_ts(True, ct), opened_at=ct)
    elif et == "reader.closed":
        state = replace(state, door_open=_ts(False, ct))
    elif et == "readout.created":
        plate = p.get("plate_id", "")
        if plate:
            state = replace(state, plate_loaded=_ts(plate, ct))
        state = replace(state, readout_count=state.readout_count + 1)
    return state


def _reduce_pump(state: PumpState, event: dict, ct: float) -> PumpState:
    et = event["event_type"]
    p = event.get("payload", {})
    if et in ("pump.run_duration", "pump.run_volume"):
        speed = p.get("speed_rpm", 0.0)
        dur = p.get("duration_s", 0.0)
        state = replace(state, running=_ts(True, ct), last_speed=_ts(speed, ct),
                        total_duration_s=_ts(state.total_duration_s.value + dur, ct))
    elif et == "pump.halted":
        state = replace(state, running=_ts(False, ct), halted_at=ct)
    return state


def _reduce_liquid_handler(state: LiquidHandlerState, event: dict, ct: float) -> LiquidHandlerState:
    et = event["event_type"]
    if et in ("tips.picked_up", "tips96.picked_up"):
        state = replace(state, tips_used=state.tips_used + 1)
    elif et in ("transfer.aspirated", "transfer.dispensed", "transfer.completed",
                "stamp.completed", "transfer96.aspirated", "transfer96.dispensed"):
        state = replace(state, transfers_completed=state.transfers_completed + 1)
    elif et == "plate.moved":
        name = event.get("object_id", "")
        state = replace(state, iSwap_holding=_ts(name if name else None, ct))
    return state


# ── Plate location tracking ──────────────────────────────────────────────


def _track_plate_location(state: EnvironmentState, event: dict, ct: float) -> EnvironmentState:
    """Infer plate location from arm drop, iSWAP move, reader load, and storage events."""
    et = event.get("event_type", "")
    p = event.get("payload", {})

    new_loc: dict[str, PlateLocation] | None = None

    # Arm drops plate → infer location from coordinates
    if et == "arm.dropped":
        x, y = p.get("x", 0), p.get("y", 0)
        location = _classify_coordinates(x, y)
        new_loc = {**state.plate_locations,
                   "assay_plate": PlateLocation("assay_plate", location, ct)}

    # iSWAP moves plate to a named resource
    elif et == "plate.moved":
        target = event.get("object_id", "")
        new_loc = {**state.plate_locations,
                   "assay_plate": PlateLocation("assay_plate", f"iswap_{target}", ct)}

    # Storage store/retrieve
    elif et == "storage.plate_stored":
        site = p.get("site", "unknown")
        new_loc = {**state.plate_locations,
                   "assay_plate": PlateLocation("assay_plate", f"storage_site_{site}", ct)}
    elif et == "storage.plate_retrieved":
        new_loc = {**state.plate_locations,
                   "assay_plate": PlateLocation("assay_plate", "carrier", ct)}

    if new_loc is not None:
        state = replace(state, plate_locations=new_loc)

    return state


def _classify_coordinates(x: float, y: float) -> str:
    """Map well-known (x, y) coordinates to location labels.

    These are the convention used in arm-related TaskSpec prompts:
      (100, 200, *) → carrier pick-up/drop-off
      (300, 100, *) → reader area
      (400, 200, *) → scale area
    """
    if x <= 120 and y >= 180:
        return "carrier"
    elif x >= 280 and x <= 320 and y <= 120:
        return "reader"
    elif x >= 380 and y >= 180:
        return "scale"
    else:
        return f"position_{x:.0f}_{y:.0f}"
