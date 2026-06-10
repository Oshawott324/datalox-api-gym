"""Minimal OpenAI-compatible tool-calling runner."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib import error, request

from api_gym.worlds.billing_support_v0.state import TASK_NAME, resolve_state_db_path
from api_gym.worlds.billing_support_v0.tools import TOOL_DEFINITIONS, dispatch_tool_call
from api_gym.worlds.billing_support_v0.verifier import verify_run

SYSTEM_PROMPT = (
    "You are solving a billing_support_v0 API Gym task. Use the provided tools for all state "
    "inspection and mutation. When the ticket is resolved, answer with a concise final summary."
)


def run_openai_compatible_agent(
    *,
    run_dir: Path,
    model: str,
    base_url: str,
    api_key: str | None = None,
    max_turns: int = 12,
) -> dict[str, Any]:
    """Run one sampled task against an OpenAI-compatible chat completions API."""
    run_dir = run_dir.resolve()
    db_path = resolve_state_db_path(run_dir)
    task = json.loads((run_dir / TASK_NAME).read_text(encoding="utf-8"))
    user_prompt = str(task["prompt"])
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    tool_call_rows: list[dict[str, Any]] = []
    final_content = ""
    stop_reason = "max_turns"
    turn_count = 0

    for turn_index in range(max_turns):
        turn_count = turn_index + 1
        response = _chat_completion(
            base_url=base_url,
            api_key=api_key,
            payload={"model": model, "messages": messages, "tools": TOOL_DEFINITIONS, "tool_choice": "auto"},
        )
        message = _assistant_message(response)
        messages.append(message)

        tool_calls = message.get("tool_calls") or []
        if tool_calls:
            for tool_call in tool_calls:
                function = tool_call.get("function", {})
                name = str(function.get("name", ""))
                arguments = function.get("arguments", "{}")
                result = dispatch_tool_call(db_path, tool_call)
                tool_call_rows.append(
                    {
                        "turn": turn_count,
                        "id": tool_call.get("id"),
                        "name": name,
                        "arguments": _parse_arguments(arguments),
                        "result": result,
                    }
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.get("id"),
                        "name": name,
                        "content": json.dumps(result, sort_keys=True),
                    }
                )
            continue

        final_content = str(message.get("content") or "")
        stop_reason = "assistant_final"
        break

    verifier_result = verify_run(run_dir).to_dict()
    final_answer = {"content": final_content, "stop_reason": stop_reason, "turns": turn_count}
    _write_jsonl(run_dir / "messages.jsonl", messages)
    _write_jsonl(run_dir / "tool_calls.jsonl", tool_call_rows)
    (run_dir / "final_answer.json").write_text(json.dumps(final_answer, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (run_dir / "verifier_result.json").write_text(
        json.dumps(verifier_result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {"ok": verifier_result["ok"], "final_answer": final_answer, "verifier_result": verifier_result}


def _chat_completion(*, base_url: str, api_key: str | None, payload: dict[str, Any]) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/chat/completions"
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key is not None:
        headers["Authorization"] = f"Bearer {api_key}"
    req = request.Request(url, data=body, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Chat completion request failed with HTTP {exc.code}: {detail}") from exc


def _assistant_message(response: dict[str, Any]) -> dict[str, Any]:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("Chat completion response did not contain choices.")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise RuntimeError("Chat completion choice did not contain a message object.")
    normalized = dict(message)
    normalized.setdefault("role", "assistant")
    return normalized


def _parse_arguments(arguments: Any) -> dict[str, Any]:
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments or "{}")
        except json.JSONDecodeError:
            return {"_raw": arguments}
        return parsed if isinstance(parsed, dict) else {"_value": parsed}
    return arguments if isinstance(arguments, dict) else {"_value": arguments}


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
