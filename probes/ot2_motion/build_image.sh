#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
# The phase-0 context deliberately excludes interactive-world tests and local
# CAD captures. Its default command remains the original 31-test probe.
COPYFILE_DISABLE=1 tar --format=ustar --exclude='__pycache__' --exclude='*.pyc' -cf - \
  api_gym/__init__.py api_gym/instrument_models api_gym/source_packs.py \
  probes/ot2_motion/__init__.py probes/ot2_motion/__main__.py \
  probes/ot2_motion/Dockerfile probes/ot2_motion/inspect_assets.py \
  probes/ot2_motion/reference.py probes/ot2_motion/requirements.lock \
  probes/ot2_motion/sources/source_pack.json \
  probes/ot2_motion/sources/docs_index.jsonl \
  probes/ot2_motion/sources/assets.jsonl \
  tests/instrument_models/test_geometry_collision.py \
  tests/instrument_models/test_ot2_motion_reference.py \
  tests/instrument_models/test_ot2_motion_sources.py \
  | docker build "$@" -f probes/ot2_motion/Dockerfile -t datalox-ot2-motion:phase0 -
