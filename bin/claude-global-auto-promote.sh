#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
PACK_CACHE="${HOME}/.datalox/cache/datalox-trajectory-mcp"

payload="$(cat)"

if [ -f "$PROJECT_DIR/bin/datalox-auto-promote.js" ]; then
  printf '%s' "$payload" | node "$PROJECT_DIR/bin/datalox-auto-promote.js" --repo "$PROJECT_DIR"
  exit 0
fi

if [ -f "$PACK_CACHE/bin/datalox-auto-promote.js" ]; then
  printf '%s' "$payload" | node "$PACK_CACHE/bin/datalox-auto-promote.js" --repo "$PROJECT_DIR"
  exit 0
fi

exit 0
