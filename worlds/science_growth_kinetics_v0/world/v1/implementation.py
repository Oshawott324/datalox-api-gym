from __future__ import annotations

import json
import math
import re
from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any, Mapping

from datalox_gated_runtime.models import CallRequest, TaskBrief
from datalox_gated_runtime.world_backend import WorldResponse
from datalox_gated_runtime.world_v1.contracts import ActorContext, WorldImplementationV1
from datalox_gated_runtime.world_v1.session import ScheduledWorldEvent, WorldSession

from .contract import DEFAULT_ROLE, TOOLS_BY_ID, WORLD_ID
from .dynamics import growth_series
from .provider_pylabrobot import (
    PyLabRobotBridgeError,
    run_incubator_load,
    run_incubator_release,
    run_ot2_transfer,
    run_plate_reader_absorbance,
)
from .verifier import GrowthVerifierResult, verify_growth

_EXPERIMENT_PATH = re.compile(r"^/api/v2/experiments/([1-9][0-9]*)$")
_RUN_PATH = re.compile(r"^/pylabrobot/plate-reader/runs/(run-[0-9]{3})$")
_STATIC_ROUTES = {
    ("POST", "/api/v2/experiments"): "elabftw.create_experiment",
    ("GET", "/pylabrobot/ot2/deck"): "pylabrobot.inspect_deck",
    ("POST", "/pylabrobot/ot2/transfers"): "pylabrobot.transfer",
    ("POST", "/pylabrobot/incubator/load"): "pylabrobot.incubator_load",
    ("GET", "/pylabrobot/incubator/status"): "pylabrobot.incubator_status",
    ("POST", "/pylabrobot/incubator/release"): "pylabrobot.incubator_release",
    ("POST", "/pylabrobot/plate-reader/runs"): "pylabrobot.start_kinetic_read",
    ("POST", "/datalox/clock/advance"): "clock.advance",
}


class GrowthWorldError(RuntimeError):
    def __init__(self, code: str, message: str, *, details: Mapping[str, Any]) -> None:
        super().__init__(message)
        self.code = code
        self.details = dict(details)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": str(self),
            "details": dict(self.details),
        }


class ScienceGrowthKineticsWorld(WorldImplementationV1):
    def initialize_episode(
        self,
        *,
        session: WorldSession,
        episode: Mapping[str, Any],
    ) -> None:
        state = episode.get("state")
        metadata = episode.get("metadata")
        if not isinstance(state, dict) or not isinstance(metadata, dict):
            raise ValueError("growth episode requires state and metadata objects")
        session.reset(
            episode_id=str(episode["id"]),
            initial_state=deepcopy(state),
            initial_time=str(metadata["clock"]),
        )
        faults = state["faults"]
        if faults.get("protocol_revision_bump_after_seconds") is not None:
            deliver_at = datetime.fromisoformat(session.current_time()) + timedelta(
                seconds=int(faults["protocol_revision_bump_after_seconds"])
            )
            with session.transaction(operation_id="growth.schedule_protocol_revision"):
                session.schedule_event(
                    event_id=f"protocol-revision:{episode['id']}",
                    deliver_at=deliver_at,
                    kind="protocol_revision_bump",
                    payload={"next_revision": int(state["protocol"]["revision"]) + 1},
                )

    def tool_for_request(self, request: CallRequest) -> str | None:
        method = request.normalized_method()
        static = _STATIC_ROUTES.get((method, request.path))
        if static is not None:
            return static
        if _EXPERIMENT_PATH.fullmatch(request.path):
            if method == "GET":
                return "elabftw.get_experiment"
            if method == "PATCH":
                return "elabftw.patch_experiment"
        if method == "GET" and _RUN_PATH.fullmatch(request.path):
            return "pylabrobot.get_kinetic_read"
        return None

    def handle(
        self,
        request: CallRequest,
        *,
        actor: ActorContext,
        session: WorldSession,
    ) -> WorldResponse | None:
        tool_id = self.tool_for_request(request)
        if tool_id is None:
            return self._response(
                404,
                {"error": {"code": "growth_route_not_declared", "message": "Route is not declared."}},
                operation_id=request.operation_id,
                reason_code="growth_route_not_declared",
                decision_kind="deny",
            )
        arguments: dict[str, Any] = {}
        try:
            arguments = self._arguments_for_request(tool_id, request)
            body, status, mutation_scope, provider_evidence = self._execute(
                tool_id=tool_id,
                arguments=arguments,
                actor=actor,
                session=session,
            )
        except (GrowthWorldError, PyLabRobotBridgeError) as error:
            self._record(
                session,
                actor=actor,
                tool_id=tool_id,
                arguments=arguments,
                decision="deny",
                mutation_scope=(),
                reason_code=error.code,
            )
            return self._response(
                409,
                {"error": error.to_dict()},
                operation_id=tool_id,
                reason_code=error.code,
                decision_kind="deny",
            )
        self._record(
            session,
            actor=actor,
            tool_id=tool_id,
            arguments=arguments,
            decision="shadow_write" if mutation_scope else "replay",
            mutation_scope=mutation_scope,
            reason_code="growth_operation_completed",
            provider_evidence=provider_evidence,
        )
        return self._response(
            status,
            body,
            operation_id=tool_id,
            reason_code="growth_operation_completed",
            is_mutation=bool(mutation_scope),
        )

    def tool_schemas(self, *, actor: ActorContext) -> dict[str, dict[str, Any]]:
        if actor.role != DEFAULT_ROLE:
            return {}
        return {
            tool_id: {
                "description": tool["description"],
                "inputSchema": deepcopy(tool["input_schema"]),
            }
            for tool_id, tool in TOOLS_BY_ID.items()
        }

    def request_for_tool(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        *,
        actor: ActorContext,
    ) -> CallRequest:
        if tool_name not in TOOLS_BY_ID:
            raise ValueError(f"unknown growth tool: {tool_name}")
        values = dict(arguments)
        _validate_arguments(tool_name, values)
        headers = {
            "x-datalox-actor-id": actor.actor_id,
            "x-datalox-actor-role": actor.role,
        }
        if tool_name == "elabftw.get_experiment":
            return CallRequest(
                method="GET",
                path=f"/api/v2/experiments/{values['experiment_id']}",
                headers=headers,
                operation_id=tool_name,
            )
        if tool_name == "elabftw.create_experiment":
            return CallRequest(
                method="POST",
                path="/api/v2/experiments",
                body={},
                headers=headers,
                operation_id=tool_name,
            )
        if tool_name == "elabftw.patch_experiment":
            experiment_id = values.pop("experiment_id")
            return CallRequest(
                method="PATCH",
                path=f"/api/v2/experiments/{experiment_id}",
                body=values,
                headers=headers,
                operation_id=tool_name,
            )
        if tool_name == "pylabrobot.inspect_deck":
            return CallRequest(
                method="GET",
                path="/pylabrobot/ot2/deck",
                headers=headers,
                operation_id=tool_name,
            )
        if tool_name == "pylabrobot.transfer":
            path = "/pylabrobot/ot2/transfers"
        elif tool_name == "pylabrobot.incubator_load":
            path = "/pylabrobot/incubator/load"
        elif tool_name == "pylabrobot.incubator_status":
            return CallRequest(
                method="GET",
                path="/pylabrobot/incubator/status",
                headers=headers,
                operation_id=tool_name,
            )
        elif tool_name == "pylabrobot.incubator_release":
            path = "/pylabrobot/incubator/release"
        elif tool_name == "pylabrobot.start_kinetic_read":
            path = "/pylabrobot/plate-reader/runs"
        elif tool_name == "pylabrobot.get_kinetic_read":
            return CallRequest(
                method="GET",
                path=f"/pylabrobot/plate-reader/runs/{values['job_id']}",
                headers=headers,
                operation_id=tool_name,
            )
        elif tool_name == "clock.advance":
            path = "/datalox/clock/advance"
        else:  # pragma: no cover - guarded by TOOLS_BY_ID
            raise AssertionError(tool_name)
        return CallRequest(
            method="POST",
            path=path,
            body=values,
            headers=headers,
            operation_id=tool_name,
        )

    def operation_for_tool(self, tool_name: str) -> str | None:
        return tool_name if tool_name in TOOLS_BY_ID else None

    def verify(
        self,
        *,
        session: WorldSession,
        episode: Mapping[str, Any],
    ) -> GrowthVerifierResult:
        del episode
        return verify_growth(session)

    def task(self, *, episode: Mapping[str, Any]) -> TaskBrief:
        task = episode["task"]
        return TaskBrief(
            task_id=str(task["task_id"]),
            title=str(task["title"]),
            instructions=str(task["instructions"]),
            success_criteria=list(task["success_criteria"]),
        )

    def _execute(
        self,
        *,
        tool_id: str,
        arguments: dict[str, Any],
        actor: ActorContext,
        session: WorldSession,
    ) -> tuple[Any, int, tuple[str, ...], dict[str, Any] | None]:
        del actor
        _validate_arguments(tool_id, arguments)
        if tool_id == "elabftw.get_experiment":
            return self._get_experiment(session, int(arguments["experiment_id"]))
        if tool_id == "elabftw.create_experiment":
            return self._create_experiment(session)
        if tool_id == "elabftw.patch_experiment":
            return self._patch_experiment(session, arguments)
        if tool_id == "pylabrobot.inspect_deck":
            deck = session.get_state("deck")
            protocol = session.get_state("protocol")
            return (
                {
                    **deepcopy(deck),
                    "transfer_plan": deepcopy(protocol["transfer_plan"]),
                },
                200,
                (),
                None,
            )
        if tool_id == "pylabrobot.transfer":
            return self._transfer(session, arguments)
        if tool_id == "pylabrobot.incubator_load":
            return self._incubator_load(session, arguments)
        if tool_id == "pylabrobot.incubator_status":
            return self._incubator_status(session)
        if tool_id == "pylabrobot.incubator_release":
            return self._incubator_release(session, arguments)
        if tool_id == "pylabrobot.start_kinetic_read":
            return self._start_kinetic_read(session, arguments)
        if tool_id == "pylabrobot.get_kinetic_read":
            return self._get_kinetic_read(session, str(arguments["job_id"]))
        if tool_id == "clock.advance":
            return self._advance_clock(session, int(arguments["seconds"]))
        raise AssertionError(tool_id)

    @staticmethod
    def _get_experiment(
        session: WorldSession,
        experiment_id: int,
    ) -> tuple[Any, int, tuple[str, ...], None]:
        elabftw = session.get_state("elabftw")
        protocol = session.get_state("protocol")
        if experiment_id == elabftw["protocol_experiment_id"]:
            body = {
                "id": experiment_id,
                "title": "Yeast growth kinetics protocol",
                "body": "Prepare the declared plate, precondition it, run OD600 kinetics, and record QC.",
                "metadata": deepcopy(protocol),
            }
            return body, 200, (), None
        record = elabftw["result_records"].get(str(experiment_id))
        if record is None:
            raise GrowthWorldError(
                "ELABFTW_EXPERIMENT_NOT_FOUND",
                "Experiment does not exist.",
                details={"experiment_id": experiment_id},
            )
        return deepcopy(record["response"]), 200, (), None

    @staticmethod
    def _create_experiment(
        session: WorldSession,
    ) -> tuple[Any, int, tuple[str, ...], None]:
        elabftw = session.get_state("elabftw")
        experiment_id = int(elabftw["next_result_id"])
        elabftw["next_result_id"] = experiment_id + 1
        elabftw["result_records"][str(experiment_id)] = {
            "phase": "awaiting_patch",
            "metadata": {},
            "response": {
                "id": experiment_id,
                "title": "",
                "body": "",
                "metadata": {},
            },
        }
        session.set_state("elabftw", elabftw)
        return (
            {
                "id": experiment_id,
                "location": f"/api/v2/experiments/{experiment_id}",
            },
            201,
            ("state:elabftw",),
            None,
        )

    @staticmethod
    def _patch_experiment(
        session: WorldSession,
        arguments: Mapping[str, Any],
    ) -> tuple[Any, int, tuple[str, ...], None]:
        elabftw = session.get_state("elabftw")
        experiment_id = int(arguments["experiment_id"])
        record = elabftw["result_records"].get(str(experiment_id))
        if record is None:
            raise GrowthWorldError(
                "ELABFTW_EXPERIMENT_NOT_FOUND",
                "Experiment does not exist.",
                details={"experiment_id": experiment_id},
            )
        if record["phase"] != "awaiting_patch":
            raise GrowthWorldError(
                "ELABFTW_SEQUENCE_VIOLATION",
                "The result experiment has already been patched.",
                details={"experiment_id": experiment_id, "phase": record["phase"]},
            )
        try:
            metadata = json.loads(str(arguments["metadata"]))
        except json.JSONDecodeError as error:
            raise GrowthWorldError(
                "ELABFTW_INVALID_METADATA_JSON",
                "metadata must be a valid JSON string.",
                details={"line": error.lineno, "column": error.colno},
            ) from error
        if not isinstance(metadata, dict):
            raise GrowthWorldError(
                "ELABFTW_INVALID_METADATA_SHAPE",
                "metadata must decode to an object.",
                details={"type": type(metadata).__name__},
            )
        record["phase"] = "patched"
        record["metadata"] = deepcopy(metadata)
        record["response"] = {
            "id": experiment_id,
            "title": str(arguments["title"]),
            "body": str(arguments["body"]),
            "metadata": deepcopy(metadata),
        }
        elabftw["result_records"][str(experiment_id)] = record
        session.set_state("elabftw", elabftw)
        facts = session.get_state("facts")
        facts["decision_record_id"] = experiment_id
        session.set_state("facts", facts)
        return (
            deepcopy(record["response"]),
            200,
            ("state:elabftw", "state:facts"),
            None,
        )

    @staticmethod
    def _transfer(
        session: WorldSession,
        arguments: Mapping[str, Any],
    ) -> tuple[Any, int, tuple[str, ...], dict[str, Any]]:
        deck = session.get_state("deck")
        protocol = session.get_state("protocol")
        source_well = str(arguments["source_well"])
        target_well = str(arguments["target_well"])
        tip_spot = str(arguments["tip_spot"])
        volume_ul = float(arguments["volume_ul"])
        known_sources = {
            row["source_well"] for row in protocol["transfer_plan"]
        } | {
            backup
            for row in protocol["transfer_plan"]
            for backup in row["backup_source_wells"]
        }
        if source_well not in known_sources or target_well not in protocol["expected_wells"]:
            raise GrowthWorldError(
                "GROWTH_TRANSFER_RESOURCE_UNKNOWN",
                "Transfer references a resource outside the protocol.",
                details={"source_well": source_well, "target_well": target_well},
            )
        provider = run_ot2_transfer(
            source_volumes_ul=deck["source_volumes_ul"],
            target_volumes_ul=deck["target_volumes_ul"],
            tip_availability=deck["tip_availability"],
            source_well=source_well,
            target_well=target_well,
            tip_spot=tip_spot,
            volume_ul=volume_ul,
        )
        deck["source_volumes_ul"][source_well] = provider["source_volume_ul"]
        deck["target_volumes_ul"][target_well] = provider["target_volume_ul"]
        deck["tip_availability"][tip_spot] = False
        session.set_state("deck", deck)
        facts = session.get_state("facts")
        facts["used_tips"].append(tip_spot)
        facts["transfer_lineage"][target_well] = {
            "source_well": source_well,
            "volume_ul": volume_ul,
        }
        facts["prep_complete"] = all(
            math.isclose(float(deck["target_volumes_ul"].get(well, 0)), 200.0)
            for well in protocol["expected_wells"]
        )
        facts["provider_execution_counts"]["ot2"] += 1
        session.set_state("facts", facts)
        return (
            {
                "transfer": {
                    "source_well": source_well,
                    "target_well": target_well,
                    "tip_spot": tip_spot,
                    "volume_ul": volume_ul,
                },
                "provider_execution": provider,
            },
            200,
            ("state:deck", "state:facts"),
            provider,
        )

    @staticmethod
    def _incubator_load(
        session: WorldSession,
        arguments: Mapping[str, Any],
    ) -> tuple[Any, int, tuple[str, ...], dict[str, Any]]:
        protocol = session.get_state("protocol")
        facts = session.get_state("facts")
        if not facts["prep_complete"]:
            raise GrowthWorldError(
                "GROWTH_PLATE_PREP_INCOMPLETE",
                "All protocol wells must be prepared before incubation.",
                details={"expected_wells": protocol["expected_wells"]},
            )
        _require_equal("plate_barcode", arguments["plate_barcode"], protocol["plate_barcode"])
        _require_equal("temperature_c", float(arguments["temperature_c"]), protocol["temperature_c"])
        provider = run_incubator_load(
            plate_name=str(arguments["plate_barcode"]),
            temperature_c=float(arguments["temperature_c"]),
            shaking_hz=float(arguments["shaking_hz"]),
        )
        incubator = session.get_state("incubator")
        now = datetime.fromisoformat(session.current_time())
        incubator.update(
            {
                "plate_barcode": protocol["plate_barcode"],
                "location": "incubator",
                "loaded_at": now.isoformat(),
                "temperature_c": float(arguments["temperature_c"]),
                "shaking_hz": float(arguments["shaking_hz"]),
                "stabilization_ready_at": (
                    now + timedelta(seconds=int(protocol["stabilization_seconds"]))
                ).isoformat(),
                "stabilized": False,
                "released_at": None,
            }
        )
        session.set_state("incubator", incubator)
        facts["provider_execution_counts"]["incubator"] += 1
        session.set_state("facts", facts)
        return (
            {"incubator": deepcopy(incubator), "provider_execution": provider},
            200,
            ("state:incubator", "state:facts"),
            provider,
        )

    @staticmethod
    def _incubator_status(
        session: WorldSession,
    ) -> tuple[Any, int, tuple[str, ...], None]:
        incubator = session.get_state("incubator")
        ready_at = incubator.get("stabilization_ready_at")
        if ready_at is not None and datetime.fromisoformat(session.current_time()) >= datetime.fromisoformat(ready_at):
            if not incubator["stabilized"]:
                incubator["stabilized"] = True
                session.set_state("incubator", incubator)
                return deepcopy(incubator), 200, ("state:incubator",), None
        return deepcopy(incubator), 200, (), None

    @staticmethod
    def _incubator_release(
        session: WorldSession,
        arguments: Mapping[str, Any],
    ) -> tuple[Any, int, tuple[str, ...], dict[str, Any]]:
        protocol = session.get_state("protocol")
        incubator = session.get_state("incubator")
        _require_equal("plate_barcode", arguments["plate_barcode"], protocol["plate_barcode"])
        ready_at = incubator.get("stabilization_ready_at")
        if (
            incubator.get("location") != "incubator"
            or ready_at is None
            or datetime.fromisoformat(session.current_time()) < datetime.fromisoformat(ready_at)
        ):
            raise GrowthWorldError(
                "GROWTH_INCUBATION_NOT_STABILIZED",
                "The plate cannot be released before the stabilization interval.",
                details={"ready_at": ready_at, "current_time": session.current_time()},
            )
        provider = run_incubator_release(plate_name=protocol["plate_barcode"])
        incubator["stabilized"] = True
        incubator["location"] = "reader_loading"
        incubator["released_at"] = session.current_time()
        session.set_state("incubator", incubator)
        facts = session.get_state("facts")
        facts["provider_execution_counts"]["incubator"] += 1
        session.set_state("facts", facts)
        return (
            {"incubator": deepcopy(incubator), "provider_execution": provider},
            200,
            ("state:incubator", "state:facts"),
            provider,
        )

    @staticmethod
    def _start_kinetic_read(
        session: WorldSession,
        arguments: Mapping[str, Any],
    ) -> tuple[Any, int, tuple[str, ...], dict[str, Any]]:
        protocol = session.get_state("protocol")
        incubator = session.get_state("incubator")
        reader = session.get_state("reader")
        _require_equal("plate_barcode", arguments["plate_barcode"], protocol["plate_barcode"])
        _require_equal("protocol_revision", arguments["protocol_revision"], protocol["revision"])
        _require_equal("wavelength_nm", arguments["wavelength_nm"], protocol["wavelength_nm"])
        _require_equal("interval_seconds", arguments["interval_seconds"], protocol["interval_seconds"])
        _require_equal("duration_seconds", arguments["duration_seconds"], protocol["duration_seconds"])
        if list(arguments["wells"]) != protocol["expected_wells"]:
            raise GrowthWorldError(
                "GROWTH_WELL_SET_MISMATCH",
                "Kinetic read wells must exactly match the current protocol order.",
                details={"expected": protocol["expected_wells"], "received": arguments["wells"]},
            )
        if incubator.get("location") not in {"reader_loading", "reader"}:
            raise GrowthWorldError(
                "GROWTH_PLATE_NOT_AT_READER",
                "The stabilized plate has not been released to the reader.",
                details={"location": incubator.get("location")},
            )
        now = datetime.fromisoformat(session.current_time())
        busy_until = reader.get("busy_until")
        if busy_until is not None and now < datetime.fromisoformat(busy_until):
            raise GrowthWorldError(
                "GROWTH_READER_BUSY",
                "The reader is occupied; wait or reschedule.",
                details={"available_at": busy_until, "current_time": session.current_time()},
            )
        if reader.get("active_job_id") is not None:
            raise GrowthWorldError(
                "GROWTH_READER_JOB_OVERLAP",
                "A kinetic job is already active.",
                details={"active_job_id": reader["active_job_id"]},
            )
        provider = run_plate_reader_absorbance(
            plate_name=protocol["plate_barcode"],
            wells=tuple(protocol["expected_wells"]),
            wavelength_nm=int(protocol["wavelength_nm"]),
        )
        job_id = f"run-{int(reader['next_job_number']):03d}"
        reader["next_job_number"] += 1
        deliver_at = now + timedelta(seconds=int(protocol["duration_seconds"]))
        partial = bool(
            session.get_state("faults").get("partial_first_run")
            and not reader["jobs"]
        )
        reader["jobs"][job_id] = {
            "job_id": job_id,
            "status": "pending",
            "complete": False,
            "partial": partial,
            "plate_barcode": protocol["plate_barcode"],
            "protocol_revision": protocol["revision"],
            "wavelength_nm": protocol["wavelength_nm"],
            "interval_seconds": protocol["interval_seconds"],
            "duration_seconds": protocol["duration_seconds"],
            "expected_wells": deepcopy(protocol["expected_wells"]),
            "observation_count": 0,
            "series": {},
            "started_at": session.current_time(),
            "completed_at": None,
            "provider_execution": provider,
        }
        reader["active_job_id"] = job_id
        reader["busy_until"] = deliver_at.isoformat()
        session.set_state("reader", reader)
        incubator["location"] = "reader"
        session.set_state("incubator", incubator)
        session.schedule_event(
            event_id=f"kinetic-complete:{session.episode_id}:{job_id}",
            deliver_at=deliver_at,
            kind="kinetic_run_complete",
            payload={"job_id": job_id},
        )
        facts = session.get_state("facts")
        facts["provider_execution_counts"]["plate_reader"] += 1
        session.set_state("facts", facts)
        return (
            {
                "job_id": job_id,
                "status": "pending",
                "complete_at": deliver_at.isoformat(),
                "provider_execution": provider,
            },
            202,
            (
                "state:reader",
                "state:incubator",
                "state:facts",
                f"scheduled_event:kinetic-complete:{session.episode_id}:{job_id}",
            ),
            provider,
        )

    @staticmethod
    def _get_kinetic_read(
        session: WorldSession,
        job_id: str,
    ) -> tuple[Any, int, tuple[str, ...], None]:
        reader = session.get_state("reader")
        job = reader["jobs"].get(job_id)
        if job is None:
            raise GrowthWorldError(
                "GROWTH_READER_JOB_NOT_FOUND",
                "Kinetic job does not exist.",
                details={"job_id": job_id},
            )
        return deepcopy(job), 200, (), None

    @staticmethod
    def _advance_clock(
        session: WorldSession,
        seconds: int,
    ) -> tuple[Any, int, tuple[str, ...], None]:
        delivered = session.advance_clock_by(
            timedelta(seconds=seconds),
            handler=ScienceGrowthKineticsWorld._deliver_event,
        )
        return (
            {
                "current_time": session.current_time(),
                "delivered_events": [
                    {"id": event.id, "kind": event.kind} for event in delivered
                ],
            },
            200,
            ("clock", *(f"scheduled_event:{event.id}" for event in delivered)),
            None,
        )

    @staticmethod
    def _deliver_event(session: WorldSession, event: ScheduledWorldEvent) -> None:
        if event.kind == "protocol_revision_bump":
            protocol = session.get_state("protocol")
            protocol["revision"] = int(event.payload["next_revision"])
            protocol["read_method_note"] = (
                f"Revision {protocol['revision']} confirms the same OD600 contract."
            )
            session.set_state("protocol", protocol)
            session.append_event(
                "growth_protocol_revised",
                {"revision": protocol["revision"], "scheduled_event_id": event.id},
            )
            return
        if event.kind != "kinetic_run_complete":
            raise GrowthWorldError(
                "GROWTH_EVENT_KIND_UNKNOWN",
                "Scheduled event kind is not supported.",
                details={"kind": event.kind},
            )
        reader = session.get_state("reader")
        job_id = str(event.payload["job_id"])
        job = reader["jobs"][job_id]
        wells = list(job["expected_wells"])
        if job["partial"]:
            wells = wells[:-1]
        job["series"] = growth_series(
            wells=wells,
            seed=int(session.get_state("facts")["seed"]),
            interval_seconds=int(job["interval_seconds"]),
            duration_seconds=int(job["duration_seconds"]),
        )
        job["observation_count"] = (
            int(job["duration_seconds"]) // int(job["interval_seconds"]) + 1
        )
        job["complete"] = not job["partial"]
        job["status"] = "complete" if job["complete"] else "partial"
        job["completed_at"] = session.current_time()
        reader["jobs"][job_id] = job
        reader["active_job_id"] = None
        reader["busy_until"] = None
        session.set_state("reader", reader)
        if job["complete"]:
            facts = session.get_state("facts")
            facts["current_complete_job_id"] = job_id
            session.set_state("facts", facts)
        session.append_event(
            "growth_kinetic_completed",
            {
                "job_id": job_id,
                "complete": job["complete"],
                "protocol_revision": job["protocol_revision"],
                "scheduled_event_id": event.id,
            },
        )

    @staticmethod
    def _arguments_for_request(tool_id: str, request: CallRequest) -> dict[str, Any]:
        experiment = _EXPERIMENT_PATH.fullmatch(request.path)
        if tool_id == "elabftw.get_experiment":
            return {"experiment_id": int(experiment.group(1))}
        if tool_id == "elabftw.create_experiment":
            if request.body != {}:
                raise GrowthWorldError(
                    "ELABFTW_INVALID_CREATE_PAYLOAD",
                    "Experiment creation requires an empty JSON object.",
                    details={"body": request.body},
                )
            return {}
        if tool_id == "elabftw.patch_experiment":
            body = _body(request)
            return {"experiment_id": int(experiment.group(1)), **body}
        if tool_id in {"pylabrobot.inspect_deck", "pylabrobot.incubator_status"}:
            return {}
        if tool_id == "pylabrobot.get_kinetic_read":
            matched = _RUN_PATH.fullmatch(request.path)
            return {"job_id": matched.group(1)}
        return _body(request)

    @staticmethod
    def _record(
        session: WorldSession,
        *,
        actor: ActorContext,
        tool_id: str,
        arguments: Mapping[str, Any],
        decision: str,
        mutation_scope: tuple[str, ...],
        reason_code: str,
        provider_evidence: Mapping[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "operation_id": tool_id,
            "tool_name": tool_id,
            "actor_id": actor.actor_id,
            "actor_role": actor.role,
            "decision": decision,
            "request": deepcopy(dict(arguments)),
            "mutation_scope": list(mutation_scope),
            "reason_code": reason_code,
        }
        if provider_evidence is not None:
            payload["provider_execution"] = {
                "grounding_level": provider_evidence["grounding_level"],
                "provider": deepcopy(provider_evidence["provider"]),
                "executed_methods": deepcopy(provider_evidence["executed_methods"]),
            }
        session.append_event("growth_operation", payload)

    @staticmethod
    def _response(
        status: int,
        body: Any,
        *,
        operation_id: str | None,
        reason_code: str,
        is_mutation: bool = False,
        decision_kind: str | None = None,
    ) -> WorldResponse:
        return WorldResponse(
            status_code=status,
            body=body,
            is_mutation=is_mutation,
            world_id=WORLD_ID,
            operation_id=operation_id,
            decision_kind=decision_kind or ("shadow_write" if is_mutation else "replay"),
            reason_code=reason_code,
            message=reason_code,
        )


def _body(request: CallRequest) -> dict[str, Any]:
    if not isinstance(request.body, dict):
        raise GrowthWorldError(
            "GROWTH_REQUEST_BODY_INVALID",
            "Request body must be a JSON object.",
            details={"received_type": type(request.body).__name__},
        )
    return deepcopy(request.body)


def _require_equal(field: str, received: Any, expected: Any) -> None:
    if received != expected:
        raise GrowthWorldError(
            f"GROWTH_{field.upper()}_MISMATCH",
            f"{field} does not match the current protocol.",
            details={"expected": expected, "received": received},
        )


def _validate_arguments(tool_id: str, arguments: Mapping[str, Any]) -> None:
    schema = TOOLS_BY_ID[tool_id]["input_schema"]
    required = set(schema.get("required", []))
    properties = schema["properties"]
    if set(arguments) - set(properties) or not required.issubset(arguments):
        raise GrowthWorldError(
            "GROWTH_ARGUMENTS_INVALID",
            "Tool arguments do not match the declared fields.",
            details={
                "required": sorted(required),
                "allowed": sorted(properties),
                "received": sorted(arguments),
            },
        )
    for name, value in arguments.items():
        expected = properties[name]
        value_type = expected.get("type")
        if value_type == "string" and not isinstance(value, str):
            _argument_type_error(name, "string", value)
        if value_type == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
            _argument_type_error(name, "integer", value)
        if value_type == "number" and (
            not isinstance(value, (int, float)) or isinstance(value, bool)
        ):
            _argument_type_error(name, "number", value)
        if value_type == "array" and not isinstance(value, list):
            _argument_type_error(name, "array", value)
        if isinstance(value, str):
            if len(value) < int(expected.get("minLength", 0)):
                _argument_value_error(name, value)
            if "pattern" in expected and re.fullmatch(expected["pattern"], value) is None:
                _argument_value_error(name, value)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if "minimum" in expected and value < expected["minimum"]:
                _argument_value_error(name, value)
            if "maximum" in expected and value > expected["maximum"]:
                _argument_value_error(name, value)
            if "exclusiveMinimum" in expected and value <= expected["exclusiveMinimum"]:
                _argument_value_error(name, value)
        if isinstance(value, list):
            if len(value) < int(expected.get("minItems", 0)):
                _argument_value_error(name, value)
            if expected.get("uniqueItems") and len(value) != len(set(value)):
                _argument_value_error(name, value)
            if any(not isinstance(item, str) for item in value):
                _argument_type_error(name, "array of strings", value)


def _argument_type_error(name: str, expected: str, value: Any) -> None:
    raise GrowthWorldError(
        "GROWTH_ARGUMENT_TYPE_INVALID",
        f"{name} must be {expected}.",
        details={"field": name, "received_type": type(value).__name__},
    )


def _argument_value_error(name: str, value: Any) -> None:
    raise GrowthWorldError(
        "GROWTH_ARGUMENT_VALUE_INVALID",
        f"{name} is outside the declared contract.",
        details={"field": name, "received": value},
    )


def create_world() -> ScienceGrowthKineticsWorld:
    return ScienceGrowthKineticsWorld()
