# LabLongRun-Wet v0 Projection Contract

## Live/Scientific Workflow Being Projected

This world projects a wet-lab OD600 serial-dilution QC workflow: inspect run
artifacts, prepare a diluted culture sample with a liquid handler, transfer the
prepared sample to a QC plate, wait before readout, read absorbance at 600 nm,
and submit a continue/hold protocol decision with readout evidence.

The current OD600 templates are calibration-only benchmark fixtures. They do
not claim empirical biology coverage, growth dynamics, instrument noise, or
source-grounded failure biology.

## Action Semantics Grounded In Opentrons/PyLabRobot

Liquid-handling actions use source-analog semantics from Opentrons protocol
concepts:

- `pick_up_tip` and `drop_tip` follow tip attachment and disposal concepts.
- `aspirate`, `dispense`, and `mix` follow pipette liquid movement concepts.
- `wait` projects protocol delay as a logical delay event.
- deck, labware, well, and pipette observations project Opentrons deck/labware
  state into stable JSON.

The `read_absorbance` action uses the PyLabRobot `PlateReader.read_absorbance`
name as the primary naming source, with Opentrons absorbance-reader concepts as
secondary context.

## Benchmark-Local Semantics

The following behavior is benchmark-local and must be labeled as such in task
metadata and source refs:

- stable JSON observations and action results;
- file-based protocol artifact inspection through `get_protocol_artifact`;
- SQLite-backed volume, tip, cell-signal, readout, note, and submission ledgers;
- logical timestamps and logical wait records;
- deterministic OD600 value calculation from template state;
- `submit_protocol_decision` as the final verifier-facing protocol decision.

## Hidden State

Agents must not receive direct access to hidden state. Hidden state includes:

- `initial_state.sqlite` and per-run `state.sqlite`;
- `hidden/verifier_expectations.json`;
- `hidden/oracle_plan.json`;
- `hidden/known_bad_plans.json`;
- `hidden/fault_schedule.json`;
- `hidden/noise_schedule.json`.

Agent-visible artifacts are limited to `agent_task.json`, `task.json`, source
ref metadata, and files under `visible_artifacts/`.

## Temporal/Stochastic Assumptions

Time is logical. `wait` records elapsed seconds and ordering evidence; it does
not sleep or model real wall-clock instrument timing.

Current templates have `stochastic_source_status: none`. Generated bundles must
therefore include deterministic empty schedules for both faults and noise. Each
schedule is keyed by `environment_seed`, and admission must reject schedules
that are missing, non-deterministic for that seed, or non-empty while the
template declares no stochastic source.

## Safety/Live-Boundary Rule

This prototype is dry-run only. It must not call live hardware, live providers,
production credentials, Opentrons robots, PyLabRobot hardware backends, plate
readers, or lab scheduling systems. Adding live execution requires an explicit
live-gate policy and user approval outside this projection contract.

## Verifier Projection

The hidden verifier projects scientific workflow success into state and
workflow-invariant checks:

- required visible artifacts were inspected;
- final well volumes match deterministic template expectations;
- the expected OD600 readout exists and is inside the configured acceptance
  band;
- the final decision matches the expected decision;
- the final decision cites a readout produced in the run;
- submission ordering follows readout creation;
- the dry-run boundary remains intact.

Known-bad plans must declare the exact expected verifier or tool failure code.
For the current wrong-decision negative control, the expected verifier check is
`decision_matches_expected`.

## Known Gaps

- No empirical OD600 calibration curves or plate-reader noise model.
- No stochastic liquid-handling fault model.
- No contamination, evaporation, carryover, growth, or instrument drift model.
- No live hardware or provider semantics.
- No additional biology templates beyond the current calibration-only OD600
  fixtures.
