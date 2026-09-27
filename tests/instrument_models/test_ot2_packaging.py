from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "probes" / "ot2_motion"


def _text(name: str) -> str:
    return (PROBE / name).read_text()


def test_phase0_default_remains_the_original_31_test_selection() -> None:
    dockerfile = _text("Dockerfile")
    selected = set(re.findall(r'tests/instrument_models/(test_[a-z0-9_]+\.py)', dockerfile))
    assert selected == {
        "test_geometry_collision.py",
        "test_ot2_motion_reference.py",
        "test_ot2_motion_sources.py",
    }
    assert "test_ot2_motion_world.py" not in dockerfile


def test_interactive_image_separates_controller_from_native_worker() -> None:
    dockerfile = _text("Dockerfile.interactive")
    assert "FROM ${PHASE0_IMAGE}" in dockerfile
    assert "python -m venv /opt/ot2-controller" in dockerfile
    assert "PYTHONPATH=/workspace:/opt/runtime-source/src" in dockerfile
    assert "find_spec('opentrons') is None" in dockerfile
    assert "DATALOX_OT2_WORKER_PYTHON=/usr/local/bin/python" in dockerfile
    assert "USER 65534:65534" in dockerfile


def test_interactive_build_selects_runtime_source_without_vendoring_it() -> None:
    script = _text("build_interactive_image.sh")
    assert "--runtime-source is required" in script
    assert "src/datalox_gated_runtime" in script
    assert "requirements/opentrons-ot2-motion-worker.txt" in script
    assert "SOURCE-MANIFEST.sha256" in script
    assert "api_paths=(" in script
    assert "api_gym/worlds/specs.py" in script
    assert "tar -C \"$context/runtime-source\"" in script
    assert not (PROBE / "runtime-source").exists()


def test_interactive_smoke_uses_explicit_native_interpreter() -> None:
    script = _text("run_interactive_smoke.sh")
    assert "DATALOX_OT2_WORKER_PYTHON must name" in script
    assert '--native-python "$DATALOX_OT2_WORKER_PYTHON"' in script
    assert "test_ot2_motion_runtime_bridge.py" in script
