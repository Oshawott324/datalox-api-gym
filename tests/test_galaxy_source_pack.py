from __future__ import annotations

import ast
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

from api_gym.source_packs import validate_source_pack


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_PACK = REPO_ROOT / "source_packs/apis/galaxy/2026-07-21"
CAPTURE = SOURCE_PACK / "raw/public_get_capture.json"
OPENAPI = SOURCE_PACK / "raw/openapi.json"
CAPTURE_SCRIPT = REPO_ROOT / "scripts/providers/galaxy/capture_public_gets.py"

EXPECTED_CAPTURE_SHA256 = "19d1bcbd61371df7cdd20df37a84fb5f918fa50297beface8af0ddbd2d4dfd0a"
EXPECTED_OPENAPI_SHA256 = "3943ae65ed8cdf9af9395b9db0a4a0b5c87f2203b9681bd3fb251e5730e5f42a"
EXPECTED_RECIPE_SHA256 = "704fe528bdda078af7eb19c53921389e93200ba77ed5b18ae494c29e50c9c15a"
EXPECTED_GAP_IDS = (
    "known_gap:galaxy:authenticated_reads",
    "known_gap:galaxy:writes",
    "known_gap:galaxy:arbitrary_workflows",
    "known_gap:galaxy:deployed_source_commit",
    "known_gap:galaxy:timing_sla",
    "known_gap:galaxy:binary_data",
    "known_gap:galaxy:raw_response_bytes",
)


def test_galaxy_source_pack_validates_with_expected_record_counts() -> None:
    result = validate_source_pack(SOURCE_PACK)

    assert result == {
        "ok": True,
        "path": str(SOURCE_PACK / "source_pack.json"),
        "source_pack_id": "api.galaxy.2026-07-21",
        "provider": "galaxy",
        "version": "2026-07-21",
        "record_counts": {
            "docs_index": 6,
            "known_gaps": 7,
            "observed_errors": 11,
            "operations": 62,
            "probes": 1,
            "response_cases": 74,
        },
    }


def test_capture_bytes_hash_and_openapi_object_are_preserved() -> None:
    pack = _read_json(SOURCE_PACK / "source_pack.json")
    capture = _read_json(CAPTURE)
    openapi = _read_json(OPENAPI)
    captured_openapi = next(row for row in capture["captures"] if row["id"] == "openapi")

    assert _sha256(CAPTURE) == EXPECTED_CAPTURE_SHA256
    assert CAPTURE.stat().st_size == 4_081_301
    assert pack["artifacts"]["public_get_capture"]["sha256"] == EXPECTED_CAPTURE_SHA256
    assert pack["artifacts"]["public_get_capture"]["byte_count"] == 4_081_301
    assert capture["capture_count"] == 34
    assert capture["allowed_method"] == "GET"
    assert capture["secret_headers_forwarded"] is False
    assert capture["cookies_persisted"] is False

    assert _sha256(OPENAPI) == EXPECTED_OPENAPI_SHA256
    assert pack["artifacts"]["openapi"]["sha256"] == EXPECTED_OPENAPI_SHA256
    assert captured_openapi["body_sha256"] == (
        "sha256:7e9e5bd5fc3c0a238afcf6273ee8d021b193bd51e5514133159cf4643cd2e4ed"
    )
    assert captured_openapi["body"] == openapi


def test_operations_separate_observed_gets_from_contract_candidates() -> None:
    operations = _read_jsonl(SOURCE_PACK / "operations.jsonl")
    raw_coverage = _read_json(SOURCE_PACK / "raw/provider_core_coverage.json")
    by_operation_id = {row["operation_id"]: row for row in operations}

    assert Counter(row["evidence_level"] for row in operations) == {
        "provider_observed_public_get": 19,
        "contract_shaped_candidate": 43,
    }
    assert set(by_operation_id) == {row["id"] for row in raw_coverage["operations"]}

    observed = [
        row for row in operations if row["evidence_level"] == "provider_observed_public_get"
    ]
    assert all(row["method"] == "GET" for row in observed)
    assert all(row["provider_execution"]["status"] == "observed" for row in observed)
    assert all(row["observed_capture_ids"] for row in observed)
    assert sum(len(row["observed_capture_ids"]) for row in observed) == 31

    candidates = [
        row for row in operations if row["evidence_level"] == "contract_shaped_candidate"
    ]
    assert all(row["provider_execution"]["status"] == "not_observed" for row in candidates)
    assert all(row["candidate_only"] is True for row in candidates)
    assert all("observed_capture_ids" not in row for row in candidates)


def test_response_cases_preserve_evidence_level_counts() -> None:
    cases = _read_jsonl(SOURCE_PACK / "response_cases.jsonl")
    capture = _read_json(CAPTURE)
    captures_by_id = {row["id"]: row for row in capture["captures"]}
    probe = _read_jsonl(SOURCE_PACK / "probes.jsonl")[0]

    assert Counter(row["evidence_level"] for row in cases) == {
        "provider_observed_public_get": 31,
        "contract_shaped_candidate": 43,
    }

    captured_cases = [
        row for row in cases if row["evidence_level"] == "provider_observed_public_get"
    ]
    for case in captured_cases:
        captured = captures_by_id[case["capture_id"]]
        assert case["status"] == captured["status"]
        assert case["body"] == captured["body"]
        assert case["body_sha256"] == captured["body_sha256"]
        assert case["body_bytes"] == captured["body_bytes"]

    assert probe["capture_count"] == 34
    assert probe["provider_observed_operation_count"] == 19
    assert probe["operation_linked_capture_count"] == 31
    assert probe["auxiliary_capture_ids"] == [
        "auth_datasets",
        "auth_extended_metadata",
        "anonymous_whoami",
    ]


def test_no_write_is_claimed_as_provider_executed() -> None:
    operations = _read_jsonl(SOURCE_PACK / "operations.jsonl")
    cases = _read_jsonl(SOURCE_PACK / "response_cases.jsonl")
    cases_by_operation = {row["operation_ref"]: row for row in cases}
    writes = [row for row in operations if row["effect"] == "write"]

    assert len(writes) == 24
    assert Counter(row["method"] for row in writes) == {
        "DELETE": 7,
        "POST": 9,
        "PUT": 8,
    }
    for operation in writes:
        assert operation["evidence_level"] == "contract_shaped_candidate"
        assert operation["provider_execution"] == {
            "status": "not_observed",
            "note": "Official-source contract shape only; no provider execution is claimed.",
        }
        assert operation["candidate_only"] is True
        case = cases_by_operation[operation["id"]]
        assert case["response_mode"] == "body_shape"
        assert case["gating_notes"] == (
            "Contract shape only. This is not a concrete provider response and must not be "
            "presented as provider-executed behavior."
        )


def test_known_gaps_and_forbidden_claims_are_stable_and_explicit() -> None:
    gaps = _read_jsonl(SOURCE_PACK / "known_gaps.jsonl")

    assert tuple(row["id"] for row in gaps) == EXPECTED_GAP_IDS
    assert [row["scope"] for row in gaps] == [
        "Authenticated reads",
        "Provider writes",
        "Arbitrary Galaxy workflows",
        "Deployed Galaxy source commit",
        "Timing, availability, and SLA",
        "Binary response data",
        "Raw provider response bytes",
    ]
    assert all(row["status"] in {"unsupported", "partial"} for row in gaps)
    assert all(row["reason"] for row in gaps)
    assert all(row["source_refs"] for row in gaps)
    assert all(row["forbidden_claims"] for row in gaps)


def test_capture_script_is_a_pinned_thin_runtime_delegate() -> None:
    source = CAPTURE_SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_roots = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    pack = _read_json(SOURCE_PACK / "source_pack.json")

    assert {"httpx", "requests", "urllib"} & imported_roots == set()
    assert "subprocess.run" in source
    assert pack["capture_recipe"]["runtime_recipe_sha256"] == EXPECTED_RECIPE_SHA256
    assert pack["capture_recipe"]["allowed_method"] == "GET"

    result = subprocess.run(
        [sys.executable, str(CAPTURE_SCRIPT), "check"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(result.stdout) == {
        "allowed_host": "usegalaxy.org",
        "allowed_method": "GET",
        "capture_count": 34,
        "path": str(CAPTURE),
        "sha256": EXPECTED_CAPTURE_SHA256,
    }
    assert result.stderr == ""


def test_capture_script_strips_credentials_and_rejects_unsafe_capture(
    tmp_path: Path,
) -> None:
    module = _load_capture_script()
    delegated_env = module.build_delegate_environment(
        {
            "PATH": "/usr/bin",
            "LANG": "C",
            "GALAXY_API_KEY": "secret",
            "AUTHORIZATION": "Bearer secret",
            "HTTP_PROXY": "https://user:secret@proxy.invalid",
            "HOME": "/credential-bearing-home",
        },
        home=tmp_path / "empty-home",
    )

    assert delegated_env == {
        "HOME": str(tmp_path / "empty-home"),
        "LANG": "C",
        "PATH": "/usr/bin",
        "PYTHONNOUSERSITE": "1",
    }

    unsafe = _read_json(CAPTURE)
    unsafe["allowed_method"] = "POST"
    unsafe_path = tmp_path / "unsafe.json"
    unsafe_path.write_text(json.dumps(unsafe), encoding="utf-8")

    with pytest.raises(ValueError, match="allowed_method must be GET"):
        module.validate_capture(unsafe_path)


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_capture_script():
    spec = importlib.util.spec_from_file_location("galaxy_capture_public_gets", CAPTURE_SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
