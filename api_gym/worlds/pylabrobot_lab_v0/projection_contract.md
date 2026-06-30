# Projection Contract — pylabrobot_lab_v0

## 1. Source System

**Opentrons OT-2 liquid handling robot** via **PyLabRobot** Python library.

The live system being projected:
- Opentrons OT-2: a programmable pipetting robot with 8-channel pipette, 12-slot deck, and standard SBS-format labware
- PyLabRobot: an open-source lab automation library providing dry-run simulation backends (Chatterbox, OpentronsOT2Simulator)
- Standard protocols: plate QC transfer, serial dilution, absorbance reading (OD600)

This projection is a **dry-run only** environment. No physical OT-2 hardware is connected or required.

## 2. Structural Projection

| Entity | Real-World Counterpart | Modeled Properties |
|--------|----------------------|-------------------|
| Deck | OT-2 deck (12 SBS slots) | slot layout, child assignment |
| Plate | 96-well flat-bottom plate (CellTreat 350µL) | name, slot location, 96 wells |
| Well | Single well in a plate | volume (0-max_volume), cross-section (circle), contents metadata |
| TipRack | Opentrons 300µL tip rack | 96 tip spots, each with has_tip flag |
| TipSpot | Single tip position | has_tip boolean |
| LiquidHandler | OT-2 pipette (single channel 0) | head channels, backend simulator |
| Readout | OD600 absorbance measurement | plate_id, wavelength_nm, wells, values |

**Not modeled:**
- Multi-channel pipetting (only channel 0 used)
- Trash/waste container
- Temperature or humidity
- Evaporation over time
- Liquid class / viscosity variations

## 3. Action Projection

Seven tools map to real OT-2 operations:

| Tool | Real Semantics | Simulation Behavior |
|------|---------------|-------------------|
| `get_deck_state` | List labware on deck | Returns deck slot assignments |
| `get_labware_state` | Inspect one labware item | Returns well volumes, tip status, metadata |
| `aspirate` | Pick up tip + draw liquid | Calls `lh.pick_up_tips` + `lh.aspirate` via simulator; mutates VolumeTracker; 3s duration |
| `dispense` | Dispense liquid + return tip | Calls `lh.dispense` + `lh.return_tips` via simulator; mutates VolumeTracker; 3s duration |
| `read_absorbance` | Measure OD600 | Simulated reading based on well volume, with optional noise; 5s duration |
| `add_workflow_note` | Record a note | Appends to notes list; no physical action |
| `submit_protocol` | Submit final QC decision | Records decision with rationale and evidence |

**Benchmark-local tools (not present in real OT-2):**
- `submit_protocol` — in reality this would be an external LIMS/ELN action
- `add_workflow_note` — annotation not natively supported by OT-2

## 4. State Projection

### Visible to Agent (via tool responses)

- Deck layout: which labware is in which slot
- Well volumes: current liquid volume per well (0 to max_volume)
- Well metadata: contents description, purpose labels
- Tip status: whether each tip spot has a tip
- Readout history: past OD600 measurements with well-level values
- Event log: visible events (transfers, readouts, notes)

### Hidden from Agent

- `expected_resolution` events: the verifier's ground truth for this scenario
- `noise_schedule.json`: pre-generated OD600 measurement noise values
- `fault_schedule.json`: pre-generated instrument fault triggers
- Verifier state: check definitions, attribution logic

## 5. Temporal Projection

Actions have non-zero duration, tracked by `LabClock`:

| Action | Duration |
|--------|----------|
| `get_deck_state` | 1s |
| `get_labware_state` | 1s |
| `aspirate` | 3s (pick_up_tip 1.5s + aspirate 1.5s) |
| `dispense` | 3s (dispense 1.5s + return_tips 1.5s) |
| `read_absorbance` | 5s |
| `add_workflow_note` | 1s |
| `submit_protocol` | 1s |

**Not modeled:**
- Incubation delays
- Centrifugation / shaking
- Operator transfer time between stations
- Real instrument scheduling / queuing

## 6. Stochastic Projection

### OD600 Measurement Noise

```
name: od600_measurement_noise
source_status: assumption_for_calibration
distribution: normal(mean=0, sd=0.03), clipped to [-0.1, 0.1]
seed_behavior: deterministic per (task_seed, readout_id)
agent_visible_observation: observed OD600 = true_od600 + noise
hidden_truth: true OD600 and sampled noise value
verifier_effect: check borderline decision handling
attribution_label: environment_noise
```

Applied only when `stochastic_config.od600_noise = True` in TaskSpec.

### Instrument Busy Fault

```
name: instrument_busy_fault
source_status: assumption_for_calibration
distribution: per-readout-attempt fault probability p=0.15, deterministic per seed
seed_behavior: pre-generated fault schedule, deterministic per (task_seed, readout_spec)
agent_visible_observation: error response with code "instrument_busy"
hidden_truth: fault schedule and retry count
verifier_effect: check retry and recovery behavior
attribution_label: environment_fault
max_retries: 2
```

Applied only when `stochastic_config.fault_prob > 0` in TaskSpec.

## 7. Safety Projection

- **Dry-run only**: All operations execute against simulator backends (Chatterbox or OpentronsOT2Simulator)
- **No live hardware**: No physical OT-2, no real liquid handling
- **No network side effects**: No LIMS/ELN integration, no database writes outside run directory
- **No reagent consumption**: Volumes are tracked in VolumeTracker, no real reagents used
- **Task isolation**: Each run directory is independent, seeds guarantee reproducibility

## 8. Verifier Projection

The verifier checks both terminal state and process invariants:

### Terminal State Checks
- No overdrawn wells (negative volume)
- Required transfers completed (minimum count, correct wells, correct volumes)
- Required readouts performed (correct plate, wavelength, wells)
- Protocol submitted with valid decision

### Temporal Predicates
- `after(A, B)`: Event A must occur before event B in the event log
- `fresh(observation, usage, max_age)`: Observation must be recent enough when used
- `never(pattern)`: Forbidden event pattern must not appear
- `resource_available(resource, required)`: Resource must be sufficient at time of use

### Attribution
- Failure classification into agent_error / environment_fault / environment_noise / agent_recovery_failure / ambiguous / success_despite_fault

## 9. Known Gaps

| Gap | Reason |
|-----|--------|
| No temperature or evaporation modeling | Requires domain-specific physical models not available |
| No cross-contamination chemistry | Only tip-reuse pattern detection, not actual chemical carryover |
| No multi-channel pipetting | Single-channel focus keeps task complexity manageable |
| No real lab scheduling | Discrete clock is linear, no concurrent instrument usage |
| No incubation timing | Tasks focus on liquid handling + measurement, not biology |
| No liquid class variation | All transfers use uniform volumes, no viscosity/wetting effects |
| Hardcoded OD600 base value (0.82) | No real spectrophotometer curve model; value is calibration placeholder |
| No LIMS integration | submit_protocol is a benchmark-local abstraction |
