# Enzyme activity v0

This slice freezes the Phase 0 interface and implements the Phase 1 coupled
scientific model for an alkaline-phosphatase/pNPP relative-rate workflow.
Readings are synthetic modeled observations routed through the exact
PyLabRobot 0.2.1 absorbance interface. They are not physical CLARIOstar data.

Canonical units are uL, nmol, mM, seconds, dimensionless absorbance, and
delta-absorbance per minute. Install with
`pip install -e '.[dev,enzyme-activity]'` and run
`python -m pytest tests/enzyme_activity -q`.

The numeric plate adaptation, kinetics, detector, noise, timing, fit, and repeat
thresholds are explicitly provisional. The 405 nm pNPP signal, 37 degC method,
and blank-corrected rate basis are grounded in the cited AP0100 procedure.

## Reproducible integration bundle

The tested repositories are this API Gym checkout starting from `8c922bdf` and
`datalox-gated-runtime` commit
`c0cdcd538af89733971cbb4cc7b314c367aac015`. The native worker uses a separate
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
