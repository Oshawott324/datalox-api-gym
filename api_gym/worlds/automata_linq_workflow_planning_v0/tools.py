"""OpenAI-compatible tool schemas for automata_linq_workflow_planning_v0."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from api_gym.worlds.automata_linq_workflow_planning_v0 import services

ToolHandler = Callable[[Path, dict[str, Any]], dict[str, Any]]


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "automata_linq_get_api_version",
            "description": "Read the dry-run Automata LINQ Workflow Builder API version shape.",
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "automata_linq_get_organizations",
            "description": "Read the scenario organization and workspace context.",
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "automata_linq_get_scheduler_versions",
            "description": "Read supported scheduler versions for dry-run planning.",
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "automata_linq_get_all_drivers",
            "description": "Read driver catalog for a scheduler and version.",
            "parameters": _schema({"scheduler": {"type": "string"}, "version": {"type": "string"}}, ["scheduler", "version"]),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "automata_linq_get_workcells",
            "description": "Read workcells in a workspace.",
            "parameters": _schema({"workspace_id": {"type": "string"}}, ["workspace_id"]),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "automata_linq_get_device_status",
            "description": "Read device state and latest error shape.",
            "parameters": _schema({"device_id": {"type": "string"}}, ["device_id"]),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "automata_linq_get_run_histories",
            "description": "Read dry-run run-history page for a device.",
            "parameters": _schema({"device_id": {"type": "string"}, "count": {"type": "integer"}}, ["device_id"]),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "automata_linq_export_run_logs",
            "description": "Return the source-shaped dry-run log export URL without dereferencing it.",
            "parameters": _schema({"run_id": {"type": "string"}}, ["run_id"]),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "automata_linq_create_workflow",
            "description": "Store a provider-shaped workflow config in dry-run state.",
            "parameters": _schema(
                {
                    "name": {"type": "string"},
                    "metadata": {"type": "object"},
                    "workflow": {"type": "object"},
                    "workcell": {"type": "object"},
                    "options": {"type": "object"},
                    "scheduler_config": {"type": "object"},
                    "parameter_definitions": {"type": "array"},
                    "run_instructions": {"type": "array"},
                    "drivers_version": {"type": "string"},
                    "evals_version": {"type": "string"},
                },
                ["name", "metadata", "workflow", "workcell", "options", "scheduler_config"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "automata_linq_list_workflows",
            "description": "List stored dry-run workflows.",
            "parameters": _schema({"page_size": {"type": "integer"}}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "automata_linq_get_workflow",
            "description": "Read one stored workflow by id.",
            "parameters": _schema({"workflow_id": {"type": "string"}}, ["workflow_id"]),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "automata_linq_validate_workflow",
            "description": "Validate a workflow config with explicit dry-run synthetic rules.",
            "parameters": _schema(
                {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "metadata": {"type": "object"},
                    "workflow": {"type": "object"},
                    "workcell": {"type": "object"},
                    "options": {"type": "object"},
                    "scheduler_config": {"type": "object"},
                    "parameter_definitions": {"type": "array"},
                    "parameter_values": {"type": "array"},
                    "run_instructions": {"type": "array"},
                    "drivers_version": {"type": "string"},
                    "evals_version": {"type": "string"},
                    "validate_for_execution": {"type": "boolean"},
                    "validate_for_infeasibility": {"type": "boolean"},
                },
                ["workflow", "workcell", "scheduler_config"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "automata_linq_plan_workflow",
            "description": "Submit a valid stored workflow to the dry-run planner.",
            "parameters": _schema(
                {"workflow_id": {"type": "string"}, "parameter_values": {"type": "array"}},
                ["workflow_id"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "automata_linq_get_plan_status",
            "description": "Poll dry-run plan status.",
            "parameters": _schema({"workflow_id": {"type": "string"}, "plan_id": {"type": "string"}}, ["workflow_id", "plan_id"]),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "automata_linq_get_plan_result",
            "description": "Fetch a completed dry-run plan result.",
            "parameters": _schema({"workflow_id": {"type": "string"}, "plan_id": {"type": "string"}}, ["workflow_id", "plan_id"]),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "automata_linq_reject_live_action",
            "description": "Return the dry-run boundary response for forbidden live Automata LINQ actions.",
            "parameters": _schema({"operation": {"type": "string"}}, ["operation"]),
        },
    },
]


def dispatch_tool(db_path: Path, *, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        return _tool_error("unknown_tool", "Tool name is not registered for this world.", {"tool_name": name})
    try:
        return handler(db_path, arguments)
    except KeyError as exc:
        return _tool_error(
            "missing_tool_argument",
            "A required tool argument is missing.",
            {"tool_name": name, "argument": str(exc).strip("'")},
        )
    except (TypeError, ValueError) as exc:
        return _tool_error(
            "invalid_tool_arguments",
            "Tool arguments do not match the tool schema.",
            {"tool_name": name, "message": str(exc)},
        )


def _validate_payload(arguments: dict[str, Any]) -> tuple[dict[str, Any], bool, bool]:
    payload = dict(arguments)
    validate_for_execution = bool(payload.pop("validate_for_execution", False))
    validate_for_infeasibility = bool(payload.pop("validate_for_infeasibility", False))
    return payload, validate_for_execution, validate_for_infeasibility


def _tool_error(code: str, message: str, details: dict[str, Any]) -> dict[str, Any]:
    return {"ok": False, "error": {"code": code, "message": message, "details": details}}


TOOL_HANDLERS: dict[str, ToolHandler] = {
    "automata_linq_get_api_version": lambda db_path, arguments: services.get_api_version(db_path),
    "automata_linq_get_organizations": lambda db_path, arguments: services.get_organizations(db_path),
    "automata_linq_get_scheduler_versions": lambda db_path, arguments: services.get_scheduler_versions(db_path),
    "automata_linq_get_all_drivers": lambda db_path, arguments: services.get_all_drivers(
        db_path, scheduler=str(arguments["scheduler"]), version=str(arguments["version"])
    ),
    "automata_linq_get_workcells": lambda db_path, arguments: services.get_workcells(db_path, workspace_id=str(arguments["workspace_id"])),
    "automata_linq_get_device_status": lambda db_path, arguments: services.get_device_status(db_path, device_id=str(arguments["device_id"])),
    "automata_linq_get_run_histories": lambda db_path, arguments: services.get_run_histories(
        db_path,
        device_id=str(arguments["device_id"]),
        count=None if arguments.get("count") is None else int(arguments["count"]),
    ),
    "automata_linq_export_run_logs": lambda db_path, arguments: services.export_run_logs(db_path, run_id=str(arguments["run_id"])),
    "automata_linq_create_workflow": lambda db_path, arguments: services.create_workflow(db_path, arguments),
    "automata_linq_list_workflows": lambda db_path, arguments: services.list_workflows_paginated(
        db_path, page_size=int(arguments.get("page_size", 100))
    ),
    "automata_linq_get_workflow": lambda db_path, arguments: services.get_workflow(db_path, workflow_id=str(arguments["workflow_id"])),
    "automata_linq_validate_workflow": lambda db_path, arguments: services.validate_workflow(db_path, *_validate_payload(arguments)),
    "automata_linq_plan_workflow": lambda db_path, arguments: services.plan_workflow(
        db_path,
        workflow_id=str(arguments["workflow_id"]),
        parameter_values=arguments.get("parameter_values") if isinstance(arguments.get("parameter_values"), list) else None,
    ),
    "automata_linq_get_plan_status": lambda db_path, arguments: services.get_plan_status(
        db_path, workflow_id=str(arguments["workflow_id"]), plan_id=str(arguments["plan_id"])
    ),
    "automata_linq_get_plan_result": lambda db_path, arguments: services.get_plan_result(
        db_path, workflow_id=str(arguments["workflow_id"]), plan_id=str(arguments["plan_id"])
    ),
    "automata_linq_reject_live_action": lambda db_path, arguments: services.reject_live_action(db_path, operation=str(arguments["operation"])),
}
