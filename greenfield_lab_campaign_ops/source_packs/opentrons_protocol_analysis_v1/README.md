# Opentrons Protocol Analysis Source Pack

This pack is grounded in local Opentrons protocol-analysis probes, not live
robot HTTP execution.

Probe environment used to capture the checked-in fixtures:

```bash
python -m venv /tmp/opentrons_probe_venv
source /tmp/opentrons_probe_venv/bin/activate
pip install opentrons==9.1.0
python - <<'PY'
import opentrons
from opentrons.protocol_api import MAX_SUPPORTED_VERSION
print(opentrons.__version__)
print(MAX_SUPPORTED_VERSION)
PY
```

Captured environment:

```text
opentrons==9.1.0
MAX_SUPPORTED_VERSION=2.29
```

Recapture fixtures from this directory:

```bash
source /tmp/opentrons_probe_venv/bin/activate

python -m opentrons.cli analyze \
  --json-output fixtures/analysis_flex_core_liquid_waste.json \
  protocols/flex_core_liquid_waste.py

python -m opentrons.cli analyze \
  --json-output fixtures/analysis_flex_temperature_magnetic.json \
  protocols/flex_temperature_magnetic.py

python -m opentrons.cli analyze \
  --json-output fixtures/analysis_flex_heater_shaker.json \
  protocols/flex_heater_shaker.py

python -m opentrons.cli analyze \
  --json-output fixtures/analysis_flex_thermocycler.json \
  protocols/flex_thermocycler.py

python -m opentrons.cli analyze \
  --json-output fixtures/analysis_flex_absorbance_gripper.json \
  protocols/flex_absorbance_gripper.py

python -m opentrons.cli analyze \
  --json-output fixtures/analysis_flex_stacker.json \
  protocols/flex_stacker.py

python -m opentrons.cli analyze \
  --check \
  --json-output fixtures/analysis_flex_invalid_deck_conflict_check.json \
  protocols/flex_invalid_deck_conflict.py || test "$?" = 255

python -m opentrons.cli analyze \
  --json-output fixtures/analysis_vacuum_api_version_error.json \
  protocols/vacuum_api_version_error.py || true
```

The two negative fixtures are intentional:

```text
analysis_flex_invalid_deck_conflict_check.json
  Captures an analyzer failure for an incompatible deck/fixture placement.

analysis_vacuum_api_version_error.json
  Captures that VacuumModuleContext.start_set_vacuum_power requires API 2.30,
  while opentrons==9.1.0 supports API 2.29.
```

Do not extend this pack with live `/runs`, `/commands`, homing, or movement
responses unless they are captured from a real robot server or a faithful
robot-server test fixture and gated separately.
