from __future__ import annotations

import json
from typing import Any


def render_system_prompt(tools: list[dict[str, Any]]) -> str:
    lines = [
        "You are an agent running in a Datalox world.",
        "Use only the available tools for the current task.",
        "Base claims on tool observations and cite evidence ids returned by tools.",
        "Tool argument names in the schemas below are authoritative.",
        "Final answer must be structured JSON with task_id, family, diagnosis, evidence_ids, next_action, missing_fields, forbidden_actions_avoided, and task-specific family_output when needed.",
        "Do not cite evidence ids that were not returned by tool observations in this trajectory.",
        "",
        "Available tools:",
    ]
    for tool in tools:
        lines.append(f"- {tool['name']}: {tool['description']}")
        lines.append(f"  input_schema: {json.dumps(tool['input_schema'], sort_keys=True)}")
    return "\n".join(lines)
