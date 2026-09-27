#!/usr/bin/env bash
set -euo pipefail

: "${DATALOX_OT2_WORKER_PYTHON:?DATALOX_OT2_WORKER_PYTHON must name the pinned native worker interpreter}"

python -m pytest -q -p no:cacheprovider \
  tests/instrument_models/test_ot2_packaging.py \
  tests/instrument_models/test_ot2_observations.py \
  tests/instrument_models/test_ot2_motion_world.py \
  tests/instrument_models/test_ot2_motion_runtime_bridge.py

python -m probes.ot2_motion.interactive_example \
  --native-python "$DATALOX_OT2_WORKER_PYTHON"
