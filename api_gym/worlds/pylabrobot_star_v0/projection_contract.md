# Projection Contract — pylabrobot_star_v0

Last updated: 2026-07-09 | Tools: 101 total (95 PLR-grounded + 6 benchmark-specific) | Scenarios: 88

## 1. Source System

**Hamilton STAR(let) liquid handling robot** + 15 auxiliary instruments via **PyLabRobot** Python library.

The live system being projected:
- Hamilton STAR/STARlet/Vantage: programmable liquid handlers with 8 independent
  channels, optional 96-channel head, optional iSWAP robotic arm
- 15 auxiliary PLR instrument modules: plate reader, pump, scale, centrifuge,
  heater-shaker, thermocycler, SCARA arm, sealer, peeler, shaker, temperature
  controller, tilter, incubator storage, powder dispenser, barcode scanner
- PyLabRobot: open-source lab automation library providing dry-run backends
  for all 16 modules (no hardware required)
- Standard SBS-format labware: 96-well plates, tip racks, troughs

This projection is **dry-run only**. No physical hardware is connected. Every
tool is grounded in a real PLR API method (annotated with `PLR: <Class>.<method>`)
or explicitly marked as `benchmark-specific`.

## 2. Structural Projection

| Entity | Real-World Counterpart | PLR Class | Backend |
|--------|----------------------|-----------|---------|
| STARLetDeck | STARlet deck (32 rail) | `STARLetDeck` | `STARChatterboxBackend` |
| PlateCarrier | 5-position plate carrier | `PLT_CAR_L5AC_A00` | — |
| TipCarrier | 5-position tip carrier | `TIP_CAR_480_A00` | — |
| Plate | 96-well flat-bottom (Corning 360µL) | `Plate` | VolumeTracker |
| Well | Single well | `Well` | volume (0–max_volume) |
| TipRack | 96-position tip rack | `TipRack` | TipTracker |
| TipSpot | Single tip position | `TipSpot` | has_tip |
| Trough | Hamilton 60mL V-bottom | `Trough` | VolumeTracker |
| LiquidHandler | 8-channel + optional 96-head + iSWAP | `LiquidHandler` | `STARDryRunBackend` |
| PlateReader | Absorbance/Fluorescence/Luminescence | `PlateReader` | `PlateReaderDryRunBackend` |
| Pump | Peristaltic pump | `Pump` | `PumpDryRunBackend` |
| Scale | Analytical balance | `Scale` | `ScaleDryRunBackend` |
| Centrifuge | Bucket centrifuge | `Centrifuge` | `CentrifugeDryRunBackend` |
| HeaterShaker | Heating + orbital shaking | `HeaterShaker` | `HeaterShakerDryRunBackend` |
| Thermocycler | PCR thermal cycler | `Thermocycler` | `ThermocyclerDryRunBackend` |
| Arm | SCARA robot arm | `ExperimentalSCARA` | `ArmDryRunBackend` |
| Sealer | Heat sealer | `Sealer` | `SealerDryRunBackend` |
| Peeler | Automated peel station | `XPeel` | `PeelerDryRunBackend` |
| Shaker | Dedicated plate shaker | `Shaker` | `ShakerDryRunBackend` |
| TempController | Precision temperature controller | `TemperatureController` | `TempControllerDryRunBackend` |
| Tilter | Plate tilter (±45°) | `Tilter` | `TilterDryRunBackend` |
| Storage | Incubator with plate storage | `Incubator` | `StorageDryRunBackend` |
| PowderDispenser | Solid powder dispenser | `PowderDispenser` | `PowderDispenserDryRunBackend` |
| BarcodeScanner | Plate/container barcode scanner | `BarcodeScanner` | `BarcodeScannerDryRunBackend` |

## 3. Action Projection

### 3.1 LiquidHandler (18 PLR-grounded tools)

| Tool | PLR Method | Duration |
|------|-----------|----------|
| `get_deck_state` | `LiquidHandler.summary()` + deck tree | 1s |
| `get_labware_state` | Resource.children → VolumeTracker/TipSpot | 1s |
| `get_mounted_tips` | `LiquidHandler.get_mounted_tips()` | 1s |
| `aspirate` | `LiquidHandler.aspirate([well], vols, use_channels)` | 3s |
| `dispense` | `LiquidHandler.dispense([well], vols, use_channels)` | 3s |
| `pick_up_tips` | `LiquidHandler.pick_up_tips(tip_spots, use_channels)` | 2s |
| `drop_tips` | `LiquidHandler.drop_tips(tip_spots, use_channels)` | 1s |
| `discard_tips` | `LiquidHandler.discard_tips(use_channels)` | 1s |
| `return_tips` | `LiquidHandler.return_tips(use_channels)` | 1s |
| `transfer` | `LiquidHandler.transfer(source, targets, ...)` | varies |
| `stamp` | `LiquidHandler.stamp(source, target, volume)` | varies |
| `aspirate96` | `LiquidHandler.aspirate96(plate, volume)` | 2s |
| `dispense96` | `LiquidHandler.dispense96(plate, volume)` | 2s |
| `pick_up_tips96` | `LiquidHandler.pick_up_tips96(tip_rack)` | 2s |
| `drop_tips96` | `LiquidHandler.drop_tips96(resource)` | 1s |
| `discard_tips96` | `LiquidHandler.discard_tips96()` | 1s |
| `move_plate` | `LiquidHandler.move_plate(plate, to)` | 3s |
| `move_lid` | `LiquidHandler.move_lid(lid, to)` | 3s |

### 3.2 PlateReader (5 PLR-grounded tools)

| Tool | PLR Method | Duration |
|------|-----------|----------|
| `plate_reader_open` | `PlateReader.open()` | 1s |
| `plate_reader_close` | `PlateReader.close()` | 1s |
| `read_absorbance` | `PlateReader.read_absorbance(wavelength, wells)` | 5s |
| `read_fluorescence` | `PlateReader.read_fluorescence(excitation, emission, ...)` | 5s |
| `read_luminescence` | `PlateReader.read_luminescence(focal_height, wells)` | 5s |

### 3.3 Pump (3 PLR-grounded tools)

| Tool | PLR Method | Duration |
|------|-----------|----------|
| `pump_run_duration` | `Pump.run_for_duration(speed, duration)` | duration_s |
| `pump_run_volume` | `Pump.pump_volume(speed, volume)` | volume/1000s |
| `pump_halt` | `Pump.halt()` | 0.5s |

### 3.4 Scale (3 PLR-grounded tools)

| Tool | PLR Method | Duration |
|------|-----------|----------|
| `scale_zero` | `Scale.zero()` | 0.5s |
| `scale_tare` | `Scale.tare()` | 0.5s |
| `scale_get_weight` | `Scale.get_weight()` | 1.0s |

### 3.5 Centrifuge (7 PLR-grounded tools)

| Tool | PLR Method | Duration |
|------|-----------|----------|
| `centrifuge_open_door` | `Centrifuge.open_door()` | 0.5s |
| `centrifuge_close_door` | `Centrifuge.close_door()` | 0.5s |
| `centrifuge_lock_door` | `Centrifuge.lock_door()` | 0.5s |
| `centrifuge_go_to_bucket1` | `Centrifuge.go_to_bucket1()` | 1.0s |
| `centrifuge_go_to_bucket2` | `Centrifuge.go_to_bucket2()` | 1.0s |
| `centrifuge_lock_bucket` | `Centrifuge.lock_bucket()` | 0.5s |
| `centrifuge_spin` | `Centrifuge.spin(g, duration, acceleration)` | duration_s |

### 3.6 HeaterShaker (5 PLR-grounded tools)

| Tool | PLR Method | Duration |
|------|-----------|----------|
| `hs_set_temperature` | `HeaterShaker.set_temperature(temperature)` | 0.5s |
| `hs_get_temperature` | `HeaterShaker.get_temperature()` | 0.5s |
| `hs_shake` | `HeaterShaker.shake(speed, duration)` | duration_s |
| `hs_stop_shaking` | `HeaterShaker.stop_shaking()` | 0.5s |
| `hs_deactivate` | `HeaterShaker.deactivate()` | 0.5s |

### 3.7 Thermocycler (6 PLR-grounded tools)

| Tool | PLR Method | Duration |
|------|-----------|----------|
| `tc_close_lid` | `Thermocycler.close_lid()` | 0.5s |
| `tc_open_lid` | `Thermocycler.open_lid()` | 0.5s |
| `tc_set_lid_temp` | `Thermocycler.set_lid_temperature(temperature)` | 0.5s |
| `tc_set_block_temp` | `Thermocycler.set_block_temperature(temperature)` | 0.5s |
| `tc_get_block_temp` | `Thermocycler.get_block_current_temperature()` | 0.5s |
| `tc_deactivate` | `Thermocycler.deactivate_block()` + `deactivate_lid()` | 0.5s |

### 3.8 Arm — SCARA Robot (11 PLR-grounded tools)

| Tool | PLR Method | Duration |
|------|-----------|----------|
| `arm_home` | `ExperimentalSCARA.home()` | 2.0s |
| `arm_move_to` | `ExperimentalSCARA.move_to(CartesianCoords)` | 1.0s |
| `arm_move_to_safe` | `ExperimentalSCARA.move_to_safe()` | 1.0s |
| `arm_approach` | `ExperimentalSCARA.approach(CartesianCoords, access)` | 1.0s |
| `arm_pick_up_resource` | `ExperimentalSCARA.pick_up_resource(position, width)` | 2.0s |
| `arm_drop_resource` | `ExperimentalSCARA.drop_resource(position)` | 1.0s |
| `arm_open_gripper` | `ExperimentalSCARA.open_gripper(gripper_width)` | 0.5s |
| `arm_close_gripper` | `ExperimentalSCARA.close_gripper(gripper_width)` | 0.5s |
| `arm_get_position` | `ExperimentalSCARA.get_cartesian_position()` | 0.5s |
| `arm_get_gripper_state` | `ExperimentalSCARA.is_gripper_closed()` | 0.5s |
| `arm_halt` | `ExperimentalSCARA.halt()` | 0.5s |

### 3.9 Sealer (5 PLR-grounded tools)

| Tool | PLR Method | Duration |
|------|-----------|----------|
| `sealer_open` | `Sealer.open()` | 0.5s |
| `sealer_close` | `Sealer.close()` | 0.5s |
| `sealer_seal` | `Sealer.seal(temperature, duration)` | duration_s |
| `sealer_set_temperature` | `Sealer.set_temperature(temperature)` | 0.5s |
| `sealer_get_temperature` | `Sealer.get_temperature()` | 0.5s |

### 3.10 Peeler — XPeel (9 PLR-grounded tools)

| Tool | PLR Method | Duration |
|------|-----------|----------|
| `peeler_seal_check` | `XPeelBackend.seal_check()` | 0.5s |
| `peeler_peel` | `XPeelBackend.peel(begin_location, fast, adhere_time)` | 2.5s |
| `peeler_move_conveyor_in` | `XPeelBackend.move_conveyor_in()` | 1.0s |
| `peeler_move_conveyor_out` | `XPeelBackend.move_conveyor_out()` | 1.0s |
| `peeler_move_elevator_up` | `XPeelBackend.move_elevator_up()` | 0.5s |
| `peeler_move_elevator_down` | `XPeelBackend.move_elevator_down()` | 0.5s |
| `peeler_advance_tape` | `XPeelBackend.advance_tape()` | 0.5s |
| `peeler_get_tape_remaining` | `XPeelBackend.get_tape_remaining()` | 0.5s |
| `peeler_get_status` | `XPeelBackend.get_status()` | 0.5s |

### 3.11 Shaker — Dedicated (4 PLR-grounded tools)

| Tool | PLR Method | Duration |
|------|-----------|----------|
| `shaker_lock_plate` | `Shaker.lock_plate()` | 0.5s |
| `shaker_unlock_plate` | `Shaker.unlock_plate()` | 0.5s |
| `shaker_shake` | `Shaker.shake(speed, duration)` | duration_s |
| `shaker_stop_shaking` | `Shaker.stop_shaking()` | 0.5s |

### 3.12 TemperatureController (4 PLR-grounded tools)

| Tool | PLR Method | Duration |
|------|-----------|----------|
| `temp_controller_set_temperature` | `TemperatureController.set_temperature(temperature, passive)` | 0.5s |
| `temp_controller_get_temperature` | `TemperatureController.get_temperature()` | 0.5s |
| `temp_controller_deactivate` | `TemperatureController.deactivate()` | 0.5s |
| `temp_controller_wait_for_temperature` | `TemperatureController.wait_for_temperature(timeout, tolerance)` | waits |

### 3.13 Tilter (2 PLR-grounded + 2 benchmark-local tools)

| Tool | PLR Method | Duration |
|------|-----------|----------|
| `tilter_set_angle` | `Tilter.set_angle(absolute_angle)` | 0.5s |
| `tilter_tilt` | `Tilter.tilt(relative_angle)` | 0.5s |
| `tilter_get_angle` *(benchmark-local)* | Reads backend state; no dedicated PLR getter | 0.5s |
| `tilter_return_to_level` *(benchmark-local)* | Convenience wrapper around `set_angle(0.0)` | 0.5s |

### 3.14 Storage — Incubator (9 PLR-grounded tools)

| Tool | PLR Method | Duration |
|------|-----------|----------|
| `storage_open_door` | `Incubator.open_door()` | 0.5s |
| `storage_close_door` | `Incubator.close_door()` | 0.5s |
| `storage_set_temperature` | `Incubator.set_temperature(temperature)` | 0.5s |
| `storage_get_temperature` | `Incubator.get_temperature()` | 0.5s |
| `storage_start_shaking` | `Incubator.start_shaking(frequency)` | 0.5s |
| `storage_stop_shaking` | `Incubator.stop_shaking()` | 0.5s |
| `storage_store_plate` | `Incubator.take_in_plate(site)` | 1.0s |
| `storage_retrieve_plate` | `Incubator.fetch_plate_to_loading_tray(plate_name)` | 1.0s |
| `storage_get_free_sites` | `Incubator.get_num_free_sites()` | 0.5s |

### 3.15 PowderDispenser (2 PLR-grounded tools)

| Tool | PLR Method | Duration |
|------|-----------|----------|
| `powder_dispense` | `PowderDispenser.dispense(resources, powders, amounts)` | 2.0s |
| `powder_dispense_multi` | `PowderDispenser.dispense(...)` with lists | 2.0s |

### 3.16 BarcodeScanner (1 PLR-grounded tool)

| Tool | PLR Method | Duration |
|------|-----------|----------|
| `barcode_scan` | `BarcodeScanner.scan()` | 1.0s |

### 3.17 Benchmark-Specific Tools (not PLR-backed)

| Tool | Source | Duration |
|------|--------|----------|
| `add_workflow_note` | `LabState.notes` append | 1s |
| `submit_protocol` | `LabState.submissions` append | 1s |
| `list_workspace_files` | Benchmark workspace directory | 0.5s |
| `get_workspace_file` | Benchmark workspace directory | 0.5s |
| `tilter_get_angle` | Reads backend state; no dedicated PLR getter | 0.5s |
| `tilter_return_to_level` | Convenience wrapper around `set_angle(0.0)` | 0.5s |

**Summary:** 95 PLR-grounded + 6 benchmark-specific = **101 total tools**

## 4. State Projection

### 4.1 Instrument State (LabState fields)

Each instrument has a dedicated field in `LabState`, initialized via factory functions
in `state.py` and tracked by corresponding dry-run backends in `backend.py`:

| Field | Type | Factory |
|-------|------|---------|
| `deck` | `STARLetDeck` | `create_star_deck()` |
| `liquid_handler` | `LiquidHandler` | `create_liquid_handler()` |
| `plate_reader` | `PlateReader` | `create_plate_reader()` |
| `pump` | `Pump` | `create_pump()` |
| `scale` | `Scale` | `create_scale()` |
| `centrifuge` | `Centrifuge` | `create_centrifuge()` |
| `heater_shaker` | `HeaterShaker` | `create_heater_shaker()` |
| `thermocycler` | `Thermocycler` | `create_thermocycler()` |
| `arm` | `ExperimentalSCARA` | `create_arm()` |
| `sealer` | `Sealer` | `create_sealer()` |
| `peeler` | `XPeel` | `create_peeler()` |
| `shaker` | `Shaker` | `create_shaker()` |
| `temp_controller` | `TemperatureController` | `create_temp_controller()` |
| `tilter` | `Tilter` | `create_tilter()` |
| `storage` | `Incubator` | `create_storage()` |
| `powder_dispenser` | `PowderDispenser` | `create_powder_dispenser()` |
| `barcode_scanner` | `BarcodeScanner` | `create_barcode_scanner()` |

### 4.2 Event Types

Every tool execution produces events tracked in `LabState.events`. Key event families:

| Instrument | Event Types |
|-----------|------------|
| Deck/Labware | `inspection.labware`, `inspection.mounted_tips` |
| LiquidHandler | `tips.picked_up`, `tips.dropped`, `tips.discarded`, `tips.returned`, `transfer.aspirated`, `transfer.dispensed`, `transfer.completed`, `stamp.completed` |
| 96-Head | `tips96.picked_up`, `tips96.dropped`, `tips96.discarded`, `transfer96.aspirated`, `transfer96.dispensed` |
| iSWAP | `plate.moved`, `lid.moved`, `resource.moved` |
| PlateReader | `reader.opened`, `reader.closed`, `readout.created` |
| Pump | `pump.run_duration`, `pump.run_volume`, `pump.halted` |
| Scale | `scale.zeroed`, `scale.tared`, `scale.weight_read` |
| Centrifuge | `centrifuge.door_opened`, `centrifuge.door_closed`, `centrifuge.door_locked`, `centrifuge.bucket1`, `centrifuge.bucket2`, `centrifuge.bucket_locked`, `centrifuge.spin` |
| HeaterShaker | `hs.temp_set`, `hs.temp_read`, `hs.shake`, `hs.shake_stop`, `hs.deactivated` |
| Thermocycler | `tc.lid_closed`, `tc.lid_opened`, `tc.lid_temp_set`, `tc.block_temp_set`, `tc.block_temp_read`, `tc.deactivated` |
| Arm | `arm.homed`, `arm.moved_to`, `arm.safe`, `arm.approached`, `arm.picked_up`, `arm.dropped`, `arm.gripper_opened`, `arm.gripper_closed`, `arm.position_read`, `arm.gripper_state`, `arm.halted` |
| Sealer | `sealer.sealed`, `sealer.opened`, `sealer.closed`, `sealer.temp_set`, `sealer.temp_read` |
| Peeler | `peeler.seal_checked`, `peeler.peeled`, `peeler.conveyor_in`, `peeler.conveyor_out`, `peeler.elevator_up`, `peeler.elevator_down`, `peeler.tape_advanced`, `peeler.tape_checked`, `peeler.status_checked` |
| Shaker | `shaker.plate_locked`, `shaker.plate_unlocked`, `shaker.shaking`, `shaker.stopped` |
| TempController | `tc.set_temp`, `tc.read_temp`, `tc.deactivated`, `tc.temp_reached` |
| Tilter | `tilter.angle_set`, `tilter.tilted`, `tilter.angle_read` |
| Storage | `storage.door_opened`, `storage.door_closed`, `storage.temp_set`, `storage.temp_read`, `storage.shaking_started`, `storage.shaking_stopped`, `storage.plate_stored`, `storage.plate_retrieved`, `storage.free_sites_checked` |
| Powder | `powder.dispensed`, `powder.dispensed_multi` |
| Barcode | `barcode.scanned` |
| Workspace | `workspace.listed`, `workspace.read` |
| Protocol | `workflow_note.created`, `protocol.submitted` |
| Error | `error.instrument_busy`, `error.insufficient_well_volume` |

### 4.3 Hidden from Agent

- `expected_resolution.created` events: verifier ground truth (`visible_to_agent=False`)
- `noise_schedule.json`: pre-generated OD600 measurement noise
- `fault_schedule.json`: pre-generated instrument fault triggers
- Verifier state: check definitions, predicate logic, attribution rules

## 5. Temporal Projection

Actions have non-zero duration tracked by `LabClock`. The `clock_time` field is
recorded in every event and used by temporal verifier predicates (`after`, `fresh`).

| Action Family | Typical Duration |
|--------------|-----------------|
| Inspection (get_deck_state, get_labware_state, get_mounted_tips) | 1s |
| Single-channel pipetting (aspirate, dispense) | 3s |
| 96-head pipetting (aspirate96, dispense96) | 2s |
| Tip management (pick_up, drop, discard, return) | 1–2s |
| iSWAP moves (move_plate, move_lid) | 3s |
| PlateReader reads (absorbance, fluorescence, luminescence) | 5s |
| Pump operations | duration_s or volume/1000s |
| Scale reads (zero, tare, weigh) | 0.5–1.0s |
| Centrifuge spin | duration_s |
| HeaterShaker shake | duration_s |
| Thermocycler operations | 0.5s per set/read |
| Arm movements (home, move, approach, pick, drop) | 0.5–2.0s |
| Sealer seal | duration_s |
| Peeler operations (conveyor, elevator, peel) | 0.5–2.5s |
| Shaker shake | duration_s |
| Storage operations (door, store, retrieve) | 0.5–1.0s |
| Powder dispense | 2.0s |
| Barcode scan | 1.0s |
| Notes, submissions | 1s |

## 6. Stochastic Projection

### 6.1 OD600 Measurement Noise

```
name: od600_measurement_noise
source_status: assumption_for_calibration
distribution: normal(mean=0, sd=0.03), Box-Muller, clipped to [-0.1, 0.1]
seed_behavior: deterministic per (task_seed, readout_id, well)
agent_visible: observed OD600 = true_od600 + noise
hidden: true OD600 and sampled noise per (seed, readout, well)
attribution: environment_noise
```

Applied when `stochastic_config.od600_noise = True` in TaskSpec.

### 6.2 Instrument Busy Fault

```
name: instrument_busy_fault
source_status: assumption_for_calibration
distribution: per-readout-attempt Bernoulli(p=fault_prob), deterministic per seed
seed_behavior: pre-generated FaultSchedule per (task_seed, readout_spec)
agent_visible: error response with code "instrument_busy"
hidden: fault_schedule.json with retry count up to max_retries=2
attribution: environment_fault
```

### 6.3 Source Status Summary

| Element | Source Status | Basis |
|---------|-------------|-------|
| od600_measurement_noise | `assumption_for_calibration` | σ=0.03 placeholder |
| instrument_busy_fault | `assumption_for_calibration` | Scenario-configured probabilities |
| base OD600 = 0.82 | `assumption_for_calibration` | Not calibrated against real QC readings |

## 7. Safety Projection

- **Dry-run only**: All operations execute against dry-run backends
- **No live hardware**: No physical instruments connected
- **No network side effects**: No LIMS/ELN integration
- **Task isolation**: Each run directory independent; seeds guarantee reproducibility
- **No real reagents**: Volumes tracked in VolumeTracker; no physical liquids or powders

## 8. Verifier Projection

### 8.1 Check Types

- **Terminal checks**: Minimum counts, presence/absence of operations, safety interlock violations
- **Temporal checks**: Ordering constraints (`after`, `before`), freshness (`readout_after_cycling`), bracketing (`labware_before_*` / `labware_after_*`)
- **Cross-validation checks**: Instrument A independently verifies instrument B's work (e.g., scale verifies pump dispense weight, peeler verifies sealer's seal)
- **Resource checks**: Tip availability, well volume sufficiency, free storage sites
- **Structured refusal checks**: Agent must produce structured `reason_code` + `evidence` when refusing due to resource limits

### 8.2 Attribution Labels (Direction 2)

| Label | Meaning |
|-------|---------|
| `agent_error` | Agent made wrong decision or violated protocol |
| `environment_fault` | Instrument fault occurred (agent may or may not recover) |
| `agent_recovery_failure` | Fault occurred but agent did not recover |
| `success_despite_fault` | Agent correctly mitigated noise/fault |
| `ambiguous` | Reading near band boundary; reasonable people could disagree |
| `environment_noise` | Noise made reading unreliable but agent handled it |

### 8.3 Strict Admission (Direction 4)

`lab_strict_admission.py` validates verifier correctness via oracle + mutant runners:
- **Oracle**: Hardcoded correct tool sequence → verifier must pass
- **Mutant**: Hardcoded faulty sequence → verifier must fail with exact expected check names

Currently 11 scenarios have strict admission coverage (56/56 cases passing).

## 9. Known Gaps

| Gap | Status |
|-----|--------|
| `projection_contract.md` out of sync with 101-tool reality | **Fixed (this update)** |
| OD600 simulation not PLR PlateReader | Benchmark-local; PLR PlateReader available but not wired |
| No LiquidClass calibration | Simple volume arithmetic; real Hamilton uses correction curves |
| No concurrent channels | Simulator runs channels sequentially |
| No real incubation | No timer/temperature model for biological processes |
| No collision consequences | Warnings logged but operations not blocked |
| No tube rack physical model | `tube_transfer_qc` uses source plate wells as proxy |
| No multi-liquid mixing | Liquid enum exists in PLR but not used in scenarios |
| `pump_run_volume` requires calibration | `PumpDryRunBackend` lacks calibration data; `TypeError` on volume-based pumping |
| No plate washing | PLR `plate_washing` module is empty (no API surface) |

## 10. Public Visual Replay

`replay.py` provides an opt-in `STARReplayRecorder` for hosted or published
runs. It attaches to the sampled world's actual `LiquidHandler`, records the
commands emitted by PyLabRobot's `Visualizer`, groups them by completed API Gym
tool call, and writes `public_replay_projection.json` atomically.

The recorder is deliberately not enabled for ordinary sampling or admission,
so generating benchmark tasks does not create a thread or visualization
artifact. A host starts and stops it explicitly:

```python
start_public_replay(run_dir)
# Run agent tool calls through the normal world dispatcher.
stop_public_replay(run_dir)
```

The artifact declares the tested compatibility pair:

```text
capture: PyLabRobot 0.2.1
viewer:  PyLabRobot 0.2.2
replay protocol: 0.1.0
```

The split is intentional. Version 0.2.1 preserves the admitted benchmark's
volume-tracking behavior but its wheel omits visualizer image assets. Version
0.2.2 supplies the complete viewer assets, but running the benchmark itself on
0.2.2 changes the OT-2 serial-dilution final-volume result. Datalox Gated
Runtime validates both versions before publishing or displaying the replay.

The visual replay covers renderer-native STAR deck, resource, tip, and liquid
state changes. It does not claim continuous arm motion. Standalone instruments
such as the plate reader, centrifuge, and thermocycler are represented in the
world state and tool trace but are not yet rendered in the PyLabRobot deck
view. A later multi-service timeline should compose those views without
inventing PyLabRobot commands for instruments outside its visual root.
