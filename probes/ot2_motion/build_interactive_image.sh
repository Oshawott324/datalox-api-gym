#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: build_interactive_image.sh --runtime-source PATH [options] [-- DOCKER_BUILD_ARGS...]

Options:
  --runtime-source PATH  Required datalox-gated-runtime checkout.
  --tag IMAGE            Output image (default: datalox-ot2-motion:interactive).
  --context-output PATH  Write the selected build context and stop before Docker.
  -h, --help             Show this help.

Place Docker build options after --. The same options are used for the phase-0
base and interactive builds, including proxy build arguments.
EOF
}

runtime_source=""
image_tag="datalox-ot2-motion:interactive"
context_output=""
docker_args=()
has_docker_args=false

while (($#)); do
  case "$1" in
    --runtime-source)
      (($# >= 2)) || { echo "--runtime-source needs a path" >&2; exit 2; }
      runtime_source=$2
      shift 2
      ;;
    --tag)
      (($# >= 2)) || { echo "--tag needs an image name" >&2; exit 2; }
      image_tag=$2
      shift 2
      ;;
    --context-output)
      (($# >= 2)) || { echo "--context-output needs a path" >&2; exit 2; }
      context_output=$2
      shift 2
      ;;
    --)
      shift
      docker_args=("$@")
      has_docker_args=true
      break
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option before --: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

[[ -n "$runtime_source" ]] || { echo "--runtime-source is required" >&2; exit 2; }
runtime_source=$(cd "$runtime_source" && pwd -P)
api_root=$(cd "$(dirname "$0")/../.." && pwd -P)

required_runtime_paths=(
  pyproject.toml
  README.md
  LICENSE
  requirements/opentrons-ot2-motion-worker.txt
  src/datalox_gated_runtime
)
for path in "${required_runtime_paths[@]}"; do
  [[ -e "$runtime_source/$path" ]] || {
    echo "Runtime source is missing required path: $path" >&2
    exit 2
  }
done

if [[ -n "$context_output" ]]; then
  [[ ! -e "$context_output" ]] || {
    echo "--context-output must not already exist: $context_output" >&2
    exit 2
  }
  mkdir -p "$context_output"
  context=$(cd "$context_output" && pwd -P)
  cleanup=false
else
  context=$(mktemp -d "${TMPDIR:-/tmp}/datalox-ot2-interactive.XXXXXX")
  cleanup=true
fi

cleanup_context() {
  if [[ "$cleanup" == true ]]; then
    rm -rf "$context"
  fi
}
trap cleanup_context EXIT

api_paths=(
  api_gym/__init__.py
  api_gym/instrument_models
  api_gym/worlds/__init__.py
  api_gym/worlds/specs.py
  api_gym/worlds/ot2_motion_v0
  probes/ot2_motion/__init__.py
  probes/ot2_motion/Dockerfile
  probes/ot2_motion/Dockerfile.interactive
  probes/ot2_motion/build_image.sh
  probes/ot2_motion/build_interactive_image.sh
  probes/ot2_motion/interactive-requirements.in
  probes/ot2_motion/interactive-requirements.lock
  probes/ot2_motion/interactive_example.py
  probes/ot2_motion/run_interactive_smoke.sh
  tests/instrument_models/test_ot2_packaging.py
  tests/instrument_models/test_ot2_observations.py
  tests/instrument_models/test_ot2_motion_world.py
  tests/instrument_models/test_ot2_motion_runtime_bridge.py
  worlds/ot2_motion_v0
)
for path in "${api_paths[@]}"; do
  [[ -e "$api_root/$path" ]] || {
    echo "API Gym source is missing required path: $path" >&2
    exit 2
  }
done

COPYFILE_DISABLE=1 tar --format=ustar --exclude='__pycache__' --exclude='*.pyc' \
  -C "$api_root" -cf - "${api_paths[@]}" | tar -C "$context" -xf -
mkdir -p "$context/runtime-source"
COPYFILE_DISABLE=1 tar --format=ustar --exclude='__pycache__' --exclude='*.pyc' \
  -C "$runtime_source" -cf - "${required_runtime_paths[@]}" \
  | tar -C "$context/runtime-source" -xf -

if find "$context" -type l -print -quit | grep -q .; then
  echo "Selected source contains a symbolic link; refusing ambiguous build input" >&2
  exit 2
fi

hash_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

(
  cd "$context"
  find . -type f ! -name SOURCE-MANIFEST.sha256 -print | LC_ALL=C sort \
    | while IFS= read -r file; do
        printf '%s  %s\n' "$(hash_file "$file")" "${file#./}"
      done
) > "$context/SOURCE-MANIFEST.sha256"
source_bundle_sha256=$(hash_file "$context/SOURCE-MANIFEST.sha256")
printf 'Selected source bundle sha256: %s\n' "$source_bundle_sha256"

if [[ -n "$context_output" ]]; then
  printf 'Selected context: %s\n' "$context"
  exit 0
fi

phase0_tag="datalox-ot2-motion:phase0-${source_bundle_sha256:0:16}"
if [[ "$has_docker_args" == true ]]; then
  bash "$api_root/probes/ot2_motion/build_image.sh" \
    "${docker_args[@]}" -t "$phase0_tag"
  docker build "${docker_args[@]}" \
    --build-arg "PHASE0_IMAGE=$phase0_tag" \
    --build-arg "SOURCE_BUNDLE_SHA256=$source_bundle_sha256" \
    -f "$context/probes/ot2_motion/Dockerfile.interactive" \
    -t "$image_tag" "$context"
else
  bash "$api_root/probes/ot2_motion/build_image.sh" -t "$phase0_tag"
  docker build \
    --build-arg "PHASE0_IMAGE=$phase0_tag" \
    --build-arg "SOURCE_BUNDLE_SHA256=$source_bundle_sha256" \
    -f "$context/probes/ot2_motion/Dockerfile.interactive" \
    -t "$image_tag" "$context"
fi

image_id=$(docker image inspect --format '{{.Id}}' "$image_tag")
printf 'Built %s\nImage ID: %s\n' "$image_tag" "$image_id"
