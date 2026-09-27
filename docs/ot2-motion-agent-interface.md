# OT-2 Motion Agent Interface

The OT-2 motion bridge exposes one existing API Gym task through the existing
Datalox world-bundle and MCP runtime. The runtime owns a persistent, device-free
Opentrons 9.1.1 simulator worker for the active episode. A trusted reset destroys
that worker and starts a new generation; an agent cannot create, reset, resume,
or configure the worker.

## Current Scope

The bundle at `worlds/ot2_motion_v0` contains only
`engineering_control_02`. The task starts at slot 1 well A1, 5 mm above the top,
and asks the agent to reach slot 3 well A1 at the same relative height.

Path checks use an authored 0.5 mm sphere and thin wall. This is a mathematical
control fixture, not source-backed pipette, tip, labware, deck, or robot
geometry. No physical robot validation has been performed.

The bundle hashes every authored file it contains. Its small implementation
entry point imports the installed API Gym world and runtime adapter; those
external Python modules are not covered by the bundle's file hashes. A
reproducible release therefore also needs immutable API Gym and gated-runtime
source revisions or image provenance. The bundle is not a standalone,
self-contained executable artifact.

## Trusted Configuration

The controller process must set `DATALOX_OT2_WORKER_PYTHON` to an absolute,
executable interpreter containing the pinned Opentrons 9.1.1 worker
dependencies. There is no default path.

The controller environment needs editable or installed copies of both API Gym
and `datalox-gated-runtime`, plus FastAPI, MCP, and FCL. The native child does
not receive the agent's environment or arguments and cannot be pointed at
another interpreter, file, import, URL, or hardware address through MCP.

## Agent Tools

`ot2.inspect_setup` returns the task, configured labware and offsets, reported
tip state, and the authored model-scope disclosure.

`ot2.move_to_well` accepts a slot, well, `top` or `bottom` reference, optional
XYZ offset, and native `force_direct`, `minimum_z_height_mm`, and `speed_mm_s`
options.

`ot2.move_to_deck_point` accepts an absolute deck XYZ point and the same native
path options.

`ot2.request_operator_observation` accepts one declared scope and subject. The
current episode contains no supplied operator record, so a permitted request
returns `available: false`.

`ot2.defer` records an explicit evidence-based deferral only when the selected
task permits it. The current task does not, so it returns a structured denial.

Labware-offset mutation is not exposed in this first bundle because the selected
task does not authorize it. Hidden physical setup, resolved goals, path-check
witnesses, evaluator state, and researcher-view payloads have no MCP tool or
route.

All tool schemas reject unknown fields. Native errors remain separate from
modeled path results, retain the completed native segment prefix, and never
trigger an automatic retry.

## Run The Focused Check

From the API Gym checkout:

```bash
export DATALOX_OT2_WORKER_PYTHON=/absolute/path/to/native-opentrons-9.1.1/bin/python
runs/ot2-controller-env/bin/python -m pytest -q \
  tests/instrument_models/test_ot2_motion_runtime_bridge.py
```

Without `DATALOX_OT2_WORKER_PYTHON`, the content-hash/factory test runs and the
three native integration tests are explicitly skipped. If the variable is set to
a missing, incompatible, or source-mismatched interpreter, the tests fail.

The focused check validates the bundle, executes direct and raised native moves,
resets to a fresh generation, closes the worker, and connects an official MCP
client to the existing `datalox-gate mcp` process. It also attempts an unknown
tool, unknown fields, and a hidden-state route.

## Create A Session And Connect An Agent

Run this from the API Gym checkout. Replace the worker path with the trusted
Opentrons 9.1.1 interpreter for the host or container:

```bash
export CONTROLLER_PYTHON="$PWD/runs/ot2-controller-env/bin/python"
export DATALOX_OT2_WORKER_PYTHON=/absolute/path/to/native-opentrons-9.1.1/bin/python
export OT2_RUN_DIR="$(mktemp -d "${TMPDIR:-/tmp}/datalox-ot2-motion.XXXXXX")"

"$CONTROLLER_PYTHON" - "$OT2_RUN_DIR" <<'PY'
import json
import shutil
import sys
from pathlib import Path

from datalox_gated_runtime.world_v1.backend import initialize_world_bundle_session

checkout = Path.cwd()
bundle = checkout / "worlds" / "ot2_motion_v0"
run_dir = Path(sys.argv[1])
initialize_world_bundle_session(
    source_bundle_dir=bundle,
    run_dir=run_dir,
    episode_id="ot2-motion-engineering-control-02",
)
for name in ("gate_config.json", "task.json"):
    shutil.copy2(bundle / name, run_dir / name)
(run_dir / "session_manifest.json").write_text(
    json.dumps(
        {
            "session_id": "ot2-motion-local",
            "world_id": "ot2_motion_v0",
        },
        sort_keys=True,
    ),
    encoding="utf-8",
)
print(run_dir)
PY
```

The exact stdio MCP command is:

```bash
"$CONTROLLER_PYTHON" -m datalox_gated_runtime.cli mcp \
  --run "$OT2_RUN_DIR" \
  --actor-id local-motion-agent \
  --actor-role motion_agent
```

For an MCP-capable agent host, configure that command directly instead of
starting it separately. After substituting the exported absolute paths, the
connection entry is:

```json
{
  "mcpServers": {
    "ot2-motion": {
      "command": "/absolute/path/to/controller/bin/python",
      "args": [
        "-m",
        "datalox_gated_runtime.cli",
        "mcp",
        "--run",
        "/absolute/path/to/fresh/run-directory",
        "--actor-id",
        "local-motion-agent",
        "--actor-role",
        "motion_agent"
      ],
      "env": {
        "DATALOX_OT2_WORKER_PYTHON": "/absolute/path/to/native-opentrons-9.1.1/bin/python"
      }
    }
  }
}
```

Each prepared managed run accepts one runtime create. Create a new run directory
for another MCP process; do not reconnect by resuming the prior SQLite state.

## Lifecycle And Evidence

Verification must run while the long-lived backend still owns the native worker:

```python
result = backend.verify()
backend.reset()   # trusted controller only; starts a fresh worker generation
backend.close()
```

After each completed tool response, the adapter writes the bounded agent
observation, trusted episode summary, and final verifier result into the runtime
session transaction. After MCP shutdown, a trusted controller can inspect that
persisted verifier snapshot and the runtime event export through `WorldSession`.
The agent has no access to the SQLite file.

Managed worker sessions cannot be resumed from `world_v1.sqlite3`. The ordinary
post-shutdown world verification/export path currently opens a resumed backend,
so it is intentionally unsupported for this world. Do not advertise the usual
post-shutdown finalize flow as working until the runtime gains a trusted export
path that consumes the persisted snapshot without recreating native state.

If argument parsing, native-result normalization, core application, or snapshot
persistence fails after motion may have occurred, the runtime invalidates and
closes the worker. Further actions fail until a trusted reset; the command is
not retried.

## Isolation Limit

The host-process tests establish native behavior, lifecycle ownership, MCP
projection, and information boundaries. They do not establish network or
device isolation. Evaluation requires the separate network-disabled,
device-free container target with read-only code/assets, bounded writable
temporary storage, non-root execution, and resource limits.
