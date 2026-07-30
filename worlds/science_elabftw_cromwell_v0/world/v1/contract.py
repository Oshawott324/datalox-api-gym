from __future__ import annotations

from typing import Any

WORLD_ID = "science_elabftw_cromwell_v0"
DEFAULT_ROLE = "scientist_agent"
RESULT_TITLE = "Analysis-control qualification handoff"
RESULT_BODY = (
    "The captured Cromwell program qualified for evidence handoff. "
    "This record makes no biological or scientific inference."
)
ROLE = {
    "id": DEFAULT_ROLE,
    "description": "Executes a bounded analysis-control and evidence-handoff workflow.",
}


def schema(
    properties: dict[str, Any],
    required: tuple[str, ...] = (),
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        result["required"] = list(required)
    return result


EMPTY = schema({})
EXPERIMENT_ID = schema(
    {"experiment_id": {"type": "integer", "minimum": 1}},
    ("experiment_id",),
)
WORKFLOW_ID = schema(
    {
        "workflow_id": {
            "type": "string",
            "pattern": (
                "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
                "[0-9a-f]{4}-[0-9a-f]{12}$"
            ),
        }
    },
    ("workflow_id",),
)

TOOLS = (
    {
        "id": "elabftw.get_experiment",
        "description": "Read one eLabFTW source or result experiment.",
        "list_roles": [DEFAULT_ROLE],
        "invoke_roles": [DEFAULT_ROLE],
        "input_schema": EXPERIMENT_ID,
        "source_refs": ["elabftw_complete_capture"],
        "operation_family": "analysis_record",
    },
    {
        "id": "elabftw.create_experiment",
        "description": "Create one empty eLabFTW result experiment.",
        "list_roles": [DEFAULT_ROLE],
        "invoke_roles": [DEFAULT_ROLE],
        "input_schema": EMPTY,
        "source_refs": ["elabftw_complete_capture"],
        "operation_family": "analysis_record",
    },
    {
        "id": "elabftw.patch_experiment",
        "description": (
            "Patch an eLabFTW result using the task's exact title/body contract "
            "and JSON metadata."
        ),
        "list_roles": [DEFAULT_ROLE],
        "invoke_roles": [DEFAULT_ROLE],
        "input_schema": schema(
            {
                "experiment_id": {"type": "integer", "minimum": 1},
                "title": {"type": "string", "minLength": 1},
                "body": {"type": "string", "minLength": 1},
                "metadata": {"type": "string", "minLength": 2},
            },
            ("experiment_id", "title", "body", "metadata"),
        ),
        "source_refs": ["elabftw_complete_capture"],
        "operation_family": "analysis_record",
    },
    {
        "id": "cromwell.submit_workflow",
        "description": "Submit an admitted Cromwell WDL source and input object.",
        "list_roles": [DEFAULT_ROLE],
        "invoke_roles": [DEFAULT_ROLE],
        "input_schema": schema(
            {
                "workflowSource": {"type": "string", "minLength": 1},
                "workflowInputs": {"type": "object"},
            },
            ("workflowSource", "workflowInputs"),
        ),
        "source_refs": ["cromwell_complete_captures"],
        "operation_family": "workflow_execution",
    },
    {
        "id": "cromwell.get_workflow_status",
        "description": "Read provider-native Cromwell workflow status.",
        "list_roles": [DEFAULT_ROLE],
        "invoke_roles": [DEFAULT_ROLE],
        "input_schema": WORKFLOW_ID,
        "source_refs": [
            "cromwell_complete_captures",
            "analysis_projection_contract",
        ],
        "operation_family": "workflow_execution",
    },
    {
        "id": "cromwell.get_workflow_outputs",
        "description": "Read terminal Cromwell outputs for one admitted workflow.",
        "list_roles": [DEFAULT_ROLE],
        "invoke_roles": [DEFAULT_ROLE],
        "input_schema": WORKFLOW_ID,
        "source_refs": ["cromwell_complete_captures"],
        "operation_family": "workflow_execution",
    },
    {
        "id": "cromwell.get_workflow_logs",
        "description": "Read sanitized terminal Cromwell log references.",
        "list_roles": [DEFAULT_ROLE],
        "invoke_roles": [DEFAULT_ROLE],
        "input_schema": WORKFLOW_ID,
        "source_refs": ["cromwell_complete_captures"],
        "operation_family": "workflow_execution",
    },
    {
        "id": "cromwell.get_workflow_metadata",
        "description": "Read terminal Cromwell workflow metadata.",
        "list_roles": [DEFAULT_ROLE],
        "invoke_roles": [DEFAULT_ROLE],
        "input_schema": WORKFLOW_ID,
        "source_refs": ["cromwell_complete_captures"],
        "operation_family": "workflow_execution",
    },
    {
        "id": "cromwell.abort_workflow",
        "description": "Abort one Running Cromwell workflow.",
        "list_roles": [DEFAULT_ROLE],
        "invoke_roles": [DEFAULT_ROLE],
        "input_schema": WORKFLOW_ID,
        "source_refs": ["cromwell_complete_captures"],
        "operation_family": "workflow_execution",
    },
    {
        "id": "clock.advance",
        "description": "Advance benchmark logical time and deliver due revisions.",
        "list_roles": [DEFAULT_ROLE],
        "invoke_roles": [DEFAULT_ROLE],
        "input_schema": schema(
            {"seconds": {"type": "integer", "minimum": 0, "maximum": 3600}},
            ("seconds",),
        ),
        "source_refs": ["analysis_projection_contract"],
        "operation_family": "logical_time",
    },
)

TOOLS_BY_ID = {tool["id"]: tool for tool in TOOLS}
