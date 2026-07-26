#!/usr/bin/env python3
"""Capture sanitized PyLabRobot 0.2.1 sequences and build their source pack."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api_gym.provider_components.pylabrobot.executor import (
    capture_reference_sequences,
)
from api_gym.provider_components.pylabrobot.grounding import OPERATION_GROUNDING

DEFAULT_OUTPUT = (
    REPO_ROOT / "source_packs" / "apis" / "pylabrobot" / "2026-07-26"
)
SOURCE_PACK_ID = "api.pylabrobot.2026-07-26"

_DOCS = {
    "incubator": "https://docs.pylabrobot.org/stable/user_guide/01_material-handling/storage/cytomat.html",
    "ot2": "https://docs.pylabrobot.org/stable/user_guide/00_liquid-handling/opentrons/ot2/ot2-simulator.html",
    "plate_reader": "https://docs.pylabrobot.org/stable/user_guide/02_analytical/plate-reading/plate-reading.html",
}

_KNOWN_GAPS = (
    {
        "scope": "OT-2 simulator physical fidelity",
        "status": "partial",
        "reason": (
            "OpentronsOT2Simulator executes the PyLabRobot backend interface and tracker "
            "updates but does not establish pipetting accuracy, collision safety, sterility, "
            "liquid physics, or equivalence to physical OT-2 execution."
        ),
        "forbidden_claims": [
            "The retained sequence validates physical pipetting accuracy or hardware safety."
        ],
        "source": "ot2_success_v0",
    },
    {
        "scope": "PyLabRobot global tracking switches",
        "status": "partial",
        "reason": (
            "PyLabRobot 0.2.1 tip and volume tracking switches are process-global. The "
            "component restores their previous values but does not claim concurrent in-process "
            "fixture isolation."
        ),
        "forbidden_claims": [
            "Multiple concurrent component instances have isolated tracker configuration."
        ],
        "source": "ot2_tracker_errors_v0",
    },
    {
        "scope": "Incubator temperature and shaking dynamics",
        "status": "partial",
        "reason": (
            "IncubatorChatterboxBackend prints set and shaking commands but retains no "
            "temperature-setpoint, stabilization, elapsed-time, exposure, or shaking state. "
            "Its get_temperature method returns a fixed 37.0 degrees C."
        ),
        "forbidden_claims": [
            "The Chatterbox sequence simulates temperature stabilization, incubation exposure, or shaking."
        ],
        "source": "incubator_success_v0",
    },
    {
        "scope": "Plate-reader measurement semantics",
        "status": "partial",
        "reason": (
            "PlateReaderChatterboxBackend returns fixed zero-valued dummy matrices, a wall-clock "
            "timestamp, and NaN temperature. It does not simulate an assay, detector noise, "
            "calibration, kinetics, or plate-reader hardware."
        ),
        "forbidden_claims": [
            "The captured Chatterbox readings are biologically or instrument-calibrated measurements."
        ],
        "source": "plate_reader_success_v0",
    },
    {
        "scope": "Cross-instrument plate transport",
        "status": "unsupported",
        "reason": (
            "The three retained fixtures are independent. No robot arm, barcode system, "
            "operator handoff, or workcell transport was executed."
        ),
        "forbidden_claims": [
            "The source pack executes or verifies transport between the OT-2, incubator, and plate reader."
        ],
        "source": "incubator_success_v0",
    },
    {
        "scope": "Live hardware and network execution",
        "status": "unsupported",
        "reason": (
            "The component constructs only OpentronsOT2Simulator, "
            "IncubatorChatterboxBackend, and PlateReaderChatterboxBackend. It accepts no host, "
            "serial port, provider credential, or hardware backend."
        ),
        "forbidden_claims": [
            "The source pack connected to or controlled physical laboratory equipment."
        ],
        "source": "ot2_success_v0",
    },
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture local PyLabRobot reference sequences and source-pack records."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    capture = capture_reference_sequences()
    write_capture(args.output, capture)
    print(
        json.dumps(
            {
                "ok": True,
                "output": str(args.output),
                "sequence_count": len(capture["sequences"]),
                "operation_count": len(OPERATION_GROUNDING),
            },
            sort_keys=True,
        )
    )
    return 0


def write_capture(output: Path, capture: dict[str, Any]) -> None:
    raw_root = output / "raw" / "reference_sequences"
    raw_root.mkdir(parents=True, exist_ok=True)

    for sequence_id, sequence in sorted(capture["sequences"].items()):
        _write_json(
            raw_root / f"{sequence_id}.json",
            {
                "schema_version": capture["schema_version"],
                "sequence_id": sequence_id,
                "package": capture["package"],
                "hardware_execution_allowed": capture["hardware_execution_allowed"],
                "network_access_required": capture["network_access_required"],
                "normalization": capture["normalization"],
                "sequence": sequence,
            },
        )

    operations = _operation_rows()
    response_cases = _response_case_rows(capture)
    observed_errors = _observed_error_rows(capture)
    known_gaps = _known_gap_rows()

    _write_json(
        output / "source_pack.json",
        {
            "schema_version": "api_gym.api_source_pack.v0",
            "source_pack_id": SOURCE_PACK_ID,
            "provider": "pylabrobot",
            "version": "2026-07-26",
            "status": "captured_local_reference",
            "provider_package": {
                "distribution": "pylabrobot",
                "version": "0.2.1",
            },
            "source_types": ["installed_package", "local_execution", "docs"],
            "records": {
                "operations": "operations.jsonl",
                "response_cases": "response_cases.jsonl",
                "observed_errors": "observed_errors.jsonl",
                "known_gaps": "known_gaps.jsonl",
            },
            "reference_sequences": [
                f"raw/reference_sequences/{name}.json"
                for name in sorted(capture["sequences"])
            ],
            "normalization": capture["normalization"],
            "live_execution": {
                "allowed": False,
                "reason": (
                    "This source pack executes only local simulator and Chatterbox backends. "
                    "Physical hardware and network provider execution are not exposed."
                ),
            },
        },
    )
    _write_jsonl(output / "operations.jsonl", operations)
    _write_jsonl(output / "response_cases.jsonl", response_cases)
    _write_jsonl(output / "observed_errors.jsonl", observed_errors)
    _write_jsonl(output / "known_gaps.jsonl", known_gaps)


def _operation_rows() -> list[dict[str, Any]]:
    rows = []
    for operation_id, grounding in sorted(OPERATION_GROUNDING.items()):
        source_file = _source_file_for_operation(operation_id)
        rows.append(
            {
                "id": f"operation:{operation_id}",
                "source_pack_id": SOURCE_PACK_ID,
                "operation_id": operation_id,
                "method": "CALL",
                "path": grounding.implementation,
                "summary": grounding.summary,
                "grounding_level": grounding.level,
                "live_execution_allowed": False,
                "source_refs": _source_refs(source_file, operation_id),
            }
        )
    return rows


def _response_case_rows(capture: dict[str, Any]) -> list[dict[str, Any]]:
    successful_steps: dict[str, tuple[str, dict[str, Any]]] = {}
    error_cases: list[tuple[str, dict[str, Any]]] = []
    for sequence_id, sequence in sorted(capture["sequences"].items()):
        for step in sequence.get("steps", []):
            successful_steps.setdefault(step["operation_id"], (sequence_id, step))
        for case in sequence.get("cases", []):
            error_cases.append((sequence_id, case))

    missing = sorted(set(OPERATION_GROUNDING) - set(successful_steps))
    if missing:
        raise RuntimeError(
            f"reference sequences do not execute every declared operation: {missing}"
        )

    rows: list[dict[str, Any]] = []
    for operation_id, (sequence_id, step) in sorted(successful_steps.items()):
        rows.append(
            {
                "id": f"response_case:{operation_id}:success",
                "source_pack_id": SOURCE_PACK_ID,
                "operation_ref": f"operation:{operation_id}",
                "case": "success",
                "status": "completed",
                "response_mode": "body",
                "body": step,
                "grounding_level": OPERATION_GROUNDING[operation_id].level,
                "source_refs": _source_refs(sequence_id, operation_id),
            }
        )
    for sequence_id, case in error_cases:
        error = case["error"]
        operation_id = error["operation_id"]
        rows.append(
            {
                "id": f"response_case:{operation_id}:{error['code'].lower()}",
                "source_pack_id": SOURCE_PACK_ID,
                "operation_ref": f"operation:{operation_id}",
                "case": "error",
                "status": "error",
                "response_mode": "error_shape",
                "error_shape": error,
                "grounding_level": OPERATION_GROUNDING[operation_id].level,
                "source_refs": _source_refs(sequence_id, operation_id),
            }
        )
    return rows


def _observed_error_rows(capture: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for sequence_id, sequence in sorted(capture["sequences"].items()):
        for case in sequence.get("cases", []):
            error = case["error"]
            operation_id = error["operation_id"]
            rows.append(
                {
                    "id": f"observed_error:{error['code'].lower()}",
                    "source_pack_id": SOURCE_PACK_ID,
                    "operation_ref": f"operation:{operation_id}",
                    "status": "observed_local_error",
                    "code": error["code"],
                    "message_shape": error,
                    "grounding_level": OPERATION_GROUNDING[operation_id].level,
                    "source_refs": _source_refs(sequence_id, operation_id),
                }
            )
    rows.append(
        {
            "id": "observed_error:pylabrobot_hardware_execution_unsupported",
            "source_pack_id": SOURCE_PACK_ID,
            "status": "boundary",
            "code": "PYLABROBOT_HARDWARE_EXECUTION_UNSUPPORTED",
            "message_shape": {
                "hardware_execution_allowed": False,
                "allowed_backends": [
                    "OpentronsOT2Simulator",
                    "IncubatorChatterboxBackend",
                    "PlateReaderChatterboxBackend",
                ],
            },
            "source_refs": _source_refs("ot2_success_v0", "hardware_boundary"),
        }
    )
    return rows


def _known_gap_rows() -> list[dict[str, Any]]:
    rows = []
    for index, gap in enumerate(_KNOWN_GAPS, start=1):
        source = gap["source"]
        rows.append(
            {
                "id": f"known_gap:pylabrobot:{index:02d}",
                "source_pack_id": SOURCE_PACK_ID,
                "scope": gap["scope"],
                "status": gap["status"],
                "reason": gap["reason"],
                "source_refs": _source_refs(source, gap["scope"]),
                "forbidden_claims": gap["forbidden_claims"],
            }
        )
    return rows


def _source_file_for_operation(operation_id: str) -> str:
    if operation_id.startswith("pylabrobot.ot2."):
        return "ot2_success_v0"
    if operation_id.startswith("pylabrobot.incubator."):
        return "incubator_success_v0"
    if operation_id.startswith("pylabrobot.plate_reader."):
        return "plate_reader_success_v0"
    raise KeyError(operation_id)


def _source_refs(sequence_id: str, pointer: str) -> list[dict[str, str]]:
    family = (
        "ot2"
        if sequence_id.startswith("ot2")
        else "incubator"
        if sequence_id.startswith("incubator")
        else "plate_reader"
    )
    return [
        {
            "kind": "local_execution",
            "path": f"raw/reference_sequences/{sequence_id}.json",
            "pointer": pointer,
        },
        {"kind": "docs", "url": _DOCS[family]},
    ]


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(row, sort_keys=True, allow_nan=False) + "\n" for row in rows
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
