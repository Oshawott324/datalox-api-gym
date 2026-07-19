# Datalox API Gym — LabLongRun

Resettable dry-run environments for training and evaluating tool-using agents
in lab automation. Agents practice lab workflows repeatedly without touching
real hardware.

## Overview

API Gym provides **API worlds** — stateful fake systems with seeded scenarios,
tool contracts, hidden verifier state, and exportable run evidence.

| World | Backend | Scenarios | Tools | Instruments |
|-------|---------|:---------:|:-----:|:-----------:|
| `pylabrobot_star_v0` | Hamilton STAR (ChatterBox) | **91** | **101** | 16 |
| `pylabrobot_lab_v0` | Opentrons OT-2 (ChatterBox) | 20 | 8 | 2 |
| `unitelabs_plate_qc_v0` | SQLite | 1 | 7 | 1 |
| `billing_support_v0` | SQLite | 3 | 10 | — |

### Key Capabilities

- **16 instrument modules** on STAR: liquid handler, 96-head, iSWAP arm,
  centrifuge, heater-shaker, thermocycler, sealer, peeler, shaker,
  temperature controller, tilter, storage, powder dispenser, barcode scanner,
  pump, scale, plate reader
- **101 tools**: 99 grounded in real PyLabRobot API methods + 2 benchmark protocol tools
- **91 STAR scenarios** across 17 instrument categories + 14 cross-instrument (xover)
- **Tiered environment state** (L1/L2/L3): event-driven reducers, cross-instrument facts,
  reusable predicate functions — all verifiers use the state system
- **Strict admission**: 66 oracle + mutant test cases validating verifier correctness
- **Two-phase tool selection**: agent selects relevant tools from a compact catalog
  before execution, cutting per-trajectory tokens by **60%**
- **Unified trajectory runner**: one script for all worlds, no demo server required
- **Seeded determinism**: same seed + same scenario → identical initial state
- **Temporal + state verifier**: checks process invariants (ordering, freshness,
  provenance, safety interlocks) plus final-state consistency
- **Web demo**: LLM-driven execution at `http://127.0.0.1:8080`

---

## Quickstart

```bash
# Install
pip install -e '.[dev]'

# List all STAR scenarios
python gen_trajectory/run.py --world pylabrobot_star_v0 --list-scenarios

# Run a single trajectory (requires DEEPSEEK_API_KEY)
python gen_trajectory/run.py --world pylabrobot_star_v0 --scenario spin_down_qc --seed 42

# Compare with/without tool filtering
python gen_trajectory/run.py --world pylabrobot_star_v0 --scenario spin_down_qc --no-tool-filter

# Start web demo
python gen_trajectory/demo/server.py
# Open http://127.0.0.1:8080

# Run strict admission quality checks
python -c "
from api_gym.lab_strict_admission import run_all
result = run_all()
print(f'Strict: {result[\"strict_pass\"]}/{result[\"strict_total\"]}')
print(f'Experimental: {result[\"experimental_pass\"]}/{result[\"experimental_total\"]}')
"
```

---

## Architecture

### Tiered Environment State (`environment.py`)

The environment state system operates at three levels, all driven by PLR API events:

```
Events (from services)
  → L1: Per-instrument reducers (16 dataclasses, one per instrument module)
        - Each reducer processes one event → updates instrument state
        - Violations detected at event time (e.g. spin_without_lock)
        - Uses dataclasses.replace() for immutability
  → L2: Cross-instrument facts (pure L1 state reading, zero event scanning)
        - centrifuge_safe, sealer_safe, shaker_safe, peeler_safe
        - hs_before_tc, pump_halted_before_tilter
        - plate_where_it_should_be, incubation_chain_complete
  → L3: Reusable predicate functions → (bool, str)
        - is_centrifuge_safe, is_sealer_safe, is_shaker_safe
        - is_peeler_safe, is_hs_before_tc, is_pump_halted_before_tilter
        - is_plate_where_it_should_be, is_incubation_chain_complete
        - is_pcr_chain_complete, is_seal_peel_chain_complete
        - is_plate_weighing_valid
```

All 91 verifiers use L1 state checks + L3 predicates. Violations are caught at the
earliest possible point (L1 reducers at event time), not retroactively.

### Tool Selection Optimization

The STAR world has 101 tools, but a single-instrument scenario typically needs only
6–10. The two-phase approach eliminates this overhead:

```
Phase 1: Agent receives a compact catalog (~2,800 tokens, grouped by instrument)
         → calls select_tools with the 6–15 tools it actually needs

Phase 2: Only the selected tools' full JSON schemas are sent each turn
         → per-turn tool overhead drops from ~10,000 → ~1,000 tokens
         → total trajectory tokens drop ~54% on average
```

| Scenario | Tools needed | Before | After | Saving |
|----------|:------------:|--------|-------|:------:|
| Simple (centrifuge) | 6 | 147k | 57k | 61% |
| Medium (HS combo) | 9 | 228k | 105k | 54% |
| Complex (xover) | 16 | 518k | 312k | 40% |
| Full workflow | 22 | 682k | 451k | 34% |

### Verifier + Strict Admission

- **91 verifier functions** — one per scenario
- **66 admission cases** — oracle (correct behavior) + mutant (error injection)
- Each mutant must produce exact failure codes; near-miss cases must pass
- 44 strict cases + 22 experimental choreography cases

---

## STAR Scenario Catalog (91 total)

### Liquid Handler — Core Operations (29 scenarios)

Plate transfer, serial dilution, multi-channel, tube transfer, stamp, trough-to-plate,
multi-dispense, tip exhaustion, tip return/reuse, mounted tips query, liquid switching,
three-liquid, low reagent (well + trough), balanced load, multi-plate, lid handling,
plate stamp, shake mix, parallel stamp, stamp replicate, workspace protocol.

**Fault & noise**: instrument_fault, fault_and_noise, noisy_readout, borderline,
stale_deck, stale_after_move.

### Instrument Modules (48 scenarios, 16 categories)

| Instrument | Scenarios | Example |
|-----------|:---------:|---------|
| iSWAP Robotic Arm | 4 | `arm_plate_transfer_qc`, `arm_position_verify_qc`, `arm_halt_recovery_qc`, `arm_stale_state_combo_qc` |
| Centrifuge | 2 | `spin_down_qc`, `door_safety_qc` |
| Heater-Shaker | 2 | `heat_shake_combo_qc`, `heat_incubate_qc` |
| Thermocycler | 3 | `pcr_heat_qc`, `pcr_lid_safety_qc`, `pcr_cool_down_qc` |
| Sealer | 3 | `seal_plate_qc`, `seal_door_safety_qc`, `seal_temp_verify_qc` |
| Peeler | 3 | `peel_plate_qc`, `peel_no_seal_qc`, `peel_tape_monitor_qc` |
| Shaker | 3 | `shaker_mix_qc`, `shaker_continuous_qc`, `shaker_lock_safety_qc` |
| Temperature Controller | 3 | `temp_control_incubate_qc`, `temp_control_verify_qc`, `temp_control_timeout_qc` |
| Tilter | 3 | `tilter_drain_qc`, `tilter_multi_angle_qc`, `tilter_safety_qc` |
| Storage | 3 | `storage_store_retrieve_qc`, `storage_capacity_qc`, `storage_env_monitor_qc` |
| Powder Dispenser | 3 | `powder_dispense_qc`, `powder_multi_dispense_qc`, `powder_amount_validate_qc` |
| Barcode Scanner | 3 | `barcode_scan_qc`, `barcode_verify_qc`, `barcode_multi_scan_qc` |
| Pump | 4 | `pump_calibrated_dispense_qc`, `pump_fill_trough_qc`, `pump_halt_recovery_qc`, `pump_multi_step_qc` |
| Scale | 3 | `tare_weigh_qc`, `zero_scale_qc`, `gravimetric_qc` |
| Plate Reader | 4 | `reader_door_qc`, `fluorescence_qc`, `luminescence_qc`, `multi_mode_qc` |

### Cross-Instrument (14 xover scenarios)

| Pair | Scenarios |
|------|-----------|
| Arm + Reader | `arm_reader_xover_qc` |
| Arm + Scale | `arm_scale_xover_qc` |
| Centrifuge + Reader | `centrifuge_reader_xover_qc` |
| Centrifuge + Scale | `centrifuge_scale_xover_qc` |
| HS + Reader | `hs_reader_xover_qc` |
| HS + Thermocycler | `hs_thermocycler_xover_qc` |
| PCR + Reader | `pcr_reader_xover_qc` |
| Pump + Scale | `pump_scale_xover_qc` |
| TempCtrl + Reader | `tempctrl_reader_xover_qc` |
| Sealer + Peeler | `sealer_peeler_xover_qc` |
| Tilter + Pump | `tilter_pump_xover_qc` |
| Shaker + Reader | `shaker_reader_xover_qc` |
| Powder + Scale | `powder_scale_xover_qc` |
| Barcode + Storage | `barcode_storage_xover_qc` |

Each xover scenario involves two instruments cooperating on one task. Verifiers
check both single-instrument invariants and cross-instrument ordering/safety.

---

## Tools (101 total)

99 tools are grounded in real [PyLabRobot](https://docs.pylabrobot.org) API methods
(annotated `PLR: <ClassName>.<method>`). 2 are benchmark-specific protocol tools.

| Category | Tools | PLR Module |
|----------|:-----:|------------|
| Inspection & Workspace | 5 | `LiquidHandler`, Resource API |
| Single-Channel Pipetting | 7 | `LiquidHandler` |
| 96-Channel Head | 6 | `LiquidHandler` |
| iSWAP Robotic Arm | 20 | `LiquidHandler`, `STARLetDeck` |
| Centrifuge | 7 | `Centrifuge` |
| Heater-Shaker | 5 | `InhecoThermoShake` |
| Thermocycler | 6 | `Thermocycler` |
| Sealer | 6 | `Sealer` |
| Peeler | 8 | `Peeler` |
| Shaker | 4 | `Shaker` |
| Temperature Controller | 4 | `InhecoThermoShake` |
| Tilter | 4 | `Tilter` |
| Storage | 9 | `Cytomat` |
| Powder Dispenser | 2 | `PowderDispenser` |
| Barcode Scanner | 1 | `BarcodeScanner` |
| Pump | 3 | `Pump` |
| Scale | 3 | `Scale` |
| Plate Reader | 5 | `SynergyH1` |
| Protocol & Submission | 2 | benchmark-specific |

---

## Design Principles

### Projection Contract (`projection_contract.md`)

Every world declares what is modeled, what is omitted, and what assumptions
underpin each element. Agents are evaluated against a **controlled projection**
of a real system — not a claim of full simulation.

### Grounded Instrument Behavior

All tool calls go through the real PyLabRobot API → DryRunBackend chain:

```
LLM tool call → dispatch_tool → services.<function> → PLR API method
  → DryRunBackend (state update) → insert_event → tool result
```

Events are the single source of truth for state reconstruction. The dry-run
backends simulate instrument behavior without hardware.

### Quality Control

```bash
# Strict admission: oracle + mutant validation
python -c "
from api_gym.lab_strict_admission import run_all
print(run_all())
"
```

Each scenario's verifier is validated with:
- **Oracle**: correct trajectory → all checks pass
- **Mutant**: injected error → exact failure code produced
- **Near-miss**: borderline correct behavior → still passes

---

## Layout

```text
api_gym/
  lab_strict_admission.py           Strict admission oracle + mutant runners
  worlds/
    pylabrobot_star_v0/             Hamilton STAR world (91 scenarios, 101 tools)
      projection_contract.md        Modeled vs omitted behavior
      environment.py                L1/L2/L3 tiered environment state
      sampler.py                    91 TaskSpecs + scenario builders
      verifier.py                   91 verifier functions (L1 + L3 checks)
      services.py                   PLR service wrappers (101 tool handlers)
      tools.py                      OpenAI tool schemas + dispatcher
      state.py                      STARLetDeck, carriers, LabState, LabClock
    pylabrobot_lab_v0/              OT-2 world (20 scenarios, 8 tools)
      projection_contract.md
      stochastic.py                 NoiseSchedule, FaultSchedule
      sampler.py                    TaskSpec + scenarios
      verifier.py                   Terminal + temporal predicates
      services.py / services_ot2.py
      tools.py / state.py / state_ot2.py
    unitelabs_plate_qc_v0/          SQLite-based plate QC (1 scenario)
    billing_support_v0/             SQLite-based billing/support (3 scenarios)

gen_trajectory/
  run.py                            Unified trajectory runner (all worlds)
  demo/
    server.py                       FastAPI backend (multi-world, LLM execution)
    static/index.html               Web UI

scripts/
  package_benchmark.py              Benchmark packaging + verification

docs/
  contract-compiled-tiered-verification.md   Tiered verification IR proposal
```

---

## Research Directions

The benchmark supports several research threads:

| Direction | Status | Description |
|-----------|:------:|-------------|
| **Multi-instrument coordination** | ✅ | 14 xover scenarios, 16 instrument modules |
| **Tiered state verification** | ✅ | L1 (event-time) → L2 (cross-instrument) → L3 (predicates) |
| **Strict admission** | ✅ | 66 oracle + mutant cases with exact failure codes |
| **Tool selection optimization** | ✅ | Compact catalog → agent selects tools → 60% token reduction |
| **Long-horizon trajectories** | 🔬 | 25–30 turn xover/full-workflow scenarios |
| **Failure attribution** | ✅ | agent_error / ambiguous / success_despite_fault / recovery_failure |
| **Scaffold realism** | ✅ | Workspace files, protocol artifacts, plate maps |
| **RL training infrastructure** | 🔬 | Unified runner, token metrics, tool filtering |

---

## Token Economy

Per-trajectory token measurements on `deepseek-v4-pro`:

| Scenario | Turns | No filter | With filter | Savings |
|----------|:-----:|----------:|------------:|:-------:|
| `spin_down_qc` | 10 | 124,553 | 49,858 | 60% |
| Weighted avg (91 scenarios) | 14 | 228,480 | 104,134 | 54% |

Estimated RL training scale (batch=64, steps=1000):

| Metric | Before | After |
|--------|--------|-------|
| Total trajectories | 64,000 | 64,000 |
| Total tokens | 14.6B | 6.7B |
| GPU time (8×H100) | ~2,000 h | ~940 h |
