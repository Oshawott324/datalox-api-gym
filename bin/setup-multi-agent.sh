#!/usr/bin/env bash
set -euo pipefail

# Datalox API Gym multi-agent setup
# Compatibility shim for the CLI-first install flow.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${1:-all}"

exec node "$REPO_ROOT/bin/datalox.js" install "$HOST" "${@:2}"
