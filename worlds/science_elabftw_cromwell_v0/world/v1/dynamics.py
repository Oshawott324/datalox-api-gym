from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping


def workflow_status(
    workflow: Mapping[str, Any],
    *,
    current_time: str,
) -> str | None:
    """Project the G0 compressed schedule onto captured provider-native statuses."""

    now = datetime.fromisoformat(current_time)
    abort_requested_at = workflow.get("abort_requested_at")
    if isinstance(abort_requested_at, str):
        abort_elapsed = (
            now - datetime.fromisoformat(abort_requested_at)
        ).total_seconds()
        return "Aborted" if abort_elapsed >= 5 else "Aborting"

    elapsed = (now - datetime.fromisoformat(str(workflow["submitted_at"]))).total_seconds()
    if elapsed < int(workflow["visible_after_seconds"]):
        return None
    if elapsed < int(workflow["running_after_seconds"]):
        return "Submitted"
    terminal_after = workflow.get("terminal_after_seconds")
    if terminal_after is None or elapsed < int(terminal_after):
        return "Running"
    return str(workflow["terminal_status"])
