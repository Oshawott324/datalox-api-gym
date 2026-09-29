"""Researcher-only enzyme-assay visualization from immutable run evidence."""

from __future__ import annotations

import hashlib
import json
import math
import re
from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any, Mapping


VISUALIZATION_SCHEMA_VERSION = "datalox_visualization_run_v1"
RENDERER_ID = "enzyme_assay_v1"
RENDERER_PROTOCOL_VERSION = "1.0.0"
WORLD_ID = "enzyme_activity_v0"
OBSERVATION_EVENT = "enzyme_activity_observation_snapshot"

_IDENTIFIER = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,127}$")
_PHASES = (
    ("preparation", "Prepare", "native_liquid_handling"),
    ("transfer", "Transfer", "operator_transfer"),
    ("acquisition", "Acquire", "modeled_plate_reader"),
    ("analysis", "Analyze", "evidence_analysis"),
)
_PREPARATION_OPERATIONS = frozenset(
    {"lab.inspect", "ot2.pick_up_tip", "ot2.aspirate", "ot2.dispense", "ot2.drop_tip"}
)
_TITLES = {
    "world.reset": "Initialize the experiment",
    "lab.inspect": "Inspect available materials",
    "ot2.pick_up_tip": "Pick up a fresh tip",
    "ot2.aspirate": "Aspirate liquid",
    "ot2.dispense": "Dispense liquid",
    "ot2.drop_tip": "Drop the used tip",
    "operator.request_transfer": "Request operator transfer",
    "lab.wait": "Advance experiment time",
    "reader.start_series": "Start kinetic acquisition",
    "reader.get_data": "Retrieve acquired observations",
    "experiment.submit_report": "Submit evidence-backed analysis",
}


class UnsupportedAssayVisualization(ValueError):
    """The run evidence cannot be represented without inventing assay state."""


def export_enzyme_assay_visualization(run_export: Mapping[str, Any]) -> dict[str, Any]:
    """Project a completed private run export into the researcher viewer contract.

    Only causal public snapshots recorded by the world are replayed. Private
    mixture parameters and scenario controls are deliberately ignored.
    """

    root = _object(run_export, "run_export")
    run_id = _identifier(root.get("run_id"), "run_export.run_id")
    world = _object(root.get("world"), "run_export.world")
    if world.get("world_id") != WORLD_ID:
        raise UnsupportedAssayVisualization(
            f"run_export.world.world_id must be {WORLD_ID!r}"
        )
    raw_events = world.get("events")
    if not isinstance(raw_events, list):
        raise UnsupportedAssayVisualization("run_export.world.events must be an array")
    events = [
        _observation_event(event, index=index)
        for index, event in enumerate(raw_events)
        if isinstance(event, Mapping) and event.get("type") == OBSERVATION_EVENT
    ]
    if not events or events[0]["operation"] != "world.reset":
        raise UnsupportedAssayVisualization(
            "run evidence must begin with a causal world.reset observation snapshot"
        )
    if len(events) < 2:
        raise UnsupportedAssayVisualization("run evidence contains no assay operation")

    verification = _object(world.get("verification"), "run_export.world.verification")
    if verification.get("passed") is not True:
        raise UnsupportedAssayVisualization(
            "the completed-run viewer requires a passing world verification"
        )

    initial_snapshot = _snapshot(events[0], native_snapshot=None, final_report=None)
    operations: list[dict[str, Any]] = []
    native_snapshot: dict[str, Any] | None = deepcopy(initial_snapshot["deck"])
    final_report: Mapping[str, Any] | None = None
    previous_measurements: dict[str, dict[str, Any]] = {}
    for event in events[1:]:
        result = event["result"]
        if event["operation"] == "experiment.submit_report":
            final_report = _object(result, "report result")
        receipt = result.get("receipt") if isinstance(result, Mapping) else None
        if isinstance(receipt, Mapping):
            after = receipt.get("after")
            if isinstance(after, Mapping):
                native_snapshot = _native_deck_snapshot(after, event["observation"])
        snapshot = _snapshot(
            event,
            native_snapshot=native_snapshot,
            final_report=final_report,
        )
        current_measurements = {
            item["measurement_id"]: item for item in snapshot["measurements"]
        }
        for measurement_id, previous in previous_measurements.items():
            current = current_measurements.get(measurement_id)
            if current is None or {
                key: value for key, value in current.items() if key != "selected_as"
            } != {
                key: value for key, value in previous.items() if key != "selected_as"
            }:
                raise UnsupportedAssayVisualization(
                    "later observation snapshots must preserve acquired measurement evidence"
                )
        previous_measurements = current_measurements
        sequence = len(operations) + 1
        operation_id = _safe_operation_id(event["operation_id"], sequence)
        operations.append(
            {
                "id": f"assay-operation-{sequence:03d}",
                "sequence": sequence,
                "operation_id": operation_id,
                "action": event["operation"],
                "title": _TITLES.get(event["operation"], event["operation"]),
                "simulated_at": _logical_timestamp(
                    events[0]["simulated_at"], snapshot["logical_time_s"]
                ),
                "result": _result_summary(event["operation"], result, snapshot),
                "snapshot": snapshot,
            }
        )

    if operations[-1]["action"] != "experiment.submit_report":
        raise UnsupportedAssayVisualization(
            "the completed-run viewer requires a terminal submitted report"
        )
    if operations[-1]["snapshot"]["analysis"] is None:
        raise UnsupportedAssayVisualization("terminal report evidence is unavailable")

    source_record = {
        "world_id": WORLD_ID,
        "episode_id": world.get("episode_id"),
        "observation_events": [
            {
                "event_id": event["event_id"],
                "sequence": event["sequence"],
                "operation": event["operation"],
                "operation_id": event["operation_id"],
                "logical_time_s": event["observation"]["logical_time_s"],
            }
            for event in events
        ],
        "verification": deepcopy(verification),
    }
    source_digest = _digest(source_record)
    job_plate_ids = {
        item["plate_id"]
        for operation in operations
        for item in operation["snapshot"]["measurements"]
    }
    used_fresh_reaction = len(job_plate_ids) > 1
    title = (
        "Enzyme assay fresh-reaction recovery"
        if used_fresh_reaction
        else "Enzyme assay nominal run"
    )
    artifact_ids = ["assay-evidence"]
    steps = _steps(operations, artifact_ids[0])
    stages = [
        {
            "id": phase_id,
            "label": label,
            "kind": kind,
            "provider": "API Gym + gated runtime",
            "status": "completed",
        }
        for phase_id, label, kind in _PHASES
    ]
    return {
        "schema_version": VISUALIZATION_SCHEMA_VERSION,
        "run_id": run_id,
        "world_id": WORLD_ID,
        "presentation": {
            "title": title,
            "summary": (
                "Recorded native preparation, operator transfer, modeled absorbance "
                "observations, and the submitted blank-corrected analysis."
            ),
            "subject": "Completed modeled assay evidence",
            "mode": "recorded_run",
            "status": "completed",
            "agent": None,
        },
        "workflow": {
            "stages": stages,
            "edges": [
                {"from": previous[0], "to": current[0]}
                for previous, current in zip(_PHASES, _PHASES[1:], strict=False)
            ],
        },
        "renderer": {
            "id": RENDERER_ID,
            "protocol_version": RENDERER_PROTOCOL_VERSION,
            "payload": {
                "visibility": "researcher_only",
                "source": {
                    "kind": "recorded_assay_run",
                    "claim": "Modeled observations; not physical reader captures.",
                    "run_export_sha256": _digest(root),
                    "evidence_sha256": source_digest,
                    "software_versions": {
                        "api_gym_world": WORLD_ID,
                        "renderer_contract": RENDERER_PROTOCOL_VERSION,
                    },
                    "limitations": [
                        "Liquid composition labels are modeled and public; latent kinetic parameters are omitted.",
                        "Operator transfer is shown as a recorded handoff, not a robotic-arm motion.",
                    ],
                },
                "plate_layout": {
                    "rows": list("ABCDEFGH"),
                    "columns": list(range(1, 13)),
                    "active_wells": {
                        "A1": "SAMPLE-A",
                        "A2": "BLANK",
                        "A3": "REF-AP",
                    },
                },
                "initial_snapshot": initial_snapshot,
                "operations": operations,
            },
        },
        "resources": [
            {
                "id": "assay-system",
                "label": "Modeled enzyme assay",
                "type": "experiment",
                "status": "completed",
                "summary": "Native liquid accounting coupled to modeled 405 nm acquisition.",
                "attributes": {
                    "observed_plate_ids": sorted(job_plate_ids),
                    "fresh_reaction_used": used_fresh_reaction,
                },
            }
        ],
        "artifacts": [
            {
                "id": "assay-evidence",
                "label": "Causal assay evidence index",
                "type": "researcher_run_evidence",
                "summary": "Digest-bound public snapshots and final verification consumed by the view.",
                "data": {**source_record, "evidence_sha256": source_digest},
            }
        ],
        "steps": steps,
        "outcome": {
            "label": "Verified modeled result",
            "summary": (
                "The submitted report passed the independent world verifier using only "
                "measurements available before submission."
            ),
            "tone": "success",
        },
    }


def _observation_event(event: Mapping[str, Any], *, index: int) -> dict[str, Any]:
    path = f"run_export.world.events[{index}]"
    payload = _object(event.get("payload"), f"{path}.payload")
    required = {"operation", "operation_id", "arguments", "result", "observation"}
    if set(payload) != required:
        raise UnsupportedAssayVisualization(
            f"{path}.payload must contain exactly {sorted(required)}"
        )
    observation = _object(payload["observation"], f"{path}.payload.observation")
    if observation.get("schema_version") != "enzyme_activity_observation_v0":
        raise UnsupportedAssayVisualization(f"{path} has an unsupported observation")
    logical_time = _number(observation.get("logical_time_s"), f"{path}.logical_time_s")
    if logical_time < 0:
        raise UnsupportedAssayVisualization(
            f"{path}.logical_time_s must be nonnegative"
        )
    return {
        "event_id": _identifier(event.get("id"), f"{path}.id"),
        "sequence": _integer(event.get("sequence"), f"{path}.sequence"),
        "simulated_at": _string(event.get("simulated_at"), f"{path}.simulated_at"),
        "operation": _string(payload["operation"], f"{path}.operation"),
        "operation_id": _string(payload["operation_id"], f"{path}.operation_id"),
        "arguments": deepcopy(_object(payload["arguments"], f"{path}.arguments")),
        "result": (
            None
            if payload["result"] is None
            else deepcopy(_object(payload["result"], f"{path}.result"))
        ),
        "observation": deepcopy(observation),
    }


def _snapshot(
    event: Mapping[str, Any],
    *,
    native_snapshot: Mapping[str, Any] | None,
    final_report: Mapping[str, Any] | None,
) -> dict[str, Any]:
    observation = _object(event["observation"], "observation")
    inventory = _object(observation.get("inventory"), "observation.inventory")
    mode = _mode(event["operation"], observation)
    deck = (
        _native_deck_snapshot(native_snapshot, observation)
        if native_snapshot is not None
        else _public_deck_snapshot(inventory)
    )
    measurements: list[dict[str, Any]] = []
    latest_job: Mapping[str, Any] | None = None
    jobs = observation.get("reader_jobs")
    if not isinstance(jobs, list):
        raise UnsupportedAssayVisualization("observation.reader_jobs must be an array")
    for job_index, raw_job in enumerate(jobs):
        job = _object(raw_job, f"observation.reader_jobs[{job_index}]")
        latest_job = job
        raw_measurements = job.get("measurements")
        if not isinstance(raw_measurements, list):
            raise UnsupportedAssayVisualization(
                "reader job measurements must be an array"
            )
        for raw_measurement in raw_measurements:
            measurement = _object(raw_measurement, "reader measurement")
            acquired_at_s = _number(
                measurement.get("acquired_at_s"), "measurement.acquired_at_s"
            )
            if (
                acquired_at_s
                > _number(observation["logical_time_s"], "logical_time_s") + 1e-9
            ):
                raise UnsupportedAssayVisualization(
                    "an observation snapshot contains a future reader measurement"
                )
            absorbance = measurement.get("absorbance")
            if absorbance is not None:
                absorbance = _number(absorbance, "measurement.absorbance")
            measurements.append(
                {
                    "measurement_id": _string(
                        measurement.get("measurement_id"), "measurement.measurement_id"
                    ),
                    "job_id": _string(job.get("job_id"), "reader_job.job_id"),
                    "well": _string(measurement.get("well"), "measurement.well"),
                    "acquired_at_s": acquired_at_s,
                    "status": _string(measurement.get("status"), "measurement.status"),
                    "absorbance": absorbance,
                    "unit": "absorbance",
                    "plate_id": _string(job.get("plate_id"), "reader_job.plate_id"),
                    "plate_revision": _integer(
                        job.get("plate_revision"), "reader_job.plate_revision"
                    ),
                    "selected_as": None,
                }
            )
    measurements.sort(key=lambda item: (item["acquired_at_s"], item["well"]))

    analysis = None
    if final_report is not None:
        submitted = _object(final_report.get("submitted"), "report.submitted")
        selected = {
            measurement_id: role
            for role, field in (
                ("sample", "sample_measurement_ids"),
                ("blank", "blank_measurement_ids"),
                ("reference", "reference_measurement_ids"),
            )
            for measurement_id in _string_array(submitted.get(field), f"report.{field}")
        }
        by_id = {item["measurement_id"]: item for item in measurements}
        missing = set(selected) - set(by_id)
        if missing:
            raise UnsupportedAssayVisualization(
                f"the report selects unavailable measurements: {sorted(missing)}"
            )
        for measurement_id, role in selected.items():
            by_id[measurement_id]["selected_as"] = role
        observed_plate_ids = {item["plate_id"] for item in measurements}
        analysis = {
            "disposition": _string(submitted.get("disposition"), "report.disposition"),
            "estimated_rate": _optional_number(
                submitted.get("estimated_rate"), "report.estimated_rate"
            ),
            "uncertainty": _optional_number(
                submitted.get("uncertainty"), "report.uncertainty"
            ),
            "units": _string(submitted.get("units"), "report.units"),
            "fit_window_s": _optional_window(
                submitted.get("fit_window_s"), "report.fit_window_s"
            ),
            "dilution_factor": _number(
                submitted.get("dilution_factor"), "report.dilution_factor"
            ),
            "selected_measurement_ids": sorted(selected),
            "repeat_decision": (
                "fresh reaction used" if len(observed_plate_ids) > 1 else "not repeated"
            ),
            "accepted": final_report.get("accepted") is True,
        }

    transfer = _latest_transfer(observation)
    reader = None
    if latest_job is not None:
        settings = _object(latest_job.get("settings"), "reader_job.settings")
        reader = {
            "job_id": _string(latest_job.get("job_id"), "reader_job.job_id"),
            "plate_id": _string(latest_job.get("plate_id"), "reader_job.plate_id"),
            "plate_revision": _integer(
                latest_job.get("plate_revision"), "reader_job.plate_revision"
            ),
            "status": _string(latest_job.get("status"), "reader_job.status"),
            "wavelength_nm": _number(
                settings.get("wavelength_nm"), "settings.wavelength_nm"
            ),
            "temperature_c": _number(
                settings.get("temperature_c"), "settings.temperature_c"
            ),
        }
    return {
        "mode": mode,
        "logical_time_s": _number(observation["logical_time_s"], "logical_time_s"),
        "active_plate": _active_plate(mode, observation, transfer, reader),
        "active_well": _active_well(event),
        "deck": deck,
        "transfer": transfer,
        "reader": reader,
        "measurements": measurements,
        "analysis": analysis,
    }


def _mode(operation: str, observation: Mapping[str, Any]) -> str:
    if operation in _PREPARATION_OPERATIONS or operation == "world.reset":
        return "preparation"
    if operation == "operator.request_transfer":
        return "transfer"
    if operation in {"reader.start_series", "reader.get_data"}:
        return "acquisition"
    if operation == "experiment.submit_report":
        return "analysis"
    if operation == "lab.wait":
        requests = observation.get("operator_requests")
        if not isinstance(requests, list):
            raise UnsupportedAssayVisualization(
                "observation.operator_requests must be an array"
            )
        if requests:
            latest = _object(requests[-1], "operator request")
            completed_at = latest.get("completed_at_s")
            logical_time = _number(
                observation.get("logical_time_s"), "observation.logical_time_s"
            )
            if latest.get("status") == "pending" or (
                completed_at is not None
                and abs(_number(completed_at, "transfer.completed_at_s") - logical_time)
                <= 1e-9
            ):
                return "transfer"
        return "acquisition" if observation.get("reader_jobs") else "transfer"
    raise UnsupportedAssayVisualization(f"unsupported assay operation {operation!r}")


def _public_deck_snapshot(inventory: Mapping[str, Any]) -> dict[str, Any]:
    volumes = _object(inventory.get("well_volumes_ul"), "inventory.well_volumes_ul")
    combined: dict[str, float] = {}
    for field in ("source_plate", "assay_plate"):
        for address, value in _object(
            volumes.get(field), f"well_volumes_ul.{field}"
        ).items():
            combined[_string(address, "well address")] = _number(value, "well volume")
    plate = _deck_plate(inventory)
    return {
        "plate_id": plate["plate_id"],
        "plate_revision": plate["revision"],
        "has_tip": _number(inventory.get("tip_volume_ul"), "tip_volume_ul") > 0,
        "tip_volume_ul": _number(inventory.get("tip_volume_ul"), "tip_volume_ul"),
        "well_volumes_ul": combined,
    }


def _native_deck_snapshot(
    value: Mapping[str, Any], observation: Mapping[str, Any]
) -> dict[str, Any]:
    inventory = _object(observation.get("inventory"), "observation.inventory")
    plate = _deck_plate(inventory)
    if "current_volume_ul" in value:
        volumes = _object(value["well_volumes_ul"], "native.well_volumes_ul")
        has_tip = value.get("has_tip")
        tip_volume = value.get("current_volume_ul")
    else:
        volumes = _object(value.get("well_volumes_ul"), "deck.well_volumes_ul")
        has_tip = value.get("has_tip")
        tip_volume = value.get("tip_volume_ul")
    if type(has_tip) is not bool:
        raise UnsupportedAssayVisualization("native has_tip must be boolean")
    return {
        "plate_id": plate["plate_id"],
        "plate_revision": plate["revision"],
        "has_tip": has_tip,
        "tip_volume_ul": _number(tip_volume, "native tip volume"),
        "well_volumes_ul": {
            _string(address, "native well address"): _number(
                volume, "native well volume"
            )
            for address, volume in volumes.items()
        },
    }


def _deck_plate(inventory: Mapping[str, Any]) -> dict[str, Any]:
    plates = inventory.get("plates")
    if not isinstance(plates, list):
        raise UnsupportedAssayVisualization("inventory.plates must be an array")
    matches = [
        _object(item, "inventory plate")
        for item in plates
        if isinstance(item, Mapping) and item.get("location") == "ot2_slot_3"
    ]
    if len(matches) != 1:
        raise UnsupportedAssayVisualization("exactly one OT-2 deck plate is required")
    return {
        "plate_id": _string(matches[0].get("plate_id"), "plate.plate_id"),
        "revision": _integer(matches[0].get("revision"), "plate.revision"),
    }


def _latest_transfer(observation: Mapping[str, Any]) -> dict[str, Any] | None:
    requests = observation.get("operator_requests")
    if not isinstance(requests, list):
        raise UnsupportedAssayVisualization(
            "observation.operator_requests must be an array"
        )
    if not requests:
        return None
    raw = _object(requests[-1], "operator request")
    confirmation = raw.get("operator_confirmation")
    observed_plate_id = None
    if confirmation is not None:
        confirmation = _object(confirmation, "operator confirmation")
        observed_plate_id = _string(
            confirmation.get("observed_plate_id"), "operator observed_plate_id"
        )
    return {
        "request_id": _string(raw.get("request_id"), "transfer.request_id"),
        "plate_id": _string(raw.get("plate_id"), "transfer.plate_id"),
        "source": _string(raw.get("source"), "transfer.source"),
        "destination": _string(raw.get("destination"), "transfer.destination"),
        "status": _string(raw.get("status"), "transfer.status"),
        "requested_at_s": _number(raw.get("requested_at_s"), "transfer.requested_at_s"),
        "completed_at_s": _optional_number(
            raw.get("completed_at_s"), "transfer.completed_at_s"
        ),
        "observed_plate_id": observed_plate_id,
    }


def _active_plate(
    mode: str,
    observation: Mapping[str, Any],
    transfer: Mapping[str, Any] | None,
    reader: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if mode in {"acquisition", "analysis"} and reader is not None:
        return {
            "plate_id": reader["plate_id"],
            "revision": reader["plate_revision"],
            "location": "modeled_reader",
        }
    if mode == "transfer" and transfer is not None:
        target_id = transfer["observed_plate_id"] or transfer["plate_id"]
        inventory = _object(observation.get("inventory"), "observation.inventory")
        plates = inventory.get("plates")
        if not isinstance(plates, list):
            raise UnsupportedAssayVisualization("inventory.plates must be an array")
        matches = [
            _object(item, "inventory plate")
            for item in plates
            if isinstance(item, Mapping) and item.get("plate_id") == target_id
        ]
        if len(matches) != 1:
            raise UnsupportedAssayVisualization(
                "transfer plate must have one public inventory identity"
            )
        return {
            "plate_id": target_id,
            "revision": _integer(matches[0].get("revision"), "plate.revision"),
            "location": (
                "modeled_reader" if transfer["status"] == "completed" else "in_transfer"
            ),
        }
    inventory = _object(observation.get("inventory"), "observation.inventory")
    deck = _deck_plate(inventory)
    return {
        "plate_id": deck["plate_id"],
        "revision": deck["revision"],
        "location": "ot2_slot_3",
    }


def _active_well(event: Mapping[str, Any]) -> str | None:
    arguments = _object(event["arguments"], "event.arguments")
    for field in ("destination", "source", "tip_well"):
        value = arguments.get(field)
        if isinstance(value, str):
            return value
    return None


def _result_summary(
    operation: str, result: Mapping[str, Any] | None, snapshot: Mapping[str, Any]
) -> dict[str, str]:
    if result is None:
        return {"status": "completed", "summary": "Observation recorded."}
    if operation in _PREPARATION_OPERATIONS and isinstance(
        result.get("receipt"), Mapping
    ):
        receipt = _object(result["receipt"], "result.receipt")
        return {
            "status": "completed",
            "summary": f"Native {receipt.get('operation', operation)} receipt committed.",
        }
    if operation == "operator.request_transfer":
        return {"status": "pending", "summary": "Operator transfer is pending."}
    if operation == "reader.start_series":
        return {
            "status": _string(result.get("status"), "reader status"),
            "summary": f"Reader job {result.get('job_id')} started.",
        }
    if operation == "reader.get_data":
        return {
            "status": "completed",
            "summary": f"Returned {len(snapshot['measurements'])} recorded observations.",
        }
    if operation == "experiment.submit_report":
        return {
            "status": "accepted" if result.get("accepted") is True else "rejected",
            "summary": "Submitted report accepted by the world verifier."
            if result.get("accepted") is True
            else "Submitted report rejected by the world verifier.",
        }
    transfer = snapshot.get("transfer")
    if (
        operation == "lab.wait"
        and snapshot.get("mode") == "transfer"
        and isinstance(transfer, Mapping)
    ):
        return {
            "status": str(transfer["status"]),
            "summary": f"Logical time advanced to {snapshot['logical_time_s']:g} s.",
        }
    return {
        "status": "completed",
        "summary": f"Logical time advanced to {snapshot['logical_time_s']:g} s.",
    }


def _steps(operations: list[dict[str, Any]], artifact_id: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    previous_count = 0
    for operation in operations:
        snapshot = operation["snapshot"]
        count = len(snapshot["measurements"])
        plate = snapshot["active_plate"]
        state_changes = []
        if count != previous_count:
            state_changes.append(
                {
                    "resource_id": "assay-system",
                    "field": "available observations",
                    "before": str(previous_count),
                    "after": str(count),
                    "unit": "readings",
                }
            )
        previous_count = count
        result.append(
            {
                "sequence": operation["sequence"],
                "phase_id": snapshot["mode"],
                "operation_id": operation["operation_id"],
                "title": operation["title"],
                "description": operation["result"]["summary"],
                "simulated_at": operation["simulated_at"],
                "duration_ms": 650,
                "status": "completed",
                "render": {
                    "commands": [
                        {
                            "event": "show_operation",
                            "data": {"operation_id": operation["id"]},
                        }
                    ]
                },
                "scene": {
                    "kind": "process",
                    "label": "Recorded assay operation",
                    "data": {
                        "actor": "assay runtime",
                        "action": operation["action"],
                        "source": None,
                        "target": plate["plate_id"],
                        "quantity": {
                            "value": f"{snapshot['logical_time_s']:g}",
                            "unit": "s",
                        },
                        "detail": operation["result"]["summary"],
                    },
                },
                "facts": [
                    {
                        "label": "Logical time",
                        "value": f"{snapshot['logical_time_s']:g}",
                        "unit": "s",
                        "tone": "info",
                    },
                    {
                        "label": "Plate",
                        "value": plate["plate_id"],
                        "unit": None,
                        "tone": "neutral",
                    },
                    {
                        "label": "Result",
                        "value": operation["result"]["status"],
                        "unit": None,
                        "tone": "success"
                        if operation["result"]["status"] in {"completed", "accepted"}
                        else "warning",
                    },
                ],
                "state_changes": state_changes,
                "artifact_ids": [artifact_id]
                if operation["sequence"] == len(operations)
                else [],
            }
        )
    return result


def _logical_timestamp(initial: str, elapsed_s: float) -> str:
    try:
        parsed = datetime.fromisoformat(initial.replace("Z", "+00:00"))
    except ValueError as exc:
        raise UnsupportedAssayVisualization("initial simulated_at is invalid") from exc
    return (parsed + timedelta(seconds=elapsed_s)).isoformat()


def _digest(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _safe_operation_id(value: str, sequence: int) -> str:
    if _IDENTIFIER.fullmatch(value):
        return value
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"operation-{sequence:03d}-{digest}"


def _object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise UnsupportedAssayVisualization(f"{path} must be an object")
    return dict(value)


def _string(value: Any, path: str) -> str:
    if type(value) is not str or not value or value.strip() != value:
        raise UnsupportedAssayVisualization(
            f"{path} must be a non-empty trimmed string"
        )
    return value


def _identifier(value: Any, path: str) -> str:
    result = _string(value, path)
    if _IDENTIFIER.fullmatch(result) is None:
        raise UnsupportedAssayVisualization(f"{path} must be a portable identifier")
    return result


def _integer(value: Any, path: str) -> int:
    if type(value) is not int:
        raise UnsupportedAssayVisualization(f"{path} must be an integer")
    return value


def _number(value: Any, path: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(float(value)):
        raise UnsupportedAssayVisualization(f"{path} must be a finite number")
    return float(value)


def _optional_number(value: Any, path: str) -> float | None:
    return None if value is None else _number(value, path)


def _string_array(value: Any, path: str) -> list[str]:
    if not isinstance(value, list):
        raise UnsupportedAssayVisualization(f"{path} must be an array")
    return [_string(item, f"{path}[]") for item in value]


def _optional_window(value: Any, path: str) -> list[float] | None:
    if value is None:
        return None
    if not isinstance(value, list) or len(value) != 2:
        raise UnsupportedAssayVisualization(f"{path} must be null or two numbers")
    start, end = (_number(item, f"{path}[]") for item in value)
    if end < start:
        raise UnsupportedAssayVisualization(f"{path} must be ordered")
    return [start, end]


__all__ = [
    "OBSERVATION_EVENT",
    "RENDERER_ID",
    "RENDERER_PROTOCOL_VERSION",
    "UnsupportedAssayVisualization",
    "export_enzyme_assay_visualization",
]
