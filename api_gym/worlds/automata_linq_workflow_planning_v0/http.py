"""FastAPI surface for automata_linq_workflow_planning_v0 run state."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api_gym.worlds.automata_linq_workflow_planning_v0 import services
from api_gym.worlds.automata_linq_workflow_planning_v0.state import resolve_state_db_path
from api_gym.worlds.http import append_world_http_trace, query_params

WORLD = "automata_linq_workflow_planning_v0"


def create_app(run_dir: Path) -> FastAPI:
    """Create an HTTP app bound to one sampled Automata LINQ run."""
    db_path = resolve_state_db_path(run_dir)
    trace_path = run_dir / "traces" / "http_requests.jsonl"
    app = FastAPI(title="Datalox API Gym automata_linq_workflow_planning_v0")

    @app.get("/version")
    def get_api_version(http_request: Request) -> JSONResponse:
        return _response(trace_path, request=http_request, request_json=None, result=services.get_api_version(db_path))

    @app.get("/v2/user/organizations")
    def get_organizations(http_request: Request) -> JSONResponse:
        return _response(trace_path, request=http_request, request_json=None, result=services.get_organizations(db_path))

    @app.post("/v3/workflow")
    async def create_workflow(http_request: Request) -> JSONResponse:
        body = await http_request.json()
        return _response(trace_path, request=http_request, request_json=body, result=services.create_workflow(db_path, body))

    @app.post("/v3/workflow/paginated")
    async def list_workflows(http_request: Request) -> JSONResponse:
        body = await _json_body_or_empty(http_request)
        page_size = _int_query(http_request, "page_size", default=100)
        return _response(
            trace_path,
            request=http_request,
            request_json=body,
            result=services.list_workflows_paginated(db_path, page_size=page_size),
        )

    @app.get("/v3/workflow/scheduler_versions")
    def get_scheduler_versions(http_request: Request) -> JSONResponse:
        return _response(trace_path, request=http_request, request_json=None, result=services.get_scheduler_versions(db_path))

    @app.get("/v3/workflow/{workflow_id}")
    def get_workflow(workflow_id: str, http_request: Request) -> JSONResponse:
        return _response(
            trace_path,
            request=http_request,
            request_json=None,
            result=services.get_workflow(db_path, workflow_id=workflow_id),
        )

    @app.post("/v3/workflow/validate")
    async def validate_workflow(http_request: Request) -> JSONResponse:
        body = await http_request.json()
        return _response(
            trace_path,
            request=http_request,
            request_json=body,
            result=services.validate_workflow(
                db_path,
                body,
                validate_for_execution=_bool_query(http_request, "validate_for_execution"),
                validate_for_infeasibility=_bool_query(http_request, "validate_for_infeasibility"),
            ),
        )

    @app.post("/v3/workflow/plan")
    async def plan_workflow(http_request: Request) -> JSONResponse:
        body = await _json_body_or_empty(http_request)
        return _response(
            trace_path,
            request=http_request,
            request_json=body,
            result=services.plan_workflow(
                db_path,
                workflow_id=str(http_request.query_params.get("workflow_id", "")),
                parameter_values=body.get("parameter_values") if isinstance(body.get("parameter_values"), list) else None,
            ),
        )

    @app.get("/v3/workflow/{workflow_id}/plan/{plan_id}/status")
    def get_plan_status(workflow_id: str, plan_id: str, http_request: Request) -> JSONResponse:
        return _response(
            trace_path,
            request=http_request,
            request_json=None,
            result=services.get_plan_status(db_path, workflow_id=workflow_id, plan_id=plan_id),
        )

    @app.get("/v3/workflow/{workflow_id}/plan/{plan_id}/result")
    def get_plan_result(workflow_id: str, plan_id: str, http_request: Request) -> JSONResponse:
        result = services.get_plan_result(db_path, workflow_id=workflow_id, plan_id=plan_id)
        status_code = 404 if result.get("error", {}).get("code") == "plan_result_unavailable" else 200
        return _response(trace_path, request=http_request, request_json=None, result=result, status_code=status_code)

    @app.get("/v3/driver/{scheduler}/{version}")
    def get_all_drivers(scheduler: str, version: str, http_request: Request) -> JSONResponse:
        return _response(
            trace_path,
            request=http_request,
            request_json=None,
            result=services.get_all_drivers(db_path, scheduler=scheduler, version=version),
        )

    @app.get("/v1/workspace/{workspace_id}/workcells")
    def get_workcells(workspace_id: str, http_request: Request) -> JSONResponse:
        return _response(
            trace_path,
            request=http_request,
            request_json=None,
            result=services.get_workcells(db_path, workspace_id=workspace_id),
        )

    @app.get("/v1/devices/{device_id}")
    def get_device_status(device_id: str, http_request: Request) -> JSONResponse:
        return _response(
            trace_path,
            request=http_request,
            request_json=None,
            result=services.get_device_status(db_path, device_id=device_id),
        )

    @app.get("/v1/devices/{device_id}/history/run-histories")
    def get_run_histories(device_id: str, http_request: Request) -> JSONResponse:
        return _response(
            trace_path,
            request=http_request,
            request_json=None,
            result=services.get_run_histories(
                db_path,
                device_id=device_id,
                count=_int_query(http_request, "count", default=100),
            ),
        )

    @app.get("/v1/run-histories/{run_id}/logs/export")
    def export_run_logs(run_id: str, http_request: Request) -> JSONResponse:
        return _response(
            trace_path,
            request=http_request,
            request_json=None,
            result=services.export_run_logs(db_path, run_id=run_id),
        )

    @app.post("/v3/workflow/{workflow_id}/start")
    def reject_start_workflow(workflow_id: str, http_request: Request) -> JSONResponse:
        _ = workflow_id
        return _boundary_response(trace_path, request=http_request, db_path=db_path, operation="start_workflow")

    @app.post("/v3/workflow/{workflow_id}/deploy")
    def reject_deploy_workflow(workflow_id: str, http_request: Request) -> JSONResponse:
        _ = workflow_id
        return _boundary_response(trace_path, request=http_request, db_path=db_path, operation="deploy_workflow")

    @app.post("/v3/workflow/{workflow_id}/publish")
    def reject_publish_workflow(workflow_id: str, http_request: Request) -> JSONResponse:
        _ = workflow_id
        return _boundary_response(trace_path, request=http_request, db_path=db_path, operation="publish_workflow")

    @app.post("/v3/workflow/{workflow_id}/pause")
    def reject_pause_workflow(workflow_id: str, http_request: Request) -> JSONResponse:
        _ = workflow_id
        return _boundary_response(trace_path, request=http_request, db_path=db_path, operation="pause_workflow")

    @app.post("/v3/workflow/{workflow_id}/resume")
    def reject_resume_workflow(workflow_id: str, http_request: Request) -> JSONResponse:
        _ = workflow_id
        return _boundary_response(trace_path, request=http_request, db_path=db_path, operation="resume_workflow")

    @app.post("/v3/workflow/{workflow_id}/stop")
    def reject_stop_workflow(workflow_id: str, http_request: Request) -> JSONResponse:
        _ = workflow_id
        return _boundary_response(trace_path, request=http_request, db_path=db_path, operation="stop_workflow")

    @app.post("/v3/workflow/{workflow_id}/reset")
    def reject_reset_workflow(workflow_id: str, http_request: Request) -> JSONResponse:
        _ = workflow_id
        return _boundary_response(trace_path, request=http_request, db_path=db_path, operation="reset_workflow")

    @app.post("/v1/devices/{device_id}/errors/{error_id}/respond")
    def reject_respond_to_error(device_id: str, error_id: str, http_request: Request) -> JSONResponse:
        _ = (device_id, error_id)
        return _boundary_response(trace_path, request=http_request, db_path=db_path, operation="respond_to_error")

    @app.post("/v1/workspace/{workspace_id}/hubs/{hub_id}/restart")
    def reject_restart_hub(workspace_id: str, hub_id: str, http_request: Request) -> JSONResponse:
        _ = (workspace_id, hub_id)
        return _boundary_response(trace_path, request=http_request, db_path=db_path, operation="restart_hub")

    @app.post("/v1/workspace/{workspace_id}/transport-configs/{transport_config_id}")
    def reject_mutate_transport_config(workspace_id: str, transport_config_id: str, http_request: Request) -> JSONResponse:
        _ = (workspace_id, transport_config_id)
        return _boundary_response(trace_path, request=http_request, db_path=db_path, operation="mutate_transport_config")

    @app.post("/v1/workspace/{workspace_id}/credentials/{credential_id}/rotate")
    def reject_rotate_credentials(workspace_id: str, credential_id: str, http_request: Request) -> JSONResponse:
        _ = (workspace_id, credential_id)
        return _boundary_response(trace_path, request=http_request, db_path=db_path, operation="rotate_credentials")

    return app


def _boundary_response(trace_path: Path, *, request: Request, db_path: Path, operation: str) -> JSONResponse:
    return _response(
        trace_path,
        request=request,
        request_json=None,
        result=services.reject_live_action(db_path, operation=operation),
    )


def _response(
    trace_path: Path,
    *,
    request: Request,
    request_json: object,
    result: dict[str, Any],
    status_code: int = 200,
) -> JSONResponse:
    append_world_http_trace(
        trace_path,
        world=WORLD,
        method=request.method,
        path_value=request.url.path,
        query_params=query_params(request),
        request_json=request_json,
        status_code=status_code,
        response=result,
    )
    content = result["data"] if result.get("ok") is True else result["error"]
    return JSONResponse(content=content, status_code=status_code)


async def _json_body_or_empty(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}


def _bool_query(request: Request, key: str) -> bool:
    value = request.query_params.get(key)
    return value is not None and value.lower() in {"1", "true", "yes"}


def _int_query(request: Request, key: str, *, default: int) -> int:
    value = request.query_params.get(key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default
