from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Mapping

from datalox_gated_runtime.models import CallRequest, TaskBrief
from datalox_gated_runtime.world_backend import WorldResponse
from datalox_gated_runtime.world_v1.contracts import ActorContext, WorldImplementationV1
from datalox_gated_runtime.world_v1.session import ScheduledWorldEvent, WorldSession

from .contract import (
    DEFAULT_ROLE,
    TOOLS_BY_ID,
    WORLD_ID,
)
from .dynamics import workflow_status
from .provider_cromwell import (
    CromwellAnalysisProjectionError,
    canonical_digest,
    classify_program,
    deterministic_workflow_id,
    render_abort_response,
    render_logs,
    render_metadata,
    render_outputs,
    render_status,
    render_submit_response,
    validate_capture_facts as validate_cromwell_facts,
)
from .provider_elabftw import (
    ELabFTWAnalysisProjectionError,
    render_create_response,
    render_experiment,
    validate_capture_facts as validate_elabftw_facts,
    validate_patch_body,
)
from .provider_cromwell_facts import FACTS as _CROMWELL_FACTS
from .provider_elabftw_facts import FACTS as _ELABFTW_FACTS
from .verifier import AnalysisVerifierResult, verify_analysis

validate_elabftw_facts(_ELABFTW_FACTS)
validate_cromwell_facts(_CROMWELL_FACTS)

_EXPERIMENT_PATH = re.compile(r"^/api/v2/experiments/([1-9][0-9]*)$")
_WORKFLOW_PATH = re.compile(
    r"^/api/workflows/v1/"
    r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/"
    r"(status|outputs|logs|metadata|abort)$"
)
_STATIC_ROUTES = {
    ("POST", "/api/v2/experiments"): "elabftw.create_experiment",
    ("POST", "/api/workflows/v1"): "cromwell.submit_workflow",
    ("POST", "/datalox/clock/advance"): "clock.advance",
}
_WORKFLOW_ROUTE_TO_TOOL = {
    ("GET", "status"): "cromwell.get_workflow_status",
    ("GET", "outputs"): "cromwell.get_workflow_outputs",
    ("GET", "logs"): "cromwell.get_workflow_logs",
    ("GET", "metadata"): "cromwell.get_workflow_metadata",
    ("POST", "abort"): "cromwell.abort_workflow",
}


class AnalysisWorldError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: Mapping[str, Any],
        status_code: int = 409,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = dict(details)
        self.status_code = status_code

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": str(self),
            "details": deepcopy(self.details),
        }


@dataclass(frozen=True)
class ExecutionResult:
    body: Any
    status_code: int
    mutation_scope: tuple[str, ...] = ()
    headers: Mapping[str, str] | None = None
    reason_code: str = "analysis_operation_completed"
    workflow_id: str | None = None
    provider_status: str | None = None
    evidence: Mapping[str, Any] | None = None


class ScienceELabFTWCromwellWorld(WorldImplementationV1):
    def initialize_episode(
        self,
        *,
        session: WorldSession,
        episode: Mapping[str, Any],
    ) -> None:
        state = episode.get("state")
        metadata = episode.get("metadata")
        if not isinstance(state, dict) or not isinstance(metadata, dict):
            raise ValueError("analysis episode requires state and metadata objects")
        session.reset(
            episode_id=str(episode["id"]),
            initial_state=deepcopy(state),
            initial_time=str(metadata["clock"]),
        )
        revision_event = metadata.get("revision_event")
        if isinstance(revision_event, dict):
            deliver_at = datetime.fromisoformat(session.current_time()) + timedelta(
                seconds=int(revision_event["after_seconds"])
            )
            with session.transaction(operation_id="analysis.schedule_source_revision"):
                session.schedule_event(
                    event_id=f"source-revision:{episode['id']}",
                    deliver_at=deliver_at,
                    kind="source_revision_change",
                    payload={"revision": int(revision_event["revision"])},
                )

    def tool_for_request(self, request: CallRequest) -> str | None:
        method = request.normalized_method()
        static = _STATIC_ROUTES.get((method, request.path))
        if static is not None:
            return static
        experiment = _EXPERIMENT_PATH.fullmatch(request.path)
        if experiment:
            if method == "GET":
                return "elabftw.get_experiment"
            if method == "PATCH":
                return "elabftw.patch_experiment"
        workflow = _WORKFLOW_PATH.fullmatch(request.path)
        if workflow:
            return _WORKFLOW_ROUTE_TO_TOOL.get((method, workflow.group(2)))
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
                {
                    "error": {
                        "code": "ANALYSIS_ROUTE_NOT_DECLARED",
                        "message": "Route is not declared by this bounded world.",
                    }
                },
                operation_id=request.operation_id,
                reason_code="ANALYSIS_ROUTE_NOT_DECLARED",
                decision_kind="deny",
            )
        arguments: dict[str, Any] = {}
        try:
            arguments = self._arguments_for_request(tool_id, request)
            result = self._execute(
                tool_id=tool_id,
                arguments=arguments,
                session=session,
            )
        except (
            AnalysisWorldError,
            CromwellAnalysisProjectionError,
            ELabFTWAnalysisProjectionError,
        ) as error:
            code = error.code
            details = getattr(error, "details", {})
            status_code = getattr(error, "status_code", 400)
            self._record(
                session,
                actor=actor,
                tool_id=tool_id,
                arguments=arguments,
                decision="deny",
                mutation_scope=(),
                reason_code=code,
                response_status_code=status_code,
                evidence={"error": deepcopy(dict(details))},
            )
            body = (
                error.to_dict()
                if isinstance(error, AnalysisWorldError)
                else {"code": code, "message": str(error), "details": {}}
            )
            return self._response(
                status_code,
                {"error": body},
                operation_id=tool_id,
                reason_code=code,
                decision_kind="deny",
            )

        self._record(
            session,
            actor=actor,
            tool_id=tool_id,
            arguments=arguments,
            decision="shadow_write" if result.mutation_scope else "replay",
            mutation_scope=result.mutation_scope,
            reason_code=result.reason_code,
            response_status_code=result.status_code,
            workflow_id=result.workflow_id,
            provider_status=result.provider_status,
            evidence=result.evidence,
        )
        return self._response(
            result.status_code,
            result.body,
            operation_id=tool_id,
            reason_code=result.reason_code,
            is_mutation=bool(result.mutation_scope),
            headers=result.headers,
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
            raise ValueError(f"unknown analysis tool: {tool_name}")
        values = deepcopy(dict(arguments))
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
        if tool_name == "cromwell.submit_workflow":
            return CallRequest(
                method="POST",
                path="/api/workflows/v1",
                body=values,
                headers=headers,
                operation_id=tool_name,
            )
        if tool_name == "clock.advance":
            return CallRequest(
                method="POST",
                path="/datalox/clock/advance",
                body=values,
                headers=headers,
                operation_id=tool_name,
            )
        workflow_id = values["workflow_id"]
        suffix_by_tool = {
            "cromwell.get_workflow_status": ("GET", "status"),
            "cromwell.get_workflow_outputs": ("GET", "outputs"),
            "cromwell.get_workflow_logs": ("GET", "logs"),
            "cromwell.get_workflow_metadata": ("GET", "metadata"),
            "cromwell.abort_workflow": ("POST", "abort"),
        }
        method, suffix = suffix_by_tool[tool_name]
        return CallRequest(
            method=method,
            path=f"/api/workflows/v1/{workflow_id}/{suffix}",
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
    ) -> AnalysisVerifierResult:
        return verify_analysis(session, episode)

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
        session: WorldSession,
    ) -> ExecutionResult:
        _validate_arguments(tool_id, arguments)
        if tool_id == "elabftw.get_experiment":
            return self._get_experiment(session, int(arguments["experiment_id"]))
        if tool_id == "elabftw.create_experiment":
            return self._create_experiment(session)
        if tool_id == "elabftw.patch_experiment":
            return self._patch_experiment(session, arguments)
        if tool_id == "cromwell.submit_workflow":
            return self._submit_workflow(session, arguments)
        if tool_id == "cromwell.get_workflow_status":
            return self._get_workflow_status(
                session, str(arguments["workflow_id"])
            )
        if tool_id == "cromwell.get_workflow_outputs":
            return self._get_workflow_evidence(
                session,
                str(arguments["workflow_id"]),
                kind="outputs",
            )
        if tool_id == "cromwell.get_workflow_logs":
            return self._get_workflow_evidence(
                session,
                str(arguments["workflow_id"]),
                kind="logs",
            )
        if tool_id == "cromwell.get_workflow_metadata":
            return self._get_workflow_evidence(
                session,
                str(arguments["workflow_id"]),
                kind="metadata",
            )
        if tool_id == "cromwell.abort_workflow":
            return self._abort_workflow(session, str(arguments["workflow_id"]))
        if tool_id == "clock.advance":
            return self._advance_clock(session, int(arguments["seconds"]))
        raise AssertionError(tool_id)

    @staticmethod
    def _get_experiment(
        session: WorldSession,
        experiment_id: int,
    ) -> ExecutionResult:
        elabftw = session.get_state("elabftw")
        source = session.get_state("source")
        if experiment_id == int(source["experiment_id"]):
            revision = source["revisions"][str(source["current_revision"])]
            cromwell = session.get_state("cromwell")
            referenced_workflow_id = source.get("current_workflow_id")
            referenced_workflow = (
                cromwell["workflows"].get(referenced_workflow_id)
                if isinstance(referenced_workflow_id, str)
                else None
            )
            metadata = {
                "record_kind": "analysis_source",
                "source_revision": int(source["current_revision"]),
                "source_content_digest": revision["content_digest"],
                "workflow_content_digest": revision["workflow_digest"],
                "qualification_context": deepcopy(revision["qualification_context"]),
                "workflow_source": revision["workflow_source"],
                "workflow_inputs": deepcopy(revision["workflow_inputs"]),
                "cromwell_workflow_id": referenced_workflow_id,
                "cromwell_workflow_source_revision": (
                    referenced_workflow.get("source_revision_at_submit")
                    if isinstance(referenced_workflow, Mapping)
                    else None
                ),
                "cromwell_workflow_source_content_digest": (
                    referenced_workflow.get("source_digest_at_submit")
                    if isinstance(referenced_workflow, Mapping)
                    else None
                ),
            }
            body = render_experiment(
                _ELABFTW_FACTS,
                experiment_id=experiment_id,
                title="Analysis-control qualification source",
                body=(
                    "Copy the exact admitted WDL and inputs. This record defines "
                    "analysis-control execution, not biological inference."
                ),
                metadata=metadata,
                created_at=str(source["created_at"]),
                modified_at=str(source["modified_at"]),
            )
            return ExecutionResult(
                body=body,
                status_code=200,
                headers={"content-type": "application/json"},
                evidence={
                    "experiment_id": experiment_id,
                    "record_kind": "source",
                    "source_revision": int(source["current_revision"]),
                    "source_content_digest": revision["content_digest"],
                    "cromwell_workflow_id": source.get("current_workflow_id"),
                },
            )
        record = elabftw["result_records"].get(str(experiment_id))
        if record is None:
            raise AnalysisWorldError(
                "ELABFTW_EXPERIMENT_NOT_FOUND",
                "Experiment does not exist in this episode.",
                details={"experiment_id": experiment_id},
                status_code=404,
            )
        body = render_experiment(
            _ELABFTW_FACTS,
            experiment_id=experiment_id,
            title=record["title"],
            body=record["body"],
            metadata=record["metadata"],
            created_at=str(record["created_at"]),
            modified_at=str(record.get("patched_at", record["created_at"])),
            changelog_repetitions=max(0, int(record["patch_count"]) - 1) * 2,
        )
        return ExecutionResult(
            body=body,
            status_code=200,
            headers={"content-type": "application/json"},
            evidence={
                "experiment_id": experiment_id,
                "record_kind": "result",
                "patch_count": int(record["patch_count"]),
            },
        )

    @staticmethod
    def _create_experiment(session: WorldSession) -> ExecutionResult:
        elabftw = session.get_state("elabftw")
        experiment_id = int(elabftw["next_result_id"])
        elabftw["next_result_id"] = experiment_id + 1
        elabftw["result_records"][str(experiment_id)] = {
            "title": "",
            "body": "",
            "metadata": {},
            "patch_count": 0,
            "created_at": session.current_time(),
        }
        session.set_state("elabftw", elabftw)
        status, body, headers = render_create_response(
            _ELABFTW_FACTS, experiment_id
        )
        return ExecutionResult(
            body=body,
            status_code=status,
            headers=headers,
            mutation_scope=("state:elabftw",),
            evidence={"experiment_id": experiment_id, "record_kind": "result"},
        )

    @staticmethod
    def _patch_experiment(
        session: WorldSession,
        arguments: Mapping[str, Any],
    ) -> ExecutionResult:
        experiment_id = int(arguments["experiment_id"])
        source = session.get_state("source")
        if experiment_id == int(source["experiment_id"]):
            raise AnalysisWorldError(
                "ELABFTW_SOURCE_RECORD_IMMUTABLE",
                "The benchmark source record changes only through its declared schedule.",
                details={"experiment_id": experiment_id},
            )
        elabftw = session.get_state("elabftw")
        record = elabftw["result_records"].get(str(experiment_id))
        if record is None:
            raise AnalysisWorldError(
                "ELABFTW_EXPERIMENT_NOT_FOUND",
                "Experiment does not exist in this episode.",
                details={"experiment_id": experiment_id},
                status_code=404,
            )
        patch_body = {
            "title": arguments["title"],
            "body": arguments["body"],
            "metadata": arguments["metadata"],
        }
        metadata = validate_patch_body(_ELABFTW_FACTS, patch_body)
        record.update(
            {
                "title": str(arguments["title"]),
                "body": str(arguments["body"]),
                "metadata": deepcopy(metadata),
                "patch_count": int(record["patch_count"]) + 1,
                "patched_at": session.current_time(),
                "source_revision_at_patch": int(source["current_revision"]),
                "source_digest_at_patch": source["revisions"][
                    str(source["current_revision"])
                ]["content_digest"],
            }
        )
        elabftw["result_records"][str(experiment_id)] = record
        session.set_state("elabftw", elabftw)
        facts = session.get_state("facts")
        facts["result_record_id"] = experiment_id
        session.set_state("facts", facts)
        body = render_experiment(
            _ELABFTW_FACTS,
            experiment_id=experiment_id,
            title=record["title"],
            body=record["body"],
            metadata=record["metadata"],
            created_at=str(record["created_at"]),
            modified_at=str(record["patched_at"]),
            changelog_repetitions=max(0, int(record["patch_count"]) - 1) * 2,
        )
        return ExecutionResult(
            body=body,
            status_code=200,
            headers={"content-type": "application/json"},
            mutation_scope=("state:elabftw", "state:facts"),
            evidence={
                "experiment_id": experiment_id,
                "record_kind": "result",
                "patch_count": int(record["patch_count"]),
                "writeback_source_revision": int(source["current_revision"]),
                "writeback_source_digest": record["source_digest_at_patch"],
            },
        )

    @staticmethod
    def _submit_workflow(
        session: WorldSession,
        arguments: Mapping[str, Any],
    ) -> ExecutionResult:
        workflow_source = str(arguments["workflowSource"])
        workflow_inputs = deepcopy(dict(arguments["workflowInputs"]))
        program = classify_program(
            _CROMWELL_FACTS,
            workflow_source,
            workflow_inputs,
        )
        source = session.get_state("source")
        revision = source["revisions"][str(source["current_revision"])]
        cromwell = session.get_state("cromwell")
        ordinal = int(cromwell["next_ordinal"])
        workflow_id = deterministic_workflow_id(
            seed=int(session.get_state("scenario")["seed"]),
            ordinal=ordinal,
        )
        if workflow_id in cromwell["workflows"]:
            raise AnalysisWorldError(
                "CROMWELL_WORKFLOW_ID_COLLISION",
                "Deterministic workflow id already exists.",
                details={"workflow_id": workflow_id},
            )
        terminal_after = None if program == "abort" else 30
        cromwell["next_ordinal"] = ordinal + 1
        cromwell["workflows"][workflow_id] = {
            "workflow_id": workflow_id,
            "ordinal": ordinal,
            "program": program,
            "workflow_source": workflow_source,
            "workflow_inputs": workflow_inputs,
            "submitted_content_digest": canonical_digest(
                {
                    "workflowInputs": workflow_inputs,
                    "workflowSource": workflow_source,
                }
            ),
            "source_experiment_id": int(source["experiment_id"]),
            "source_revision_at_submit": int(source["current_revision"]),
            "source_digest_at_submit": revision["content_digest"],
            "submitted_at": session.current_time(),
            "visible_after_seconds": 5,
            "running_after_seconds": 10,
            "terminal_after_seconds": terminal_after,
            "terminal_status": _CROMWELL_FACTS["programs"][program][
                "terminal_status"
            ],
            "abort_requested_at": None,
            "observed_statuses": [],
            "outputs_inspected": False,
            "logs_inspected": False,
            "metadata_inspected": False,
            "seeded_existing": False,
        }
        session.set_state("cromwell", cromwell)
        return ExecutionResult(
            body=render_submit_response(_CROMWELL_FACTS, workflow_id),
            status_code=201,
            headers={"content-type": "application/json"},
            mutation_scope=("state:cromwell",),
            workflow_id=workflow_id,
            provider_status="Submitted",
            evidence={
                "program": program,
                "source_experiment_id": int(source["experiment_id"]),
                "source_revision": int(source["current_revision"]),
                "source_content_digest": revision["content_digest"],
                "submitted_content_digest": cromwell["workflows"][workflow_id][
                    "submitted_content_digest"
                ],
            },
        )

    @staticmethod
    def _get_workflow_status(
        session: WorldSession,
        workflow_id: str,
    ) -> ExecutionResult:
        cromwell = session.get_state("cromwell")
        workflow = cromwell["workflows"].get(workflow_id)
        if workflow is None:
            status_code, body = render_status(
                _CROMWELL_FACTS,
                workflow_id=workflow_id,
                provider_status=None,
            )
            return ExecutionResult(
                body=body,
                status_code=status_code,
                headers={"content-type": "application/json"},
                reason_code="cromwell_workflow_not_visible",
                workflow_id=workflow_id,
            )
        status = workflow_status(workflow, current_time=session.current_time())
        status_code, body = render_status(
            _CROMWELL_FACTS,
            workflow_id=workflow_id,
            provider_status=status,
        )
        workflow["observed_statuses"].append(
            "transient_404" if status is None else status
        )
        cromwell["workflows"][workflow_id] = workflow
        session.set_state("cromwell", cromwell)
        return ExecutionResult(
            body=body,
            status_code=status_code,
            headers={"content-type": "application/json"},
            mutation_scope=("state:cromwell",),
            reason_code=(
                "cromwell_workflow_not_visible"
                if status is None
                else "cromwell_status_observed"
            ),
            workflow_id=workflow_id,
            provider_status=status,
        )

    @staticmethod
    def _get_workflow_evidence(
        session: WorldSession,
        workflow_id: str,
        *,
        kind: str,
    ) -> ExecutionResult:
        cromwell = session.get_state("cromwell")
        workflow = cromwell["workflows"].get(workflow_id)
        if workflow is None:
            raise AnalysisWorldError(
                "CROMWELL_WORKFLOW_NOT_FOUND",
                "Workflow does not exist in this episode.",
                details={"workflow_id": workflow_id},
                status_code=404,
            )
        status = workflow_status(workflow, current_time=session.current_time())
        if status not in {"Succeeded", "Failed", "Aborted"}:
            raise AnalysisWorldError(
                "CROMWELL_WORKFLOW_NOT_TERMINAL",
                "Terminal workflow evidence is unavailable before a terminal status.",
                details={"workflow_id": workflow_id, "status": status},
            )
        renderers = {
            "outputs": render_outputs,
            "logs": render_logs,
            "metadata": render_metadata,
        }
        if kind == "metadata":
            body = render_metadata(
                _CROMWELL_FACTS,
                str(workflow["program"]),
                workflow_id,
                projected_timing=_workflow_projection_timing(workflow),
            )
        else:
            body = renderers[kind](
                _CROMWELL_FACTS,
                str(workflow["program"]),
                workflow_id,
            )
        workflow[f"{kind}_inspected"] = True
        if kind == "outputs":
            workflow["outputs_digest"] = canonical_digest(body["outputs"])
        if kind == "metadata":
            workflow["metadata_digest"] = canonical_digest(body)
        cromwell["workflows"][workflow_id] = workflow
        session.set_state("cromwell", cromwell)
        evidence: dict[str, Any] = {"evidence_kind": kind}
        if kind == "outputs":
            evidence["outputs_digest"] = canonical_digest(body["outputs"])
        if kind == "metadata":
            evidence["metadata_digest"] = canonical_digest(body)
        if kind == "logs":
            evidence["paths_dereferenced"] = False
            evidence["projected_log_paths"] = _projected_log_paths(body)
        return ExecutionResult(
            body=body,
            status_code=200,
            headers={"content-type": "application/json"},
            mutation_scope=("state:cromwell",),
            workflow_id=workflow_id,
            provider_status=status,
            evidence=evidence,
        )

    @staticmethod
    def _abort_workflow(
        session: WorldSession,
        workflow_id: str,
    ) -> ExecutionResult:
        cromwell = session.get_state("cromwell")
        workflow = cromwell["workflows"].get(workflow_id)
        if workflow is None:
            status_code, body = render_abort_response(
                _CROMWELL_FACTS,
                workflow_id=workflow_id,
                provider_status=None,
            )
            return ExecutionResult(
                body=body,
                status_code=status_code,
                headers={"content-type": "application/json"},
                reason_code="cromwell_abort_not_in_progress",
                workflow_id=workflow_id,
            )
        status = workflow_status(workflow, current_time=session.current_time())
        status_code, body = render_abort_response(
            _CROMWELL_FACTS,
            workflow_id=workflow_id,
            provider_status=status,
        )
        mutation_scope: tuple[str, ...] = ()
        if status == "Running":
            workflow["abort_requested_at"] = session.current_time()
            workflow["abort_request_count"] = int(
                workflow.get("abort_request_count", 0)
            ) + 1
            cromwell["workflows"][workflow_id] = workflow
            session.set_state("cromwell", cromwell)
            mutation_scope = ("state:cromwell",)
            status = "Aborting"
        elif status == "Aborting":
            workflow["abort_request_count"] = int(
                workflow.get("abort_request_count", 0)
            ) + 1
            cromwell["workflows"][workflow_id] = workflow
            session.set_state("cromwell", cromwell)
            mutation_scope = ("state:cromwell",)
        return ExecutionResult(
            body=body,
            status_code=status_code,
            headers={"content-type": "application/json"},
            mutation_scope=mutation_scope,
            reason_code=(
                "cromwell_abort_requested"
                if status_code == 200
                else "cromwell_abort_not_in_progress"
            ),
            workflow_id=workflow_id,
            provider_status=status if status_code == 200 else None,
            evidence={
                "abort_request_count": int(
                    workflow.get("abort_request_count", 0)
                )
            },
        )

    @staticmethod
    def _advance_clock(
        session: WorldSession,
        seconds: int,
    ) -> ExecutionResult:
        delivered = session.advance_clock_by(
            timedelta(seconds=seconds),
            handler=ScienceELabFTWCromwellWorld._deliver_event,
        )
        return ExecutionResult(
            body={
                "current_time": session.current_time(),
                "delivered_events": [
                    {"id": event.id, "kind": event.kind} for event in delivered
                ],
            },
            status_code=200,
            mutation_scope=(
                "clock",
                *(f"scheduled_event:{event.id}" for event in delivered),
            ),
            evidence={
                "delivered_event_ids": [event.id for event in delivered],
            },
        )

    @staticmethod
    def _deliver_event(
        session: WorldSession,
        event: ScheduledWorldEvent,
    ) -> None:
        if event.kind != "source_revision_change":
            raise AnalysisWorldError(
                "ANALYSIS_EVENT_KIND_UNKNOWN",
                "Scheduled event kind is not supported.",
                details={"kind": event.kind},
            )
        source = session.get_state("source")
        revision = int(event.payload["revision"])
        if str(revision) not in source["revisions"]:
            raise AnalysisWorldError(
                "ANALYSIS_SOURCE_REVISION_UNDECLARED",
                "Scheduled source revision is not declared in the episode.",
                details={"revision": revision},
            )
        source["current_revision"] = revision
        source["current_workflow_id"] = None
        source["modified_at"] = session.current_time()
        session.set_state("source", source)
        session.append_event(
            "analysis_source_revised",
            {
                "experiment_id": int(source["experiment_id"]),
                "revision": revision,
                "content_digest": source["revisions"][str(revision)][
                    "content_digest"
                ],
                "scheduled_event_id": event.id,
            },
        )

    @staticmethod
    def _arguments_for_request(
        tool_id: str,
        request: CallRequest,
    ) -> dict[str, Any]:
        experiment = _EXPERIMENT_PATH.fullmatch(request.path)
        workflow = _WORKFLOW_PATH.fullmatch(request.path)
        if tool_id == "elabftw.get_experiment":
            return {"experiment_id": int(experiment.group(1))}
        if tool_id == "elabftw.create_experiment":
            if request.body != {}:
                raise AnalysisWorldError(
                    "ELABFTW_INVALID_CREATE_PAYLOAD",
                    "Captured experiment creation requires an empty JSON object.",
                    details={"body": request.body},
                    status_code=400,
                )
            return {}
        if tool_id == "elabftw.patch_experiment":
            return {"experiment_id": int(experiment.group(1)), **_body(request)}
        if tool_id == "cromwell.submit_workflow":
            return _body(request)
        if tool_id == "clock.advance":
            return _body(request)
        return {"workflow_id": workflow.group(1)}

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
        response_status_code: int,
        workflow_id: str | None = None,
        provider_status: str | None = None,
        evidence: Mapping[str, Any] | None = None,
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
            "response_status_code": response_status_code,
        }
        if workflow_id is not None:
            payload["workflow_id"] = workflow_id
        if provider_status is not None:
            payload["provider_status"] = provider_status
        if evidence is not None:
            payload["evidence"] = deepcopy(dict(evidence))
        session.append_event("analysis_operation", payload)

    @staticmethod
    def _response(
        status: int,
        body: Any,
        *,
        operation_id: str | None,
        reason_code: str,
        is_mutation: bool = False,
        decision_kind: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> WorldResponse:
        return WorldResponse(
            status_code=status,
            body=body,
            is_mutation=is_mutation,
            world_id=WORLD_ID,
            operation_id=operation_id,
            decision_kind=decision_kind
            or ("shadow_write" if is_mutation else "replay"),
            reason_code=reason_code,
            message=reason_code,
            headers=deepcopy(dict(headers or {})),
        )


def _body(request: CallRequest) -> dict[str, Any]:
    if not isinstance(request.body, dict):
        raise AnalysisWorldError(
            "ANALYSIS_REQUEST_BODY_INVALID",
            "Request body must be a JSON object.",
            details={"received_type": type(request.body).__name__},
            status_code=400,
        )
    return deepcopy(request.body)


def _projected_log_paths(value: Any) -> list[str]:
    paths: list[str] = []
    if isinstance(value, Mapping):
        for item in value.values():
            paths.extend(_projected_log_paths(item))
    elif isinstance(value, list):
        for item in value:
            paths.extend(_projected_log_paths(item))
    elif isinstance(value, str) and value.startswith("datalox-world://cromwell/"):
        paths.append(value)
    return paths


def _workflow_projection_timing(workflow: Mapping[str, Any]) -> dict[str, str]:
    submitted = datetime.fromisoformat(str(workflow["submitted_at"]))
    started = submitted + timedelta(seconds=int(workflow["running_after_seconds"]))
    abort_requested_at = workflow.get("abort_requested_at")
    if isinstance(abort_requested_at, str):
        ended = datetime.fromisoformat(abort_requested_at) + timedelta(seconds=5)
    else:
        terminal_after = workflow.get("terminal_after_seconds")
        if terminal_after is None:
            raise AnalysisWorldError(
                "CROMWELL_TERMINAL_TIMING_UNAVAILABLE",
                "Terminal metadata requires a declared terminal time.",
                details={"workflow_id": workflow["workflow_id"]},
            )
        ended = submitted + timedelta(seconds=int(terminal_after))
    return {
        "submitted_at": submitted.isoformat(),
        "started_at": started.isoformat(),
        "ended_at": ended.isoformat(),
    }


def _validate_arguments(tool_id: str, arguments: Mapping[str, Any]) -> None:
    schema = TOOLS_BY_ID[tool_id]["input_schema"]
    required = set(schema.get("required", []))
    properties = schema["properties"]
    if set(arguments) - set(properties) or not required.issubset(arguments):
        raise AnalysisWorldError(
            "ANALYSIS_ARGUMENTS_INVALID",
            "Tool arguments do not match the declared fields.",
            details={
                "required": sorted(required),
                "allowed": sorted(properties),
                "received": sorted(arguments),
            },
            status_code=400,
        )
    for name, value in arguments.items():
        expected = properties[name]
        value_type = expected.get("type")
        if value_type == "string" and not isinstance(value, str):
            _argument_type_error(name, "string", value)
        if value_type == "integer" and (
            not isinstance(value, int) or isinstance(value, bool)
        ):
            _argument_type_error(name, "integer", value)
        if value_type == "object" and not isinstance(value, dict):
            _argument_type_error(name, "object", value)
        if isinstance(value, str):
            if len(value) < int(expected.get("minLength", 0)):
                _argument_value_error(name, value)
            if "pattern" in expected and re.fullmatch(expected["pattern"], value) is None:
                _argument_value_error(name, value)
        if isinstance(value, int) and not isinstance(value, bool):
            if "minimum" in expected and value < expected["minimum"]:
                _argument_value_error(name, value)
            if "maximum" in expected and value > expected["maximum"]:
                _argument_value_error(name, value)


def _argument_type_error(name: str, expected: str, value: Any) -> None:
    raise AnalysisWorldError(
        "ANALYSIS_ARGUMENT_TYPE_INVALID",
        f"{name} must be {expected}.",
        details={"field": name, "received_type": type(value).__name__},
        status_code=400,
    )


def _argument_value_error(name: str, value: Any) -> None:
    raise AnalysisWorldError(
        "ANALYSIS_ARGUMENT_VALUE_INVALID",
        f"{name} is outside the declared contract.",
        details={"field": name, "received": value},
        status_code=400,
    )


def create_world() -> ScienceELabFTWCromwellWorld:
    return ScienceELabFTWCromwellWorld()
