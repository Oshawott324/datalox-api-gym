# Enzyme activity v0

This slice freezes the Phase 0 interface, implements the coupled scientific
model and native execution contract, admits the Phase 3 scenario verifier, and
exports Phase 4 completed-run evidence for an alkaline-phosphatase/pNPP
relative-rate workflow.
Readings are synthetic modeled observations routed through the exact
PyLabRobot 0.2.1 absorbance interface. They are not physical CLARIOstar data.

Canonical units are uL, nmol, mM, seconds, dimensionless absorbance, and
delta-absorbance per minute. Install with
`pip install -e '.[dev,enzyme-activity]'` and run
`python -m pytest tests/enzyme_activity -q`.

The numeric plate adaptation, kinetics, detector, noise, timing, fit, and repeat
thresholds are explicitly provisional. The 405 nm pNPP signal, 37 degC method,
and blank-corrected rate basis are grounded in the cited AP0100 procedure.

## Phase 3 admission

Six frozen families exercise nominal measurement, unsuitable high activity,
delayed acquisition, an interrupted series, changing reagent background, and
sample/plate lineage. Their public tasks contain the SOP requirements but omit
private concentrations, fault indices, future observations, and oracle choices.
The admitted v0 instances provide at most two assay plates and two confirmed
operator transfers. A completed transfer leaves the measured plate in the
reader and a separately identified fresh plate on the OT-2 deck. A recovery
therefore prepares a new reaction from remaining stock, transfers that new
plate, and retains the first plate's immutable readings under their original
lineage.

The report contract requires a disposition, immutable SAMPLE-A, BLANK, and
REF-AP measurement IDs, an explicit fit window, preparation-supported dilution,
rate units, and uncertainty. The independent verifier recomputes the fit from
trusted acquired records without calling the production reference analysis. It
also checks plate revision/settings provenance, acquisition time, operator
confirmation, reference-control performance, sample coverage, unresolved
evidence, and resource limits. Every check states whether it was applicable.

Trusted tests contain literal hand-calculated traces, a positive and an
alternative-valid fit for every family, plus targeted scientific, provenance,
and resource mutants. These fixtures establish correctness inside the authored
model only; they do not establish physical assay fidelity.

## Phase 4 completed-run view

`api_gym.worlds.enzyme_activity_v0.visualization` maps immutable world run
evidence into the runtime's `datalox_visualization_run_v1` contract. The world
records one public snapshot after every completed operation, including its
public result and all observations acquired by that logical time. The exporter
does not read `trusted_summary`, private scenario conditions, seeds, or future
reader schedule.

The `enzyme_assay_v1` runtime renderer shows native preparation volumes on the
OT-2 deck, explicit operator handoff state, a 96-well acquisition heatmap and
growing raw-absorbance series, then the submitted fit window and selected
sample/blank/reference points. Its nominal and fresh-reaction recovery
documents upload through the existing visualization endpoint. Browser QA checks
every step at desktop, tablet, and 439 px app-panel widths, with the timeline on
the left and plate identity, latest data timestamp, and all 96 wells aligned to
the evidence.

## Reproducible integration bundle

The tested repositories are this API Gym checkout starting from `8c922bdf` and
`datalox-gated-runtime` commit
`87691ba1417c6ae8eab46b46588158798d3a2d3b`. The native worker uses a separate
Python environment containing exactly `opentrons==9.1.1` and
`opentrons-shared-data==9.1.1`; its absolute interpreter path is supplied in
`DATALOX_OT2_WORKER_PYTHON`. The application/test environment installs this
repository with `.[dev,enzyme-activity]` and installs the pinned runtime commit.

Run the complete contract with both repository `src` roots on `PYTHONPATH` and
the native interpreter environment variable set:

```text
python -m pytest tests/enzyme_activity -q
```

The world entry point is `world/implementation.py:create_world`; trusted reset
creates a fresh native process and reseeds the modeled reader from the episode.
Public contracts and task material are under this directory. Mutable scientific
state, latent amounts, seeds, verifier data, and native receipts remain in the
runtime's private run database and worker process. Agent observations are the
explicit `agent_observation` projection; the agent must not receive the run
database or simulator source tree.

Native integration tests exercise both the nominal episode and a high-activity
fresh-dilution recovery across two native plate exchanges. Phase 3 scenario
admission remains deterministic at the scientific verifier boundary; an
external model rollout over all six families remains Phase 5 work.
