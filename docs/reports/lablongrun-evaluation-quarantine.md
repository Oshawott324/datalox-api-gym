# LabLongRun Evaluation Quarantine

Status date: 2026-08-28

The existing OD600 prompts and all results derived from them are calibration
artifacts, not valid model-evaluation evidence. Their public task materials
disclose an ordered reference procedure; several variants also name the fault
and expected recovery behavior.

Do not use these generated directories for benchmark scores or capability
claims:

- `runs/greenfield_lablongrun_phase1/`
- `runs/greenfield_lablongrun_phase2/`
- `runs/greenfield_lablongrun_phase2_all/`
- `runs/greenfield_lablongrun_low_source_once/`
- `runs/greenfield_lablongrun_model_rollouts/`

The oracle-pass and known-bad-failure results remain useful for testing the
world dynamics and verifier. They do not establish task difficulty.

Release requires all of the following:

1. The public task schema contains no evaluator metadata.
2. Every agent-visible file passes the visibility scanner.
3. A disclosure review approves the exact public-template digest.
4. The agent runs from the allowlisted public workspace, outside the evaluator
   filesystem namespace.
5. Oracle and known-bad controls still produce their declared outcomes.
6. Fresh model rollouts are collected only after the first five gates pass.
