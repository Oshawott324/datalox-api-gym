#!/usr/bin/env bash
set -euo pipefail

readonly bind_host="0.0.0.0"
readonly bind_port="${PORT:-7860}"
readonly runtime_commit="ce5372623ddbab41dab169e4e0d0fc1c000a56c2"
readonly runtime_repository="https://github.com/Oshawott324/datalox-gated-runtime.git"
temporary_paths=()

cleanup_temporary_paths() {
  if ((${#temporary_paths[@]})); then
    rm -rf "${temporary_paths[@]}"
  fi
}
trap cleanup_temporary_paths EXIT

install_runtime_from_local_source() {
  local source_dir="${DATALOX_RUNTIME_SOURCE}"
  local revision_file="${source_dir}/.datalox-source-revision"
  local build_dir

  if [[ ! -r "${revision_file}" ]]; then
    echo "DATALOX_RUNTIME_SOURCE must contain .datalox-source-revision." >&2
    exit 2
  fi
  if [[ "$(<"${revision_file}")" != "${runtime_commit}" ]]; then
    echo "DATALOX_RUNTIME_SOURCE does not match the pinned runtime commit." >&2
    exit 2
  fi

  build_dir="$(mktemp -d)"
  temporary_paths=("${build_dir}")
  cp -R "${source_dir}/." "${build_dir}/"

  python -m pip install \
    --user \
    --disable-pip-version-check \
    --no-build-isolation \
    --no-cache-dir \
    --no-deps \
    "${build_dir}"

  cleanup_temporary_paths
  temporary_paths=()
}

install_runtime_from_private_repository() {
  local credential_dir
  local fetched=0
  local attempt
  local source_dir
  credential_dir="$(mktemp -d)"
  source_dir="$(mktemp -d)"
  temporary_paths=("${credential_dir}" "${source_dir}")

  umask 077
  printf 'machine github.com\n  login x-access-token\n  password %s\n' \
    "${GITHUB_TOKEN}" >"${credential_dir}/.netrc"

  HOME="${credential_dir}" git -C "${source_dir}" init --initial-branch=main
  git -C "${source_dir}" remote add origin "${runtime_repository}"
  git -C "${source_dir}" sparse-checkout init --cone
  git -C "${source_dir}" sparse-checkout set src
  for attempt in 1 2 3; do
    if HOME="${credential_dir}" git -C "${source_dir}" \
      -c http.version=HTTP/1.1 \
      fetch \
      --depth=1 \
      --filter=blob:none \
      origin "${runtime_commit}"; then
      fetched=1
      break
    fi
    if ((attempt < 3)); then
      sleep "$((attempt * 2))"
    fi
  done
  if ((fetched != 1)); then
    echo "Private runtime fetch failed after three attempts." >&2
    exit 2
  fi
  HOME="${credential_dir}" git -C "${source_dir}" checkout --detach FETCH_HEAD
  if [[ "$(git -C "${source_dir}" rev-parse HEAD)" != "${runtime_commit}" ]]; then
    echo "Private runtime fetch did not resolve the pinned commit." >&2
    exit 2
  fi

  PYTHONUSERBASE=/home/user/.local \
  python -m pip install \
    --user \
    --disable-pip-version-check \
    --no-build-isolation \
    --no-cache-dir \
    --no-deps \
    "${source_dir}"

  cleanup_temporary_paths
  temporary_paths=()
  unset GITHUB_TOKEN
}

if [[ -n "${DATALOX_RUNTIME_SOURCE:-}" ]]; then
  install_runtime_from_local_source
elif [[ -n "${GITHUB_TOKEN:-}" ]]; then
  install_runtime_from_private_repository
else
  echo "Set GITHUB_TOKEN or mount an exact DATALOX_RUNTIME_SOURCE." >&2
  exit 2
fi

python -c '
from importlib.metadata import version

assert version("datalox-gated-runtime") == "0.1.0"
'
trap - EXIT

mkdir -p "${DATALOX_RUNS_ROOT:-/home/user/runs}"
exec uvicorn app:app --host "${bind_host}" --port "${bind_port}"
