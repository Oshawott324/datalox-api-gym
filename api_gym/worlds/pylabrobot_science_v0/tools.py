"""MCP-facing tool aggregation and dispatch for the science workflow world."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .operations.common import Handler, error, ok, tool_definition
from .operations.incubator_shaker import (
    HANDLERS as INCUBATOR_SHAKER_HANDLERS,
)
from .operations.incubator_shaker import (
    TOOL_DEFINITIONS as INCUBATOR_SHAKER_TOOL_DEFINITIONS,
)
from .operations.powder_balance import HANDLERS as POWDER_BALANCE_HANDLERS
from .operations.powder_balance import (
    TOOL_DEFINITIONS as POWDER_BALANCE_TOOL_DEFINITIONS,
)
from .operations.thermocycler import HANDLERS as THERMOCYCLER_HANDLERS
from .operations.thermocycler import (
    TOOL_DEFINITIONS as THERMOCYCLER_TOOL_DEFINITIONS,
)
from .state import (
    CONTRACT_NAME,
    connect,
    insert_decision,
    insert_event,
    load_state,
    resolve_state_db_path,
)


_INSPECT_TOOL = tool_definition(
    "inspect_science_workcell",
    "Inspect the public state and required workflow contract.",
    {},
    [],
)

_SUBMIT_DECISION_TOOL = tool_definition(
    "submit_science_decision",
    "Submit a run decision tied to a produced evidence artifact.",
    {
        "decision": {"type": "string", "enum": ["accept", "reject"]},
        "evidence_id": {"type": "string"},
        "rationale": {"type": "string", "minLength": 1},
    },
    ["decision", "evidence_id", "rationale"],
)

TOOL_DEFINITIONS = [
    _INSPECT_TOOL,
    *THERMOCYCLER_TOOL_DEFINITIONS,
    *INCUBATOR_SHAKER_TOOL_DEFINITIONS,
    *POWDER_BALANCE_TOOL_DEFINITIONS,
    _SUBMIT_DECISION_TOOL,
]


def _inspect(
    conn: Any,
    _arguments: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    state = load_state(conn)
    insert_event(conn, operation="workcell.inspected", time_s=float(state["clock_s"]))
    return ok(
        {
            "clock_s": state["clock_s"],
            "family": state["family"],
            "state": state,
            "contract": contract,
        }
    )


def _submit_science_decision(
    conn: Any,
    arguments: dict[str, Any],
    _contract: dict[str, Any],
) -> dict[str, Any]:
    state = load_state(conn)
    decision = str(arguments["decision"])
    evidence_id = str(arguments["evidence_id"])
    rationale = str(arguments["rationale"])
    if decision not in {"accept", "reject"}:
        return error("invalid_decision", "Decision must be accept or reject.")
    evidence = conn.execute(
        "SELECT 1 FROM artifacts WHERE artifact_id = ?",
        (evidence_id,),
    ).fetchone()
    if evidence is None:
        return error(
            "unknown_evidence",
            "The referenced evidence artifact does not exist.",
            evidence_id=evidence_id,
        )
    insert_decision(
        conn,
        decision=decision,
        evidence_id=evidence_id,
        rationale=rationale,
        time_s=float(state["clock_s"]),
    )
    insert_event(
        conn,
        operation="science.decision_submitted",
        time_s=float(state["clock_s"]),
        payload={"decision": decision, "evidence_id": evidence_id},
    )
    return ok({"decision": decision, "evidence_id": evidence_id})


HANDLERS: dict[str, Handler] = {
    "inspect_science_workcell": _inspect,
    **THERMOCYCLER_HANDLERS,
    **INCUBATOR_SHAKER_HANDLERS,
    **POWDER_BALANCE_HANDLERS,
    "submit_science_decision": _submit_science_decision,
}


def _contract(run_dir: Path) -> dict[str, Any]:
    return json.loads((run_dir.resolve() / CONTRACT_NAME).read_text(encoding="utf-8"))


def dispatch_tool(
    run_dir: Path,
    *,
    name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    handler = HANDLERS.get(name)
    if handler is None:
        return error("unknown_tool", f"Unknown tool: {name}")
    try:
        with connect(resolve_state_db_path(run_dir)) as conn:
            return handler(conn, arguments, _contract(run_dir))
    except (KeyError, TypeError, ValueError) as exc:
        return error("invalid_arguments", str(exc))
    except RuntimeError as exc:
        return error("operation_rejected", str(exc))
