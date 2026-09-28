from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("datalox_gated_runtime")

from datalox_gated_runtime.models import CallRequest
from datalox_gated_runtime.world_v1.backend import (
    WorldBundleBackend,
    initialize_world_bundle_session,
)
from datalox_gated_runtime.world_v1.errors import WorldSessionError


WORLD = Path(__file__).parents[2] / "worlds" / "enzyme_activity_v0"


@pytest.fixture(scope="module")
def native_python() -> Path:
    configured = os.environ.get("DATALOX_OT2_WORKER_PYTHON")
    if not configured:
        pytest.skip("Set DATALOX_OT2_WORKER_PYTHON to the pinned Opentrons interpreter")
    path = Path(configured)
    if not path.is_file():
        pytest.fail(f"DATALOX_OT2_WORKER_PYTHON does not exist: {path}")
    return path


def open_backend(
    tmp_path: Path, *, episode_id: str = "enzyme-activity-nominal-01"
) -> WorldBundleBackend:
    run_dir = tmp_path / "run"
    initialize_world_bundle_session(
        source_bundle_dir=WORLD,
        run_dir=run_dir,
        episode_id=episode_id,
    )
    return WorldBundleBackend(run_dir=run_dir)


def invoke(
    backend: WorldBundleBackend,
    *,
    method: str,
    path: str,
    body: dict | None = None,
) -> dict:
    operation_id = None if body is None else body.get("action_id")
    response = backend.handle(
        CallRequest(method=method, path=path, body=body, operation_id=operation_id)
    )
    assert response is not None
    assert response.status_code == 200, response.body
    assert isinstance(response.body, dict)
    return response.body


def prepare_plate(backend: WorldBundleBackend, *, prefix: str) -> None:
    steps = (
        ("/v1/ot2/tips/pick-up", {"action_id": f"{prefix}-pick-1", "tip_well": "A1"}),
        (
            "/v1/ot2/aspirate",
            {"action_id": f"{prefix}-asp-1", "source": "1:A1", "volume_ul": 50},
        ),
        (
            "/v1/ot2/dispense",
            {"action_id": f"{prefix}-dsp-1", "destination": "3:A1", "volume_ul": 50},
        ),
        ("/v1/ot2/tips/drop", {"action_id": f"{prefix}-drop-1"}),
        ("/v1/ot2/tips/pick-up", {"action_id": f"{prefix}-pick-2", "tip_well": "A2"}),
        (
            "/v1/ot2/aspirate",
            {"action_id": f"{prefix}-asp-2", "source": "1:A2", "volume_ul": 50},
        ),
        (
            "/v1/ot2/dispense",
            {"action_id": f"{prefix}-dsp-2", "destination": "3:A1", "volume_ul": 50},
        ),
        ("/v1/ot2/tips/drop", {"action_id": f"{prefix}-drop-2"}),
        ("/v1/ot2/tips/pick-up", {"action_id": f"{prefix}-pick-3", "tip_well": "B1"}),
        (
            "/v1/ot2/aspirate",
            {"action_id": f"{prefix}-asp-3", "source": "1:A3", "volume_ul": 50},
        ),
        (
            "/v1/ot2/dispense",
            {"action_id": f"{prefix}-dsp-3", "destination": "3:A2", "volume_ul": 50},
        ),
        ("/v1/ot2/tips/drop", {"action_id": f"{prefix}-drop-3"}),
        ("/v1/ot2/tips/pick-up", {"action_id": f"{prefix}-pick-4", "tip_well": "B2"}),
        (
            "/v1/ot2/aspirate",
            {"action_id": f"{prefix}-asp-4", "source": "1:A2", "volume_ul": 50},
        ),
        (
            "/v1/ot2/dispense",
            {"action_id": f"{prefix}-dsp-4", "destination": "3:A2", "volume_ul": 50},
        ),
        ("/v1/ot2/tips/drop", {"action_id": f"{prefix}-drop-4"}),
        ("/v1/ot2/tips/pick-up", {"action_id": f"{prefix}-pick-5", "tip_well": "B3"}),
        (
            "/v1/ot2/aspirate",
            {"action_id": f"{prefix}-asp-5", "source": "1:A4", "volume_ul": 50},
        ),
        (
            "/v1/ot2/dispense",
            {"action_id": f"{prefix}-dsp-5", "destination": "3:A3", "volume_ul": 50},
        ),
        ("/v1/ot2/tips/drop", {"action_id": f"{prefix}-drop-5"}),
        ("/v1/ot2/tips/pick-up", {"action_id": f"{prefix}-pick-6", "tip_well": "B4"}),
        (
            "/v1/ot2/aspirate",
            {"action_id": f"{prefix}-asp-6", "source": "1:A2", "volume_ul": 50},
        ),
        (
            "/v1/ot2/dispense",
            {"action_id": f"{prefix}-dsp-6", "destination": "3:A3", "volume_ul": 50},
        ),
        ("/v1/ot2/tips/drop", {"action_id": f"{prefix}-drop-6"}),
    )
    for path, body in steps:
        invoke(backend, method="POST", path=path, body=body)


def slope(readings: list[dict]) -> float:
    times = [item["acquired_at_s"] for item in readings]
    values = [item["absorbance"] for item in readings]
    mean_t = sum(times) / len(times)
    mean_y = sum(values) / len(values)
    return sum(
        (time_s - mean_t) * (value - mean_y)
        for time_s, value in zip(times, values, strict=True)
    ) / sum((time_s - mean_t) ** 2 for time_s in times)


def slope_standard_error(readings: list[dict]) -> float:
    fitted_slope = slope(readings)
    times = [item["acquired_at_s"] for item in readings]
    values = [item["absorbance"] for item in readings]
    mean_t = sum(times) / len(times)
    mean_y = sum(values) / len(values)
    denominator = sum((time_s - mean_t) ** 2 for time_s in times)
    residual_sum_squares = sum(
        (value - (mean_y + fitted_slope * (time_s - mean_t))) ** 2
        for time_s, value in zip(times, values, strict=True)
    )
    return (residual_sum_squares / (len(readings) - 2) / denominator) ** 0.5


def complete_run(backend: WorldBundleBackend, *, prefix: str) -> list[dict]:
    prepare_plate(backend, prefix=prefix)
    invoke(
        backend,
        method="POST",
        path="/v1/operator/transfers",
        body={"action_id": f"{prefix}-transfer", "plate_id": "assay-plate-001"},
    )
    transfer_observation = invoke(
        backend,
        method="POST",
        path="/v1/lab/wait",
        body={"action_id": f"{prefix}-transfer-wait", "duration_s": 5},
    )
    confirmation = transfer_observation["operator_requests"][0]["operator_confirmation"]
    assert confirmation["confirmed"] is True
    assert (
        confirmation["retired_native_plate_id"]
        != confirmation["replacement_native_plate_id"]
    )

    job = invoke(
        backend,
        method="POST",
        path="/v1/reader/series",
        body={
            "action_id": f"{prefix}-series",
            "plate_id": "assay-plate-001",
            "wells": ["A1", "A2", "A3"],
        },
    )
    assert len(job["measurements"]) == 1
    invoke(
        backend,
        method="POST",
        path="/v1/lab/wait",
        body={"action_id": f"{prefix}-read-wait", "duration_s": 120.4},
    )
    data = invoke(
        backend,
        method="POST",
        path="/v1/reader/data",
        body={"job_id": job["job_id"]},
    )["measurements"]
    assert len(data) == 15
    assert all(item["status"] == "acquired" for item in data)
    sample = [item for item in data if item["well"] == "A1"]
    blank = [item for item in data if item["well"] == "A2"]
    reference = [item for item in data if item["well"] == "A3"]
    estimated_rate = (slope(sample) - slope(blank)) * 60
    uncertainty = (
        slope_standard_error(sample) ** 2 + slope_standard_error(blank) ** 2
    ) ** 0.5 * 60
    report = invoke(
        backend,
        method="POST",
        path="/v1/experiment/report",
        body={
            "action_id": f"{prefix}-report",
            "sample_id": "SAMPLE-A",
            "job_id": job["job_id"],
            "disposition": "usable",
            "sample_measurement_ids": [item["measurement_id"] for item in sample],
            "blank_measurement_ids": [item["measurement_id"] for item in blank],
            "reference_measurement_ids": [item["measurement_id"] for item in reference],
            "fit_window_s": [
                min(item["acquired_at_s"] for item in sample + blank + reference),
                max(item["acquired_at_s"] for item in sample + blank + reference),
            ],
            "dilution_factor": 1,
            "estimated_rate": estimated_rate,
            "uncertainty": uncertainty,
            "units": "delta_absorbance_per_minute",
            "unresolved_reason_code": None,
            "evidence_refs": [],
        },
    )
    assert report["accepted"] is True
    return data


def complete_scenario_run(backend: WorldBundleBackend, *, prefix: str) -> dict:
    prepare_plate(backend, prefix=prefix)
    transfer = invoke(
        backend,
        method="POST",
        path="/v1/operator/transfers",
        body={"action_id": f"{prefix}-transfer", "plate_id": "assay-plate-001"},
    )
    transfer_observation = invoke(
        backend,
        method="POST",
        path="/v1/lab/wait",
        body={
            "action_id": f"{prefix}-transfer-wait",
            "duration_s": transfer["complete_at_s"] - transfer["requested_at_s"],
        },
    )
    plate_id = transfer_observation["plate"]["plate_id"]
    job = invoke(
        backend,
        method="POST",
        path="/v1/reader/series",
        body={
            "action_id": f"{prefix}-series",
            "plate_id": plate_id,
            "wells": ["A1", "A2", "A3"],
        },
    )
    invoke(
        backend,
        method="POST",
        path="/v1/lab/wait",
        body={"action_id": f"{prefix}-read-wait", "duration_s": 120.4},
    )
    data = invoke(
        backend,
        method="POST",
        path="/v1/reader/data",
        body={"job_id": job["job_id"]},
    )["measurements"]

    def usable(well: str) -> list[dict]:
        return [
            item
            for item in data
            if item["well"] == well
            and item["status"] == "acquired"
            and item["absorbance"] is not None
            and 0.02 <= item["absorbance"] <= 1.5
        ]

    sample, blank, reference = usable("A1"), usable("A2"), usable("A3")
    assert all(
        len(series) >= 4
        and series[-1]["acquired_at_s"] - series[0]["acquired_at_s"] >= 90
        for series in (sample, blank, reference)
    )
    estimated_rate = (slope(sample) - slope(blank)) * 60
    uncertainty = (
        slope_standard_error(sample) ** 2 + slope_standard_error(blank) ** 2
    ) ** 0.5 * 60
    report = invoke(
        backend,
        method="POST",
        path="/v1/experiment/report",
        body={
            "action_id": f"{prefix}-report",
            "sample_id": "SAMPLE-A",
            "job_id": job["job_id"],
            "disposition": "usable",
            "sample_measurement_ids": [item["measurement_id"] for item in sample],
            "blank_measurement_ids": [item["measurement_id"] for item in blank],
            "reference_measurement_ids": [item["measurement_id"] for item in reference],
            "fit_window_s": [
                min(item["acquired_at_s"] for item in sample + blank + reference),
                max(item["acquired_at_s"] for item in sample + blank + reference),
            ],
            "dilution_factor": 1,
            "estimated_rate": estimated_rate,
            "uncertainty": uncertainty,
            "units": "delta_absorbance_per_minute",
            "unresolved_reason_code": None,
            "evidence_refs": [],
        },
    )
    return {
        "report": report,
        "measurements": data,
        "transfer": transfer,
        "transfer_observation": transfer_observation,
    }


def test_executable_contract_replays_after_seeded_reset(
    tmp_path: Path, native_python: Path
) -> None:
    del native_python
    backend = open_backend(tmp_path)
    try:
        first = complete_run(backend, prefix="first")
        assert backend.verify().passed is True
        backend.reset()
        second = complete_run(backend, prefix="second")
        assert backend.verify().passed is True
        assert first == second
    finally:
        backend.close()


def test_post_dispense_persistence_failure_forbids_redispatch_and_reset_recovers(
    tmp_path: Path,
    native_python: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del native_python
    backend = open_backend(tmp_path)
    try:
        invoke(
            backend,
            method="POST",
            path="/v1/ot2/tips/pick-up",
            body={"action_id": "interrupted-pick", "tip_well": "A1"},
        )
        invoke(
            backend,
            method="POST",
            path="/v1/ot2/tips/pick-up",
            body={"action_id": "interrupted-pick", "tip_well": "A1"},
        )
        assert len(backend.bundle.implementation._native_receipts) == 1
        invoke(
            backend,
            method="POST",
            path="/v1/ot2/aspirate",
            body={
                "action_id": "interrupted-aspirate",
                "source": "1:A1",
                "volume_ul": 50,
            },
        )
        request = CallRequest(
            method="POST",
            path="/v1/ot2/dispense",
            body={
                "action_id": "interrupted-dispense",
                "destination": "3:A1",
                "volume_ul": 50,
            },
            operation_id="interrupted-dispense",
        )
        original = backend.session.set_state
        failed = False

        def fail_after_native(key: str, value: object) -> None:
            nonlocal failed
            if not failed:
                failed = True
                raise RuntimeError("injected state persistence failure")
            original(key, value)

        monkeypatch.setattr(backend.session, "set_state", fail_after_native)
        with pytest.raises(RuntimeError, match="injected state persistence failure"):
            backend.handle(request)
        receipt_count = len(backend.bundle.implementation._native_receipts)
        assert receipt_count == 3
        with pytest.raises(WorldSessionError) as caught:
            backend.handle(request)
        assert caught.value.code == "world_managed_worker_state_unknown"
        assert len(backend.bundle.implementation._native_receipts) == receipt_count
        assert backend.verify().passed is False
        assert any(
            event["type"] == "world_operation_invalidated"
            and event["payload"]["operation_id"] == "interrupted-dispense"
            and event["payload"]["redispatch_allowed"] is False
            for event in backend.session.list_events()
        )

        monkeypatch.setattr(backend.session, "set_state", original)
        backend.reset()
        observation = invoke(backend, method="GET", path="/v1/lab")
        assert (
            observation["inventory"]["well_volumes_ul"]["source_plate"]["1:A1"] == 120
        )
        assert observation["inventory"]["well_volumes_ul"]["assay_plate"] == {}
        assert observation["inventory"]["source_well_map"]["1:A4"] == "REF-AP-stock"
        assert (
            observation["inventory"]["stock_metadata"]["substrate-stock"][
                "substrate_concentration_mM"
            ]
            == 2.0
        )
    finally:
        backend.close()


@pytest.mark.parametrize(
    "episode_id",
    [
        "enzyme-activity-nominal-01",
        "enzyme-activity-high-01",
        "enzyme-activity-delayed-01",
        "enzyme-activity-interrupted-01",
        "enzyme-activity-background-01",
        "enzyme-activity-lineage-01",
    ],
)
def test_each_scenario_has_a_native_reference_plan(
    tmp_path: Path, native_python: Path, episode_id: str
) -> None:
    del native_python
    backend = open_backend(tmp_path, episode_id=episode_id)
    try:
        result = complete_scenario_run(backend, prefix=episode_id)
        report = result["report"]
        data = result["measurements"]
        assert report["accepted"] is True, report["verification"]
        assert backend.verify().passed is True
        if episode_id == "enzyme-activity-high-01":
            assert any(
                item["well"] == "A1"
                and (
                    item["status"] == "overrange"
                    or (item["absorbance"] is not None and item["absorbance"] > 1.5)
                )
                for item in data
            )
        elif episode_id == "enzyme-activity-delayed-01":
            transfer = result["transfer"]
            assert transfer["complete_at_s"] - transfer["requested_at_s"] == 125
        elif episode_id == "enzyme-activity-interrupted-01":
            assert any(item["status"] == "missing" for item in data)
        elif episode_id == "enzyme-activity-background-01":
            blank = [item for item in data if item["well"] == "A2"]
            assert slope(blank) * 60 > 0.02
        elif episode_id == "enzyme-activity-lineage-01":
            observation = result["transfer_observation"]
            assert observation["plate"]["plate_id"] == "assay-plate-unexpected"
            assert (
                observation["operator_requests"][0]["operator_confirmation"][
                    "observed_plate_id"
                ]
                == "assay-plate-unexpected"
            )
    finally:
        backend.close()
