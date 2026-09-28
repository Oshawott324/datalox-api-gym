"""Executable Phase 0 integration slice over the gated runtime's native worker."""

from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from datalox_gated_runtime.models import CallRequest, TaskBrief
from datalox_gated_runtime.sdk_adapters.opentrons_ot2_motion import (
    PINNED_SOURCE_HASHES,
    Aspirate,
    Dispense,
    DropTip,
    ExchangeFreshPlate,
    OpentronsOT2MotionManager,
    OpentronsOT2WorkerLauncher,
    PickUpTip,
)
from datalox_gated_runtime.world_backend import WorldResponse
from datalox_gated_runtime.world_v1.contracts import ActorContext, WorldImplementationV1
from datalox_gated_runtime.world_v1.session import WorldSession

from api_gym.instrument_models.plate_reader_v0.contracts import (
    AcquisitionSettings,
)
from api_gym.instrument_models.plate_reader_v0.dynamics import PlateReaderDynamics
from api_gym.worlds.enzyme_activity_v0.analysis import ObservedReading, fit_blank_corrected_rate
from api_gym.worlds.enzyme_activity_v0.defaults import (
    ANALYSIS_RULES,
    REACTION_PARAMETERS,
    READER_PROFILE,
)
from api_gym.worlds.enzyme_activity_v0.observations import public_experiment_observation
from api_gym.worlds.enzyme_activity_v0.state import ExperimentState, Mixture


WORLD_ID = "enzyme_activity_v0"
WORKER_PYTHON_ENV = "DATALOX_OT2_WORKER_PYTHON"

INSPECT = "lab.inspect"
PICK_UP_TIP = "ot2.pick_up_tip"
ASPIRATE = "ot2.aspirate"
DISPENSE = "ot2.dispense"
DROP_TIP = "ot2.drop_tip"
REQUEST_TRANSFER = "operator.request_transfer"
START_SERIES = "reader.start_series"
GET_DATA = "reader.get_data"
WAIT = "lab.wait"
SUBMIT_REPORT = "experiment.submit_report"

_ROUTES = {
    INSPECT: ("GET", "/v1/lab"),
    PICK_UP_TIP: ("POST", "/v1/ot2/tips/pick-up"),
    ASPIRATE: ("POST", "/v1/ot2/aspirate"),
    DISPENSE: ("POST", "/v1/ot2/dispense"),
    DROP_TIP: ("POST", "/v1/ot2/tips/drop"),
    REQUEST_TRANSFER: ("POST", "/v1/operator/transfers"),
    START_SERIES: ("POST", "/v1/reader/series"),
    GET_DATA: ("POST", "/v1/reader/data"),
    WAIT: ("POST", "/v1/lab/wait"),
    SUBMIT_REPORT: ("POST", "/v1/experiment/report"),
}
_MUTATIONS = frozenset(
    {
        PICK_UP_TIP,
        ASPIRATE,
        DISPENSE,
        DROP_TIP,
        REQUEST_TRANSFER,
        START_SERIES,
        WAIT,
        SUBMIT_REPORT,
    }
)


def _object_schema(properties: Mapping[str, Any], required: tuple[str, ...]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": deepcopy(dict(properties)),
        "required": list(required),
        "additionalProperties": False,
    }


_ACTION_ID = {"type": "string", "minLength": 1, "maxLength": 128}
_WELL = {"type": "string", "pattern": "^[13]:[A-H](?:[1-9]|1[0-2])$"}
TOOL_SCHEMAS = {
    INSPECT: _object_schema({}, ()),
    PICK_UP_TIP: _object_schema(
        {"action_id": _ACTION_ID, "tip_well": {"type": "string"}},
        ("action_id", "tip_well"),
    ),
    ASPIRATE: _object_schema(
        {"action_id": _ACTION_ID, "source": _WELL, "volume_ul": {"type": "number"}},
        ("action_id", "source", "volume_ul"),
    ),
    DISPENSE: _object_schema(
        {
            "action_id": _ACTION_ID,
            "destination": _WELL,
            "volume_ul": {"type": "number"},
        },
        ("action_id", "destination", "volume_ul"),
    ),
    DROP_TIP: _object_schema({"action_id": _ACTION_ID}, ("action_id",)),
    REQUEST_TRANSFER: _object_schema(
        {"action_id": _ACTION_ID, "plate_id": {"type": "string"}},
        ("action_id", "plate_id"),
    ),
    START_SERIES: _object_schema(
        {
            "action_id": _ACTION_ID,
            "plate_id": {"type": "string"},
            "wells": {"type": "array", "items": {"type": "string"}},
        },
        ("action_id", "plate_id", "wells"),
    ),
    GET_DATA: _object_schema({"job_id": {"type": "string"}}, ("job_id",)),
    WAIT: _object_schema(
        {"action_id": _ACTION_ID, "duration_s": {"type": "number"}},
        ("action_id", "duration_s"),
    ),
    SUBMIT_REPORT: _object_schema(
        {
            "action_id": _ACTION_ID,
            "sample_id": {"type": "string"},
            "job_id": {"type": "string"},
            "sample_measurement_ids": {"type": "array", "items": {"type": "string"}},
            "blank_measurement_ids": {"type": "array", "items": {"type": "string"}},
            "dilution_factor": {"type": "number"},
            "estimated_rate": {"type": "number"},
            "units": {"type": "string"},
        },
        (
            "action_id",
            "sample_id",
            "job_id",
            "sample_measurement_ids",
            "blank_measurement_ids",
            "dilution_factor",
            "estimated_rate",
            "units",
        ),
    ),
}


@dataclass(frozen=True)
class VerificationResult:
    passed: bool
    result: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, **self.result}


class EnzymeActivityRuntimeAdapter(WorldImplementationV1):
    """One minimal assay path proving the API Gym/runtime integration contract."""

    def __init__(self, native_python: Path) -> None:
        self._launcher = OpentronsOT2WorkerLauncher(
            python_executable=native_python,
            expected_source_hashes=PINNED_SOURCE_HASHES,
            initial_tip_well=None,
            initial_well_volumes_ul={"1:A1": 120, "1:A2": 240, "1:A3": 240},
        )
        self._manager: OpentronsOT2MotionManager | None = None
        self._state: ExperimentState | None = None
        self._reader: PlateReaderDynamics | None = None
        self._ledger: dict[str, tuple[str, dict[str, Any]]] = {}
        self._plate_id = "assay-plate-001"
        self._plate_revision = 1
        self._plate_location = "ot2_slot_3"
        self._reader_plate_id: str | None = None
        self._reader_plate_revision: int | None = None
        self._transfer: dict[str, Any] | None = None
        self._report: dict[str, Any] | None = None
        self._native_receipts: list[dict[str, Any]] = []

    def reset_managed_resources(self) -> None:
        if self._manager is None:
            manager = OpentronsOT2MotionManager(self._launcher)
            try:
                manager.start()
            except BaseException:
                manager.close()
                raise
            self._manager = manager
        else:
            self._manager.reset()

    def close_managed_resources(self) -> None:
        manager, self._manager = self._manager, None
        if manager is not None:
            manager.close()

    def initialize_episode(self, *, session: WorldSession, episode: Mapping[str, Any]) -> None:
        if self._manager is None or not self._manager.valid:
            raise RuntimeError("native OT-2 worker is not active")
        seed = _integer(episode.get("seed"), "episode.seed")
        self._state = ExperimentState(
            0,
            REACTION_PARAMETERS,
            {
                "1:A1": Mixture.pure(
                    source_id="SAMPLE-A-stock",
                    volume_ul=120,
                    enzyme_concentration_mM=0.002,
                ),
                "1:A2": Mixture.pure(
                    source_id="substrate-stock",
                    volume_ul=240,
                    substrate_concentration_mM=2.0,
                ),
                "1:A3": Mixture.pure(source_id="assay-buffer", volume_ul=240),
            },
        )
        self._reader = PlateReaderDynamics(READER_PROFILE, noise_seed=seed + 1000)
        self._ledger = {}
        self._plate_id = "assay-plate-001"
        self._plate_revision = 1
        self._plate_location = "ot2_slot_3"
        self._reader_plate_id = None
        self._reader_plate_revision = None
        self._transfer = None
        self._report = None
        self._native_receipts = []
        session.reset(
            episode_id=_string(episode.get("id"), "episode.id"),
            initial_state=self._projection(),
            initial_time=_string(episode.get("initial_time"), "episode.initial_time"),
        )

    def tool_schemas(self, *, actor: ActorContext) -> dict[str, dict[str, Any]]:
        del actor
        return deepcopy(TOOL_SCHEMAS)

    def operation_for_tool(self, tool_name: str) -> str | None:
        return tool_name if tool_name in _ROUTES else None

    def tool_for_request(self, request: CallRequest) -> str | None:
        route = (request.normalized_method(), request.path.rstrip("/") or "/")
        return next((name for name, candidate in _ROUTES.items() if candidate == route), None)

    def request_for_tool(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        *,
        actor: ActorContext,
    ) -> CallRequest:
        del actor
        method, path = _ROUTES[tool_name]
        body = None if method == "GET" else deepcopy(dict(arguments))
        operation_id = (
            _string(arguments.get("action_id"), "action_id")
            if tool_name in _MUTATIONS
            else tool_name
        )
        return CallRequest(method=method, path=path, body=body, operation_id=operation_id)

    def handle(
        self,
        request: CallRequest,
        *,
        actor: ActorContext,
        session: WorldSession,
    ) -> WorldResponse | None:
        del actor
        operation = self.tool_for_request(request)
        if operation is None:
            return None
        try:
            arguments = _arguments(request)
            cached = self._cached(operation, arguments) if operation in _MUTATIONS else None
            if cached is not None:
                return self._response(operation, cached, mutated=False, reason="action_replay")
            body = self._dispatch(operation, arguments, session=session)
            if operation in _MUTATIONS:
                self._remember(operation, arguments, body)
            self._persist(session)
            return self._response(
                operation,
                body,
                mutated=operation in _MUTATIONS,
                reason="world_state_write" if operation in _MUTATIONS else "world_state_read",
            )
        except (KeyError, TypeError, ValueError) as exc:
            return self._error(operation, "enzyme_activity_request_invalid", str(exc))

    def verify(
        self, *, session: WorldSession, episode: Mapping[str, Any]
    ) -> VerificationResult:
        del episode
        invalidations = [
            event
            for event in session.list_events()
            if event["type"] == "world_operation_invalidated"
        ]
        checks = {
            "no_uncertain_native_operation": not invalidations,
            "operator_transfer_confirmed": bool(
                self._transfer and self._transfer.get("status") == "completed"
            ),
            "reader_series_complete": self._reader_series_complete(),
            "supported_report_submitted": bool(
                self._report and self._report.get("accepted") is True
            ),
        }
        return VerificationResult(
            passed=all(checks.values()),
            result={"checks": checks, "failure_codes": [key for key, ok in checks.items() if not ok]},
        )

    def task(self, *, episode: Mapping[str, Any]) -> TaskBrief:
        del episode
        return TaskBrief(
            task_id="enzyme-activity-contract-01",
            title="Prepare and measure one modeled enzyme reaction",
            instructions=(
                "Prepare SAMPLE-A and a matched blank from the declared stocks, request the "
                "plate transfer, acquire 405 nm observations, and submit a supported "
                "blank-corrected relative rate."
            ),
            success_criteria=[
                "Use only confirmed native liquid actions.",
                "Cite acquired sample and matched blank measurements.",
                "Report delta_absorbance_per_minute or an evidence-backed unresolved result.",
            ],
        )

    def _dispatch(
        self, operation: str, arguments: dict[str, Any], *, session: WorldSession
    ) -> dict[str, Any]:
        if operation == INSPECT:
            _fields(arguments, set(), set())
            return self._observation()
        if operation == PICK_UP_TIP:
            _fields(arguments, {"action_id", "tip_well"}, {"action_id", "tip_well"})
            tip_well = _string(arguments["tip_well"], "tip_well")
            self._state_required().wait(2)
            receipt = self._manager_required().execute_liquid(PickUpTip(tip_well))
            if receipt.before.has_tip or not receipt.after.has_tip:
                raise RuntimeError("native tip receipt disagrees with the requested transition")
            body = {"action_id": arguments["action_id"], "receipt": receipt.to_dict()}
            return self._record_native_receipt(session, body)
        if operation == ASPIRATE:
            _fields(arguments, {"action_id", "source", "volume_ul"}, {"action_id", "source", "volume_ul"})
            source = _native_well(arguments["source"])
            volume = _positive(arguments["volume_ul"], "volume_ul")
            state = self._state_required()
            if source not in state.wells or state.tip.volume_ul != 0:
                raise ValueError("aspiration requires a known source and empty tip")
            state.wait(3)
            request = Aspirate(*source.split(":"), volume)
            receipt = self._manager_required().execute_liquid(request)
            _volume_agreement(receipt.before.well_volumes_ul[source], state.wells[source].volume_ul)
            state.aspirate(source, volume)
            _volume_agreement(receipt.after.well_volumes_ul[source], state.wells[source].volume_ul)
            _volume_agreement(receipt.after.current_volume_ul, state.tip.volume_ul)
            body = {"action_id": arguments["action_id"], "receipt": receipt.to_dict()}
            return self._record_native_receipt(session, body)
        if operation == DISPENSE:
            _fields(arguments, {"action_id", "destination", "volume_ul"}, {"action_id", "destination", "volume_ul"})
            destination = _native_well(arguments["destination"])
            volume = _positive(arguments["volume_ul"], "volume_ul")
            state = self._state_required()
            if state.tip.volume_ul < volume:
                raise ValueError("dispense volume exceeds modeled tip contents")
            state.wait(3)
            request = Dispense(*destination.split(":"), volume)
            receipt = self._manager_required().execute_liquid(request)
            before_volume = state.wells.get(
                destination, Mixture(last_integrated_s=state.clock_s)
            ).volume_ul
            _volume_agreement(receipt.before.well_volumes_ul[destination], before_volume)
            state.dispense(destination, volume)
            _volume_agreement(
                receipt.after.well_volumes_ul[destination], state.wells[destination].volume_ul
            )
            _volume_agreement(receipt.after.current_volume_ul, state.tip.volume_ul)
            self._plate_revision += 1 if destination.startswith("3:") else 0
            body = {"action_id": arguments["action_id"], "receipt": receipt.to_dict()}
            return self._record_native_receipt(session, body)
        if operation == DROP_TIP:
            _fields(arguments, {"action_id"}, {"action_id"})
            state = self._state_required()
            if state.tip.volume_ul != 0:
                raise ValueError("tip must be empty before drop")
            state.wait(2)
            receipt = self._manager_required().execute_liquid(DropTip())
            if not receipt.before.has_tip or receipt.after.has_tip:
                raise RuntimeError("native tip receipt disagrees with the requested transition")
            body = {"action_id": arguments["action_id"], "receipt": receipt.to_dict()}
            return self._record_native_receipt(session, body)
        if operation == REQUEST_TRANSFER:
            _fields(arguments, {"action_id", "plate_id"}, {"action_id", "plate_id"})
            if arguments["plate_id"] != self._plate_id or self._plate_location != "ot2_slot_3":
                raise ValueError("requested plate is not available in OT-2 slot 3")
            if self._transfer is not None:
                raise ValueError("a transfer request already exists")
            self._transfer = {
                "request_id": "transfer-0001",
                "plate_id": self._plate_id,
                "source": "ot2_slot_3",
                "destination": "modeled_reader",
                "status": "pending",
                "requested_at_s": self._state_required().clock_s,
                "complete_at_s": self._state_required().clock_s + 5,
                "operator_confirmation": None,
            }
            return deepcopy(self._transfer)
        if operation == START_SERIES:
            _fields(arguments, {"action_id", "plate_id", "wells"}, {"action_id", "plate_id", "wells"})
            if arguments["plate_id"] != self._reader_plate_id or self._plate_location != "modeled_reader":
                raise ValueError("plate is not confirmed inside the modeled reader")
            wells_raw = arguments["wells"]
            if not isinstance(wells_raw, list) or not wells_raw:
                raise ValueError("wells must be a non-empty array")
            wells = tuple(_reader_well(value) for value in wells_raw)
            reader = self._reader_required()
            job_id = reader.start_series(
                plate_id=self._reader_plate_id,
                plate_revision=self._reader_plate_revision_required(),
                start_s=self._state_required().clock_s,
                settings=AcquisitionSettings(405, 37, wells, (0, 30, 60, 90, 120)),
            )
            self._acquire_until(job_id, self._state_required().clock_s)
            return reader.get_job(job_id)
        if operation == GET_DATA:
            _fields(arguments, {"job_id"}, {"job_id"})
            job_id = _string(arguments["job_id"], "job_id")
            return {"job_id": job_id, "measurements": list(self._reader_required().get_data(job_id))}
        if operation == WAIT:
            _fields(arguments, {"action_id", "duration_s"}, {"action_id", "duration_s"})
            duration = _positive(arguments["duration_s"], "duration_s")
            if duration > 300:
                raise ValueError("one wait may not exceed 300 logical seconds")
            target = self._state_required().clock_s + duration
            if (
                self._transfer
                and self._transfer["status"] == "pending"
                and self._transfer["complete_at_s"] <= target
            ):
                self._advance_reader_to(self._transfer["complete_at_s"])
                receipt = self._manager_required().exchange_fresh_plate(ExchangeFreshPlate("3"))
                self._complete_transfer(receipt.to_dict())
                self._record_native_receipt(
                    session,
                    {"action_id": arguments["action_id"], "receipt": receipt.to_dict()},
                )
            self._advance_reader_to(target)
            return self._observation()
        if operation == SUBMIT_REPORT:
            required = {
                "action_id",
                "sample_id",
                "job_id",
                "sample_measurement_ids",
                "blank_measurement_ids",
                "dilution_factor",
                "estimated_rate",
                "units",
            }
            _fields(arguments, required, required)
            return self._submit_report(arguments)
        raise AssertionError(operation)

    def _complete_transfer(self, native_receipt: dict[str, Any]) -> None:
        assert self._transfer is not None
        state = self._state_required()
        for address, native_volume in native_receipt["before"]["well_volumes_ul"].items():
            if not address.startswith("3:"):
                continue
            modeled = state.wells.get(
                address, Mixture(last_integrated_s=state.clock_s)
            ).volume_ul
            _volume_agreement(native_volume, modeled)
        for address, native_volume in native_receipt["after"]["well_volumes_ul"].items():
            if address.startswith("3:"):
                _volume_agreement(native_volume, 0)
        moved = {
            address.removeprefix("3:"): mixture
            for address, mixture in list(state.wells.items())
            if address.startswith("3:") and mixture.volume_ul > 0
        }
        for address in [key for key in state.wells if key.startswith("3:")]:
            del state.wells[address]
        for well, mixture in moved.items():
            state.wells[f"reader:{well}"] = mixture
        self._reader_plate_id = self._plate_id
        self._reader_plate_revision = self._plate_revision
        self._plate_location = "modeled_reader"
        self._transfer.update(
            {
                "status": "completed",
                "completed_at_s": state.clock_s,
                "operator_confirmation": {
                    "confirmed": True,
                    "retired_native_plate_id": native_receipt["retired_plate_id"],
                    "replacement_native_plate_id": native_receipt["replacement_plate_id"],
                },
            }
        )

    def _advance_reader_to(self, target_s: float) -> None:
        reader = self._reader_required()
        for job_id in reader.job_ids:
            self._acquire_until(job_id, target_s)
        self._state_required().advance_to(target_s)

    def _acquire_until(self, job_id: str, target_s: float) -> None:
        state = self._state_required()

        def mixture_at(well: str, acquisition_s: float) -> Mixture:
            state.advance_to(acquisition_s)
            try:
                return state.wells[f"reader:{well}"]
            except KeyError as exc:
                raise ValueError(f"reader well {well!r} has no modeled mixture") from exc

        self._reader_required().acquire_due(
            job_id,
            now_s=target_s,
            mixture_at=mixture_at,
        )

    def _submit_report(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if arguments["sample_id"] != "SAMPLE-A":
            raise ValueError("unknown public sample ID")
        job = self._reader_required().get_job(_string(arguments["job_id"], "job_id"))
        measurements = {item["measurement_id"]: item for item in job["measurements"]}
        sample_ids = _string_list(arguments["sample_measurement_ids"], "sample_measurement_ids")
        blank_ids = _string_list(arguments["blank_measurement_ids"], "blank_measurement_ids")

        def observed(ids: tuple[str, ...]) -> tuple[ObservedReading, ...]:
            result = []
            for measurement_id in ids:
                item = measurements.get(measurement_id)
                if item is None or item["status"] != "acquired" or item["absorbance"] is None:
                    raise ValueError("report cites an unavailable or non-numeric measurement")
                result.append(
                    ObservedReading(
                        measurement_id=measurement_id,
                        well=item["well"],
                        acquired_at_s=item["acquired_at_s"],
                        absorbance=item["absorbance"],
                        plate_id=job["plate_id"],
                        plate_revision=job["plate_revision"],
                        settings_digest=job["settings_digest"],
                    )
                )
            return tuple(result)

        estimate = fit_blank_corrected_rate(
            sample_readings=observed(sample_ids),
            blank_readings=observed(blank_ids),
            dilution_factor=_positive(arguments["dilution_factor"], "dilution_factor"),
            rules=ANALYSIS_RULES,
        )
        submitted_rate = _finite(arguments["estimated_rate"], "estimated_rate")
        accepted = (
            estimate.disposition == "usable"
            and arguments["units"] == estimate.units
            and estimate.rate is not None
            and abs(submitted_rate - estimate.rate) <= max(1e-9, abs(estimate.rate) * 1e-6)
        )
        self._report = {
            "sample_id": "SAMPLE-A",
            "submitted_rate": submitted_rate,
            "units": arguments["units"],
            "reference_analysis": estimate.to_dict(),
            "accepted": accepted,
        }
        return deepcopy(self._report)

    def _observation(self) -> dict[str, Any]:
        state = self._state_required()
        public_wells = {
            "source_plate": {
                address: mixture.volume_ul
                for address, mixture in sorted(state.wells.items())
                if address.startswith("1:")
            },
            "assay_plate": {
                address: mixture.volume_ul
                for address, mixture in sorted(state.wells.items())
                if address.startswith("3:")
            },
        }
        jobs = tuple(
            self._reader_required().get_job(job_id)
            for job_id in self._reader_required().job_ids
        )
        return public_experiment_observation(
            logical_time_s=state.clock_s,
            inventory={
                "sample_labels": ["SAMPLE-A", "BLANK"],
                "well_volumes_ul": public_wells,
                "tip_volume_ul": state.tip.volume_ul,
            },
            plate_id=self._reader_plate_id or self._plate_id,
            plate_revision=self._reader_plate_revision or self._plate_revision,
            plate_location=self._plate_location,
            operator_requests=() if self._transfer is None else (self._transfer,),
            reader_jobs=jobs,
        )

    def _projection(self) -> dict[str, Any]:
        verification = {
            "report_submitted": self._report is not None,
            "report_accepted": bool(self._report and self._report.get("accepted")),
        }
        return {
            "agent_observation": self._observation(),
            "trusted_summary": {
                "mixtures": {
                    address: mixture.to_dict()
                    for address, mixture in sorted(self._state_required().wells.items())
                },
                "native_receipts": deepcopy(self._native_receipts),
                "report": deepcopy(self._report),
            },
            "verification": verification,
        }

    def _persist(self, session: WorldSession) -> None:
        for key, value in self._projection().items():
            session.set_state(key, value)

    def _record_native_receipt(
        self, session: WorldSession, body: dict[str, Any]
    ) -> dict[str, Any]:
        self._native_receipts.append(deepcopy(body))
        session.append_event("native_action_receipt", deepcopy(body))
        return body

    def _cached(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
        action_id = _string(arguments.get("action_id"), "action_id")
        digest = _request_digest(operation, arguments)
        existing = self._ledger.get(action_id)
        if existing is None:
            return None
        if existing[0] != digest:
            raise ValueError("action_id was already used with a different request")
        return deepcopy(existing[1])

    def _remember(self, operation: str, arguments: dict[str, Any], body: dict[str, Any]) -> None:
        action_id = _string(arguments["action_id"], "action_id")
        self._ledger[action_id] = (_request_digest(operation, arguments), deepcopy(body))

    def _reader_series_complete(self) -> bool:
        reader = self._reader_required()
        return reader.all_jobs_complete

    def _state_required(self) -> ExperimentState:
        if self._state is None:
            raise RuntimeError("episode is not initialized")
        return self._state

    def _reader_required(self) -> PlateReaderDynamics:
        if self._reader is None:
            raise RuntimeError("reader is not initialized")
        return self._reader

    def _manager_required(self) -> OpentronsOT2MotionManager:
        if self._manager is None or not self._manager.valid:
            raise RuntimeError("native worker is not active")
        return self._manager

    def _reader_plate_revision_required(self) -> int:
        if self._reader_plate_revision is None:
            raise RuntimeError("reader plate is unavailable")
        return self._reader_plate_revision

    @staticmethod
    def _response(
        operation: str, body: dict[str, Any], *, mutated: bool, reason: str
    ) -> WorldResponse:
        return WorldResponse(
            status_code=200,
            body=deepcopy(body),
            is_mutation=mutated,
            world_id=WORLD_ID,
            operation_id=operation,
            decision_kind="shadow_write" if mutated else "replay",
            reason_code=reason,
            message="Enzyme activity modeled operation completed.",
        )

    @staticmethod
    def _error(operation: str, code: str, message: str) -> WorldResponse:
        return WorldResponse(
            status_code=422,
            body={"error": {"code": code, "message": message}},
            is_mutation=False,
            world_id=WORLD_ID,
            operation_id=operation,
            decision_kind="deny",
            reason_code=code,
            message="Enzyme activity operation was rejected before native dispatch.",
        )


def create_world() -> EnzymeActivityRuntimeAdapter:
    configured = os.environ.get(WORKER_PYTHON_ENV)
    if configured is None:
        raise RuntimeError(f"Trusted controller must set {WORKER_PYTHON_ENV}.")
    return EnzymeActivityRuntimeAdapter(Path(configured))


def _arguments(request: CallRequest) -> dict[str, Any]:
    if request.normalized_method() == "GET":
        if request.body is not None:
            raise ValueError("GET body must be empty")
        return {}
    if not isinstance(request.body, Mapping):
        raise ValueError("request body must be an object")
    return deepcopy(dict(request.body))


def _fields(value: Mapping[str, Any], allowed: set[str], required: set[str]) -> None:
    missing = required - set(value)
    unknown = set(value) - allowed
    if missing or unknown:
        raise ValueError(f"request fields invalid; missing={sorted(missing)}, unknown={sorted(unknown)}")


def _string(value: Any, name: str) -> str:
    if type(value) is not str or not value or value.strip() != value:
        raise ValueError(f"{name} must be a non-empty trimmed string")
    return value


def _integer(value: Any, name: str) -> int:
    if type(value) is not int:
        raise ValueError(f"{name} must be an integer")
    return value


def _finite(value: Any, name: str) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{name} must be numeric")
    result = float(value)
    if not (-float("inf") < result < float("inf")):
        raise ValueError(f"{name} must be finite")
    return result


def _positive(value: Any, name: str) -> float:
    result = _finite(value, name)
    if result <= 0:
        raise ValueError(f"{name} must be positive")
    return result


def _native_well(value: Any) -> str:
    result = _string(value, "well")
    if len(result.split(":")) != 2 or result.split(":")[0] not in {"1", "3"}:
        raise ValueError("well must use '<slot>:<well>' for slot 1 or 3")
    return result


def _reader_well(value: Any) -> str:
    result = _string(value, "reader well")
    if result not in {"A1", "A2"}:
        raise ValueError("the integration slice admits reader wells A1 and A2")
    return result


def _string_list(value: Any, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{name} must be a non-empty array")
    result = tuple(_string(item, name) for item in value)
    if len(set(result)) != len(result):
        raise ValueError(f"{name} must not contain duplicates")
    return result


def _request_digest(operation: str, arguments: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        {"operation": operation, "arguments": arguments},
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _volume_agreement(native_ul: float, modeled_ul: float) -> None:
    if abs(float(native_ul) - float(modeled_ul)) > 1e-7:
        raise RuntimeError(
            f"native/model volume disagreement: native={native_ul}, modeled={modeled_ul}"
        )
