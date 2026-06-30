# Projection Contract — pylabrobot_star_v0

## 1. Source System

**Hamilton STAR(let) liquid handling robot** via **PyLabRobot** Python library
with **STARChatterboxBackend** (dry-run simulator).

The live system being projected:
- Hamilton STAR/STARlet/Vantage: programmable liquid handlers with 8 independent
  channels, optional 96-channel head, optional iSWAP robotic arm
- PyLabRobot: open-source lab automation library providing the
  `STARChatterboxBackend` simulator (logs commands, no hardware required)
- Standard SBS-format labware: 96-well plates, tip racks, troughs, tube racks
- Plate and tip carriers for rail-based deck layout
- Hamilton LiquidClass system for pipetting calibration

This projection is **dry-run only**. No physical STAR hardware is connected.

## 2. Structural Projection

| Entity | Real-World Counterpart | Modeled Properties |
|--------|----------------------|-------------------|
| STARLetDeck | STARlet deck (32 rail) | rail layout, waste block, trash, core96 trash |
| PlateCarrier | 5-position plate carrier (PLT_CAR_L5AC_A00) | site assignment, resource holding |
| TipCarrier | 5-position tip carrier (TIP_CAR_480_A00) | site assignment, tip rack holding |
| Plate | 96-well flat-bottom (Corning 360µL) | 96 Wells with VolumeTracker |
| Well | Single well | volume (0–max_volume), cross-section (circle) |
| TipRack | 96-position tip rack | TipSpots with TipTracker |
| TipSpot | Single tip position | has_tip, tip type (300µL standard) |
| Trough | Hamilton 60mL V-bottom trough | VolumeTracker, height-volume calibration data |
| LiquidHandler | 8-channel + optional 96-head + optional iSWAP | backend simulator |
| Readout | OD600 absorbance measurement | plate_id, wavelength_nm, wells, values |

**Not modeled:**
- Temperature, humidity, evaporation
- Incubation timing (no integrated incubator resource)
- Multi-channel Liquid class variation per liquid type
- Collision detection consequences (warnings logged but not enforced)
- Nested tip racks
- Heater/shaker modules

## 3. Action Projection

13 tools map to real STAR operations, all backed by STARChatterboxBackend:

| Tool | Real STAR Operation | PLR Backing | Duration |
|------|-------------------|-------------|----------|
| `get_deck_state` | List carriers + labware | `deck_summary()` | 1s |
| `get_labware_state` | Inspect one resource | Resource tree walk | 1s |
| `aspirate` | Single-channel pick_up_tip + aspirate | `lh.pick_up_tips()` + `lh.aspirate()` | 3s |
| `dispense` | Single-channel dispense + return_tip | `lh.dispense()` + `lh.return_tips()` | 3s |
| `discard_tips` | Discard tips to trash | `lh.discard_tips()` | 1s |
| `pick_up_tips96` | 96-head pick up full rack | `lh.pick_up_tips96()` | 2s |
| `aspirate96` | 96-head aspirate from plate | `lh.aspirate96()` | 2s |
| `dispense96` | 96-head dispense to plate | `lh.dispense96()` | 2s |
| `discard_tips96` | 96-head discard to waste | `lh.discard_tips96()` | 1s |
| `move_plate` | iSWAP arm move plate | `lh.move_plate()` | 3s |
| `read_absorbance` | Plate reader OD measurement | **benchmark-local simulation** | 5s |
| `add_workflow_note` | Record annotation | `LabState.notes` append | 1s |
| `submit_protocol` | Submit QC decision | `LabState.submissions` append | 1s |

**Benchmark-local (not PLR-backed):**
- `read_absorbance` — PyLabRobot has a separate `PlateReader` class with
  `PlateReaderChatterboxBackend`. Our implementation simulates OD600 as a
  function of well volume (0.82 if ≥50µL, scaled otherwise) with optional
  noise from a pre-generated `NoiseSchedule`. This is NOT the PLR PlateReader.
  **source_status: benchmark-local**

## 4. State Projection

### Visible to Agent (via tool responses)
- Deck layout: carriers and their rail assignments, labware at each site
- Well volumes: current liquid volume per well (0 to 350µL)
- Well metadata: contents description, purpose labels
- Tip status: whether each tip spot has a tip
- Readout history: past OD600 measurements with well-level values
- Instrument status: 96-head installed, iSWAP installed
- Event log: visible events (transfers, readouts, notes, submissions)

### Hidden from Agent
- `expected_resolution` events: verifier ground truth
- `noise_schedule.json`: pre-generated measurement noise values
- `fault_schedule.json`: pre-generated instrument fault triggers
- Verifier state: check definitions, predicate logic, attribution rules

## 5. Temporal Projection

Actions have non-zero duration tracked by `LabClock`:

| Action | Duration |
|--------|----------|
| `get_deck_state`, `get_labware_state` | 1s |
| `aspirate`, `dispense` | 3s each |
| `discard_tips` | 1s |
| `pick_up_tips96`, `aspirate96`, `dispense96` | 2s each |
| `discard_tips96` | 1s |
| `move_plate` (iSWAP) | 3s |
| `read_absorbance` | 5s |
| `add_workflow_note`, `submit_protocol` | 1s |

Clock time is recorded in every event (`clock_time` field) and used by temporal
verifier predicates (`after`, `fresh`).

**Not modeled:**
- Real STAR firmware timing (aspirate speed varies by liquid class)
- Concurrent operation timing (channels operate sequentially in simulator)
- Incubator delays
- Operator transfer time

## 6. Stochastic Projection

### OD600 Measurement Noise

```
name: od600_measurement_noise
source_status: assumption_for_calibration
distribution: normal(mean=0, sd=0.03), Box-Muller from stdlib random, clipped to [-0.1, 0.1]
seed_behavior: deterministic per (task_seed, readout_id, well)
agent_visible_observation: observed OD600 = true_od600 + noise
hidden_truth: true OD600 and sampled noise value per (seed, readout, well)
verifier_effect: check borderline decision handling, multiple-readout averaging
attribution_label: environment_noise
```

Applied when `stochastic_config.od600_noise = True` in TaskSpec.

### Instrument Busy Fault (planned, not yet in STAR scenarios)

```
name: instrument_busy_fault
source_status: assumption_for_calibration
distribution: per-readout-attempt Bernoulli(p=0.15), deterministic per seed
seed_behavior: pre-generated FaultSchedule per (task_seed, readout_spec)
agent_visible_observation: error response with code "instrument_busy"
hidden_truth: fault_schedule.json with retry count
verifier_effect: check retry and recovery behavior
attribution_label: environment_fault
max_retries: 2
```

### Stochastic Source Status Summary

| Element | Source Status | Basis |
|---------|-------------|-------|
| od600_measurement_noise | `assumption_for_calibration` | No real spectrophotometer data; σ=0.03 is a placeholder |
| instrument_busy_fault | `assumption_for_calibration` | No real instrument availability logs; p=0.15 is a placeholder |
| base OD600 = 0.82 | `assumption_for_calibration` | Not calibrated against real QC control readings |

## 7. Safety Projection

- **Dry-run only**: All operations execute against STARChatterboxBackend
- **No live hardware**: No physical STAR, no liquid handling, no tip consumption
- **No network side effects**: No LIMS/ELN integration
- **Task isolation**: Each run directory independent, seeds guarantee reproducibility
- **No real reagents**: Volumes tracked in VolumeTracker, no physical liquids

## 8. Verifier Projection

### Terminal State Checks
- Minimum transfers completed (count, volume, target well)
- Required readouts performed (plate, wavelength, wells)
- Protocol submitted with valid decision
- OD600 monotonicity (for dilution series)

### Temporal Predicates (Direction 3)
- `after(A, B)` — event A must occur before event B
- `fresh(observation, usage, max_age)` — observation must be recent when used
- `never(pattern)` — forbidden event pattern must not appear
- Resource availability checks (tip count, well volume)

### Attribution Labels (Direction 2)
- `agent_error` — agent made wrong decision (overdrawn, tip reuse, no plate move)
- `environment_noise` — noise made reading unreliable
- `ambiguous` — reading near band boundary with noise
- `success_despite_fault` — agent mitigated noise/fault correctly
- `agent_recovery_failure` — fault occurred but agent didn't recover

Each check is tagged `predicate_type: "terminal"` or `"temporal"` for transparency.

## 9. Known Gaps

| Gap | Reason |
|-----|--------|
| No PlateReader integration | Using benchmark-local OD600 simulation; PLR PlateReader available but not wired |
| No LiquidClass calibration | Transfers use simple volume arithmetic; real Hamilton uses correction curves |
| No concurrent channels | Simulator runs channels sequentially |
| No real incubation | `add_workflow_note` simulates incubation; no timer/temperature model |
| No collision consequences | Warnings logged but operations not blocked |
| No tube rack physical model | `tube_transfer_qc` repurposes source plate wells as proxy for tubes |
| No STAR firmware error simulation | Using PLR resource-layer errors (TooLittleLiquidError, NoTipError) only |
| No multi-liquid mixing | Liquid enum exists in PLR but not used in scenario definitions |
| No lid operations | iSWAP `move_lid` available but no scenario uses it |
