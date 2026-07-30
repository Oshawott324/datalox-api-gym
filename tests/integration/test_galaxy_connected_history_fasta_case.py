from __future__ import annotations

import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, urlsplit

import pytest

from scripts.providers.galaxy import capture_connected_history_fasta as capture_script


REPO_ROOT = Path(__file__).resolve().parents[2]
CASE_ROOT = (
    REPO_ROOT
    / "source_packs/apis/galaxy/2026-07-30/behavior_cases"
    / "connected_history_fasta_v1"
)
CAPTURE_SCRIPT_PATH = (
    REPO_ROOT / "scripts/providers/galaxy/capture_connected_history_fasta.py"
)

ORIGIN = "http://127.0.0.1:32770"
COMMIT = "3d62013917dfc9e285c2be923b7b5b2034469d6f"
IMAGE_ID = "sha256:8e5b825e2d064707caa9f564bd5280bef0a79b666ccfee116ae7c311657eec62"
IMAGE_REFERENCE = f"datalox-galaxy-reference@{IMAGE_ID}"
OCI_INDEX = "sha256:100a37301e5f4fb3ac560be5cec7ec5629400673cef8511ea2a8c17b4c8b7399"
INPUT_SHA256 = "sha256:d044ffc156b7f0a06cd252ec80ab8f0c0ef40ee57bbe3b0d4139f70bd8cbd39c"
CAPTURE_SCRIPT_SHA256 = (
    "sha256:e970593dca4813b3354ff750861b94948d55f744ccf774640f8ea0975cd3f024"
)
ARTIFACT_DIGESTS = {
    "capture": "sha256:bca9a588f319b3572369b9093b312cc1d0889983bab281cb78280afa2ae5cb37",
    "connector": (
        "sha256:a982c09c7b231b009716c5ed39f3d597b55599e88222eaa44692f1eef2272c18"
    ),
    "fixture_receipt": (
        "sha256:987ea01ea4b9811e069230ec6c64640ac59d47cc9dec1d90321063d3e0719260"
    ),
    "input": INPUT_SHA256,
    "recipe": "sha256:ef426a5b7e7ec6998cc3e453b0c21ca7f26e1113541cfa01170ab927122e9c01",
}
REQUIRED_STARAMR_TOOLS = (
    "toolshed.g2.bx.psu.edu/repos/iuc/staramr/staramr_search/0.11.0+galaxy3",
    "toolshed.g2.bx.psu.edu/repos/iuc/amrfinderplus/amrfinderplus/3.12.8+galaxy0",
    "toolshed.g2.bx.psu.edu/repos/iuc/abricate/abricate/1.0.1",
    (
        "toolshed.g2.bx.psu.edu/repos/iuc/tooldistillator/"
        "tooldistillator/1.0.4+galaxy0"
    ),
    (
        "toolshed.g2.bx.psu.edu/repos/iuc/tooldistillator_summarize/"
        "tooldistillator_summarize/1.0.4+galaxy0"
    ),
)
SENSITIVE_REQUEST_HEADERS = {"authorization", "cookie", "x-api-key"}
SENSITIVE_RESPONSE_HEADERS = {"set-cookie"}


def _load_json(filename: str) -> dict[str, Any]:
    return json.loads((CASE_ROOT / filename).read_text(encoding="utf-8"))


def _digest(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _fixture_inspection_objects(
    pre_capture: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    container = {
        "Config": {
            "Image": pre_capture["configured_image"],
            "Labels": {
                "io.datalox.disposable-marker": pre_capture["disposable_marker"],
                **pre_capture["labels"],
            },
        },
        "HostConfig": {"AutoRemove": pre_capture["auto_remove"]},
        "Image": pre_capture["image_id"],
        "Mounts": [
            {
                "Destination": mount["destination"],
                "Driver": mount["driver"],
                "Name": mount["name"],
                "RW": mount["read_write"],
                "Type": mount["type"],
            }
            for mount in pre_capture["mounts"]
        ],
        "NetworkSettings": {"Ports": pre_capture["ports"]},
        "State": {"Running": pre_capture["container_running"]},
    }
    image = {
        "Architecture": pre_capture["architecture"],
        "Os": pre_capture["operating_system"],
        "RepoDigests": pre_capture["image_repo_digests"],
    }
    return container, image


def test_galaxy_connected_history_fasta_case_is_exact_and_offline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = _load_json("capture.json")
    connector = _load_json("connector.json")
    fixture_receipt = _load_json("fixture_receipt.json")
    metadata = _load_json("case_metadata.json")
    recipe = _load_json("recipe.json")
    input_bytes = (CASE_ROOT / "input.fa").read_bytes()

    assert metadata["digests"] == ARTIFACT_DIGESTS
    artifact_paths = {
        "capture": CASE_ROOT / "capture.json",
        "connector": CASE_ROOT / "connector.json",
        "fixture_receipt": CASE_ROOT / "fixture_receipt.json",
        "input": CASE_ROOT / "input.fa",
        "recipe": CASE_ROOT / "recipe.json",
    }
    assert {
        artifact: _digest(path) for artifact, path in artifact_paths.items()
    } == ARTIFACT_DIGESTS
    assert _digest(CAPTURE_SCRIPT_PATH) == CAPTURE_SCRIPT_SHA256
    assert capture_script.CASE_ROOT == CASE_ROOT
    assert capture_script.INPUT_PATH == CASE_ROOT / "input.fa"
    assert capture_script.connector(INPUT_SHA256) == connector
    assert capture_script.recipe(input_bytes) == recipe

    assert len(input_bytes) == 44
    assert _digest(CASE_ROOT / "input.fa") == INPUT_SHA256
    assert capture["input"] == {
        "body_bytes": 44,
        "body_sha256": INPUT_SHA256,
        "filename": "input.fa",
        "immutable": True,
        "media_type": "text/x-fasta",
    }
    assert metadata["claims"] == {
        "health_route": "provider_observed_http_404",
        "minimal_sequence": "provider_executed",
        "production_equivalence": "not_claimed",
        "reset_equivalence": "not_claimed",
        "staramr_execution": "unsupported",
    }
    assert capture["capture_error"] is None
    assert capture["provider_execution"] == {
        "kind": "connected_self_hosted_reference",
        "production_equivalence": "not_claimed",
        "status": "observed",
    }

    expected_pin = {
        "git_commit": COMMIT,
        "image_id": IMAGE_ID,
        "image_reference": IMAGE_REFERENCE,
        "oci_index": OCI_INDEX,
    }
    assert connector["source_pins"] == [expected_pin]
    assert connector["identity"] == {
        "git_commit": COMMIT,
        "image_id": IMAGE_ID,
        "origin": ORIGIN,
        "version_major": "26.1",
        "version_minor": "rc1",
    }
    assert connector["origin"] == capture["origin"] == ORIGIN
    parsed_origin = urlsplit(ORIGIN)
    assert (
        parsed_origin.scheme,
        parsed_origin.hostname,
        parsed_origin.port,
        parsed_origin.username,
        parsed_origin.password,
        parsed_origin.path,
        parsed_origin.query,
        parsed_origin.fragment,
    ) == ("http", "127.0.0.1", 32770, None, None, "", "", "")

    pre_capture = fixture_receipt["pre_capture"]
    assert pre_capture["container_running"] is True
    assert pre_capture["auto_remove"] is True
    assert pre_capture["disposable_marker"] == "galaxy-reference-v1"
    assert pre_capture["image_id"] == IMAGE_ID
    assert pre_capture["configured_image"] == IMAGE_REFERENCE
    assert pre_capture["image_reference"] == IMAGE_REFERENCE
    assert pre_capture["image_repo_digests"] == [IMAGE_REFERENCE]
    assert pre_capture["labels"]["org.opencontainers.image.revision"] == COMMIT
    assert pre_capture["loopback_origin"] == ORIGIN
    assert pre_capture["ports"] == {
        "8080/tcp": [{"HostIp": "127.0.0.1", "HostPort": "32770"}]
    }
    assert pre_capture["mounts"] == [
        {
            "destination": "/data",
            "driver": "local",
            "name": "datalox-galaxy-sequence-data-59441",
            "read_write": True,
            "type": "volume",
        }
    ]
    assert pre_capture["oci_index_pin"] == {
        "digest": OCI_INDEX,
        "locally_independently_verified": False,
        "provenance": "capture_request",
    }

    exchanges = capture["exchanges"]
    by_step = {exchange["step_id"]: exchange for exchange in exchanges}
    assert len(by_step) == len(exchanges) == metadata["coverage"]["exchange_count"] == 105
    assert all(exchange["provider_executed"] is True for exchange in exchanges)
    assert metadata["coverage"]["provider_executed_operations"] == [
        exchange["step_id"] for exchange in exchanges
    ]

    poll_step_ids = [f"poll_dataset_{index:02d}" for index in range(1, 86)]
    expected_step_ids = [
        "create_disposable_user",
        "create_disposable_api_key",
        "get_version",
        "get_health",
        "histories_before",
        "create_history",
        "upload_fasta",
        *poll_step_ids,
        "read_dataset",
        "read_provenance",
        "readback_dataset",
        "read_history_after",
        "read_history_contents_after",
        "search_staramr_tools",
        *(f"get_required_staramr_tool_{index:02d}" for index in range(1, 6)),
        "purge_history",
        "delete_disposable_user",
    ]
    assert [exchange["step_id"] for exchange in exchanges] == expected_step_ids
    non_200_statuses = {
        "get_health": 404,
        **{
            f"get_required_staramr_tool_{index:02d}": 404
            for index in range(1, 6)
        },
        "delete_disposable_user": 403,
    }
    assert {
        exchange["step_id"]: exchange["response"]["status_code"]
        for exchange in exchanges
    } == {
        step_id: non_200_statuses.get(step_id, 200)
        for step_id in expected_step_ids
    }
    assert all(
        exchange["request"]["headers"]["host"] == "127.0.0.1:32770"
        for exchange in exchanges
    )

    version = by_step["get_version"]["response"]["body"]
    assert version == {
        "extra": {
            "build_date": "2026-07-30T15:48:52Z",
            "git_commit": COMMIT,
            "image_tag": "26.1-auto",
        },
        "version_major": "26.1",
        "version_minor": "rc1",
    }
    assert by_step["histories_before"]["response"]["body"] == []

    sequence = capture["minimal_sequence"]
    assert sequence["completed"] is True
    assert sequence["provider_executed"] is True
    history_id = sequence["history_id"]
    dataset_id = sequence["dataset_id"]

    create_history = by_step["create_history"]
    assert (
        create_history["request"]["method"],
        create_history["request"]["target"],
        create_history["request"]["body"],
        create_history["response"]["status_code"],
    ) == (
        "POST",
        "/api/histories",
        {"name": "Datalox connected FASTA behavior case"},
        200,
    )
    assert create_history["response"]["body"]["id"] == history_id
    assert create_history["response"]["body"]["state"] == "new"

    upload = by_step["upload_fasta"]
    assert (
        upload["request"]["method"],
        upload["request"]["target"],
        upload["request"]["body"],
        upload["response"]["status_code"],
    ) == (
        "POST",
        "/api/tools",
        {
            "history_id": history_id,
            "inputs": {
                "ajax_upload": "true",
                "dbkey": "?",
                "file_type": "fasta",
                "files_0|NAME": "input.fa",
                "files_0|type": "upload_dataset",
                "files_0|url_paste": input_bytes.decode("ascii"),
            },
            "tool_id": "upload1",
        },
        200,
    )
    assert upload["response"]["body"]["outputs"][0] | {
        "id": dataset_id,
        "file_ext": "fasta",
        "name": "input.fa",
        "state": "queued",
    } == upload["response"]["body"]["outputs"][0]
    assert upload["response"]["body"]["jobs"][0]["tool_id"] == "upload1"

    polls = [by_step[step_id] for step_id in poll_step_ids]
    poll_states = [poll["response"]["body"]["state"] for poll in polls]
    assert metadata["coverage"]["poll_count"] == len(polls) == 85
    assert poll_states == ["queued"] * 3 + ["running"] * 81 + ["ok"]
    assert sequence["poll_states"] == poll_states
    assert all(
        poll["request"]["method"] == "GET"
        and poll["request"]["target"] == f"/api/datasets/{dataset_id}"
        and poll["response"]["status_code"] == 200
        for poll in polls
    )

    dataset_read = by_step["read_dataset"]
    assert dataset_read["request"]["target"] == f"/api/datasets/{dataset_id}"
    assert dataset_read["response"]["body"] | {
        "id": dataset_id,
        "history_id": history_id,
        "name": "input.fa",
        "state": "ok",
        "extension": "fasta",
        "file_ext": "fasta",
        "file_size": 44,
        "metadata_data_lines": 2,
        "metadata_sequences": 1,
    } == dataset_read["response"]["body"]

    provenance = by_step["read_provenance"]["response"]["body"]
    assert provenance == capture["observations"]["after"]["provenance"]
    assert provenance["id"] == dataset_id
    assert provenance["tool_id"] == "upload1"
    assert provenance["parameters"]["file_type"] == '"fasta"'

    readback = by_step["readback_dataset"]["response"]
    assert readback["status_code"] == 200
    assert readback["body_bytes"] == 44
    assert readback["body_sha256"] == INPUT_SHA256
    assert readback["body"].encode("ascii") == input_bytes
    assert base64.b64decode(readback["body_base64"], validate=True) == input_bytes

    after = capture["observations"]["after"]
    assert after["history"]["state"] == "ok"
    assert after["history"]["count"] == 1
    assert after["history"]["size"] == 44
    assert after["history_contents"] == [
        by_step["read_history_contents_after"]["response"]["body"][0]
    ]
    assert after["history_contents"][0] | {
        "id": dataset_id,
        "history_id": history_id,
        "name": "input.fa",
        "state": "ok",
        "extension": "fasta",
    } == after["history_contents"][0]

    expected_sanitization = {
        "cookies_persisted": False,
        "request_secret_headers_removed": sorted(SENSITIVE_REQUEST_HEADERS),
        "response_secret_headers_removed": sorted(SENSITIVE_RESPONSE_HEADERS),
        "secret_response_bodies_removed": ["create_disposable_api_key"],
        "secrets_persisted": False,
    }
    assert capture["sanitization"] == expected_sanitization
    assert connector["sensitive_transport_fields"] == {
        "request_headers_removed": sorted(SENSITIVE_REQUEST_HEADERS),
        "response_headers_removed": sorted(SENSITIVE_RESPONSE_HEADERS),
        "secret_response_bodies_removed": ["create_disposable_api_key"],
    }
    credentials = fixture_receipt["credential_lifecycle"]
    assert credentials["api_key_created"] is True
    assert credentials["api_key_persisted"] is False
    assert credentials["bootstrap_admin_key_persisted"] is False
    assert credentials["password_persisted"] is False
    assert credentials["secret_scan"] == {
        "checked_files": [
            "capture.json",
            "connector.json",
            "fixture_receipt.json",
            "recipe.json",
            "input.fa",
        ],
        "checked_variants": ["base64", "raw", "sha256_hex"],
        "passed": True,
    }
    for exchange in exchanges:
        assert (
            SENSITIVE_REQUEST_HEADERS
            & {name.lower() for name in exchange["request"]["headers"]}
            == set()
        )
        assert {
            name.lower() for name, _ in exchange["response"]["headers"]
        }.isdisjoint(SENSITIVE_RESPONSE_HEADERS)
    create_user_request = by_step["create_disposable_user"]["request"]
    assert create_user_request["body"]["password"] == "[REMOVED]"
    assert create_user_request["removed_json_fields"] == ["password"]
    assert create_user_request["body_removed"] is True
    assert "body_base64" not in create_user_request
    create_key_response = by_step["create_disposable_api_key"]["response"]
    assert create_key_response["body_removed"] is True
    assert "body" not in create_key_response
    assert "body_base64" not in create_key_response

    staramr = capture["staramr_execution"]
    assert staramr["status"] == "unsupported"
    assert staramr["search_response"] == []
    assert staramr["import_attempted"] is False
    assert staramr["invocation_attempted"] is False
    assert staramr["missing_required_tools"] == list(REQUIRED_STARAMR_TOOLS)
    assert metadata["coverage"]["staramr_import_attempted"] is False
    assert metadata["coverage"]["staramr_invocation_attempted"] is False
    assert staramr["exact_workflow"]["required_tool_count"] == 5
    assert len(staramr["exact_tool_checks"]) == 5
    for index, (tool_id, check) in enumerate(
        zip(REQUIRED_STARAMR_TOOLS, staramr["exact_tool_checks"], strict=True),
        start=1,
    ):
        step_id = f"get_required_staramr_tool_{index:02d}"
        expected_body = {
            "err_code": 404001,
            "err_msg": f"Could not find tool with id '{tool_id}'.",
        }
        assert check == {
            "body": expected_body,
            "status": 404,
            "step_id": step_id,
            "tool_id": tool_id,
        }
        assert by_step[step_id]["request"]["target"] == (
            f"/api/tools/{quote(tool_id, safe='')}"
        )
        assert by_step[step_id]["response"]["body"] == expected_body
    staramr_recipe_step = recipe["steps"][-1]
    assert staramr_recipe_step["assertions"] == {
        "exact_required_tool_statuses": [404] * 5,
        "workflow_import_attempted": False,
        "workflow_invocation_attempted": False,
    }

    teardown = fixture_receipt["teardown"]
    assert teardown["api_cleanup_steps"] == [
        "purge_history",
        (
            "delete_disposable_user_failed:RuntimeError:"
            "delete_disposable_user returned HTTP 403, expected [200]"
        ),
    ]
    assert by_step["purge_history"]["response"]["status_code"] == 200
    assert by_step["purge_history"]["response"]["body"]["purged"] is True
    assert by_step["delete_disposable_user"]["response"]["status_code"] == 403
    assert teardown["container_stop"]["exit_code"] == 0
    assert teardown["container_remove"] == {
        "action": "container_auto_removed_after_stop",
        "command": None,
        "exit_code": 0,
    }
    assert teardown["container_absent_after"] is True
    assert teardown["container_inspect_exit_code_after"] == 1
    assert teardown["attached_fixture_volumes_removed"] == [
        "datalox-galaxy-sequence-data-59441"
    ]
    assert teardown["volume_remove"]["exit_code"] == 0
    assert teardown["volume_absent_after"] is True
    assert teardown["volume_inspect_exit_code_after"] == 1

    fixture_container, fixture_image = _fixture_inspection_objects(pre_capture)

    def install_inspection(
        container: dict[str, Any],
        image: dict[str, Any],
    ) -> None:
        def fake_docker_json(kind: str, name: str) -> dict[str, Any]:
            if kind == "container":
                assert name == pre_capture["container_name"]
                return container
            assert (kind, name) == ("image", IMAGE_ID)
            return image

        monkeypatch.setattr(capture_script, "docker_json", fake_docker_json)

    install_inspection(fixture_container, fixture_image)
    assert capture_script.inspect_fixture() == pre_capture

    fixture_mutations: list[
        tuple[str, Callable[[dict[str, Any], dict[str, Any]], None]]
    ] = [
        (
            "not running",
            lambda container, _image: container["State"].__setitem__(
                "Running", False
            ),
        ),
        (
            "Unexpected Galaxy image ID",
            lambda container, _image: container.__setitem__("Image", "sha256:wrong"),
        ),
        (
            "Unexpected configured image",
            lambda container, _image: container["Config"].__setitem__(
                "Image", "galaxy:unpinned"
            ),
        ),
        (
            "Unexpected Galaxy image platform",
            lambda _container, image: image.__setitem__("Architecture", "arm64"),
        ),
        (
            "Unexpected Galaxy source revision",
            lambda container, _image: container["Config"]["Labels"].__setitem__(
                "org.opencontainers.image.revision", "unpinned"
            ),
        ),
        (
            "Unexpected Galaxy port binding",
            lambda container, _image: container["NetworkSettings"].__setitem__(
                "Ports",
                {"8080/tcp": [{"HostIp": "0.0.0.0", "HostPort": "32770"}]},
            ),
        ),
        (
            "Unexpected Galaxy mounts",
            lambda container, _image: container.__setitem__("Mounts", []),
        ),
    ]
    for expected_error, mutate in fixture_mutations:
        bad_container = deepcopy(fixture_container)
        bad_image = deepcopy(fixture_image)
        mutate(bad_container, bad_image)
        install_inspection(bad_container, bad_image)
        with pytest.raises(RuntimeError, match=expected_error):
            capture_script.inspect_fixture()
