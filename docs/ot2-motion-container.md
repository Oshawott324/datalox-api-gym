# OT-2 Motion Containers

Two images preserve two different scopes. `datalox-ot2-motion:phase0` is the
fixed reference probe and its original 31 tests. `datalox-ot2-motion:interactive`
adds the current motion world, the runtime bridge, and a real Opentrons 9.1.1
native-worker example.

## Phase 0

From the API Gym checkout:

```bash
bash probes/ot2_motion/build_image.sh
docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --pids-limit 256 --memory 2g \
  --tmpfs /tmp:rw,nosuid,nodev,size=256m \
  datalox-ot2-motion:phase0
```

The default command selects only `test_geometry_collision.py`,
`test_ot2_motion_reference.py`, and `test_ot2_motion_sources.py`. New world
tests are intentionally outside this image's contract.

## Interactive Image

The interactive image is a two-repository build. Pass the runtime checkout
explicitly; the build script copies only the runtime package, its package
metadata, license/readme, and its declared native-worker requirements into a
temporary Docker context.

```bash
bash probes/ot2_motion/build_interactive_image.sh \
  --runtime-source /absolute/path/to/datalox-gated-runtime
```

The script first builds a content-named phase-0 base from the hash-locked probe
environment. That base supplies `/usr/local/bin/python`, the native worker's
Opentrons 9.1.1 interpreter. The final image creates a separate hash-locked
controller environment at `/opt/ot2-controller`; Opentrons is deliberately
absent there. The controller imports the selected runtime package code directly
from the content recorded in the manifest; it does not build a timestamped
wheel or resolve undeclared runtime dependencies. The matching runtime revision
for this implementation is `883776fa3cb426c012f7aba25cf125c42e68b7f0`
on `codex/opentrons-motion-runtime`. Use that revision for the build described
here. Runtime source stays in its own repository, separate from API Gym.

Every build writes `/opt/ot2-source-manifest.sha256` and labels the image with
the manifest digest. To inspect the exact context without invoking Docker:

```bash
bash probes/ot2_motion/build_interactive_image.sh \
  --runtime-source /absolute/path/to/datalox-gated-runtime \
  --context-output /tmp/ot2-interactive-context
```

Proxy options belong after `--` and apply to both builds. The proxy address
must be reachable from Docker:

```bash
bash probes/ot2_motion/build_interactive_image.sh \
  --runtime-source /absolute/path/to/datalox-gated-runtime -- \
  --build-arg HTTP_PROXY=http://host.docker.internal:7897 \
  --build-arg HTTPS_PROXY=http://host.docker.internal:7897
```

Run the complete offline smoke without host mounts, forwarded environment
variables, Docker socket access, credentials, or robot-device flags:

```bash
docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --pids-limit 256 --memory 2g \
  --tmpfs /tmp:rw,nosuid,nodev,size=256m \
  datalox-ot2-motion:interactive
```

The default command runs packaging, observation, world, and runtime-bridge
tests, then runs `probes.ot2_motion.interactive_example` with the trusted native
interpreter path from `DATALOX_OT2_WORKER_PYTHON`. The native simulator starts
a child process inside the same container and uses temporary state under `/tmp`.

## Isolation Boundary

The command above demonstrates execution with Docker networking disabled, a
read-only root filesystem, dropped Linux capabilities, no additional host
mounts, no forwarded credentials, and no robot-device mounts. The build context
is an allowlist rather than either repository root. These facts establish the
container boundary used for this smoke; they do not prove resistance to a
malicious container runtime, Docker daemon, kernel, image dependency, or host
administrator. They also do not make the authored sphere-and-wall fixture a
physical OT-2 clearance model.
