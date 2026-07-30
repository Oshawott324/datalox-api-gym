#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Mapping
from urllib.parse import urlsplit


REPO_ROOT = Path(__file__).resolve().parents[3]
PACK_ROOT = REPO_ROOT / "source_packs/apis/galaxy/2026-07-21"
PACK_CAPTURE = PACK_ROOT / "raw/public_get_capture.json"
DEFAULT_RUNTIME_ROOT = REPO_ROOT.parent / "datalox-gated-runtime"
RUNTIME_RECIPE = Path("scripts/providers/capture-galaxy-usegalaxy-public.py")

EXPECTED_CAPTURE_SHA256 = "19d1bcbd61371df7cdd20df37a84fb5f918fa50297beface8af0ddbd2d4dfd0a"
EXPECTED_RUNTIME_RECIPE_SHA256 = (
    "704fe528bdda078af7eb19c53921389e93200ba77ed5b18ae494c29e50c9c15a"
)
ALLOWED_HOST = "usegalaxy.org"
ALLOWED_METHOD = "GET"
SAFE_ENVIRONMENT_KEYS = ("LANG", "LC_ALL", "PATH", "SSL_CERT_DIR", "SSL_CERT_FILE")
SAFE_RESPONSE_HEADERS = frozenset(
    {"content-type", "content-length", "date", "etag", "last-modified"}
)
EXPECTED_CAPTURES = (
    ("version", 200),
    ("configuration", 200),
    ("openapi", 200),
    ("tool_search", 200),
    ("tool_versions", 200),
    ("tool_detail", 200),
    ("tool_schema", 200),
    ("tool_citations", 200),
    ("workflows_page_1", 200),
    ("workflows_page_2", 200),
    ("workflow_detail", 200),
    ("workflow_versions", 200),
    ("workflow_download", 200),
    ("history_search", 200),
    ("history_detail", 200),
    ("history_contents", 200),
    ("dataset_detail", 200),
    ("dataset_display", 200),
    ("datatypes", 200),
    ("tool_not_found", 404),
    ("workflow_not_found", 400),
    ("history_not_found", 400),
    ("dataset_not_found", 400),
    ("workflow_invalid_limit", 400),
    ("history_invalid_limit", 400),
    ("datatype_invalid_bool", 400),
    ("auth_datasets", 403),
    ("session_jobs", 400),
    ("auth_provenance", 403),
    ("auth_extended_metadata", 403),
    ("anonymous_whoami", 200),
    ("anonymous_histories_empty", 200),
    ("workflow_off_chain_detail", 200),
    ("dataset_off_chain_detail", 200),
)
SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


class CaptureError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def build_delegate_environment(
    source: Mapping[str, str],
    *,
    home: Path,
) -> dict[str, str]:
    """Build a minimal environment that cannot forward ambient credentials."""
    delegated = {
        key: source[key]
        for key in SAFE_ENVIRONMENT_KEYS
        if key in source and source[key]
    }
    delegated["HOME"] = str(home)
    delegated["PYTHONNOUSERSITE"] = "1"
    return dict(sorted(delegated.items()))


def validate_capture(
    path: Path,
    *,
    expected_sha256: str | None = None,
) -> dict[str, object]:
    actual_sha256 = _sha256(path)
    if expected_sha256 is not None and actual_sha256 != expected_sha256:
        raise CaptureError(
            "galaxy_capture_sha256_mismatch",
            f"capture SHA-256 is {actual_sha256}; expected {expected_sha256}",
        )

    payload = _read_json_object(path)
    _require_equal(payload, "schema_version", "datalox_public_get_capture_v1")
    _require_equal(payload, "provider_id", "galaxy_usegalaxy")
    _require_equal(payload, "allowed_host", ALLOWED_HOST)
    if payload.get("allowed_method") != ALLOWED_METHOD:
        raise CaptureError(
            "galaxy_capture_method_not_allowed",
            f"allowed_method must be {ALLOWED_METHOD}",
        )
    _require_false(payload, "secret_headers_forwarded")
    _require_false(payload, "cookies_persisted")

    captures = payload.get("captures")
    if not isinstance(captures, list):
        raise CaptureError("galaxy_capture_records_invalid", "captures must be a list")
    if payload.get("capture_count") != len(captures):
        raise CaptureError(
            "galaxy_capture_count_mismatch",
            "capture_count must equal the number of capture records",
        )

    observed = []
    for index, record in enumerate(captures):
        if not isinstance(record, dict):
            raise CaptureError(
                "galaxy_capture_record_invalid",
                f"capture record {index} must be an object",
            )
        capture_id = record.get("id")
        status = record.get("status")
        observed.append((capture_id, status))
        if record.get("method") != ALLOWED_METHOD:
            raise CaptureError(
                "galaxy_capture_method_not_allowed",
                f"capture {capture_id!r} method must be {ALLOWED_METHOD}",
            )
        _validate_url(record.get("url"), capture_id, "url")
        _validate_url(record.get("final_url"), capture_id, "final_url")
        _validate_response_headers(record, capture_id)
        _validate_redaction(record, capture_id)
        _validate_body_metadata(record, capture_id)

    if tuple(observed) != EXPECTED_CAPTURES:
        raise CaptureError(
            "galaxy_capture_recipe_result_mismatch",
            "capture IDs or statuses do not match the pinned Galaxy recipe",
        )

    return {
        "allowed_host": ALLOWED_HOST,
        "allowed_method": ALLOWED_METHOD,
        "capture_count": len(captures),
        "path": str(path),
        "sha256": actual_sha256,
    }


def run_capture(*, runtime_root: Path, out: Path) -> dict[str, object]:
    if out.resolve(strict=False) == PACK_CAPTURE.resolve(strict=False):
        raise CaptureError(
            "galaxy_capture_preserved_artifact_write_forbidden",
            "capture output must not overwrite the preserved source-pack artifact",
        )

    resolved_runtime = runtime_root.resolve()
    recipe = (resolved_runtime / RUNTIME_RECIPE).resolve()
    if not recipe.is_relative_to(resolved_runtime) or not recipe.is_file():
        raise CaptureError(
            "galaxy_capture_runtime_recipe_missing",
            f"runtime capture recipe is missing: {recipe}",
        )
    recipe_sha256 = _sha256(recipe)
    if recipe_sha256 != EXPECTED_RUNTIME_RECIPE_SHA256:
        raise CaptureError(
            "galaxy_capture_runtime_recipe_mismatch",
            f"runtime recipe SHA-256 is {recipe_sha256}; "
            f"expected {EXPECTED_RUNTIME_RECIPE_SHA256}",
        )

    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".galaxy-capture-", dir=out.parent) as temp_dir:
        temp_root = Path(temp_dir)
        empty_home = temp_root / "home"
        empty_home.mkdir()
        temporary_capture = temp_root / "capture.json"
        delegated_env = build_delegate_environment(os.environ, home=empty_home)
        subprocess.run(
            [sys.executable, str(recipe), "--out", str(temporary_capture)],
            check=True,
            capture_output=True,
            text=True,
            env=delegated_env,
        )
        summary = validate_capture(temporary_capture)
        temporary_capture.replace(out)

    return {**summary, "path": str(out), "runtime_recipe_sha256": recipe_sha256}


def _validate_url(value: object, capture_id: object, field: str) -> None:
    if not isinstance(value, str):
        raise CaptureError(
            "galaxy_capture_url_invalid",
            f"capture {capture_id!r} {field} must be a string",
        )
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname != ALLOWED_HOST
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise CaptureError(
            "galaxy_capture_url_not_allowed",
            f"capture {capture_id!r} {field} must use credential-free HTTPS on {ALLOWED_HOST}",
        )


def _validate_response_headers(record: dict[str, object], capture_id: object) -> None:
    headers = record.get("response_headers")
    if not isinstance(headers, dict):
        raise CaptureError(
            "galaxy_capture_headers_invalid",
            f"capture {capture_id!r} response_headers must be an object",
        )
    unsafe = sorted(str(key) for key in headers if str(key).lower() not in SAFE_RESPONSE_HEADERS)
    if unsafe:
        raise CaptureError(
            "galaxy_capture_headers_not_allowed",
            f"capture {capture_id!r} retains unsafe response headers: {unsafe}",
        )


def _validate_redaction(record: dict[str, object], capture_id: object) -> None:
    redaction = record.get("redaction")
    expected = {
        "agent_auth_cookie_or_secret_headers_forwarded": False,
        "cookies_persisted": False,
    }
    if redaction != expected:
        raise CaptureError(
            "galaxy_capture_redaction_invalid",
            f"capture {capture_id!r} must retain the credential-free redaction receipt",
        )
    if "request_headers" in record:
        raise CaptureError(
            "galaxy_capture_request_headers_persisted",
            f"capture {capture_id!r} must not persist request headers",
        )


def _validate_body_metadata(record: dict[str, object], capture_id: object) -> None:
    digest = record.get("body_sha256")
    if not isinstance(digest, str) or SHA256_PATTERN.fullmatch(digest) is None:
        raise CaptureError(
            "galaxy_capture_body_sha256_invalid",
            f"capture {capture_id!r} body_sha256 must be a prefixed SHA-256 digest",
        )
    body_bytes = record.get("body_bytes")
    if not isinstance(body_bytes, int) or isinstance(body_bytes, bool) or body_bytes < 0:
        raise CaptureError(
            "galaxy_capture_body_bytes_invalid",
            f"capture {capture_id!r} body_bytes must be a non-negative integer",
        )
    if record.get("body_representation") not in {"parsed_json", "utf8_text"}:
        raise CaptureError(
            "galaxy_capture_body_representation_invalid",
            f"capture {capture_id!r} has an unsupported body representation",
        )


def _read_json_object(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CaptureError(
            "galaxy_capture_invalid_json",
            f"capture is not readable JSON: {path}: {exc}",
        ) from exc
    if not isinstance(payload, dict):
        raise CaptureError("galaxy_capture_invalid_json", "capture must contain a JSON object")
    return payload


def _require_equal(payload: dict[str, object], key: str, expected: object) -> None:
    if payload.get(key) != expected:
        raise CaptureError(
            "galaxy_capture_metadata_invalid",
            f"{key} must be {expected!r}",
        )


def _require_false(payload: dict[str, object], key: str) -> None:
    if payload.get(key) is not False:
        raise CaptureError(
            "galaxy_capture_credentials_not_allowed",
            f"{key} must be false",
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise CaptureError(
            "galaxy_capture_file_unreadable",
            f"cannot read file for SHA-256: {path}: {exc}",
        ) from exc
    return digest.hexdigest()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check or explicitly refresh the bounded Galaxy public GET capture."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    check = commands.add_parser("check", help="Verify the preserved capture without network.")
    check.add_argument("--capture", type=Path, default=PACK_CAPTURE)
    check.add_argument("--expected-sha256", default=EXPECTED_CAPTURE_SHA256)

    capture = commands.add_parser(
        "capture",
        help="Delegate the pinned credential-free GET recipe to datalox-gated-runtime.",
    )
    capture.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)
    capture.add_argument("--out", type=Path, required=True)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        if args.command == "check":
            summary = validate_capture(
                args.capture,
                expected_sha256=args.expected_sha256,
            )
        else:
            summary = run_capture(runtime_root=args.runtime_root, out=args.out)
    except CaptureError as exc:
        print(
            json.dumps(
                {"ok": False, "error": {"code": exc.code, "message": exc.message}},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
