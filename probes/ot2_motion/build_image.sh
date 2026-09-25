#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
# Explicit context works with both Docker builders and excludes local secrets,
# unrelated worlds, virtualenvs, and retained source captures.
COPYFILE_DISABLE=1 tar --format=ustar --exclude='__pycache__' --exclude='*.pyc' -cf - \
  api_gym/__init__.py api_gym/instrument_models api_gym/source_packs.py \
  probes/ot2_motion tests/instrument_models \
  | docker build "$@" -f probes/ot2_motion/Dockerfile -t datalox-ot2-motion:phase0 -
