from __future__ import annotations

from typing import Any


def render_system_prompt(tools: list[dict[str, Any]], task_tool_names: list[str] | None = None) -> str:
    task_tool_names = task_tool_names or [tool["name"] for tool in tools]
    tools_by_name = {tool["name"]: tool for tool in tools}
    lines = [
        "You are an agent running in a Datalox world.",
        "The MCP service exposes the environment tool catalog.",
        "For this task, prefer the task-relevant tools listed below.",
        "Base claims on tool observations and cite evidence ids returned by tools.",
        "Tool argument schemas are provided in the structured tools field.",
        "Final answer must be structured JSON with task_id, family, diagnosis, evidence_ids, next_action, missing_fields, forbidden_actions_avoided, and task-specific family_output when needed.",
        "Do not cite evidence ids that were not returned by tool observations in this trajectory.",
        "",
        "Task-relevant tools:",
    ]
    for name in task_tool_names:
        tool = tools_by_name.get(name)
        if tool is None:
            continue
        _append_tool(lines, tool)
    return "\n".join(lines)


def openai_chat_tools(tools: list[dict[str, Any]], task_tool_names: list[str]) -> list[dict[str, Any]]:
    tools_by_name = {tool["name"]: tool for tool in tools}
    scoped = []
    for name in task_tool_names:
        tool = tools_by_name.get(name)
        if tool is None:
            raise ValueError(f"Missing tool catalog entry: {name}")
        scoped.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["input_schema"],
            },
        })
    return scoped


def _append_tool(lines: list[str], tool: dict[str, Any]) -> None:
    lines.append(f"- {tool['name']}: {tool['description']}")
