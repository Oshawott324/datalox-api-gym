from __future__ import annotations

import json

import pytest

from api_gym.provider_components.elabftw.projection import (
    ELabFTWExperimentsProjection,
    ProjectionError,
)

HEADERS = {"accept": "application/json", "content-type": "application/json"}
TITLE = "Datalox AMR analysis handoff"
BODY = "<p>Reference AMR analysis handoff for isolate AMR-ISO-001.</p>"
METADATA = {
    "extra_fields": {
        "isolate_id": {
            "description": "Stable isolate identifier used across the analysis handoff",
            "type": "text",
            "value": "AMR-ISO-001",
        }
    }
}


def _run_sequence(
    projection: ELabFTWExperimentsProjection,
) -> tuple[int, dict[str, object]]:
    create = projection.request(
        "POST",
        "/api/v2/experiments",
        body={},
        headers=HEADERS,
    )
    experiment_id = int(create.headers["location"].rsplit("/", 1)[1])
    patch = projection.request(
        "PATCH",
        f"/api/v2/experiments/{experiment_id}",
        body={
            "title": TITLE,
            "body": BODY,
            "metadata": json.dumps(METADATA, separators=(",", ":")),
        },
        headers=HEADERS,
    )
    get = projection.request(
        "GET",
        f"/api/v2/experiments/{experiment_id}",
        headers={"accept": "application/json"},
    )
    assert create.status_code == 201
    assert patch.status_code == 200
    assert get.status_code == 200
    return experiment_id, get.body


def test_grounded_create_patch_get_and_reset_are_deterministic() -> None:
    projection = ELabFTWExperimentsProjection(seed=91)

    first_id, first_body = _run_sequence(projection)

    assert first_body == {
        "id": first_id,
        "title": TITLE,
        "body": BODY,
        "metadata": METADATA,
    }
    assert projection.accessible_experiment_count() == 1
    assert projection.reference_title_present(TITLE) is True
    assert projection.experiment_count_delta() == 1

    projection.reset(91)
    assert projection.accessible_experiment_count() == 0
    assert projection.reference_title_present(TITLE) is False

    second_id, second_body = _run_sequence(projection)
    assert (second_id, second_body) == (first_id, first_body)


def test_patch_requires_metadata_as_valid_json_string() -> None:
    projection = ELabFTWExperimentsProjection()
    create = projection.request(
        "POST",
        "/api/v2/experiments",
        body={},
        headers=HEADERS,
    )
    experiment_id = int(create.headers["location"].rsplit("/", 1)[1])

    with pytest.raises(ProjectionError) as object_error:
        projection.request(
            "PATCH",
            f"/api/v2/experiments/{experiment_id}",
            body={"title": TITLE, "body": BODY, "metadata": METADATA},
            headers=HEADERS,
        )
    assert object_error.value.code == "ELABFTW_METADATA_MUST_BE_JSON_STRING"

    with pytest.raises(ProjectionError) as malformed_error:
        projection.request(
            "PATCH",
            f"/api/v2/experiments/{experiment_id}",
            body={"title": TITLE, "body": BODY, "metadata": "{"},
            headers=HEADERS,
        )
    assert malformed_error.value.code == "ELABFTW_INVALID_METADATA_JSON"


@pytest.mark.parametrize(
    ("method", "path", "body", "expected_code"),
    [
        ("DELETE", "/api/v2/experiments/1", None, "ELABFTW_UNSUPPORTED_OPERATION"),
        ("PATCH", "/api/v2/experiments", {}, "ELABFTW_EXPERIMENT_ID_REQUIRED"),
        ("GET", "/api/v2/experiments/", None, "ELABFTW_EXPERIMENT_ID_REQUIRED"),
        ("POST", "/api/v2/experiments", {"title": "x"}, "ELABFTW_INVALID_CREATE_PAYLOAD"),
    ],
)
def test_unsupported_or_invalid_requests_fail_closed(
    method: str,
    path: str,
    body: object,
    expected_code: str,
) -> None:
    projection = ELabFTWExperimentsProjection()

    with pytest.raises(ProjectionError) as error:
        projection.request(method, path, body=body, headers=HEADERS)

    assert error.value.code == expected_code
    assert error.value.to_dict()["details"]


def test_patch_before_create_fails_closed() -> None:
    projection = ELabFTWExperimentsProjection()

    with pytest.raises(ProjectionError) as error:
        projection.request(
            "PATCH",
            "/api/v2/experiments/1",
            body={
                "title": TITLE,
                "body": BODY,
                "metadata": json.dumps(METADATA),
            },
            headers=HEADERS,
        )

    assert error.value.code == "ELABFTW_EXPERIMENT_NOT_FOUND"
