"""Executable enzyme-assay scenarios over the gated runtime's native worker."""

from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from dataclasses import dataclass, replace
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
from api_gym.worlds.enzyme_activity_v0.analysis import (
    ObservedReading,
    fit_blank_corrected_rate,
)
from api_gym.worlds.enzyme_activity_v0.defaults import (
    ANALYSIS_RULES,
    FINAL_SUBSTRATE_CONCENTRATION_MM,
    MAX_ASSAY_PLATES,
    MAX_LOGICAL_TIME_S,
    MAX_PLATE_TRANSFERS,
    REACTION_PARAMETERS,
    READER_PROFILE,
    SUBSTRATE_STOCK_CONCENTRATION_MM,
    UNDILUTED_SAMPLE_FRACTION,
)
from api_gym.worlds.enzyme_activity_v0.observations import public_experiment_observation
from api_gym.worlds.enzyme_activity_v0.scenarios import (
    ScenarioDefinition,
    scenario_for_id,
)
from api_gym.worlds.enzyme_activity_v0.state import ExperimentState, Mixture
from api_gym.worlds.enzyme_activity_v0.tasks import task_for_scenario
from api_gym.worlds.enzyme_activity_v0.verifier import (
    MeasurementEvidence,
    SampleReport,
    VerificationContext,
    verify_experiment,
)


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


def _object_schema(
    properties: Mapping[str, Any], required: tuple[str, ...]
) -> dict[str, Any]:
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
            "disposition": {"enum": ["usable", "unresolved"]},
            "sample_measurement_ids": {"type": "array", "items": {"type": "string"}},
            "blank_measurement_ids": {"type": "array", "items": {"type": "string"}},
            "reference_measurement_ids": {
                "type": "array",
                "items": {"type": "string"},
            },
            "fit_window_s": {
                "oneOf": [
                    {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 2,
                        "maxItems": 2,
                    },
                    {"type": "null"},
                ]
            },
            "dilution_factor": {"type": "number"},
            "estimated_rate": {"type": ["number", "null"]},
            "uncertainty": {"type": ["number", "null"]},
            "units": {"type": "string"},
            "unresolved_reason_code": {"type": ["string", "null"]},
            "evidence_refs": {"type": "array", "items": {"type": "string"}},
        },
        (
            "action_id",
            "sample_id",
            "job_id",
            "disposition",
            "sample_measurement_ids",
            "blank_measurement_ids",
            "reference_measurement_ids",
            "fit_window_s",
            "dilution_factor",
            "estimated_rate",
            "uncertainty",
            "units",
            "unresolved_reason_code",
            "evidence_refs",
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
    """Couple native preparation, modeled acquisition, and Phase 3 verification."""

    def __init__(self, native_python: Path) -> None:
        self._launcher = OpentronsOT2WorkerLauncher(
            python_executable=native_python,
            expected_source_hashes=PINNED_SOURCE_HASHES,
            initial_tip_well=None,
            initial_well_volumes_ul={
                "1:A1": 120,
                "1:A2": 360,
                "1:A3": 240,
                "1:A4": 120,
            },
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
        self._scenario: ScenarioDefinition | None = None

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

    def initialize_episode(
        self, *, session: WorldSession, episode: Mapping[str, Any]
    ) -> None:
        if self._manager is None or not self._manager.valid:
            raise RuntimeError("native OT-2 worker is not active")
        scenario = scenario_for_id(_string(episode.get("id"), "episode.id"))
        seed = _integer(episode.get("seed"), "episode.seed")
        if seed != scenario.seed:
            raise ValueError(
                "episode seed does not match the frozen scenario definition"
            )
        initial = scenario.private_initial_conditions
        self._state = ExperimentState(
            0,
            REACTION_PARAMETERS,
            {
                "1:A1": Mixture.pure(
                    source_id="SAMPLE-A-stock",
                    volume_ul=120,
                    enzyme_concentration_mM=float(
                        initial["sample_enzyme_concentration_mM"]
                    ),
                ),
                "1:A2": Mixture.pure(
                    source_id="substrate-stock",
                    volume_ul=360,
                    substrate_concentration_mM=SUBSTRATE_STOCK_CONCENTRATION_MM,
                ),
                "1:A3": Mixture.pure(source_id="assay-buffer", volume_ul=240),
                "1:A4": Mixture.pure(
                    source_id="REF-AP-stock",
                    volume_ul=120,
                    enzyme_concentration_mM=float(
                        initial["reference_enzyme_concentration_mM"]
                    ),
                ),
            },
        )
        reader_profile = replace(
            READER_PROFILE,
            blank_drift_abs_per_s=float(initial["blank_drift_abs_per_s"]),
        )
        self._reader = PlateReaderDynamics(
            reader_profile,
            noise_seed=seed + 1000,
            missing_measurement_indices=frozenset(
                scenario.private_events["missing_measurement_indices"]
            ),
        )
        self._ledger = {}
        self._plate_id = "assay-plate-001"
        self._plate_revision = 1
        self._plate_location = "ot2_slot_3"
        self._reader_plate_id = None
        self._reader_plate_revision = None
        self._transfer = None
        self._report = None
        self._native_receipts = []
        self._scenario = scenario
        session.reset(
            episode_id=scenario.scenario_id,
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
        return next(
            (name for name, candidate in _ROUTES.items() if candidate == route), None
        )

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
        return CallRequest(
            method=method, path=path, body=body, operation_id=operation_id
        )

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
            cached = (
                self._cached(operation, arguments) if operation in _MUTATIONS else None
            )
            if cached is not None:
                return self._response(
                    operation, cached, mutated=False, reason="action_replay"
                )
            body = self._dispatch(operation, arguments, session=session)
            if operation in _MUTATIONS:
                self._remember(operation, arguments, body)
            self._persist(session)
            return self._response(
                operation,
                body,
                mutated=operation in _MUTATIONS,
                reason="world_state_write"
                if operation in _MUTATIONS
                else "world_state_read",
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
        report_verification = (
            None if self._report is None else self._report.get("verification")
        )
        checks = {
            "no_uncertain_native_operation": not invalidations,
            "operator_transfer_confirmed": bool(
                self._transfer and self._transfer.get("status") == "completed"
            ),
            "supported_report_submitted": bool(
                self._report and self._report.get("accepted") is True
            ),
        }
        failure_codes = [key for key, ok in checks.items() if not ok]
        if report_verification is not None:
            failure_codes.extend(report_verification["failure_codes"])
        return VerificationResult(
            passed=all(checks.values()),
            result={
                "checks": checks,
                "failure_codes": list(dict.fromkeys(failure_codes)),
                "report_verification": deepcopy(report_verification),
            },
        )

    def task(self, *, episode: Mapping[str, Any]) -> TaskBrief:
        definition = task_for_scenario(
            scenario_for_id(_string(episode.get("id"), "episode.id"))
        )
        return TaskBrief(
            task_id=definition.task_id,
            title=definition.title,
            instructions=definition.instructions,
            success_criteria=list(definition.success_criteria),
        )

    def _dispatch(
        self, operation: str, arguments: dict[str, Any], *, session: WorldSession
    ) -> dict[str, Any]:
        if self._report is not None and operation in _MUTATIONS:
            raise ValueError("the submitted experiment report is terminal")
        if operation == INSPECT:
            _fields(arguments, set(), set())
            return self._observation()
        if operation == PICK_UP_TIP:
            _fields(arguments, {"action_id", "tip_well"}, {"action_id", "tip_well"})
            tip_well = _string(arguments["tip_well"], "tip_well")
            self._state_required().wait(2)
            receipt = self._manager_required().execute_liquid(PickUpTip(tip_well))
            if receipt.before.has_tip or not receipt.after.has_tip:
                raise RuntimeError(
                    "native tip receipt disagrees with the requested transition"
                )
            body = {"action_id": arguments["action_id"], "receipt": receipt.to_dict()}
            return self._record_native_receipt(session, body)
        if operation == ASPIRATE:
            _fields(
                arguments,
                {"action_id", "source", "volume_ul"},
                {"action_id", "source", "volume_ul"},
            )
            source = _native_well(arguments["source"])
            volume = _positive(arguments["volume_ul"], "volume_ul")
            state = self._state_required()
            if source not in state.wells or state.tip.volume_ul != 0:
                raise ValueError("aspiration requires a known source and empty tip")
            state.wait(3)
            request = Aspirate(*source.split(":"), volume)
            receipt = self._manager_required().execute_liquid(request)
            _volume_agreement(
                receipt.before.well_volumes_ul[source], state.wells[source].volume_ul
            )
            state.aspirate(source, volume)
            _volume_agreement(
                receipt.after.well_volumes_ul[source], state.wells[source].volume_ul
            )
            _volume_agreement(receipt.after.current_volume_ul, state.tip.volume_ul)
            body = {"action_id": arguments["action_id"], "receipt": receipt.to_dict()}
            return self._record_native_receipt(session, body)
        if operation == DISPENSE:
            _fields(
                arguments,
                {"action_id", "destination", "volume_ul"},
                {"action_id", "destination", "volume_ul"},
            )
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
            _volume_agreement(
                receipt.before.well_volumes_ul[destination], before_volume
            )
            state.dispense(destination, volume)
            _volume_agreement(
                receipt.after.well_volumes_ul[destination],
                state.wells[destination].volume_ul,
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
                raise RuntimeError(
                    "native tip receipt disagrees with the requested transition"
                )
            body = {"action_id": arguments["action_id"], "receipt": receipt.to_dict()}
            return self._record_native_receipt(session, body)
        if operation == REQUEST_TRANSFER:
            _fields(arguments, {"action_id", "plate_id"}, {"action_id", "plate_id"})
            if (
                arguments["plate_id"] != self._plate_id
                or self._plate_location != "ot2_slot_3"
            ):
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
                "complete_at_s": self._state_required().clock_s
                + float(self._scenario_required().private_events["transfer_delay_s"]),
                "operator_confirmation": None,
            }
            return deepcopy(self._transfer)
        if operation == START_SERIES:
            _fields(
                arguments,
                {"action_id", "plate_id", "wells"},
                {"action_id", "plate_id", "wells"},
            )
            if (
                arguments["plate_id"] != self._reader_plate_id
                or self._plate_location != "modeled_reader"
            ):
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
            return {
                "job_id": job_id,
                "measurements": list(self._reader_required().get_data(job_id)),
            }
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
                receipt = self._manager_required().exchange_fresh_plate(
                    ExchangeFreshPlate("3")
                )
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
                "disposition",
                "sample_measurement_ids",
                "blank_measurement_ids",
                "reference_measurement_ids",
                "fit_window_s",
                "dilution_factor",
                "estimated_rate",
                "uncertainty",
                "units",
                "unresolved_reason_code",
                "evidence_refs",
            }
            _fields(arguments, required, required)
            return self._submit_report(arguments, session=session)
        raise AssertionError(operation)

    def _complete_transfer(self, native_receipt: dict[str, Any]) -> None:
        assert self._transfer is not None
        state = self._state_required()
        for address, native_volume in native_receipt["before"][
            "well_volumes_ul"
        ].items():
            if not address.startswith("3:"):
                continue
            modeled = state.wells.get(
                address, Mixture(last_integrated_s=state.clock_s)
            ).volume_ul
            _volume_agreement(native_volume, modeled)
        for address, native_volume in native_receipt["after"][
            "well_volumes_ul"
        ].items():
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
        observed_plate_id = self._scenario_required().private_events.get(
            "observed_transfer_plate_id", self._plate_id
        )
        self._plate_id = _string(observed_plate_id, "observed_transfer_plate_id")
        self._reader_plate_id = self._plate_id
        self._reader_plate_revision = self._plate_revision
        self._plate_location = "modeled_reader"
        self._transfer.update(
            {
                "status": "completed",
                "completed_at_s": state.clock_s,
                "operator_confirmation": {
                    "confirmed": True,
                    "observed_plate_id": self._plate_id,
                    "retired_native_plate_id": native_receipt["retired_plate_id"],
                    "replacement_native_plate_id": native_receipt[
                        "replacement_plate_id"
                    ],
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
                raise ValueError(
                    f"reader well {well!r} has no modeled mixture"
                ) from exc

        self._reader_required().acquire_due(
            job_id,
            now_s=target_s,
            mixture_at=mixture_at,
        )

    def _submit_report(
        self, arguments: dict[str, Any], *, session: WorldSession
    ) -> dict[str, Any]:
        if arguments["sample_id"] != "SAMPLE-A":
            raise ValueError("unknown public sample ID")
        job = self._reader_required().get_job(_string(arguments["job_id"], "job_id"))
        measurements = {
            item["measurement_id"]: MeasurementEvidence(
                measurement_id=item["measurement_id"],
                job_id=job["job_id"],
                sample_id=_sample_for_well(item["well"]),
                well=item["well"],
                acquired_at_s=_finite(item["acquired_at_s"], "acquired_at_s"),
                status=item["status"],
                absorbance=item["absorbance"],
                plate_id=job["plate_id"],
                plate_revision=job["plate_revision"],
                settings_digest=job["settings_digest"],
            )
            for item in job["measurements"]
        }
        sample_ids = _string_list(
            arguments["sample_measurement_ids"],
            "sample_measurement_ids",
            allow_empty=True,
        )
        blank_ids = _string_list(
            arguments["blank_measurement_ids"],
            "blank_measurement_ids",
            allow_empty=True,
        )
        reference_ids = _string_list(
            arguments["reference_measurement_ids"],
            "reference_measurement_ids",
            allow_empty=True,
        )
        evidence_refs = _string_list(
            arguments["evidence_refs"], "evidence_refs", allow_empty=True
        )
        fit_window = _optional_window(arguments["fit_window_s"], "fit_window_s")
        submitted_rate = _optional_finite(arguments["estimated_rate"], "estimated_rate")
        uncertainty = _optional_non_negative(arguments["uncertainty"], "uncertainty")
        disposition = _string(arguments["disposition"], "disposition")
        if disposition not in {"usable", "unresolved"}:
            raise ValueError("disposition must be usable or unresolved")
        unresolved_reason = _optional_string(
            arguments["unresolved_reason_code"], "unresolved_reason_code"
        )
        report = SampleReport(
            sample_id="SAMPLE-A",
            disposition=disposition,
            sample_measurement_ids=sample_ids,
            blank_measurement_ids=blank_ids,
            reference_measurement_ids=reference_ids,
            fit_window_s=fit_window,
            dilution_factor=_positive(arguments["dilution_factor"], "dilution_factor"),
            estimated_rate=submitted_rate,
            uncertainty=uncertainty,
            units=_string(arguments["units"], "units"),
            unresolved_reason_code=unresolved_reason,
            evidence_refs=evidence_refs,
        )
        invalidations = any(
            event["type"] == "world_operation_invalidated"
            for event in session.list_events()
        )
        transfer_confirmed = bool(
            self._transfer and self._transfer.get("status") == "completed"
        )
        expected_dilution = _expected_sample_dilution(self._state_required())
        context = VerificationContext(
            required_sample_ids=("SAMPLE-A",),
            measurements=measurements,
            reports=(report,),
            submitted_at_s=self._state_required().clock_s,
            expected_plate_by_sample={
                "SAMPLE-A": (job["plate_id"], job["plate_revision"])
            },
            expected_dilution_by_sample={"SAMPLE-A": expected_dilution},
            preparation_compliance_by_sample={
                "SAMPLE-A": _assay_preparation_compliant(self._state_required())
            },
            operator_transfer_confirmed=transfer_confirmed,
            transferred_plate_ids=(self._reader_plate_id,)
            if transfer_confirmed
            else (),
            resource_usage={
                "assay_plates": 1,
                "logical_time_s": self._state_required().clock_s,
                "plate_transfers": 1 if transfer_confirmed else 0,
            },
            resource_limits={
                "assay_plates": MAX_ASSAY_PLATES,
                "logical_time_s": MAX_LOGICAL_TIME_S,
                "plate_transfers": MAX_PLATE_TRANSFERS,
            },
            uncertain_native_operation=invalidations,
            usable_result_feasible=self._scenario_required().usable_result_feasible,
        )
        outcome = verify_experiment(context)
        reference_analysis = _reference_analysis(
            measurements=measurements,
            sample_ids=sample_ids,
            blank_ids=blank_ids,
            dilution_factor=report.dilution_factor,
        )
        self._report = {
            "sample_id": "SAMPLE-A",
            "submitted": _sample_report_dict(report),
            "reference_analysis": reference_analysis,
            "accepted": outcome.passed,
            "verification": outcome.to_dict(),
            "submitted_at_s": self._state_required().clock_s,
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
                "stock_metadata": {
                    "SAMPLE-A-stock": {"activity": "coded_unknown"},
                    "substrate-stock": {
                        "substrate_concentration_mM": SUBSTRATE_STOCK_CONCENTRATION_MM
                    },
                    "assay-buffer": {"role": "enzyme-free diluent"},
                    "REF-AP-stock": {"role": "coded reference control"},
                },
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

    def _cached(
        self, operation: str, arguments: dict[str, Any]
    ) -> dict[str, Any] | None:
        action_id = _string(arguments.get("action_id"), "action_id")
        digest = _request_digest(operation, arguments)
        existing = self._ledger.get(action_id)
        if existing is None:
            return None
        if existing[0] != digest:
            raise ValueError("action_id was already used with a different request")
        return deepcopy(existing[1])

    def _remember(
        self, operation: str, arguments: dict[str, Any], body: dict[str, Any]
    ) -> None:
        action_id = _string(arguments["action_id"], "action_id")
        self._ledger[action_id] = (
            _request_digest(operation, arguments),
            deepcopy(body),
        )

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

    def _scenario_required(self) -> ScenarioDefinition:
        if self._scenario is None:
            raise RuntimeError("episode is not initialized")
        return self._scenario

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
        raise ValueError(
            f"request fields invalid; missing={sorted(missing)}, unknown={sorted(unknown)}"
        )


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


def _optional_finite(value: Any, name: str) -> float | None:
    return None if value is None else _finite(value, name)


def _optional_non_negative(value: Any, name: str) -> float | None:
    result = _optional_finite(value, name)
    if result is not None and result < 0:
        raise ValueError(f"{name} must be non-negative")
    return result


def _optional_string(value: Any, name: str) -> str | None:
    return None if value is None else _string(value, name)


def _optional_window(value: Any, name: str) -> tuple[float, float] | None:
    if value is None:
        return None
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{name} must be null or a two-number array")
    start = _finite(value[0], f"{name}[0]")
    end = _finite(value[1], f"{name}[1]")
    if end < start:
        raise ValueError(f"{name} end must not precede start")
    return start, end


def _sample_for_well(well: str) -> str:
    try:
        return {"A1": "SAMPLE-A", "A2": "BLANK", "A3": "REF-AP"}[well]
    except KeyError as exc:
        raise ValueError(
            f"reader well {well!r} has no declared sample identity"
        ) from exc


def _reference_analysis(
    *,
    measurements: Mapping[str, MeasurementEvidence],
    sample_ids: tuple[str, ...],
    blank_ids: tuple[str, ...],
    dilution_factor: float,
) -> dict[str, Any] | None:
    def observed(ids: tuple[str, ...]) -> tuple[ObservedReading, ...] | None:
        result: list[ObservedReading] = []
        for measurement_id in ids:
            item = measurements.get(measurement_id)
            if item is None or item.status != "acquired" or item.absorbance is None:
                return None
            result.append(
                ObservedReading(
                    measurement_id=item.measurement_id,
                    well=item.well,
                    acquired_at_s=item.acquired_at_s,
                    absorbance=item.absorbance,
                    plate_id=item.plate_id,
                    plate_revision=item.plate_revision,
                    settings_digest=item.settings_digest,
                )
            )
        return tuple(result)

    sample = observed(sample_ids)
    blank = observed(blank_ids)
    if sample is None or blank is None:
        return None
    return fit_blank_corrected_rate(
        sample_readings=sample,
        blank_readings=blank,
        dilution_factor=dilution_factor,
        rules=ANALYSIS_RULES,
    ).to_dict()


def _sample_report_dict(report: SampleReport) -> dict[str, Any]:
    return {
        "sample_id": report.sample_id,
        "disposition": report.disposition,
        "sample_measurement_ids": list(report.sample_measurement_ids),
        "blank_measurement_ids": list(report.blank_measurement_ids),
        "reference_measurement_ids": list(report.reference_measurement_ids),
        "fit_window_s": (
            None if report.fit_window_s is None else list(report.fit_window_s)
        ),
        "dilution_factor": report.dilution_factor,
        "estimated_rate": report.estimated_rate,
        "uncertainty": report.uncertainty,
        "units": report.units,
        "unresolved_reason_code": report.unresolved_reason_code,
        "evidence_refs": list(report.evidence_refs),
    }


def _expected_sample_dilution(state: ExperimentState) -> float:
    mixture = state.wells.get("reader:A1")
    if mixture is None or mixture.volume_ul <= 0:
        return float("nan")
    supplied_fraction = (
        mixture.lineage_ul.get("SAMPLE-A-stock", 0.0) / mixture.volume_ul
    )
    if supplied_fraction <= 0:
        return float("nan")
    return UNDILUTED_SAMPLE_FRACTION / supplied_fraction


def _assay_preparation_compliant(state: ExperimentState) -> bool:
    expected = {
        "reader:A1": (
            "SAMPLE-A-stock",
            {"SAMPLE-A-stock", "substrate-stock", "assay-buffer"},
        ),
        "reader:A2": ("assay-buffer", {"substrate-stock", "assay-buffer"}),
        "reader:A3": (
            "REF-AP-stock",
            {"REF-AP-stock", "substrate-stock", "assay-buffer"},
        ),
    }
    for address, (required_source, allowed_sources) in expected.items():
        mixture = state.wells.get(address)
        if mixture is None:
            return False
        if (
            not READER_PROFILE.reaction_volume_min_ul
            <= mixture.volume_ul
            <= READER_PROFILE.reaction_volume_max_ul
        ):
            return False
        if required_source not in mixture.lineage_ul:
            return False
        if not set(mixture.lineage_ul) <= allowed_sources:
            return False
        initial_substrate_mM = (
            mixture.substrate_nmol + mixture.product_nmol
        ) / mixture.volume_ul
        if not abs(initial_substrate_mM - FINAL_SUBSTRATE_CONCENTRATION_MM) <= 1e-12:
            return False
    blank = state.wells["reader:A2"]
    if blank.enzyme_nmol != 0:
        return False
    return _expected_sample_dilution(state) >= 1.0


def _native_well(value: Any) -> str:
    result = _string(value, "well")
    if len(result.split(":")) != 2 or result.split(":")[0] not in {"1", "3"}:
        raise ValueError("well must use '<slot>:<well>' for slot 1 or 3")
    return result


def _reader_well(value: Any) -> str:
    result = _string(value, "reader well")
    if result not in {"A1", "A2", "A3"}:
        raise ValueError("the integration slice admits reader wells A1, A2, and A3")
    return result


def _string_list(
    value: Any, name: str, *, allow_empty: bool = False
) -> tuple[str, ...]:
    if not isinstance(value, list) or (not value and not allow_empty):
        qualifier = "an array" if allow_empty else "a non-empty array"
        raise ValueError(f"{name} must be {qualifier}")
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
