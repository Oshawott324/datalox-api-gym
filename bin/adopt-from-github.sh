#!/usr/bin/env bash
set -euo pipefail

HOST_REPO="${1:-}"
PACK_REPO_URL="${2:-https://github.com/Complexity-LLC/datalox-pack.git}"
CACHE_ROOT="${HOME}/.datalox/cache"
PACK_CACHE="${CACHE_ROOT}/datalox-trajectory-mcp"

if [ -z "$HOST_REPO" ]; then
  echo "Usage: bash bin/adopt-from-github.sh /path/to/host-repo [pack-repo-url]"
  echo "Default pack repo URL: https://github.com/Complexity-LLC/datalox-pack.git"
  echo "Default local cache: ${PACK_CACHE}"
  exit 1
fi

mkdir -p "$CACHE_ROOT"

if [ -d "$PACK_CACHE/.git" ]; then
  git -C "$PACK_CACHE" pull --ff-only
else
  rm -rf "$PACK_CACHE"
  git clone --depth 1 "$PACK_REPO_URL" "$PACK_CACHE"
fi

bash "$PACK_CACHE/bin/adopt-host-repo.sh" "$HOST_REPO"
