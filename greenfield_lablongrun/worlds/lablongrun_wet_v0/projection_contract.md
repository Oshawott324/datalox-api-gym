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
- `hidden/task_metadata.json`;
- `hidden/verifier_expectations.json`;
- `hidden/oracle_plan.json`;
- `hidden/known_bad_plans.json`;
- `hidden/fault_schedule.json`;
- `hidden/noise_schedule.json`.

Agent-visible artifacts are limited to the output of
`export_agent_workspace(...)`: `agent_task.json`, the allowlisted public
`task.json`, source-ref metadata, `agent_visible_manifest.json`, and files under
`visible_artifacts/`. Internal task bundles and run directories are evaluator
workspaces and must not be used as an agent working directory. The public
manifest is content-addressed: every file has a SHA-256 digest and byte size, and
the complete record set has its own digest.

## Prompt-Disclosure Admission

Task prompts must state goals, legitimate scientific constraints, and available
observations without disclosing the reference action sequence, hidden fault
identity, expected outcome, or challenge-specific recovery action. This is a
semantic review boundary rather than a keyword filter.

Each template requires a review record in
`templates/prompt_disclosure_reviews.json`. The record is bound to the SHA-256
digest of the exact objective, agent instructions, and visible-artifact
templates together with every parameter that can be rendered into them.
Admission fails when the review is missing, rejected, incomplete, or
bound to a different digest. A prompt edit therefore invalidates the prior
approval automatically. Approval must come from a reviewer other than the prompt
author; code review is the enforcement point for that separation of duties.

## Temporal/Stochastic Assumptions

Time is logical. `wait` records elapsed seconds and ordering evidence; it does
not sleep or model real wall-clock instrument timing.

Each template declares its own `stochastic_source_status`. Generated schedules
are keyed by `environment_seed`; admission rejects schedules that are missing or
non-deterministic for that seed, and rejects non-empty schedules when a template
declares `none`.

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
