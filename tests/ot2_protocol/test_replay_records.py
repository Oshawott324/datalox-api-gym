import subprocess
from pathlib import Path

import pytest

from api_gym.worlds.ot2_protocol_v0 import OfficialAnalyzer

REPO = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(not OfficialAnalyzer.available(), reason="OT-2 analyzer interpreter not configured")
@pytest.mark.parametrize("tip_length", [None, "30.85"])
def test_recorded_arc_outcomes_reproduce(tip_length):
    command = [str(OfficialAnalyzer().python), "probes/ot2_reference/replay_arc_records.py"]
    if tip_length:
        command += ["--tip-length-mm", tip_length]
    completed = subprocess.run(command, cwd=REPO, capture_output=True, text=True, timeout=600, check=True)
    assert "5/5 recorded outcomes reproduced" in completed.stdout
    assert "MISMATCH" not in completed.stdout
