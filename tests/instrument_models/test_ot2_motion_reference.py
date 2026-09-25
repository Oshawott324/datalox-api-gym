from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

pytest.importorskip("opentrons", reason="Install probes/ot2_motion/requirements.lock")
pytest.importorskip("fcl", reason="Install probes/ot2_motion/requirements.lock")

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def reference():
    result = subprocess.run(
        [sys.executable, "-m", "probes.ot2_motion.reference"], cwd=ROOT,
        capture_output=True, text=True, check=True, timeout=120,
    )
    assert "Traceback" not in result.stderr
    assert "RuntimeWarning" not in result.stderr
    return json.loads(result.stdout)


def test_native_segments_and_distinct_path_options(reference):
    cases = {case["id"]: case["segments"] for case in reference["cases"]}
    arc, direct = cases["raised_cross_plate"], cases["direct_cross_plate"]
    assert len(arc) == 3
    assert len(direct) == 1
    assert arc[0]["reported_end_mm"][2] > arc[0]["start_mm"][2]
    assert arc[1]["reported_end_mm"][2] == arc[1]["start_mm"][2]
    assert arc[2]["reported_end_mm"][2] < arc[2]["start_mm"][2]
    assert direct[0]["reported_end_mm"] == pytest.approx(arc[0]["start_mm"])


def test_native_height_offset_and_continuity(reference):
    cases = {case["id"]: case["segments"] for case in reference["cases"]}
    assert max(s["reported_end_mm"][2] for s in cases["minimum_height"]) >= 100
    offset = cases["labware_offset"][0]
    assert [b-a for a, b in zip(offset["start_mm"], offset["reported_end_mm"])] == pytest.approx([1, -2, 0.5])
    same = cases["same_position"][0]
    assert same["start_mm"] == pytest.approx(same["reported_end_mm"])
    for case in reference["cases"]:
        for index, segment in enumerate(case["segments"]):
            assert segment["reported_end_mm"] == pytest.approx(segment["requested_end_mm"])
            if index:
                assert segment["start_mm"] == pytest.approx(case["segments"][index-1]["reported_end_mm"])


def test_reference_is_pinned_nominal_software_not_physical_evidence(reference):
    assert reference["opentrons_version"] == "9.1.1"
    assert reference["setup"]["pipette_model"] == "p300_single_v2.1"
    assert reference["setup"]["tip_length_mm"] == pytest.approx(51.1)
    assert reference["setup"]["position_frame"] == "deck"
    assert reference["setup"]["position_units"] == "mm"
    assert reference["source_files_sha256"]["opentrons/hardware_control/api.py"] == "9f4211ceaae9002bf0e9b00a4b4ad59a8164c25c0cf0707fdd59210c6d85484d"


def test_fresh_process_reproduces_reference(reference):
    result = subprocess.run([sys.executable, "-m", "probes.ot2_motion.reference"], cwd=ROOT, capture_output=True, text=True, check=True, timeout=120)
    assert json.loads(result.stdout) == reference


def test_full_feasibility_probe(tmp_path):
    path = tmp_path / "feasibility.json"
    subprocess.run([sys.executable, "-m", "probes.ot2_motion", "--out", str(path)], cwd=ROOT, check=True, capture_output=True, text=True, timeout=120)
    result = json.loads(path.read_text())
    assert result["feasibility_passed"]
    assert result["physical_validation"] == "not performed"
    assert result["instrument_geometry_admission"] == "pending"
    assert result["probe_body"]["is_pipette_model"] is False
