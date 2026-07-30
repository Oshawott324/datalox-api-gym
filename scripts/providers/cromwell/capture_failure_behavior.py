#!/usr/bin/env python3
"""Capture the complete Cromwell 92 FAILED behavior through generic V3."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from datalox_gated_runtime.behavior_harvest.engines import v3

from api_gym.provider_components.cromwell.failure_behavior import (
    CAPTURE_PATH,
    CASE_METADATA_PATH,
    CONNECTOR_PATH,
    DISPOSABLE_ROOT,
    ENGINE_IDENTITY,
    FIXTURE_RECEIPT_PATH,
    INPUTS_PATH,
    OWNERSHIP_MARKER,
    PORT,
    RECIPE_PATH,
    WDL_PATH,
    build_connector,
    build_fixture_receipt,
    build_recipe,
    canonical_bytes,
    sha256_bytes,
)
from scripts.providers.cromwell.reference_fixture import (
    FixtureError,
    disposable_cromwell_fixture,
    inspect_fixture_receipt,
)


def _write(path: Path, payload: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return sha256_bytes(payload)


def fresh_case_load_arguments(
    case_root: Path,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "capture_path": case_root / CAPTURE_PATH.name,
        "expected_capture_sha256": metadata["digests"]["capture"],
        "connector_path": case_root / CONNECTOR_PATH.name,
        "expected_connector_sha256": metadata["digests"]["connector"],
        "recipe_path": case_root / RECIPE_PATH.name,
        "expected_recipe_sha256": metadata["digests"]["recipe"],
        "expected_engine": ENGINE_IDENTITY,
        "sensitive_values": {},
        "static_input_paths": {
            "fixture_inspection": case_root / FIXTURE_RECEIPT_PATH.name
        },
        "expected_static_input_sha256": {
            "fixture_inspection": metadata["digests"]["fixture_receipt"]
        },
        "static_artifact_paths": {
            "workflow": case_root / WDL_PATH.name,
            "inputs": case_root / INPUTS_PATH.name,
        },
    }


def capture_failure_behavior(
    *,
    jar_path: Path,
    java_bin: Path,
    case_root: Path | None = None,
) -> dict[str, Any]:
    if v3.current_engine_identity() != ENGINE_IDENTITY:
        raise FixtureError(
            "installed behavior harvester does not match the pinned V3 identity"
        )
    root = CAPTURE_PATH.parent if case_root is None else case_root
    connector_path = root / CONNECTOR_PATH.name
    recipe_path = root / RECIPE_PATH.name
    receipt_path = root / FIXTURE_RECEIPT_PATH.name
    workflow_path = root / WDL_PATH.name
    inputs_path = root / INPUTS_PATH.name
    capture_path = root / CAPTURE_PATH.name
    metadata_path = root / CASE_METADATA_PATH.name

    workflow_bytes = WDL_PATH.read_bytes()
    inputs_bytes = INPUTS_PATH.read_bytes()
    fixture_receipt = build_fixture_receipt()
    with disposable_cromwell_fixture(
        jar_path=jar_path,
        java_bin=java_bin,
        root=DISPOSABLE_ROOT,
        port=PORT,
        ownership_marker=OWNERSHIP_MARKER,
        fixture_receipt=fixture_receipt,
    ) as fixture:
        receipt = inspect_fixture_receipt(fixture)
        connector = build_connector(receipt)
        recipe = build_recipe()
        receipt_sha256 = _write(receipt_path, canonical_bytes(receipt))
        connector_sha256 = _write(connector_path, canonical_bytes(connector))
        recipe_sha256 = _write(recipe_path, canonical_bytes(recipe))
        workflow_sha256 = _write(workflow_path, workflow_bytes)
        inputs_sha256 = _write(inputs_path, inputs_bytes)

        result = v3.BehaviorHarvester().run(
            connector_path=connector_path,
            recipe_path=recipe_path,
            expected_connector_sha256=connector_sha256,
            expected_recipe_sha256=recipe_sha256,
            expected_engine=ENGINE_IDENTITY,
            run_id="cromwell_workflow_failure_20260730",
            output_path=capture_path,
            sensitive_values={},
            static_input_paths={"fixture_inspection": receipt_path},
            expected_static_input_sha256={
                "fixture_inspection": receipt_sha256
            },
            static_artifact_paths={
                "workflow": workflow_path,
                "inputs": inputs_path,
            },
            execute_sandbox_writes=True,
        )

        capture = result.capture
        primary_id = capture.bindings["primary_workflow_id"]
        duplicate_id = capture.bindings["duplicate_workflow_id"]
        if primary_id == duplicate_id:
            raise FixtureError(
                "byte-identical duplicate submission did not produce a distinct workflow ID"
            )
        primary_polls = [
            item for item in capture.exchanges if item.step_id == "poll_primary"
        ]
        duplicate_polls = [
            item for item in capture.exchanges if item.step_id == "poll_duplicate"
        ]
        transient_404 = sum(
            item.status_code == 404
            for item in (*primary_polls, *duplicate_polls)
        )
        metadata = {
            "schema_id": "api_gym.provider_behavior_case_metadata.v1",
            "program_id": capture.recipe.program_id,
            "provider_id": capture.connector.provider_id,
            "provider_version": capture.connector.provider_version,
            "engine": ENGINE_IDENTITY.to_dict(),
            "digests": {
                "capture": result.artifact_sha256,
                "connector": connector_sha256,
                "fixture_receipt": receipt_sha256,
                "inputs": inputs_sha256,
                "recipe": recipe_sha256,
                "workflow": workflow_sha256,
            },
            "coverage": {
                "preflight_http_calls": len(capture.preflight_exchanges),
                "logical_program_steps": len(capture.recipe.steps),
                "program_http_calls": len(capture.exchanges),
                "primary_poll_calls": len(primary_polls),
                "duplicate_poll_calls": len(duplicate_polls),
                "transient_404_calls": transient_404,
                "roles": sorted({step.role for step in capture.recipe.steps}),
                "operations": [
                    step.operation_id for step in capture.recipe.steps
                ],
                "observed_relations": dict(capture.observed_relations),
            },
            "claims": {
                "duplicate_submit": (
                    "observed_non_idempotent_distinct_workflow_ids"
                ),
                "native_failure": (
                    "provider_native_http_404_abort_after_terminal_failed"
                ),
                "fixture": (
                    "disposable_loopback_cromwell_92_local_hsqldb_file"
                ),
                "resulting_state_relation": (
                    "observed_submitted_to_failed_changed"
                ),
                "projection": "exact_captured_program_only",
                "production_equivalence": "not_claimed",
                "reset_equivalence": "not_claimed",
                "log_paths_dereferenced": False,
            },
        }
        _write(metadata_path, canonical_bytes(metadata))
        return metadata


def _explicit_path(argument: Path | None, environment_name: str) -> Path:
    if argument is not None:
        return argument
    value = os.environ.get(environment_name)
    if not value:
        raise FixtureError(
            f"provide an explicit argument or set {environment_name}"
        )
    return Path(value)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture one complete Cromwell 92 FAILED behavior program."
    )
    parser.add_argument("--jar", type=Path)
    parser.add_argument("--java-bin", type=Path)
    parser.add_argument(
        "--case-root",
        type=Path,
        help="Override the output directory for a gated live recapture.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        metadata = capture_failure_behavior(
            jar_path=_explicit_path(args.jar, "CROMWELL_92_JAR"),
            java_bin=_explicit_path(args.java_bin, "CROMWELL_JAVA_BIN"),
            case_root=args.case_root,
        )
    except (FixtureError, v3.BehaviorContractError, v3.BehaviorHarvestError) as error:
        print(
            json.dumps(
                {
                    "ok": False,
                    "code": getattr(error, "code", "fixture_error"),
                    "error": str(error),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "program_id": metadata["program_id"],
                "capture_sha256": metadata["digests"]["capture"],
                "engine": metadata["engine"],
                "coverage": metadata["coverage"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
