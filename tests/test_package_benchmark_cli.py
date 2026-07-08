from __future__ import annotations

import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_verify_all_runs_strict_admission_suite() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/package_benchmark.py", "--verify-all"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr + completed.stdout
    assert "Strict admission: PASS" in completed.stdout
    assert "36/36 cases passed" in completed.stdout
