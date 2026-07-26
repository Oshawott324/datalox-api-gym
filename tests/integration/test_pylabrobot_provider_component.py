from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

pylabrobot = pytest.importorskip("pylabrobot")

from api_gym.provider_components.pylabrobot import (  # noqa: E402
    GROUNDING_LEVELS,
    OPERATION_GROUNDING,
    OT2SimulatorComponent,
    PyLabRobotComponentError,
    capture_reference_sequences,
)
from api_gym.source_packs import validate_source_pack  # noqa: E402
from scripts.providers.pylabrobot.capture_reference import write_capture  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_PACK = REPO_ROOT / "source_packs" / "apis" / "pylabrobot" / "2026-07-26"


def test_ot2_simulator_executes_real_tracker_transitions() -> None:
    async def execute() -> tuple[dict[str, object], dict[str, object]]:
        component = OT2SimulatorComponent(initial_source_volume_ul=100.0)
        try:
            setup = await component.setup()
            await component.pick_up_tip("A1")
            await component.aspirate("A1", 25.0)
            dispense = await component.dispense("A1", 25.0)
            await component.drop_tip("A1")
            return setup, dispense
        finally:
            await component.stop()

    setup, dispense = asyncio.run(execute())

    assert pylabrobot.__version__ == "0.2.1"
    assert setup["snapshot"]["backend"]["class"].endswith(".OpentronsOT2Simulator")
    assert dispense["snapshot"]["wells"]["source_plate:A1"]["volume_ul"] == 75.0
    assert dispense["snapshot"]["wells"]["target_plate:A1"]["volume_ul"] == 25.0
    assert dispense["snapshot"]["channels"]["0"]["tip"]["volume"]["volume_ul"] == 0.0


@pytest.mark.parametrize(
    ("initial_volume_ul", "requested_volume_ul", "expected_code", "exception_name"),
    [
        (
            0.0,
            10.0,
            "PYLABROBOT_TOO_LITTLE_LIQUID",
            "TooLittleLiquidError",
        ),
        (
            360.0,
            301.0,
            "PYLABROBOT_TOO_LITTLE_VOLUME",
            "TooLittleVolumeError",
        ),
    ],
)
def test_ot2_tracker_failures_preserve_real_exception_type(
    initial_volume_ul: float,
    requested_volume_ul: float,
    expected_code: str,
    exception_name: str,
) -> None:
    async def execute() -> None:
        component = OT2SimulatorComponent(initial_source_volume_ul=initial_volume_ul)
        try:
            await component.setup()
            await component.pick_up_tip("A1")
            await component.aspirate("A1", requested_volume_ul)
        finally:
            await component.stop()

    with pytest.raises(PyLabRobotComponentError) as raised:
        asyncio.run(execute())

    error = raised.value.to_dict()
    assert error["code"] == expected_code
    assert error["operation_id"] == "pylabrobot.ot2.aspirate"
    assert error["details"]["exception_type"].endswith(f".{exception_name}")
    assert error["details"]["hardware_execution_attempted"] is False


def test_reference_sequences_cover_declared_operations_and_grounding() -> None:
    capture = capture_reference_sequences()
    successful_operations = {
        step["operation_id"]
        for sequence in capture["sequences"].values()
        for step in sequence.get("steps", [])
    }

    assert successful_operations == set(OPERATION_GROUNDING)
    assert {
        declaration.level for declaration in OPERATION_GROUNDING.values()
    } <= GROUNDING_LEVELS
    assert capture["hardware_execution_allowed"] is False
    assert capture["network_access_required"] is False

    reader_steps = capture["sequences"]["plate_reader_success_v0"]["steps"]
    reader_operations = [step["operation_id"] for step in reader_steps]
    assert reader_operations.index("pylabrobot.plate_reader.open") < (
        reader_operations.index("pylabrobot.plate_reader.place_plate")
    )
    assert reader_operations.index("pylabrobot.plate_reader.place_plate") < (
        reader_operations.index("pylabrobot.plate_reader.close")
    )
    assert reader_operations.index("pylabrobot.plate_reader.close") < (
        reader_operations.index("pylabrobot.plate_reader.read_absorbance")
    )


def test_checked_in_source_pack_matches_fresh_execution(tmp_path: Path) -> None:
    generated = tmp_path / "2026-07-26"
    write_capture(generated, capture_reference_sequences())

    expected_files = {
        path.relative_to(SOURCE_PACK)
        for path in SOURCE_PACK.rglob("*")
        if path.is_file()
    }
    actual_files = {
        path.relative_to(generated)
        for path in generated.rglob("*")
        if path.is_file()
    }
    assert actual_files == expected_files
    for relative in sorted(expected_files):
        assert (generated / relative).read_bytes() == (SOURCE_PACK / relative).read_bytes()

    validation = validate_source_pack(generated)
    assert validation["ok"] is True
    assert validation["record_counts"] == {
        "known_gaps": 6,
        "observed_errors": 6,
        "operations": 29,
        "response_cases": 34,
    }


def test_source_pack_declares_chatterbox_and_physical_fidelity_limits() -> None:
    gaps = [
        json.loads(line)
        for line in (SOURCE_PACK / "known_gaps.jsonl").read_text().splitlines()
    ]
    scopes = {gap["scope"]: gap for gap in gaps}

    assert scopes["OT-2 simulator physical fidelity"]["status"] == "partial"
    assert (
        scopes["Cross-instrument plate transport"]["status"] == "unsupported"
    )
    assert scopes["Live hardware and network execution"]["status"] == "unsupported"
    assert "fixed zero-valued dummy matrices" in (
        scopes["Plate-reader measurement semantics"]["reason"]
    )
