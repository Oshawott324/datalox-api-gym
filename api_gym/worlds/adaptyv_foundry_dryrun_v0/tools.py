"""OpenAI-compatible tool schemas and dispatcher for adaptyv_foundry_dryrun_v0."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from api_gym.worlds.adaptyv_foundry_dryrun_v0 import services

ToolHandler = Callable[[Path, dict[str, Any]], dict[str, Any]]


LIVE_BOUNDARY_OPERATION_NAMES = {
    "attenuate_token",
    "confirm_experiment_quote_live",
    "revoke_token",
}


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def _sequence_attachment_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "sequence_id": {"type": "string"},
            "alias": {"type": "string"},
        },
        "required": ["sequence_id", "alias"],
        "additionalProperties": False,
    }


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "whoami",
            "description": "Read the simulated organization and token scope for this dry-run session.",
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_experiments",
            "description": "List dry-run experiments visible in the current SQLite state.",
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_targets",
            "description": "List target catalog entries selected for this dry-run task.",
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_target",
            "description": "Read one target catalog entry by id.",
            "parameters": _schema({"target_id": {"type": "string"}}, ["target_id"]),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_sequences",
            "description": "List candidate sequence records selected for this dry-run task.",
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_sequence",
            "description": "Read one candidate sequence by id.",
            "parameters": _schema({"sequence_id": {"type": "string"}}, ["sequence_id"]),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_experiment",
            "description": "Create a sandbox draft experiment for an available target.",
            "parameters": _schema(
                {
                    "name": {"type": "string"},
                    "target_id": {"type": "string"},
                    "experiment_type": {"type": "string"},
                    "method": {"type": "string"},
                    "sequences": {"type": "array", "items": _sequence_attachment_schema()},
                },
                ["name", "target_id"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_sequences_to_experiment",
            "description": "Attach existing candidate sequences to a draft experiment.",
            "parameters": _schema(
                {
                    "experiment_id": {"type": "string"},
                    "sequences": {"type": "array", "items": _sequence_attachment_schema()},
                },
                ["experiment_id", "sequences"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "estimate_experiment_cost",
            "description": "Create or return a sandbox cost estimate for an experiment sequence batch.",
            "parameters": _schema({"experiment_id": {"type": "string"}}, ["experiment_id"]),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_experiment",
            "description": "Move a valid draft experiment into submitted sandbox state.",
            "parameters": _schema({"experiment_id": {"type": "string"}}, ["experiment_id"]),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_experiment",
            "description": "Read one experiment by id.",
            "parameters": _schema({"experiment_id": {"type": "string"}}, ["experiment_id"]),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_experiment_sequences",
            "description": "List sequence membership for one experiment.",
            "parameters": _schema({"experiment_id": {"type": "string"}}, ["experiment_id"]),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_experiment_updates",
            "description": "List experiment updates visible at the current logical time.",
            "parameters": _schema({"experiment_id": {"type": "string"}}, ["experiment_id"]),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_experiment_quote",
            "description": "Read the current quote metadata for an experiment.",
            "parameters": _schema({"experiment_id": {"type": "string"}}, ["experiment_id"]),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "confirm_quote",
            "description": "Confirm a ready, unexpired, within-budget sandbox quote.",
            "parameters": _schema({"quote_id": {"type": "string"}}, ["quote_id"]),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reject_quote",
            "description": "Reject a sandbox quote that has not already been confirmed.",
            "parameters": _schema({"quote_id": {"type": "string"}}, ["quote_id"]),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_experiment_results",
            "description": "List experiment results visible at the current logical time.",
            "parameters": _schema({"experiment_id": {"type": "string"}}, ["experiment_id"]),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_result",
            "description": "Read one visible result by id for a specific experiment.",
            "parameters": _schema(
                {"experiment_id": {"type": "string"}, "result_id": {"type": "string"}},
                ["experiment_id", "result_id"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_campaign_decision",
            "description": "Record the final campaign decision and cited visible result ids.",
            "parameters": _schema(
                {
                    "experiment_id": {"type": "string"},
                    "decision": {"type": "string"},
                    "cited_result_ids": {"type": "array", "items": {"type": "string"}},
                    "rationale": {"type": "string"},
                },
                ["experiment_id", "decision", "cited_result_ids", "rationale"],
            ),
        },
    },
]


def dispatch_tool_call(db_path: Path, tool_call: dict[str, Any]) -> dict[str, Any]:
    """Dispatch one OpenAI-compatible function call against a run DB."""
    name, arguments = _extract_name_and_arguments(tool_call)
    if name is None:
        return _tool_error("missing_tool_name", "Tool call is missing a function name.", {"tool_call": tool_call})
    if arguments is None:
        return _tool_error("invalid_tool_arguments", "Tool arguments must be a JSON object.", {"tool_name": name})
    return dispatch_tool(db_path, name=name, arguments=arguments)


def dispatch_tool(db_path: Path, *, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        if name in LIVE_BOUNDARY_OPERATION_NAMES:
            return services.reject_live_execution(db_path, attempted_operation=name)
        return _tool_error("UNKNOWN_TOOL", "Tool name is not registered for this world.", {"tool_name": name})
    try:
        return handler(db_path, arguments)
    except KeyError as exc:
        return _tool_error(
            "MISSING_TOOL_ARGUMENT",
            "A required tool argument is missing.",
            {"tool_name": name, "argument": str(exc).strip("'")},
        )
    except (TypeError, ValueError) as exc:
        return _tool_error(
            "INVALID_TOOL_ARGUMENTS",
            "Tool arguments do not match the tool schema.",
            {"tool_name": name, "message": str(exc)},
        )


def _extract_name_and_arguments(tool_call: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    function = tool_call.get("function")
    if isinstance(function, dict):
        name = function.get("name")
        raw_arguments = function.get("arguments", {})
    else:
        name = tool_call.get("name")
        raw_arguments = tool_call.get("arguments", {})

    if isinstance(raw_arguments, str):
        try:
            arguments = json.loads(raw_arguments or "{}")
        except json.JSONDecodeError:
            return str(name) if name is not None else None, None
    else:
        arguments = raw_arguments

    if not isinstance(arguments, dict):
        return str(name) if name is not None else None, None
    return str(name) if name is not None else None, arguments


def _sequence_payloads(arguments: dict[str, Any]) -> list[dict[str, Any]]:
    sequences = arguments["sequences"]
    if not isinstance(sequences, list):
        raise TypeError("sequences must be a list")
    return [dict(item) for item in sequences]


def _result_ids(arguments: dict[str, Any]) -> list[str]:
    result_ids = arguments["cited_result_ids"]
    if not isinstance(result_ids, list):
        raise TypeError("cited_result_ids must be a list")
    return [str(result_id) for result_id in result_ids]


def _tool_error(code: str, message: str, details: dict[str, Any]) -> dict[str, Any]:
    return {"ok": False, "error": {"code": code, "message": message, "details": details}}


TOOL_HANDLERS: dict[str, ToolHandler] = {
    "whoami": lambda db_path, arguments: services.whoami(db_path),
    "list_experiments": lambda db_path, arguments: services.list_experiments(db_path),
    "list_targets": lambda db_path, arguments: services.list_targets(db_path),
    "get_target": lambda db_path, arguments: services.get_target(db_path, target_id=str(arguments["target_id"])),
    "list_sequences": lambda db_path, arguments: services.list_sequences(db_path),
    "get_sequence": lambda db_path, arguments: services.get_sequence(db_path, sequence_id=str(arguments["sequence_id"])),
    "create_experiment": lambda db_path, arguments: services.create_experiment(
        db_path,
        name=str(arguments["name"]),
        target_id=str(arguments["target_id"]),
        experiment_type=None if arguments.get("experiment_type") is None else str(arguments["experiment_type"]),
        method=None if arguments.get("method") is None else str(arguments["method"]),
        sequences=None if arguments.get("sequences") is None else _sequence_payloads(arguments),
    ),
    "add_sequences_to_experiment": lambda db_path, arguments: services.add_sequences_to_experiment(
        db_path,
        experiment_id=str(arguments["experiment_id"]),
        sequences=_sequence_payloads(arguments),
    ),
    "estimate_experiment_cost": lambda db_path, arguments: services.estimate_experiment_cost(
        db_path, experiment_id=str(arguments["experiment_id"])
    ),
    "submit_experiment": lambda db_path, arguments: services.submit_experiment(db_path, experiment_id=str(arguments["experiment_id"])),
    "get_experiment": lambda db_path, arguments: services.get_experiment(db_path, experiment_id=str(arguments["experiment_id"])),
    "list_experiment_sequences": lambda db_path, arguments: services.list_experiment_sequences(
        db_path, experiment_id=str(arguments["experiment_id"])
    ),
    "list_experiment_updates": lambda db_path, arguments: services.list_experiment_updates(
        db_path, experiment_id=str(arguments["experiment_id"])
    ),
    "get_experiment_quote": lambda db_path, arguments: services.get_experiment_quote(
        db_path, experiment_id=str(arguments["experiment_id"])
    ),
    "confirm_quote": lambda db_path, arguments: services.confirm_quote(db_path, quote_id=str(arguments["quote_id"])),
    "reject_quote": lambda db_path, arguments: services.reject_quote(db_path, quote_id=str(arguments["quote_id"])),
    "list_experiment_results": lambda db_path, arguments: services.list_experiment_results(
        db_path, experiment_id=str(arguments["experiment_id"])
    ),
    "get_result": lambda db_path, arguments: services.get_result(
        db_path,
        experiment_id=str(arguments["experiment_id"]),
        result_id=str(arguments["result_id"]),
    ),
    "submit_campaign_decision": lambda db_path, arguments: services.submit_campaign_decision(
        db_path,
        experiment_id=str(arguments["experiment_id"]),
        decision=str(arguments["decision"]),
        cited_result_ids=_result_ids(arguments),
        rationale=str(arguments["rationale"]),
    ),
}
