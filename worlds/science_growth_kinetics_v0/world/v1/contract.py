from __future__ import annotations

from typing import Any

WORLD_ID = "science_growth_kinetics_v0"
DEFAULT_ROLE = "scientist_agent"
ROLE = {
    "id": DEFAULT_ROLE,
    "description": "Executes and documents a dry-run microbial growth workflow.",
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
TOOLS = (
    {
        "id": "elabftw.get_experiment",
        "description": "Read one existing eLabFTW experiment or result record.",
        "list_roles": [DEFAULT_ROLE],
        "invoke_roles": [DEFAULT_ROLE],
        "input_schema": EXPERIMENT_ID,
        "source_refs": ["elabftw_reference_capture"],
        "operation_family": "scientific_record",
    },
    {
        "id": "elabftw.create_experiment",
        "description": "Create an empty eLabFTW result experiment and return its location.",
        "list_roles": [DEFAULT_ROLE],
        "invoke_roles": [DEFAULT_ROLE],
        "input_schema": EMPTY,
        "source_refs": ["elabftw_reference_capture"],
        "operation_family": "scientific_record",
    },
    {
        "id": "elabftw.patch_experiment",
        "description": "Patch a created eLabFTW result with title, body, and JSON-string metadata.",
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
        "source_refs": ["elabftw_reference_capture"],
        "operation_family": "scientific_record",
    },
    {
        "id": "pylabrobot.inspect_deck",
        "description": "Inspect tracked source volumes, assay wells, and clean-tip availability.",
        "list_roles": [DEFAULT_ROLE],
        "invoke_roles": [DEFAULT_ROLE],
        "input_schema": EMPTY,
        "source_refs": ["pylabrobot_executed_source_pack"],
        "operation_family": "liquid_handling",
    },
    {
        "id": "pylabrobot.transfer",
        "description": "Execute one OT-2 simulator transfer with a selected clean disposable tip.",
        "list_roles": [DEFAULT_ROLE],
        "invoke_roles": [DEFAULT_ROLE],
        "input_schema": schema(
            {
                "source_well": {"type": "string", "pattern": "^[A-H](?:[1-9]|1[0-2])$"},
                "target_well": {"type": "string", "pattern": "^[A-H](?:[1-9]|1[0-2])$"},
                "tip_spot": {"type": "string", "pattern": "^[A-H](?:[1-9]|1[0-2])$"},
                "volume_ul": {"type": "number", "exclusiveMinimum": 0, "maximum": 300},
            },
            ("source_well", "target_well", "tip_spot", "volume_ul"),
        ),
        "source_refs": ["pylabrobot_executed_source_pack"],
        "operation_family": "liquid_handling",
    },
    {
        "id": "pylabrobot.incubator_load",
        "description": "Execute the incubator Chatterbox load, temperature, and shaking calls.",
        "list_roles": [DEFAULT_ROLE],
        "invoke_roles": [DEFAULT_ROLE],
        "input_schema": schema(
            {
                "plate_barcode": {"type": "string", "minLength": 1},
                "temperature_c": {"type": "number", "minimum": 20, "maximum": 45},
                "shaking_hz": {"type": "number", "exclusiveMinimum": 0, "maximum": 10},
            },
            ("plate_barcode", "temperature_c", "shaking_hz"),
        ),
        "source_refs": [
            "pylabrobot_executed_source_pack",
            "agilent_growth_protocol",
        ],
        "operation_family": "incubation",
    },
    {
        "id": "pylabrobot.incubator_status",
        "description": "Read plate location and benchmark-defined stabilization status.",
        "list_roles": [DEFAULT_ROLE],
        "invoke_roles": [DEFAULT_ROLE],
        "input_schema": EMPTY,
        "source_refs": ["growth_projection_contract"],
        "operation_family": "incubation",
    },
    {
        "id": "pylabrobot.incubator_release",
        "description": "Execute the incubator Chatterbox plate-fetch calls after stabilization.",
        "list_roles": [DEFAULT_ROLE],
        "invoke_roles": [DEFAULT_ROLE],
        "input_schema": schema(
            {"plate_barcode": {"type": "string", "minLength": 1}},
            ("plate_barcode",),
        ),
        "source_refs": ["pylabrobot_executed_source_pack"],
        "operation_family": "incubation",
    },
    {
        "id": "pylabrobot.start_kinetic_read",
        "description": "Execute a Chatterbox OD600 read and schedule the benchmark kinetic series.",
        "list_roles": [DEFAULT_ROLE],
        "invoke_roles": [DEFAULT_ROLE],
        "input_schema": schema(
            {
                "plate_barcode": {"type": "string", "minLength": 1},
                "protocol_revision": {"type": "integer", "minimum": 1},
                "wells": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "uniqueItems": True,
                },
                "wavelength_nm": {"type": "integer", "minimum": 230, "maximum": 999},
                "interval_seconds": {"type": "integer", "minimum": 1},
                "duration_seconds": {"type": "integer", "minimum": 1},
            },
            (
                "plate_barcode",
                "protocol_revision",
                "wells",
                "wavelength_nm",
                "interval_seconds",
                "duration_seconds",
            ),
        ),
        "source_refs": [
            "pylabrobot_executed_source_pack",
            "agilent_growth_protocol",
            "growth_projection_contract",
        ],
        "operation_family": "plate_reading",
    },
    {
        "id": "pylabrobot.get_kinetic_read",
        "description": "Read kinetic-run status, completeness, provenance, and OD600 series.",
        "list_roles": [DEFAULT_ROLE],
        "invoke_roles": [DEFAULT_ROLE],
        "input_schema": schema(
            {"job_id": {"type": "string", "pattern": "^run-[0-9]{3}$"}},
            ("job_id",),
        ),
        "source_refs": ["growth_projection_contract"],
        "operation_family": "plate_reading",
    },
    {
        "id": "clock.advance",
        "description": "Advance benchmark logical time and deliver due workflow events.",
        "list_roles": [DEFAULT_ROLE],
        "invoke_roles": [DEFAULT_ROLE],
        "input_schema": schema(
            {"seconds": {"type": "integer", "minimum": 0, "maximum": 200000}},
            ("seconds",),
        ),
        "source_refs": ["growth_projection_contract"],
        "operation_family": "logical_time",
    },
)

TOOLS_BY_ID = {tool["id"]: tool for tool in TOOLS}
