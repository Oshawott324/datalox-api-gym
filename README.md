# Datalox API Gym — LabLongRun

Resettable dry-run environments for training and evaluating tool-using agents.
Agents practice lab automation workflows repeatedly without touching real hardware.

## Overview

API Gym provides **API worlds** — stateful fake systems with seeded scenarios,
tool contracts, hidden verifier state, and exportable run evidence. Currently
supports **4 worlds** across lab automation and business operations:

| World | Backend | Scenarios | Tools |
|-------|---------|:---------:|:-----:|
| `pylabrobot_star_v0` | Hamilton STAR (ChatterBox) | 24 | 15 |
| `pylabrobot_lab_v0` | Opentrons OT-2 (ChatterBox) | 10 | 8 |
| `pylabrobot_lab_v0_ot2` | Opentrons OT-2 (3D Visualizer) | 10 | 8 |
| `unitelabs_plate_qc_v0` | SQLite | 1 | 8 |
| `billing_support_v0` | SQLite | 3 | ~10 |

### Key Capabilities

- **Multi-backend dry-run**: ChatterBox, OpentronsOT2Simulator, STARChatterboxBackend
- **13 lab tools**: single-channel pipetting, 96-head parallel, iSWAP robotic arm, plate reader, workspace files
- **24 STAR scenarios** covering protocol complexity, resource constraints, faults, staleness, liquid types, and measurement noise
- **Seeded determinism**: same seed + same trajectory → same observations (stochastic or deterministic)
- **Temporal verifier**: checks process invariants (ordering, freshness, provenance), not just terminal state
- **Failure attribution**: classifies failures as `agent_error` / `ambiguous` / `success_despite_fault` / `agent_recovery_failure`
- **State snapshot & replay**: record, reset, and replay full lab trajectories
- **Web demo**: LLM-driven execution + live 3D visualization (OT-2) at `http://127.0.0.1:8080`

---

## Quickstart

```bash
# Install
pip install -e '.[dev]'

# Start web demo (OT-2 + STAR + visualizer)
python gen_trajectory/demo/server.py
# Open http://127.0.0.1:8080

# Verify all STAR scenarios sample correctly
python scripts/package_benchmark.py --verify-all

# Run STAR admission quality checks
python -c "
from api_gym.worlds.pylabrobot_star_v0.admission import run_admission_checks
print(run_admission_checks()['overall_ok'])
"
```

---

## Design Principles

### Projection Contract (`projection_contract.md`)

Every world ships a 9-dimension projection contract declaring what is modeled,
what is omitted, and what assumptions underpin each stochastic element. Agents
are evaluated against a **controlled projection** of a real system — not a
claim of full simulation.

### Structured Verification (`long-horizon-lab-agent-directions.md`)

The benchmark is organized around five research directions:

| # | Direction | Status |
|---|-----------|:------:|
| 1 | **LabLongRun-Bench** — 24 tasks in one automation family with timed, resource-constrained, stochastic dynamics | ✅ |
| 2 | **Failure Attribution** — seeded replay + counterfactual checks separate agent error from environment dynamics | ✅ |
| 3 | **Temporal/Provenance Verifier** — composable predicates over state, trajectory, timing, freshness, and provenance | ✅ |
| 4 | **State-Diff Process Rewards** — per-action diffs as dense training signal (not implemented by design) | — |
| 5 | **Lab Scaffold Realism** — workspace files, protocol artifacts, plate maps as agent-facing input | ✅ |

### Quality Control (`lablongrun-projection-stochastic-plan.md`)

Every stochastic element is documented with source status, distribution
parameters, and seed behavior. Admission checks verify determinism,
source-status labeling, attribution validity, and temporal coverage before
a world can be considered benchmark-ready.

---

## Direction Detail

### Direction 1 — LabLongRun-Bench

24 STAR scenarios organized by dimension:

**Happy Path (4)**: `plate_transfer_qc`, `serial_dilution_qc`,
`multi_channel_qc`, `tube_transfer_qc`

**96-Head Parallel (2)**: `parallel_stamp_qc`, `stamp_replicate_qc`

**Trough Bulk Reagent (2)**: `trough_to_plate_qc`, `low_reagent_trough_qc`

**iSWAP Robotic Arm (3)**: `iswap_plate_move_qc`, `iswap_lid_star_qc`,
`stale_after_move_star_qc`

**Resource Exhaustion (4)**: `limited_tips_star_qc`, `tip_exhaustion_96_star_qc`,
`low_reagent_well_star_qc`, `multi_plate_qc`

**Instrument Fault (2)**: `instrument_fault_star_qc`, `fault_and_noise_star_qc`

**Stale State (2)**: `stale_deck_star_qc`, `stale_after_move_star_qc`

**Measurement Noise (3)**: `borderline_star_qc`, `noisy_readout_star_qc`,
`fault_and_noise_star_qc`

**Liquid Type Switching (2)**: `liquid_switch_star_qc`, `three_liquid_star_qc`

**Scaffold Realism (1)**: `workspace_protocol_star_qc`

Every dimension has ≥ 2 scenarios (no single-point coverage).

### Direction 2 — Failure Attribution

Attribution labels in verifier output:

| Label | Meaning | Example trigger |
|-------|---------|----------------|
| `agent_error` | Agent made wrong decision | Overdrawn well, tip reuse, skipped re-inspect |
| `ambiguous` | Cannot clearly attribute | OD600 near band boundary with noise |
| `success_despite_fault` | Agent recovered correctly | Retried after instrument fault |
| `agent_recovery_failure` | Fault occurred but agent didn't recover | No retry after instrument fault |

**Counterfactual admission test** demonstrates that naive pass/fail is
misleading: a run where all terminal checks pass but the temporal
`fresh(inspect, transfer)` check fails is correctly attributed to
`agent_error`, not counted as success.

Seeded replay ensures the same fault/noise schedule on replay.

### Direction 3 — Temporal/Provenance Verifier

Five predicate families, each check tagged `predicate_type: "temporal"`:

| Predicate | Signature | Checks |
|-----------|-----------|--------|
| `after` | `after(events, pattern_a, pattern_b)` | A must occur before B |
| `fresh` | `fresh(events, obs, use, max_age_s)` | Observation must be recent when used |
| `never` | `never(events, forbidden)` | Forbidden pattern must not appear |
| `resource_available` | `resource_available(events, type, n)` | Resource must be sufficient |
| `provenance` | `provenance(events, obs, source)` | Observation must trace back to source event |

Used in 8 of 24 scenario verifiers. Each verifier output clearly separates
terminal checks from temporal checks.

### Direction 5 — Lab Scaffold Realism

Workspace file system:
- `list_workspace_files` tool — discover available protocol files
- `get_workspace_file` tool — read protocol, plate map, inventory
- `workspace_protocol_star_qc` scenario requires agent to read files before acting
- Verifier checks agent consulted required files

---

## Quality Control

```bash
python -c "
from api_gym.worlds.pylabrobot_star_v0.admission import run_admission_checks
import json; print(json.dumps(run_admission_checks(), indent=2))
"
```

Four admission checks:
1. **Stochastic determinism** — same seed → same noise/fault schedule
2. **Source status** — every stochastic element has valid `source_status`
3. **Attribution labels** — all labels in valid set, no mislabeling
4. **Temporal coverage** — every verifier includes temporal predicates

---

## Layout

```text
api_gym/worlds/
  pylabrobot_lab_v0/       OT-2 world (chatterbox + 3D visualizer)
    projection_contract.md
    stochastic.py           NoiseSchedule, FaultSchedule
    sampler.py              TaskSpec + 10 scenarios + SCENARIOS
    verifier.py             Terminal + temporal predicates + attribution
    services.py / services_ot2.py
    tools.py / state.py / state_ot2.py
  pylabrobot_star_v0/       Hamilton STAR world
    projection_contract.md
    sampler.py              TaskSpec + 24 scenarios
    verifier.py             Terminal + temporal predicates + attribution
    services.py             STAR chatterbox operations (13 tools)
    tools.py                15 tool definitions
    admission.py            4 admission quality checks
    state.py                STARLetDeck + carriers + LabClock
  unitelabs_plate_qc_v0/    SQLite-based plate QC
  billing_support_v0/       SQLite-based billing/support

gen_trajectory/demo/
  server.py                 FastAPI backend (4 worlds, LLM execution, replay)
  static/index.html         Web UI with dynamic scenario loading + 3D viz

scripts/
  package_benchmark.py      Benchmark packaging + verification

long-horizon-lab-agent-directions.md            Research directions
lablongrun-projection-stochastic-plan.md        Quality standards
lablongrun-bench-implementation-plan.md         Implementation blueprint
```
