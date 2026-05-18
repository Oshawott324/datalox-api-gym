#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST_REPO="${1:-}"

if [ -z "$HOST_REPO" ]; then
  echo "Usage: bash bin/adopt-host-repo.sh /path/to/host-repo"
  exit 1
fi

exec node "$REPO_ROOT/bin/datalox.js" adopt "$HOST_REPO" "${@:2}"
