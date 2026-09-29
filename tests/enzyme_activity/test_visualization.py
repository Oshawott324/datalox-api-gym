from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

pytest.importorskip("datalox_gated_runtime")

from datalox_gated_runtime.visualizations.contracts import normalize_visualization_run
from datalox_gated_runtime.visualizations.renderers.enzyme_assay import (
    EnzymeAssayRenderer,
)

from api_gym.worlds.enzyme_activity_v0.visualization import (
    UnsupportedAssayVisualization,
    export_enzyme_assay_visualization,
)


def _measurement(
    job: int,
    plate: int,
    sequence: int,
    well: str,
    acquired_at_s: float,
    absorbance: float | None,
    status: str = "acquired",
) -> dict[str, Any]:
    return {
        "measurement_id": f"reader-job-{job:04d}-measurement-{sequence:04d}",
        "well": well,
        "acquired_at_s": acquired_at_s,
        "status": status,
        "absorbance": absorbance,
        "units": "absorbance",
    }


def _job(job: int, plate: int, measurements: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "job_id": f"reader-job-{job:04d}",
        "plate_id": f"assay-plate-{plate:03d}",
        "plate_revision": 7 if plate == 1 else 8,
        "settings": {
            "wavelength_nm": 405,
            "temperature_c": 37.0,
            "wells": ["A1", "A2", "A3"],
            "time_offsets_s": [0.0, 30.0, 60.0, 90.0],
        },
        "settings_digest": f"sha256:{job:064x}",
        "created_at_s": 20.0 if job == 1 else 190.0,
        "status": "completed",
        "measurements": deepcopy(measurements),
    }


def _series(
    job: int, plate: int, start: float, *, overrange: bool = False
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    sequence = 1
    for offset in (0.0, 30.0, 60.0, 90.0):
        for index, well in enumerate(("A1", "A2", "A3")):
            acquired = start + offset + index * 0.2
            if overrange and well == "A1":
                result.append(
                    _measurement(
                        job, plate, sequence, well, acquired, None, "overrange"
                    )
                )
            else:
                slope = {"A1": 0.0008, "A2": 0.00002, "A3": 0.0006}[well]
                result.append(
                    _measurement(
                        job,
                        plate,
                        sequence,
                        well,
                        acquired,
                        0.04 + slope * (acquired - start),
                    )
                )
            sequence += 1
    return result


def completed_run_evidence(*, recovery: bool) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    sequence = 0
    jobs: list[dict[str, Any]] = []
    transfers: list[dict[str, Any]] = []
    deck_plate = 1
    deck_revision = 1
    reader_plate: int | None = None
    reader_revision: int | None = None
    logical_time = 0.0
    source_volumes = {"1:A1": 120.0, "1:A2": 360.0, "1:A3": 240.0, "1:A4": 120.0}
    assay_volumes: dict[str, float] = {}

    def observation() -> dict[str, Any]:
        plates = [
            {
                "plate_id": f"assay-plate-{deck_plate:03d}",
                "revision": deck_revision,
                "location": "ot2_slot_3",
                "prepared": bool(assay_volumes),
            }
        ]
        if reader_plate is not None:
            plates.append(
                {
                    "plate_id": f"assay-plate-{reader_plate:03d}",
                    "revision": reader_revision,
                    "location": "modeled_reader",
                    "prepared": True,
                }
            )
        return {
            "schema_version": "enzyme_activity_observation_v0",
            "logical_time_s": logical_time,
            "inventory": {
                "sample_labels": ["SAMPLE-A", "BLANK", "REF-AP"],
                "source_well_map": {
                    "1:A1": "SAMPLE-A-stock",
                    "1:A2": "substrate-stock",
                    "1:A3": "assay-buffer",
                    "1:A4": "REF-AP-stock",
                },
                "assay_well_map": {
                    "3:A1": "SAMPLE-A",
                    "3:A2": "BLANK",
                    "3:A3": "REF-AP",
                },
                "stock_metadata": {},
                "well_volumes_ul": {
                    "source_plate": deepcopy(source_volumes),
                    "assay_plate": deepcopy(assay_volumes),
                },
                "tip_volume_ul": 0.0,
                "plates": plates,
            },
            "plate": {
                "plate_id": (
                    f"assay-plate-{reader_plate:03d}"
                    if reader_plate is not None
                    else f"assay-plate-{deck_plate:03d}"
                ),
                "revision": reader_revision or deck_revision,
                "location": "modeled_reader" if reader_plate else "ot2_slot_3",
            },
            "operator_requests": deepcopy(transfers),
            "reader_jobs": deepcopy(jobs),
            "claim": "Modeled observations; not physical reader captures.",
        }

    def record(
        operation: str,
        operation_id: str,
        arguments: dict[str, Any],
        result: dict[str, Any] | None,
    ) -> None:
        nonlocal sequence
        sequence += 1
        events.append(
            {
                "id": f"event:{sequence:08d}",
                "sequence": sequence,
                "type": "enzyme_activity_observation_snapshot",
                "simulated_at": "2030-01-01T00:00:00+00:00",
                "payload": {
                    "operation": operation,
                    "operation_id": operation_id,
                    "arguments": deepcopy(arguments),
                    "result": deepcopy(result),
                    "observation": observation(),
                },
            }
        )

    record("world.reset", "world.reset", {}, None)

    def prepare(plate: int, *, diluted: bool) -> None:
        nonlocal deck_revision, logical_time, assay_volumes
        logical_time += 12
        sample_volume = 25.0 if diluted else 50.0
        assay_volumes = {"3:A1": 100.0, "3:A2": 100.0, "3:A3": 100.0}
        source_volumes["1:A1"] -= sample_volume
        source_volumes["1:A2"] -= 150.0
        source_volumes["1:A3"] -= 50.0 + (25.0 if diluted else 0.0)
        source_volumes["1:A4"] -= 50.0
        deck_revision += 6
        native_volumes = {**source_volumes, **assay_volumes}
        record(
            "ot2.dispense",
            f"plate-{plate}-preparation-complete",
            {
                "action_id": f"plate-{plate}-preparation-complete",
                "destination": "3:A3",
                "volume_ul": 50,
            },
            {
                "action_id": f"plate-{plate}-preparation-complete",
                "receipt": {
                    "operation": "dispense",
                    "before": {
                        "has_tip": True,
                        "current_volume_ul": 50.0,
                        "well_volumes_ul": native_volumes,
                    },
                    "after": {
                        "has_tip": False,
                        "current_volume_ul": 0.0,
                        "well_volumes_ul": native_volumes,
                    },
                },
            },
        )

    def transfer(plate: int) -> None:
        nonlocal deck_plate, deck_revision, reader_plate, reader_revision
        nonlocal logical_time, assay_volumes
        request = {
            "request_id": f"transfer-{plate:04d}",
            "plate_id": f"assay-plate-{plate:03d}",
            "source": "ot2_slot_3",
            "destination": "modeled_reader",
            "status": "pending",
            "requested_at_s": logical_time,
            "complete_at_s": logical_time + 5,
            "operator_confirmation": None,
        }
        transfers.append(request)
        record(
            "operator.request_transfer",
            f"transfer-{plate}",
            {"action_id": f"transfer-{plate}", "plate_id": request["plate_id"]},
            request,
        )
        logical_time += 5
        request.update(
            {
                "status": "completed",
                "completed_at_s": logical_time,
                "operator_confirmation": {
                    "confirmed": True,
                    "observed_plate_id": request["plate_id"],
                    "retired_native_plate_id": f"native-{plate}",
                    "replacement_native_plate_id": f"native-{plate + 1}",
                },
            }
        )
        reader_plate = plate
        reader_revision = deck_revision
        deck_plate += 1
        deck_revision = 1
        assay_volumes = {}
        record(
            "lab.wait",
            f"wait-transfer-{plate}",
            {"action_id": f"wait-transfer-{plate}", "duration_s": 5},
            observation(),
        )

    def acquire(
        job_number: int, plate: int, *, overrange: bool
    ) -> list[dict[str, Any]]:
        nonlocal logical_time
        measurements = _series(job_number, plate, logical_time, overrange=overrange)
        job = _job(job_number, plate, measurements[:1])
        jobs.append(job)
        record(
            "reader.start_series",
            f"series-{job_number}",
            {
                "action_id": f"series-{job_number}",
                "plate_id": job["plate_id"],
                "wells": ["A1", "A2", "A3"],
            },
            job,
        )
        logical_time = max(item["acquired_at_s"] for item in measurements)
        job["measurements"] = measurements
        record(
            "lab.wait",
            f"wait-reader-{job_number}",
            {"action_id": f"wait-reader-{job_number}", "duration_s": 90.4},
            observation(),
        )
        record(
            "reader.get_data",
            "reader.get_data",
            {"job_id": job["job_id"]},
            {"job_id": job["job_id"], "measurements": measurements},
        )
        return measurements

    prepare(1, diluted=False)
    transfer(1)
    first = acquire(1, 1, overrange=recovery)
    selected = first
    selected_job = 1
    dilution = 1.0
    if recovery:
        prepare(2, diluted=True)
        transfer(2)
        selected = acquire(2, 2, overrange=False)
        selected_job = 2
        dilution = 2.0

    sample = [
        item
        for item in selected
        if item["well"] == "A1" and item["status"] == "acquired"
    ]
    blank = [
        item
        for item in selected
        if item["well"] == "A2" and item["status"] == "acquired"
    ]
    reference = [
        item
        for item in selected
        if item["well"] == "A3" and item["status"] == "acquired"
    ]
    submitted = {
        "sample_id": "SAMPLE-A",
        "disposition": "usable",
        "sample_measurement_ids": [item["measurement_id"] for item in sample],
        "blank_measurement_ids": [item["measurement_id"] for item in blank],
        "reference_measurement_ids": [item["measurement_id"] for item in reference],
        "fit_window_s": [sample[0]["acquired_at_s"], sample[-1]["acquired_at_s"]],
        "dilution_factor": dilution,
        "estimated_rate": 0.0468,
        "uncertainty": 0.0012,
        "units": "delta_absorbance_per_minute",
        "unresolved_reason_code": None,
        "evidence_refs": [],
    }
    report = {
        "sample_id": "SAMPLE-A",
        "submitted": submitted,
        "reference_analysis": {},
        "accepted": True,
        "verification": {"passed": True, "failure_codes": []},
        "submitted_at_s": logical_time,
    }
    record(
        "experiment.submit_report",
        "report",
        {"action_id": "report", "job_id": f"reader-job-{selected_job:04d}"},
        report,
    )
    return {
        "run_id": "assay-recovery" if recovery else "assay-nominal",
        "created_at": "2030-01-01T00:00:00+00:00",
        "events": [],
        "shadow_state": {},
        "world": {
            "schema_version": "datalox_world_run_v1",
            "world_id": "enzyme_activity_v0",
            "bundle": {"schema_version": "datalox_world_bundle_ref_v1"},
            "episode_id": "enzyme-activity-high-01"
            if recovery
            else "enzyme-activity-nominal-01",
            "simulation_time": "2030-01-01T00:00:00+00:00",
            "state": {},
            "events": events,
            "verifier_events": [],
            "artifacts": [],
            "scheduled_events": [],
            "conversations": [],
            "handoffs": [],
            "verification": {"passed": True, "failure_codes": []},
        },
    }


@pytest.mark.parametrize("recovery", [False, True])
def test_generated_run_evidence_normalizes_for_assay_renderer(recovery: bool) -> None:
    document = export_enzyme_assay_visualization(
        completed_run_evidence(recovery=recovery)
    )
    renderer = EnzymeAssayRenderer()
    normalized = normalize_visualization_run(
        document, renderer_validators={renderer.id: renderer.validate}
    )

    operations = normalized["renderer"]["payload"]["operations"]
    assert normalized["presentation"]["status"] == "completed"
    assert operations[-1]["snapshot"]["analysis"]["repeat_decision"] == (
        "fresh reaction used" if recovery else "not repeated"
    )
    assert all(
        measurement["acquired_at_s"] <= operation["snapshot"]["logical_time_s"]
        for operation in operations
        for measurement in operation["snapshot"]["measurements"]
    )
    if recovery:
        transfer_waits = [
            operation
            for operation in operations
            if operation["action"] == "lab.wait"
            and operation["snapshot"]["mode"] == "transfer"
            and operation["snapshot"]["transfer"]["status"] == "completed"
        ]
        assert len(transfer_waits) == 2
        assert all(
            operation["snapshot"]["active_plate"]["plate_id"]
            == operation["snapshot"]["transfer"]["observed_plate_id"]
            for operation in transfer_waits
        )
        assert {
            measurement["plate_id"]
            for measurement in operations[-1]["snapshot"]["measurements"]
        } == {"assay-plate-001", "assay-plate-002"}


def test_visualization_rejects_future_measurement() -> None:
    evidence = completed_run_evidence(recovery=False)
    acquisition_event = next(
        event
        for event in evidence["world"]["events"]
        if event["payload"]["operation"] == "reader.start_series"
    )
    acquisition_event["payload"]["observation"]["reader_jobs"][0]["measurements"][0][
        "acquired_at_s"
    ] = 999

    with pytest.raises(
        UnsupportedAssayVisualization, match="future reader measurement"
    ):
        export_enzyme_assay_visualization(evidence)


def test_visualization_omits_private_world_state() -> None:
    evidence = completed_run_evidence(recovery=False)
    evidence["world"]["state"] = {
        "trusted_summary": {"secret_enzyme_concentration_mM": 999}
    }
    document = export_enzyme_assay_visualization(evidence)

    assert "secret_enzyme_concentration_mM" not in str(document)
