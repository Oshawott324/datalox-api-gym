# Projection Contract

## Scope

This world projects only the Agilent BioTek Synergy H1 workflow for monitoring
`Saccharomyces cerevisiae` growth. State is SQLite-backed and advances only
through `advance_logical_time`; no wall-clock sleep, provider API, backend, or
hardware operation exists.

## Source-grounded protocol

| Requirement | Value | Source ref |
|---|---:|---|
| Plate format | 96 wells | `agilent_app_note`, `agilent_technical_details` |
| Selected dilution replicates | 8 | `agilent_app_note` |
| Culture volume | 200 uL/well | `agilent_app_note` |
| Temperature | 30 C | `agilent_app_note` |
| Measurement | light scatter represented as absorbance at 600 nm | `agilent_app_note` |
| Cadence | 2 minutes | `agilent_app_note` |
| Duration | 20 hours | `agilent_app_note` |
| Agitation evidence | continuous orbital, 559 CPM, 1 mm amplitude | `agilent_app_note` |
| Long-kinetic evaporation control | adhesive-sealed plate | `agilent_app_note` |

The inclusive 0-to-20-hour schedule has 601 observations and the cadence
acceptance window is +/-5 logical seconds; both are `benchmark_defined`.

## Driver bridge gap

Installed PLR 0.2.1 exposes `shake(shake_type, frequency)` rather than
independent CPM/amplitude. Its source comment maps setting 3 to 567 CPM and
setting 1 to 1096 CPM. Executable v0 uses `ORBITAL` plus setting 3 as a closest
documented driver setting, labeled `assumption_for_calibration`. Exact 1 mm is
stored as protocol evidence but is neither encoded by the tool nor a verifier
pass condition. This gap prevents a claim of exact app-note agitation fidelity.

## Calibration assumptions

Initial 22 C and a 0.02 C/second deterministic ramp are
`assumption_for_calibration`. The deterministic logistic-shaped readout is only
stable synthetic evidence for workflow verification, not a biological model.

## Verification

Composable SQL checks inspect source contract state, stabilization evidence,
20-hour exposure, cadence deltas, uninterrupted setting-3 orbital state,
600 nm wavelength, eight-replicate coverage, and final decision evidence.
Verifier input is database state/events only; transcript text is ignored.

## Explicit omissions

No reader-busy, job overlap, partial-result, barcode, blank, external
incubator, provider execution, biological inference, independent amplitude
control, or physical timing semantics are modeled.
