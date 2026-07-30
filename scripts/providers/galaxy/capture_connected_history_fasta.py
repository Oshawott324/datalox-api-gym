#!/usr/bin/env python3
"""Capture one bounded connected Galaxy history/upload/readback behavior case."""

from __future__ import annotations

import base64
import hashlib
import http.client
import json
from pathlib import Path
import secrets
import subprocess
import time
from typing import Any
from urllib.parse import quote, urlencode


REPO_ROOT = Path(__file__).resolve().parents[3]
CASE_ROOT = (
    REPO_ROOT
    / "source_packs/apis/galaxy/2026-07-30/behavior_cases"
    / "connected_history_fasta_v1"
)
INPUT_PATH = CASE_ROOT / "input.fa"
CONTAINER_NAME = "datalox-galaxy-sequence-59441"
ORIGIN = "http://127.0.0.1:32770"
HOST = "127.0.0.1"
PORT = 32770
EXPECTED_IMAGE_ID = "sha256:8e5b825e2d064707caa9f564bd5280bef0a79b666ccfee116ae7c311657eec62"
EXPECTED_IMAGE_REFERENCE = (
    "datalox-galaxy-reference@"
    "sha256:8e5b825e2d064707caa9f564bd5280bef0a79b666ccfee116ae7c311657eec62"
)
EXPECTED_OCI_INDEX = "sha256:100a37301e5f4fb3ac560be5cec7ec5629400673cef8511ea2a8c17b4c8b7399"
EXPECTED_REVISION = "3d62013917dfc9e285c2be923b7b5b2034469d6f"
EXPECTED_VOLUME = "datalox-galaxy-sequence-data-59441"
TERMINAL_DATASET_STATES = {"ok", "error", "discarded", "failed_metadata"}
REQUIRED_STARAMR_TOOLS = (
    "toolshed.g2.bx.psu.edu/repos/iuc/staramr/staramr_search/0.11.0+galaxy3",
    "toolshed.g2.bx.psu.edu/repos/iuc/amrfinderplus/amrfinderplus/3.12.8+galaxy0",
    "toolshed.g2.bx.psu.edu/repos/iuc/abricate/abricate/1.0.1",
    "toolshed.g2.bx.psu.edu/repos/iuc/tooldistillator/tooldistillator/1.0.4+galaxy0",
    (
        "toolshed.g2.bx.psu.edu/repos/iuc/tooldistillator_summarize/"
        "tooldistillator_summarize/1.0.4+galaxy0"
    ),
)
SENSITIVE_REQUEST_HEADERS = {"authorization", "cookie", "x-api-key"}
SENSITIVE_RESPONSE_HEADERS = {"set-cookie"}


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sha256_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=check,
        capture_output=True,
        text=True,
    )


def docker_json(kind: str, name: str) -> dict[str, Any]:
    result = run(["docker", kind, "inspect", name])
    payload = json.loads(result.stdout)
    if not isinstance(payload, list) or len(payload) != 1:
        raise RuntimeError(f"Unexpected docker {kind} inspect result for {name}")
    return payload[0]


def inspect_fixture() -> dict[str, Any]:
    container = docker_json("container", CONTAINER_NAME)
    image = docker_json("image", EXPECTED_IMAGE_ID)
    labels = container["Config"].get("Labels") or {}
    mounts = [
        {
            "destination": mount["Destination"],
            "driver": mount["Driver"],
            "name": mount["Name"],
            "read_write": mount["RW"],
            "type": mount["Type"],
        }
        for mount in container["Mounts"]
    ]
    receipt = {
        "architecture": image["Architecture"],
        "auto_remove": container["HostConfig"]["AutoRemove"],
        "configured_image": container["Config"]["Image"],
        "container_name": CONTAINER_NAME,
        "container_running": container["State"]["Running"],
        "disposable_marker": labels.get("io.datalox.disposable-marker"),
        "image_id": container["Image"],
        "image_reference": EXPECTED_IMAGE_REFERENCE,
        "image_repo_digests": image.get("RepoDigests", []),
        "labels": {
            "org.opencontainers.image.created": labels.get(
                "org.opencontainers.image.created"
            ),
            "org.opencontainers.image.revision": labels.get(
                "org.opencontainers.image.revision"
            ),
            "org.opencontainers.image.version": labels.get(
                "org.opencontainers.image.version"
            ),
        },
        "loopback_origin": ORIGIN,
        "mounts": mounts,
        "oci_index_pin": {
            "digest": EXPECTED_OCI_INDEX,
            "provenance": "capture_request",
            "locally_independently_verified": False,
        },
        "operating_system": image["Os"],
        "ports": container["NetworkSettings"]["Ports"],
        "provider": "galaxy",
        "schema_id": "api_gym.galaxy_fixture_inspection.v1",
    }
    if receipt["container_running"] is not True:
        raise RuntimeError("Galaxy container is not running")
    if receipt["image_id"] != EXPECTED_IMAGE_ID:
        raise RuntimeError(f"Unexpected Galaxy image ID: {receipt['image_id']}")
    if receipt["configured_image"] != EXPECTED_IMAGE_REFERENCE:
        raise RuntimeError(
            f"Unexpected configured image: {receipt['configured_image']}"
        )
    if receipt["architecture"] != "amd64" or receipt["operating_system"] != "linux":
        raise RuntimeError("Unexpected Galaxy image platform")
    if receipt["labels"]["org.opencontainers.image.revision"] != EXPECTED_REVISION:
        raise RuntimeError("Unexpected Galaxy source revision")
    if receipt["ports"] != {
        "8080/tcp": [{"HostIp": "127.0.0.1", "HostPort": "32770"}]
    }:
        raise RuntimeError(f"Unexpected Galaxy port binding: {receipt['ports']}")
    if mounts != [
        {
            "destination": "/data",
            "driver": "local",
            "name": EXPECTED_VOLUME,
            "read_write": True,
            "type": "volume",
        }
    ]:
        raise RuntimeError(f"Unexpected Galaxy mounts: {mounts}")
    return receipt


def bootstrap_admin_key() -> str:
    result = run(
        [
            "docker",
            "exec",
            CONTAINER_NAME,
            "sh",
            "-lc",
            'printf %s "$GALAXY_CONFIG_BOOTSTRAP_ADMIN_API_KEY"',
        ]
    )
    key = result.stdout
    if not key:
        raise RuntimeError("GALAXY_CONFIG_BOOTSTRAP_ADMIN_API_KEY is not configured")
    return key


def body_receipt(raw: bytes, content_type: str | None) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "body_base64": base64.b64encode(raw).decode("ascii"),
        "body_bytes": len(raw),
        "body_sha256": sha256_bytes(raw),
    }
    if not raw:
        receipt["body_kind"] = "empty"
        return receipt
    text = raw.decode("utf-8")
    if content_type and "json" in content_type.lower():
        receipt["body"] = json.loads(text)
        receipt["body_kind"] = "json"
    else:
        receipt["body"] = text
        receipt["body_kind"] = "text"
    return receipt


def request_receipt(
    method: str,
    target: str,
    headers: dict[str, str],
    body: bytes | None,
    *,
    sanitized_json_fields: set[str] | None = None,
) -> dict[str, Any]:
    removed_headers = sorted(
        name for name in headers if name.lower() in SENSITIVE_REQUEST_HEADERS
    )
    safe_headers = {
        name.lower(): value
        for name, value in headers.items()
        if name.lower() not in SENSITIVE_REQUEST_HEADERS
    }
    receipt: dict[str, Any] = {
        "headers": safe_headers,
        "method": method,
        "removed_headers": removed_headers,
        "target": target,
    }
    if body is None:
        receipt["body"] = None
        receipt["body_bytes"] = 0
        receipt["body_sha256"] = sha256_bytes(b"")
        return receipt
    if sanitized_json_fields:
        parsed = json.loads(body.decode("utf-8"))
        for field in sanitized_json_fields:
            if field in parsed:
                parsed[field] = "[REMOVED]"
        receipt.update(
            {
                "body": parsed,
                "body_bytes": None,
                "body_removed": True,
                "body_sha256": None,
                "removed_json_fields": sorted(sanitized_json_fields),
            }
        )
        return receipt
    receipt.update(body_receipt(body, headers.get("Content-Type")))
    return receipt


def call(
    exchanges: list[dict[str, Any]],
    *,
    step_id: str,
    phase: str,
    method: str,
    path: str,
    api_key: str | None = None,
    json_body: Any = None,
    expected_status: int | set[int] | None = None,
    sanitize_request_json_fields: set[str] | None = None,
    remove_response_body: bool = False,
) -> tuple[int, Any, bytes]:
    body = None if json_body is None else canonical_json_bytes(json_body)
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "identity",
        "Connection": "close",
        "Host": f"{HOST}:{PORT}",
    }
    if body is not None:
        headers["Content-Length"] = str(len(body))
        headers["Content-Type"] = "application/json"
    if api_key is not None:
        headers["X-Api-Key"] = api_key
    started_at = utc_now()
    started = time.monotonic()
    connection = http.client.HTTPConnection(HOST, PORT, timeout=30)
    connection.request(method, path, body=body, headers=headers)
    response = connection.getresponse()
    raw = response.read()
    response_headers = response.getheaders()
    connection.close()
    completed_at = utc_now()
    duration_ms = round((time.monotonic() - started) * 1000, 3)
    content_type = next(
        (value for name, value in response_headers if name.lower() == "content-type"),
        None,
    )
    safe_response_headers = [
        [name.lower(), value]
        for name, value in response_headers
        if name.lower() not in SENSITIVE_RESPONSE_HEADERS
    ]
    removed_response_headers = sorted(
        {
            name.lower()
            for name, _ in response_headers
            if name.lower() in SENSITIVE_RESPONSE_HEADERS
        }
    )
    if remove_response_body:
        response_receipt: dict[str, Any] = {
            "body_bytes": None,
            "body_removed": True,
            "body_sha256": None,
            "headers": safe_response_headers,
            "removed_headers": removed_response_headers,
            "status_code": response.status,
        }
        parsed: Any = json.loads(raw.decode("utf-8"))
    else:
        response_receipt = {
            "headers": safe_response_headers,
            "removed_headers": removed_response_headers,
            "status_code": response.status,
            **body_receipt(raw, content_type),
        }
        parsed = response_receipt.get("body")
    exchanges.append(
        {
            "phase": phase,
            "provider_executed": True,
            "request": request_receipt(
                method,
                path,
                headers,
                body,
                sanitized_json_fields=sanitize_request_json_fields,
            ),
            "response": response_receipt,
            "step_id": step_id,
            "timing": {
                "completed_at": completed_at,
                "duration_ms": duration_ms,
                "started_at": started_at,
            },
        }
    )
    if expected_status is not None:
        allowed = (
            {expected_status} if isinstance(expected_status, int) else expected_status
        )
        if response.status not in allowed:
            raise RuntimeError(
                f"{step_id} returned HTTP {response.status}, expected {sorted(allowed)}"
            )
    return response.status, parsed, raw


def docker_action(command: list[str]) -> dict[str, Any]:
    started_at = utc_now()
    started = time.monotonic()
    result = run(command, check=False)
    return {
        "command": command,
        "completed_at": utc_now(),
        "duration_ms": round((time.monotonic() - started) * 1000, 3),
        "exit_code": result.returncode,
        "started_at": started_at,
        "stderr": result.stderr,
        "stdout": result.stdout,
    }


def is_absent(kind: str, name: str) -> tuple[bool, int]:
    result = run(["docker", kind, "inspect", name], check=False)
    return result.returncode != 0, result.returncode


def wait_absent(kind: str, name: str, timeout_seconds: float = 30) -> tuple[bool, int]:
    deadline = time.monotonic() + timeout_seconds
    last_exit_code = 0
    while time.monotonic() < deadline:
        absent, last_exit_code = is_absent(kind, name)
        if absent:
            return True, last_exit_code
        time.sleep(0.25)
    return is_absent(kind, name)


def connector(input_sha256: str) -> dict[str, Any]:
    return {
        "allowed_request_headers": [
            "accept",
            "accept-encoding",
            "connection",
            "content-length",
            "content-type",
            "host",
        ],
        "auth": {
            "contexts": [
                {
                    "actor_alias": "disposable_local_user",
                    "context_id": "fixture_user",
                    "grant_required": True,
                    "secret_source_names": ["galaxy_disposable_user_api_key"],
                    "strategy_id": "x_api_key_header",
                }
            ],
            "bootstrap": {
                "admin_secret_source": "container_environment:"
                "GALAXY_CONFIG_BOOTSTRAP_ADMIN_API_KEY",
                "method": "Galaxy admin API",
                "persisted": False,
            },
            "kind": "secret",
            "secret_sources": [
                {
                    "kind": "capture_process_memory",
                    "name": "galaxy_disposable_user_api_key",
                    "persisted": False,
                }
            ],
        },
        "authoring_policy": {"concurrency": 1, "write_retries": 0},
        "boundary": {
            "kind": "self_hosted_reference",
            "production_equivalence": "not_claimed",
            "statement": (
                "Disposable loopback Galaxy 26.1.rc1 fixture; production "
                "equivalence is not claimed."
            ),
        },
        "bounds": {
            "max_polls": 180,
            "max_requests": 220,
            "request_timeout_ms": 30000,
            "total_timeout_ms": 180000,
        },
        "connector_id": "galaxy_26_1_rc1_connected_history_fasta_v1",
        "driver_kind": "http11",
        "identity": {
            "git_commit": EXPECTED_REVISION,
            "image_id": EXPECTED_IMAGE_ID,
            "origin": ORIGIN,
            "version_major": "26.1",
            "version_minor": "rc1",
        },
        "isolation": {
            "cleanup_kind": "delete_resources_then_remove_fixture",
            "cleanup_strategy_id": (
                "delete_history_user_stop_container_remove_named_volume"
            ),
            "isolation_kind": "disposable_user_and_history",
            "reset_equivalence_claimed": False,
            "reset_kind": "fixture_destroy",
        },
        "known_limitations": [
            "This case captures one history, one upload1 FASTA ingestion, reads, provenance, and readback.",
            "The /api/health route returned 404 on this image; no alternate route is presented as that route.",
            "The exact AMR Gene Detection workflow was not imported or invoked because all five required tool versions were absent.",
            "No production, arbitrary workflow, concurrency, quota, or reset-equivalence behavior is claimed.",
        ],
        "origin": ORIGIN,
        "provider_id": "galaxy",
        "provider_version": "26.1.rc1",
        "request_encoding": "canonical_json",
        "schema_id": "api_gym.galaxy_connected_connector.v1",
        "sensitive_transport_fields": {
            "request_headers_removed": sorted(SENSITIVE_REQUEST_HEADERS),
            "response_headers_removed": sorted(SENSITIVE_RESPONSE_HEADERS),
            "secret_response_bodies_removed": ["create_disposable_api_key"],
        },
        "source_pins": [
            {
                "git_commit": EXPECTED_REVISION,
                "image_id": EXPECTED_IMAGE_ID,
                "image_reference": EXPECTED_IMAGE_REFERENCE,
                "oci_index": EXPECTED_OCI_INDEX,
            }
        ],
        "static_artifact_inputs": [
            {
                "artifact_id": "tiny_fasta",
                "expected_sha256": input_sha256,
                "filename": "input.fa",
                "media_type": "text/x-fasta",
            }
        ],
    }


def recipe(input_bytes: bytes) -> dict[str, Any]:
    return {
        "program_id": "galaxy_connected_history_fasta_v1",
        "schema_id": "api_gym.galaxy_connected_recipe.v1",
        "steps": [
            {
                "assertions": {
                    "body": {
                        "extra/git_commit": EXPECTED_REVISION,
                        "version_major": "26.1",
                        "version_minor": "rc1",
                    },
                    "status": 200,
                },
                "method": "GET",
                "path": "/api/version",
                "role": "identity",
                "step_id": "get_version",
            },
            {
                "assertions": {"status": 404},
                "method": "GET",
                "path": "/api/health",
                "role": "health_observation",
                "step_id": "get_health",
            },
            {
                "assertions": {"body": [], "status": 200},
                "method": "GET",
                "path": "/api/histories",
                "role": "before",
                "step_id": "histories_before",
            },
            {
                "assertions": {"status": 200},
                "method": "POST",
                "path": "/api/histories",
                "role": "mutation",
                "step_id": "create_history",
            },
            {
                "assertions": {"status": 200},
                "method": "POST",
                "path": "/api/tools",
                "role": "mutation",
                "step_id": "upload_fasta",
            },
            {
                "assertions": {"terminal_state": "ok"},
                "method": "GET",
                "path_template": "/api/datasets/{dataset_id}",
                "role": "poll",
                "step_id_prefix": "poll_dataset_",
            },
            {
                "assertions": {"ext": "fasta", "state": "ok", "status": 200},
                "method": "GET",
                "path_template": "/api/datasets/{dataset_id}",
                "role": "read",
                "step_id": "read_dataset",
            },
            {
                "assertions": {"status": 200},
                "method": "GET",
                "path_template": (
                    "/api/histories/{history_id}/contents/{dataset_id}/provenance"
                ),
                "role": "provenance",
                "step_id": "read_provenance",
            },
            {
                "assertions": {
                    "body_bytes": len(input_bytes),
                    "body_sha256": sha256_bytes(input_bytes),
                    "status": 200,
                },
                "method": "GET",
                "path_template": (
                    "/api/histories/{history_id}/contents/{dataset_id}/display"
                    "?raw=true"
                ),
                "role": "readback",
                "step_id": "readback_dataset",
            },
            {
                "assertions": {
                    "exact_required_tool_statuses": [404, 404, 404, 404, 404],
                    "workflow_import_attempted": False,
                    "workflow_invocation_attempted": False,
                },
                "role": "unsupported_boundary",
                "step_id": "staramr_capability_check",
            },
        ],
    }


def secret_variants(secret: str) -> dict[str, bytes]:
    raw = secret.encode("utf-8")
    return {
        "base64": base64.b64encode(raw),
        "raw": raw,
        "sha256_hex": hashlib.sha256(raw).hexdigest().encode("ascii"),
    }


def assert_secrets_absent(paths: list[Path], secrets_to_scan: list[str]) -> dict[str, Any]:
    checked_variants: set[str] = set()
    for path in paths:
        content = path.read_bytes()
        for secret in secrets_to_scan:
            for variant_name, variant in secret_variants(secret).items():
                checked_variants.add(variant_name)
                if variant and variant in content:
                    raise RuntimeError(
                        f"Secret {variant_name} variant persisted in {path}"
                    )
    return {
        "checked_files": [path.name for path in paths],
        "checked_variants": sorted(checked_variants),
        "passed": True,
    }


def main() -> None:
    CASE_ROOT.mkdir(parents=True, exist_ok=True)
    input_bytes = INPUT_PATH.read_bytes()
    input_sha256 = sha256_bytes(input_bytes)
    fixture_pre = inspect_fixture()
    capture_started_at = utc_now()
    capture_started = time.monotonic()
    exchanges: list[dict[str, Any]] = []
    admin_key = bootstrap_admin_key()
    user_key: str | None = None
    password = secrets.token_urlsafe(36)
    email = f"datalox-galaxy-{secrets.token_hex(8)}@example.invalid"
    username = f"datalox_{secrets.token_hex(6)}"
    user_id: str | None = None
    history_id: str | None = None
    dataset_id: str | None = None
    poll_states: list[str] = []
    workflow_boundary: dict[str, Any] | None = None
    minimal_complete = False
    error: str | None = None
    teardown_api_steps: list[str] = []

    try:
        _, created_user, _ = call(
            exchanges,
            step_id="create_disposable_user",
            phase="credential_setup",
            method="POST",
            path="/api/users",
            api_key=admin_key,
            json_body={"email": email, "password": password, "username": username},
            expected_status=200,
            sanitize_request_json_fields={"password"},
        )
        user_id = created_user["id"]
        _, created_key, _ = call(
            exchanges,
            step_id="create_disposable_api_key",
            phase="credential_setup",
            method="POST",
            path=f"/api/users/{user_id}/api_key",
            api_key=admin_key,
            expected_status=200,
            remove_response_body=True,
        )
        if not isinstance(created_key, str) or not created_key:
            raise RuntimeError("Galaxy did not return a disposable user API key")
        user_key = created_key

        _, version, _ = call(
            exchanges,
            step_id="get_version",
            phase="minimal_sequence",
            method="GET",
            path="/api/version",
            api_key=user_key,
            expected_status=200,
        )
        if version != {
            "extra": {
                "build_date": "2026-07-30T15:48:52Z",
                "git_commit": EXPECTED_REVISION,
                "image_tag": "26.1-auto",
            },
            "version_major": "26.1",
            "version_minor": "rc1",
        }:
            raise RuntimeError(f"Unexpected Galaxy version payload: {version}")

        call(
            exchanges,
            step_id="get_health",
            phase="minimal_sequence",
            method="GET",
            path="/api/health",
            api_key=user_key,
            expected_status=404,
        )
        _, histories_before, _ = call(
            exchanges,
            step_id="histories_before",
            phase="minimal_sequence",
            method="GET",
            path="/api/histories",
            api_key=user_key,
            expected_status=200,
        )
        if histories_before != []:
            raise RuntimeError(
                f"Disposable user did not start with empty histories: {histories_before}"
            )

        _, history, _ = call(
            exchanges,
            step_id="create_history",
            phase="minimal_sequence",
            method="POST",
            path="/api/histories",
            api_key=user_key,
            json_body={"name": "Datalox connected FASTA behavior case"},
            expected_status=200,
        )
        history_id = history["id"]
        upload_body = {
            "history_id": history_id,
            "inputs": {
                "ajax_upload": "true",
                "dbkey": "?",
                "file_type": "fasta",
                "files_0|NAME": INPUT_PATH.name,
                "files_0|type": "upload_dataset",
                "files_0|url_paste": input_bytes.decode("ascii"),
            },
            "tool_id": "upload1",
        }
        _, upload, _ = call(
            exchanges,
            step_id="upload_fasta",
            phase="minimal_sequence",
            method="POST",
            path="/api/tools",
            api_key=user_key,
            json_body=upload_body,
            expected_status=200,
        )
        dataset_id = upload["outputs"][0]["id"]

        for poll_index in range(180):
            _, dataset_poll, _ = call(
                exchanges,
                step_id=f"poll_dataset_{poll_index + 1:02d}",
                phase="minimal_sequence",
                method="GET",
                path=f"/api/datasets/{dataset_id}",
                api_key=user_key,
                expected_status=200,
            )
            poll_states.append(dataset_poll["state"])
            if dataset_poll["state"] in TERMINAL_DATASET_STATES:
                break
            time.sleep(0.5)
        if not poll_states or poll_states[-1] != "ok":
            raise RuntimeError(f"Dataset did not reach ok: {poll_states}")

        _, dataset, _ = call(
            exchanges,
            step_id="read_dataset",
            phase="minimal_sequence",
            method="GET",
            path=f"/api/datasets/{dataset_id}",
            api_key=user_key,
            expected_status=200,
        )
        if dataset["state"] != "ok" or dataset["extension"] != "fasta":
            raise RuntimeError(
                "Dataset read did not preserve terminal FASTA identity: "
                f"state={dataset['state']} extension={dataset['extension']}"
            )

        _, provenance, _ = call(
            exchanges,
            step_id="read_provenance",
            phase="minimal_sequence",
            method="GET",
            path=(
                f"/api/histories/{history_id}/contents/{dataset_id}/provenance"
            ),
            api_key=user_key,
            expected_status=200,
        )
        _, _, readback = call(
            exchanges,
            step_id="readback_dataset",
            phase="minimal_sequence",
            method="GET",
            path=(
                f"/api/histories/{history_id}/contents/{dataset_id}/display?raw=true"
            ),
            api_key=user_key,
            expected_status=200,
        )
        if readback != input_bytes:
            raise RuntimeError(
                f"Readback mismatch: expected {input_sha256}, got {sha256_bytes(readback)}"
            )

        _, history_after, _ = call(
            exchanges,
            step_id="read_history_after",
            phase="minimal_sequence",
            method="GET",
            path=f"/api/histories/{history_id}",
            api_key=user_key,
            expected_status=200,
        )
        _, contents_after, _ = call(
            exchanges,
            step_id="read_history_contents_after",
            phase="minimal_sequence",
            method="GET",
            path=f"/api/histories/{history_id}/contents",
            api_key=user_key,
            expected_status=200,
        )
        minimal_complete = True

        _, staramr_search, _ = call(
            exchanges,
            step_id="search_staramr_tools",
            phase="staramr_capability_check",
            method="GET",
            path="/api/tools?" + urlencode({"q": "staramr", "in_panel": "false"}),
            api_key=user_key,
            expected_status=200,
        )
        exact_tool_checks = []
        for index, tool_id in enumerate(REQUIRED_STARAMR_TOOLS, start=1):
            step_id = f"get_required_staramr_tool_{index:02d}"
            status, tool_body, _ = call(
                exchanges,
                step_id=step_id,
                phase="staramr_capability_check",
                method="GET",
                path=f"/api/tools/{quote(tool_id, safe='')}",
                api_key=user_key,
                expected_status={200, 404},
            )
            exact_tool_checks.append(
                {"body": tool_body, "status": status, "step_id": step_id, "tool_id": tool_id}
            )
        missing_tools = [
            item["tool_id"] for item in exact_tool_checks if item["status"] != 200
        ]
        if missing_tools:
            workflow_boundary = {
                "exact_workflow": {
                    "name": "AMR Gene Detection (release v1.1.7)",
                    "public_capture_workflow_id": "f8fab0cd6fc30d92",
                    "public_capture_workflow_uuid": (
                        "b3176e59-a390-4bcd-a549-0f351d42aa69"
                    ),
                    "required_tool_count": len(REQUIRED_STARAMR_TOOLS),
                },
                "exact_tool_checks": exact_tool_checks,
                "import_attempted": False,
                "invocation_attempted": False,
                "missing_required_tools": missing_tools,
                "reason": (
                    "The local pinned image returned HTTP 404 for required exact "
                    "workflow tool versions. Import/invocation would require "
                    "installing the absent workflow tool stack."
                ),
                "search_response": staramr_search,
                "status": "unsupported",
            }
        else:
            raise RuntimeError(
                "All exact StarAMR workflow tools are present; this bounded capture "
                "does not implement the required import/invocation branch"
            )
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        if history_id and user_key:
            try:
                call(
                    exchanges,
                    step_id="purge_history",
                    phase="teardown",
                    method="DELETE",
                    path=f"/api/histories/{history_id}?purge=true",
                    api_key=user_key,
                    expected_status=200,
                )
                teardown_api_steps.append("purge_history")
            except Exception as cleanup_exc:
                teardown_api_steps.append(
                    f"purge_history_failed:{type(cleanup_exc).__name__}:{cleanup_exc}"
                )
        if user_id:
            if user_key:
                try:
                    call(
                        exchanges,
                        step_id="delete_disposable_user",
                        phase="teardown",
                        method="DELETE",
                        path=f"/api/users/{user_id}",
                        api_key=user_key,
                        expected_status=200,
                    )
                    teardown_api_steps.append("delete_disposable_user")
                except Exception as cleanup_exc:
                    teardown_api_steps.append(
                        "delete_disposable_user_failed:"
                        f"{type(cleanup_exc).__name__}:{cleanup_exc}"
                    )

        stop_receipt = docker_action(
            ["docker", "stop", "--timeout", "30", CONTAINER_NAME]
        )
        container_absent, container_inspect_exit = wait_absent(
            "container", CONTAINER_NAME
        )
        if container_absent:
            remove_receipt = {
                "action": "container_auto_removed_after_stop",
                "command": None,
                "exit_code": 0,
            }
        else:
            remove_receipt = docker_action(["docker", "rm", "-f", CONTAINER_NAME])
            container_absent, container_inspect_exit = wait_absent(
                "container", CONTAINER_NAME
            )
        volume_receipt = docker_action(["docker", "volume", "rm", EXPECTED_VOLUME])
        if volume_receipt["exit_code"] != 0:
            time.sleep(0.5)
            volume_receipt = docker_action(
                ["docker", "volume", "rm", EXPECTED_VOLUME]
            )
        volume_absent, volume_inspect_exit = wait_absent("volume", EXPECTED_VOLUME)
        teardown = {
            "api_cleanup_steps": teardown_api_steps,
            "attached_fixture_volumes_removed": [EXPECTED_VOLUME],
            "container_absent_after": container_absent,
            "container_auto_remove": fixture_pre["auto_remove"],
            "container_inspect_exit_code_after": container_inspect_exit,
            "container_remove": remove_receipt,
            "container_stop": stop_receipt,
            "schema_id": "api_gym.galaxy_fixture_teardown.v1",
            "volume_absent_after": volume_absent,
            "volume_inspect_exit_code_after": volume_inspect_exit,
            "volume_remove": volume_receipt,
            "volumes_created_by_capture": [],
        }

    capture_completed_at = utc_now()
    capture = {
        "capture_error": error,
        "capture_id": "galaxy_connected_history_fasta_v1",
        "exchanges": exchanges,
        "input": {
            "body_bytes": len(input_bytes),
            "body_sha256": input_sha256,
            "filename": INPUT_PATH.name,
            "immutable": True,
            "media_type": "text/x-fasta",
        },
        "minimal_sequence": {
            "completed": minimal_complete,
            "dataset_id": dataset_id,
            "history_id": history_id,
            "poll_states": poll_states,
            "provider_executed": minimal_complete,
            "steps": [
                "get_version",
                "get_health",
                "histories_before",
                "create_history",
                "upload_fasta",
                "poll_dataset_*",
                "read_dataset",
                "read_provenance",
                "readback_dataset",
                "read_history_after",
                "read_history_contents_after",
            ],
        },
        "observations": {
            "after": {
                "history": history_after if minimal_complete else None,
                "history_contents": contents_after if minimal_complete else None,
                "provenance": provenance if minimal_complete else None,
            },
            "before": {
                "histories": histories_before if minimal_complete else None,
            },
        },
        "origin": ORIGIN,
        "provider_execution": {
            "kind": "connected_self_hosted_reference",
            "production_equivalence": "not_claimed",
            "status": "observed",
        },
        "provider_id": "galaxy",
        "provider_version": "26.1.rc1",
        "sanitization": {
            "cookies_persisted": False,
            "request_secret_headers_removed": sorted(SENSITIVE_REQUEST_HEADERS),
            "response_secret_headers_removed": sorted(SENSITIVE_RESPONSE_HEADERS),
            "secret_response_bodies_removed": ["create_disposable_api_key"],
            "secrets_persisted": False,
        },
        "schema_id": "api_gym.galaxy_connected_capture.v1",
        "staramr_execution": workflow_boundary,
        "timing": {
            "completed_at": capture_completed_at,
            "duration_ms": round((time.monotonic() - capture_started) * 1000, 3),
            "started_at": capture_started_at,
        },
    }
    fixture_receipt = {
        "credential_lifecycle": {
            "api_key_created": user_key is not None,
            "api_key_persisted": False,
            "bootstrap_admin_key_source": (
                "container_environment:GALAXY_CONFIG_BOOTSTRAP_ADMIN_API_KEY"
            ),
            "bootstrap_admin_key_persisted": False,
            "disposable_user_id": user_id,
            "password_persisted": False,
        },
        "pre_capture": fixture_pre,
        "schema_id": "api_gym.galaxy_fixture_receipt.v1",
        "teardown": teardown,
    }
    connector_value = connector(input_sha256)
    recipe_value = recipe(input_bytes)
    capture_path = CASE_ROOT / "capture.json"
    connector_path = CASE_ROOT / "connector.json"
    fixture_path = CASE_ROOT / "fixture_receipt.json"
    recipe_path = CASE_ROOT / "recipe.json"
    write_json(capture_path, capture)
    write_json(connector_path, connector_value)
    write_json(fixture_path, fixture_receipt)
    write_json(recipe_path, recipe_value)

    scan = assert_secrets_absent(
        [capture_path, connector_path, fixture_path, recipe_path, INPUT_PATH],
        [admin_key, password, *([user_key] if user_key else [])],
    )
    fixture_receipt["credential_lifecycle"]["secret_scan"] = scan
    write_json(fixture_path, fixture_receipt)

    metadata = {
        "claims": {
            "health_route": "provider_observed_http_404",
            "minimal_sequence": (
                "provider_executed" if minimal_complete else "capture_failed"
            ),
            "production_equivalence": "not_claimed",
            "reset_equivalence": "not_claimed",
            "staramr_execution": (
                workflow_boundary["status"] if workflow_boundary else "not_checked"
            ),
        },
        "coverage": {
            "exchange_count": len(exchanges),
            "poll_count": len(poll_states),
            "provider_executed_operations": [
                item["step_id"] for item in exchanges
            ],
            "staramr_import_attempted": bool(
                workflow_boundary and workflow_boundary["import_attempted"]
            ),
            "staramr_invocation_attempted": bool(
                workflow_boundary and workflow_boundary["invocation_attempted"]
            ),
        },
        "digests": {
            "capture": sha256_file(capture_path),
            "connector": sha256_file(connector_path),
            "fixture_receipt": sha256_file(fixture_path),
            "input": input_sha256,
            "recipe": sha256_file(recipe_path),
        },
        "program_id": "galaxy_connected_history_fasta_v1",
        "provider_id": "galaxy",
        "provider_version": "26.1.rc1",
        "schema_id": "api_gym.provider_behavior_case_metadata.v1",
    }
    write_json(CASE_ROOT / "case_metadata.json", metadata)

    if error:
        raise RuntimeError(error)
    if not teardown["container_absent_after"] or not teardown["volume_absent_after"]:
        raise RuntimeError(f"Fixture teardown verification failed: {teardown}")


if __name__ == "__main__":
    main()
