from __future__ import annotations

import json
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
    assert "44/44 cases passed" in completed.stdout


def test_package_writes_admission_matrix(tmp_path: Path) -> None:
    output_dir = tmp_path / "lablongrun-bench-v0"
    completed = subprocess.run(
        [sys.executable, "scripts/package_benchmark.py", "--output", str(output_dir)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr + completed.stdout
    matrix_path = output_dir / "admission_matrix.json"
    assert matrix_path.exists()

    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    assert matrix["summary"] == {
        "scenarios": 9,
        "cases": 44,
        "mutant_families": 14,
        "splits": {
            "dev": 32,
            "test_family_heldout": 6,
            "test_fault_heldout": 6,
        },
    }
    assert len(matrix["rows"]) == 44
    assert {
        "world",
        "scenario",
        "case_id",
        "case_kind",
        "mutant_family",
        "expected_failure_codes",
        "milestones",
        "split",
    }.issubset(matrix["rows"][0])
