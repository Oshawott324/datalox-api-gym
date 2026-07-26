from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

pytest.importorskip("datalox_gated_runtime.reference")

from datalox_gated_runtime.reference import (  # noqa: E402
    ConformanceReport,
    ObservedResponse,
    run_conformance,
)

from api_gym.provider_components.elabftw.reference_conformance import (  # noqa: E402
    CAPTURE_PROVIDER_VERSION,
    CAPTURE_WEB_IMAGE_DIGEST,
    DEFAULT_CAPTURE_PATH,
    DEFAULT_REPORT_PATH,
    CaptureContractError,
    ELabFTWProjectionTarget,
    ELabFTWReferenceProfile,
    load_reference_trace,
    run_projection_conformance,
)


def test_grounded_capture_conforms_to_projection() -> None:
    report = run_projection_conformance()

    assert report.passed is True
    assert report.provider_id == "elabftw"
    assert report.provider_version == "5.6.10"
    assert report.target_id == "elabftw_experiments_projection_v0"
    assert report.profile_id == "elabftw_experiment_id_location_v0"


def test_reference_trace_metadata_binds_raw_capture_bytes() -> None:
    trace = load_reference_trace()
    expected_digest = f"sha256:{hashlib.sha256(DEFAULT_CAPTURE_PATH.read_bytes()).hexdigest()}"

    assert trace.metadata["capture_digest"] == expected_digest
    assert expected_digest == (
        "sha256:ab08452c77328dc894fb2b081efa42eb7632f1ec6f66d539628d8ede41509cc6"
    )


@pytest.mark.parametrize(
    ("field", "tampered_value", "expected_message"),
    [
        (
            "version",
            "5.6.11",
            f"capture provider version must be {CAPTURE_PROVIDER_VERSION}",
        ),
        (
            "image_digest",
            "sha256:" + ("0" * 64),
            (
                "capture provider web image digest must be "
                f"{CAPTURE_WEB_IMAGE_DIGEST}"
            ),
        ),
    ],
)
def test_tampered_provider_identity_fails_closed(
    tmp_path: Path,
    field: str,
    tampered_value: str,
    expected_message: str,
) -> None:
    capture = json.loads(DEFAULT_CAPTURE_PATH.read_text(encoding="utf-8"))
    if field == "version":
        capture["provider"]["version"] = tampered_value
    else:
        capture["provider"]["image"]["digest"] = tampered_value
    tampered_path = tmp_path / "tampered-capture.json"
    tampered_path.write_text(json.dumps(capture), encoding="utf-8")

    with pytest.raises(CaptureContractError) as error:
        load_reference_trace(tampered_path)
    assert str(error.value) == expected_message


def test_checked_in_report_round_trips_and_matches_generation(tmp_path: Path) -> None:
    generated_path = tmp_path / "projection-report.json"
    generated = run_projection_conformance(report_path=generated_path)
    checked_in_raw = json.loads(DEFAULT_REPORT_PATH.read_text(encoding="utf-8"))

    assert json.loads(generated_path.read_text(encoding="utf-8")) == checked_in_raw
    assert ConformanceReport.from_dict(checked_in_raw) == generated


def test_intentional_projection_mismatch_is_detected() -> None:
    trace = load_reference_trace()
    target = _MismatchedTitleTarget()

    report = run_conformance(
        trace,
        target,
        profile=ELabFTWReferenceProfile(),
    )

    assert report.passed is False
    assert any(
        mismatch.code == "response_value_mismatch"
        and mismatch.path == "/body/title"
        and mismatch.step_id == "get_experiment"
        for mismatch in report.mismatches
    )


def test_generated_id_normalization_does_not_hide_cross_step_id_mismatch() -> None:
    trace = load_reference_trace()

    report = run_conformance(
        trace,
        _MismatchedIdTarget(),
        profile=ELabFTWReferenceProfile(),
    )

    assert report.passed is False
    assert any(
        mismatch.code == "response_type_mismatch"
        and mismatch.path == "/body/id"
        and mismatch.step_id == "patch_experiment"
        for mismatch in report.mismatches
    )


class _MismatchedTitleTarget(ELabFTWProjectionTarget):
    target_id = "elabftw_intentional_mismatch"

    def execute(self, call):
        response = super().execute(call)
        if call.operation_id != "elabftw.experiments.get":
            return response
        body = response.to_dict()["body"]
        body["title"] = "Incorrect result attachment"
        return ObservedResponse(
            status_code=response.status_code,
            headers=response.headers,
            body=body,
        )


class _MismatchedIdTarget(ELabFTWProjectionTarget):
    target_id = "elabftw_intentional_id_mismatch"

    def execute(self, call):
        response = super().execute(call)
        if call.operation_id != "elabftw.experiments.patch":
            return response
        body = response.to_dict()["body"]
        body["id"] += 1
        return ObservedResponse(
            status_code=response.status_code,
            headers=response.headers,
            body=body,
        )
