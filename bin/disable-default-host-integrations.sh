#!/usr/bin/env bash
set -euo pipefail

# Compatibility shim for the CLI-first disable flow.
# Removes installed default host integrations.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${1:-all}"

exec node "$REPO_ROOT/bin/datalox.js" disable "$HOST" "${@:2}"
