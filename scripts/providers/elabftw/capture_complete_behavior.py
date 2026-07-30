#!/usr/bin/env python3
"""Capture the complete eLabFTW PATCH behavior through the generic harvester."""

from __future__ import annotations

import argparse
import json
import secrets
import sys
from pathlib import Path
from typing import Any

from datalox_gated_runtime.behavior_harvest.engines import v2

from api_gym.provider_components.elabftw.complete_behavior import (
    AUTH_SECRET_NAME,
    CAPTURE_PATH,
    CASE_METADATA_PATH,
    CONNECTOR_PATH,
    ENGINE_IDENTITY,
    FIXTURE_RECEIPT_PATH,
    ORIGIN,
    RECIPE_PATH,
    build_connector,
    build_recipe,
    canonical_bytes,
    sha256_bytes,
)
from scripts.providers.elabftw.reference_fixture import (
    FixtureCredentials,
    FixtureError,
    bootstrap_fixture,
    destroy_fixture,
    inspect_fixture_receipt,
    start_fixture,
)


def _write(path: Path, payload: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return sha256_bytes(payload)


def capture_complete_behavior(
    *,
    case_root: Path | None = None,
) -> dict[str, Any]:
    if v2.current_engine_identity() != ENGINE_IDENTITY:
        raise FixtureError(
            "installed behavior harvester does not match the pinned V2 identity"
        )
    root = CAPTURE_PATH.parent if case_root is None else case_root
    connector_path = root / CONNECTOR_PATH.name
    recipe_path = root / RECIPE_PATH.name
    receipt_path = root / FIXTURE_RECEIPT_PATH.name
    capture_path = root / CAPTURE_PATH.name
    metadata_path = root / CASE_METADATA_PATH.name
    project = f"datalox-elabftw-complete-{secrets.token_hex(5)}"
    credentials = FixtureCredentials.generate()
    port = int(ORIGIN.rsplit(":", 1)[1])
    try:
        start_fixture(project, port, credentials)
        bootstrap_fixture(project, port, credentials)
        receipt = inspect_fixture_receipt(project, port, credentials)
        connector = build_connector(receipt)
        recipe = build_recipe()
        receipt_sha256 = _write(receipt_path, canonical_bytes(receipt))
        connector_sha256 = _write(connector_path, canonical_bytes(connector))
        recipe_sha256 = _write(recipe_path, canonical_bytes(recipe))
        result = v2.BehaviorHarvester().run(
            connector_path=connector_path,
            recipe_path=recipe_path,
            expected_connector_sha256=connector_sha256,
            expected_recipe_sha256=recipe_sha256,
            expected_engine=ENGINE_IDENTITY,
            run_id="elabftw_patch_complete_20260730",
            output_path=capture_path,
            sensitive_values={AUTH_SECRET_NAME: credentials.api_key.encode("utf-8")},
            static_input_paths={"fixture_inspection": receipt_path},
            expected_static_input_sha256={"fixture_inspection": receipt_sha256},
            execute_sandbox_writes=True,
        )
        capture = result.capture
        metadata = {
            "schema_id": "api_gym.provider_behavior_case_metadata.v1",
            "program_id": capture.recipe.program_id,
            "provider_id": capture.connector.provider_id,
            "provider_version": capture.connector.provider_version,
            "engine": ENGINE_IDENTITY.to_dict(),
            "digests": {
                "capture": result.artifact_sha256,
                "connector": connector_sha256,
                "recipe": recipe_sha256,
                "fixture_receipt": receipt_sha256,
            },
            "coverage": {
                "preflight_calls": len(capture.preflight_exchanges),
                "program_calls": len(capture.exchanges),
                "roles": sorted({step.role for step in capture.recipe.steps}),
                "operations": [step.operation_id for step in capture.recipe.steps],
                "observed_relations": dict(capture.observed_relations),
            },
            "claims": {
                "duplicate_patch": "observed_only_not_idempotency",
                "native_failure": "provider_native_http_400",
                "fixture": "disposable_loopback_self_hosted_reference",
                "production_equivalence": "not_claimed",
            },
        }
        _write(metadata_path, canonical_bytes(metadata))
        return metadata
    finally:
        try:
            destroy_fixture(project, port, credentials)
        finally:
            partial = capture_path.with_name(f"{capture_path.name}.partial.jsonl")
            partial.unlink(missing_ok=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture one complete eLabFTW behavior program."
    )
    parser.add_argument(
        "--case-root",
        type=Path,
        help="Override the output directory for a gated live recapture test.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        metadata = capture_complete_behavior(case_root=args.case_root)
    except (FixtureError, v2.BehaviorContractError, v2.BehaviorHarvestError) as error:
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
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
