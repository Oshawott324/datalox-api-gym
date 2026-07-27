#!/usr/bin/env bash
set -euo pipefail

readonly image="${IMAGE:-datalox-science-growth-space:local}"
readonly host_port="${HOST_PORT:-17860}"
readonly container_name="datalox-growth-smoke-$$"
readonly base_url="http://127.0.0.1:${host_port}"
readonly runtime_commit="ce5372623ddbab41dab169e4e0d0fc1c000a56c2"
readonly space_host="datalox-growth-smoke.hf.space"
runtime_archive=""

cleanup() {
  docker rm --force "${container_name}" >/dev/null 2>&1 || true
  if [[ -n "${runtime_archive}" ]]; then
    rm -rf "${runtime_archive}"
  fi
}
trap cleanup EXIT

if [[ "${SKIP_BUILD:-0}" != "1" ]]; then
  docker build --tag "${image}" .
fi

if [[ -z "${RUNTIME_SOURCE:-}" ]]; then
  echo "RUNTIME_SOURCE must name a local gated-runtime Git checkout." >&2
  exit 2
fi
if [[ "$(git -C "${RUNTIME_SOURCE}" rev-parse HEAD)" != "${runtime_commit}" ]]; then
  echo "RUNTIME_SOURCE is not at the pinned runtime commit." >&2
  exit 2
fi
if [[ -n "$(git -C "${RUNTIME_SOURCE}" status --porcelain)" ]]; then
  echo "RUNTIME_SOURCE must be clean for an exact smoke test." >&2
  exit 2
fi

runtime_archive="$(mktemp -d "${PWD}/.runtime-source.XXXXXX")"
git -C "${RUNTIME_SOURCE}" archive "${runtime_commit}" | tar -x -C "${runtime_archive}"
printf '%s\n' "${runtime_commit}" >"${runtime_archive}/.datalox-source-revision"

docker run \
  --detach \
  --name "${container_name}" \
  --publish "127.0.0.1:${host_port}:7860" \
  --volume "${runtime_archive}:/runtime-source:ro" \
  --env DATALOX_RUNTIME_SOURCE=/runtime-source \
  --env "SPACE_HOST=${space_host}" \
  --env 'DATALOX_ALLOWED_HOSTS=localhost:*,127.0.0.1:*' \
  --env "DATALOX_ALLOWED_ORIGINS=http://localhost:${host_port}" \
  --env DATALOX_MAX_SESSIONS=2 \
  --env DATALOX_SESSION_TTL_SECONDS=120 \
  "${image}" >/dev/null

healthy=0
for _ in $(seq 1 60); do
  if curl --fail --silent --show-error "${base_url}/health" >/dev/null 2>&1; then
    healthy=1
    break
  fi
  sleep 1
done

if [[ "${healthy}" != "1" ]]; then
  docker logs "${container_name}" >&2
  echo "Service did not become healthy." >&2
  exit 1
fi

health="$(
  curl --fail --silent --show-error "${base_url}/health"
)"
python3 -c '
import json
import sys

payload = json.load(sys.stdin)
assert payload == {
    "ok": True,
    "service": "datalox_remote_world_service",
    "active_sessions": 0,
    "max_sessions": 2,
    "live_mode": False,
}
' <<< "${health}"

manifest="$(curl --fail --silent --show-error "${base_url}/")"
python3 -c '
import json
import sys

payload = json.load(sys.stdin)
assert payload["schema_version"] == "datalox_science_growth_space_manifest_v1"
assert payload["world_id"] == "science_growth_kinetics_v0"
assert payload["dry_run_only"] is True
assert payload["routes"]["mcp"]["transport"] == "streamable_http"
assert payload["pinned_commits"] == {
    "api_gym": "ca47eb299ae1ea9f96848807c3d74395d486cce4",
    "gated_runtime": "ce5372623ddbab41dab169e4e0d0fc1c000a56c2",
}
' <<< "${manifest}"

if ! reference_result="$(
  docker exec "${container_name}" \
    python /home/user/app/scripts/run_reference.py \
      --transport-host "${space_host}" \
      --transport-origin "https://${space_host}"
)"; then
  docker logs "${container_name}" >&2
  exit 1
fi

printf '%s\n' \
  "Smoke test passed." \
  "Image: ${image}" \
  "World: science_growth_kinetics_v0" \
  "Seed: 0"
printf '%s\n' "${reference_result}"
