#!/usr/bin/env bash
set -euo pipefail

# Compatibility shim for the CLI-first install flow.
# Installed default host integrations.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${1:-all}"

exec node "$REPO_ROOT/bin/datalox.js" install "$HOST" "${@:2}"
