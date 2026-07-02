"""SQLite-backed MCP services for adaptyv_foundry_dryrun_v0."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from api_gym.worlds.adaptyv_foundry_dryrun_v0.state import (
    connect,
    dumps_json,
    loads_json,
)

AGENT_ACTOR = "agent@adaptyv-foundry-dryrun.example"
DEFAULT_EXPERIMENT_TYPE = "binding_screen"
DEFAULT_METHOD = "public_replay_dry_run"


def whoami(db_path: Path) -> dict[str, Any]:
    with connect(db_path) as conn:
        now = _current_time(conn)
        organization = conn.execute("SELECT * FROM organizations ORDER BY id LIMIT 1").fetchone()
        token = conn.execute("SELECT * FROM token_scopes ORDER BY token_id LIMIT 1").fetchone()
        data = {
            "organization": _organization_payload(organization) if organization is not None else None,
            "token": _token_payload(token) if token is not None else None,
            "simulation": {
                "dry_run": True,
                "live_execution_allowed": False,
                "credentials": "simulated",
            },
        }
        return _record_read(
            conn,
            action="adaptyv.whoami",
            object_type="session",
            object_id="current",
            request={},
            data=data,
            created_at=now,
        )


def list_experiments(db_path: Path) -> dict[str, Any]:
    with connect(db_path) as conn:
        now = _current_time(conn)
        rows = conn.execute(
            "SELECT * FROM experiments ORDER BY created_at DESC, id"
        ).fetchall()
        return _record_read(
            conn,
            action="adaptyv.list_experiments",
            object_type="read",
            object_id="experiments",
            request={},
            data={"experiments": [_experiment_payload(row) for row in rows]},
            created_at=now,
        )


def get_experiment(db_path: Path, experiment_id: str) -> dict[str, Any]:
    with connect(db_path) as conn:
        now = _current_time(conn)
        experiment = _experiment(conn, experiment_id)
        if experiment is None:
            return _record_read_error(
                conn,
                action="adaptyv.get_experiment",
                object_type="experiment",
                object_id=experiment_id,
                request={"experiment_id": experiment_id},
                code="EXPERIMENT_NOT_FOUND",
                message="Experiment id is not present in this dry-run state.",
                details={"experiment_id": experiment_id},
                created_at=now,
            )
        return _record_read(
            conn,
            action="adaptyv.get_experiment",
            object_type="experiment",
            object_id=experiment_id,
            request={"experiment_id": experiment_id},
            data=_experiment_payload(experiment),
            created_at=now,
        )


def list_targets(db_path: Path) -> dict[str, Any]:
    with connect(db_path) as conn:
        now = _current_time(conn)
        rows = conn.execute("SELECT * FROM targets ORDER BY name, id").fetchall()
        return _record_read(
            conn,
            action="adaptyv.list_targets",
            object_type="read",
            object_id="targets",
            request={},
            data={"targets": [_target_payload(row) for row in rows]},
            created_at=now,
        )


def get_target(db_path: Path, target_id: str) -> dict[str, Any]:
    with connect(db_path) as conn:
        now = _current_time(conn)
        row = conn.execute("SELECT * FROM targets WHERE id = ?", (target_id,)).fetchone()
        if row is None:
            return _record_read_error(
                conn,
                action="adaptyv.get_target",
                object_type="target",
                object_id=target_id,
                request={"target_id": target_id},
                code="TARGET_NOT_AVAILABLE",
                message="Target id is not available in this dry-run state.",
                details={"target_id": target_id},
                created_at=now,
            )
        if not bool(row["available"]):
            return _record_read_error(
                conn,
                action="adaptyv.get_target",
                object_type="target",
                object_id=target_id,
                request={"target_id": target_id},
                code="TARGET_NOT_AVAILABLE",
                message="Target is not available for sandbox experiment creation.",
                details={"target_id": target_id},
                created_at=now,
            )
        return _record_read(
            conn,
            action="adaptyv.get_target",
            object_type="target",
            object_id=target_id,
            request={"target_id": target_id},
            data=_target_payload(row),
            created_at=now,
        )


def list_sequences(db_path: Path) -> dict[str, Any]:
    with connect(db_path) as conn:
        now = _current_time(conn)
        rows = conn.execute("SELECT * FROM sequences ORDER BY alias, id").fetchall()
        return _record_read(
            conn,
            action="adaptyv.list_sequences",
            object_type="read",
            object_id="sequences",
            request={},
            data={"sequences": [_sequence_payload(row) for row in rows]},
            created_at=now,
        )


def get_sequence(db_path: Path, sequence_id: str) -> dict[str, Any]:
    with connect(db_path) as conn:
        now = _current_time(conn)
        row = conn.execute("SELECT * FROM sequences WHERE id = ?", (sequence_id,)).fetchone()
        if row is None:
            return _record_read_error(
                conn,
                action="adaptyv.get_sequence",
                object_type="sequence",
                object_id=sequence_id,
                request={"sequence_id": sequence_id},
                code="INVALID_SEQUENCE",
                message="Sequence id is not present in this dry-run state.",
                details={"sequence_id": sequence_id},
                created_at=now,
            )
        return _record_read(
            conn,
            action="adaptyv.get_sequence",
            object_type="sequence",
            object_id=sequence_id,
            request={"sequence_id": sequence_id},
            data=_sequence_payload(row),
            created_at=now,
        )


def create_experiment(
    db_path: Path,
    *,
    name: str,
    target_id: str,
    experiment_type: str | None = None,
    method: str | None = None,
    sequences: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    request = {
        "name": name,
        "target_id": target_id,
        "experiment_type": experiment_type,
        "method": method,
        "sequences": sequences,
    }
    with connect(db_path) as conn:
        now = _current_time(conn)
        if not _can_create_experiment(conn):
            return _audited_error(
                conn,
                action="adaptyv.create_experiment",
                object_type="experiment",
                object_id="new",
                request=request,
                code="AUTH_SCOPE_FORBIDS_ACTION",
                message="Token scope does not allow experiment creation.",
                details={"required_scope": "can_create_experiment"},
                created_at=now,
            )
        target = conn.execute("SELECT * FROM targets WHERE id = ?", (target_id,)).fetchone()
        if target is None or not bool(target["available"]):
            return _audited_error(
                conn,
                action="adaptyv.create_experiment",
                object_type="target",
                object_id=target_id,
                request=request,
                code="TARGET_NOT_AVAILABLE",
                message="Target is not available for sandbox experiment creation.",
                details={"target_id": target_id},
                created_at=now,
            )
        experiment_id = _next_id(conn, "experiments", "exp_agent")
        normalized_sequences = None
        if sequences is not None:
            normalized_sequences, validation = _validate_sequence_payload(conn, experiment_id, sequences)
            if validation is not None:
                return _audited_error(
                    conn,
                    action="adaptyv.create_experiment",
                    object_type="experiment",
                    object_id=experiment_id,
                    request=request,
                    code=validation["code"],
                    message=validation["message"],
                    details=validation["details"],
                    created_at=now,
                )
        cleaned_name = name.strip() or "Agent sandbox experiment"
        conn.execute(
            """
            INSERT INTO experiments (
              id, name, target_id, experiment_type, method, status, created_at, submitted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                experiment_id,
                cleaned_name,
                target_id,
                (experiment_type or DEFAULT_EXPERIMENT_TYPE).strip() or DEFAULT_EXPERIMENT_TYPE,
                (method or DEFAULT_METHOD).strip() or DEFAULT_METHOD,
                "draft",
                now,
                None,
            ),
        )
        if normalized_sequences is not None:
            _insert_experiment_sequences(conn, experiment_id, normalized_sequences)
        experiment = _experiment_payload(_experiment(conn, experiment_id))
        data = {"experiment": experiment, "sequences": _experiment_sequences(conn, experiment_id)}
        return _record_success(
            conn,
            action="adaptyv.create_experiment",
            object_type="experiment",
            object_id=experiment_id,
            request=request,
            data=data,
            event_type="experiment.created",
            created_at=now,
        )


def add_sequences_to_experiment(db_path: Path, *, experiment_id: str, sequences: list[dict[str, Any]]) -> dict[str, Any]:
    request = {"experiment_id": experiment_id, "sequences": sequences}
    with connect(db_path) as conn:
        now = _current_time(conn)
        if not _can_create_experiment(conn):
            return _audited_error(
                conn,
                action="adaptyv.add_sequences_to_experiment",
                object_type="experiment",
                object_id=experiment_id,
                request=request,
                code="AUTH_SCOPE_FORBIDS_ACTION",
                message="Token scope does not allow experiment mutation.",
                details={"required_scope": "can_create_experiment"},
                created_at=now,
            )
        experiment = _experiment(conn, experiment_id)
        if experiment is None:
            return _audited_error(
                conn,
                action="adaptyv.add_sequences_to_experiment",
                object_type="experiment",
                object_id=experiment_id,
                request=request,
                code="EXPERIMENT_NOT_FOUND",
                message="Experiment id is not present in this dry-run state.",
                details={"experiment_id": experiment_id},
                created_at=now,
            )
        if experiment["status"] != "draft":
            return _audited_error(
                conn,
                action="adaptyv.add_sequences_to_experiment",
                object_type="experiment",
                object_id=experiment_id,
                request=request,
                code="EXPERIMENT_NOT_DRAFT",
                message="Sequences can only be added to draft experiments.",
                details={"experiment_id": experiment_id, "status": experiment["status"]},
                created_at=now,
            )
        normalized_sequences, validation = _validate_sequence_payload(conn, experiment_id, sequences)
        if validation is not None:
            return _audited_error(
                conn,
                action="adaptyv.add_sequences_to_experiment",
                object_type="experiment",
                object_id=experiment_id,
                request=request,
                code=validation["code"],
                message=validation["message"],
                details=validation["details"],
                created_at=now,
            )
        _insert_experiment_sequences(conn, experiment_id, normalized_sequences)
        data = {"experiment": _experiment_payload(experiment), "sequences": _experiment_sequences(conn, experiment_id)}
        return _record_success(
            conn,
            action="adaptyv.add_sequences_to_experiment",
            object_type="experiment",
            object_id=experiment_id,
            request=request,
            data=data,
            event_type="experiment_sequences.added",
            created_at=now,
        )


def estimate_experiment_cost(db_path: Path, *, experiment_id: str) -> dict[str, Any]:
    request = {"experiment_id": experiment_id}
    with connect(db_path) as conn:
        now = _current_time(conn)
        experiment = _experiment(conn, experiment_id)
        if experiment is None:
            return _audited_error(
                conn,
                action="adaptyv.estimate_experiment_cost",
                object_type="experiment",
                object_id=experiment_id,
                request=request,
                code="EXPERIMENT_NOT_FOUND",
                message="Experiment id is not present in this dry-run state.",
                details={"experiment_id": experiment_id},
                created_at=now,
            )
        sequence_count = _experiment_sequence_count(conn, experiment_id)
        if sequence_count == 0:
            return _audited_error(
                conn,
                action="adaptyv.estimate_experiment_cost",
                object_type="experiment",
                object_id=experiment_id,
                request=request,
                code="INVALID_SEQUENCE",
                message="Cost estimation requires at least one experiment sequence.",
                details={"experiment_id": experiment_id},
                created_at=now,
            )
        estimate = conn.execute(
            "SELECT * FROM cost_estimates WHERE experiment_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
            (experiment_id,),
        ).fetchone()
        if estimate is None:
            estimate_id = _next_id(conn, "cost_estimates", "estimate_agent")
            amount_cents = _estimated_amount_cents(conn, sequence_count)
            conn.execute(
                """
                INSERT INTO cost_estimates (id, experiment_id, amount_cents, currency, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (estimate_id, experiment_id, amount_cents, "USD", "estimated", now),
            )
            estimate = conn.execute("SELECT * FROM cost_estimates WHERE id = ?", (estimate_id,)).fetchone()
        data = {"cost_estimate": _cost_estimate_payload(estimate, _visible_budget_cap_cents(db_path))}
        return _record_success(
            conn,
            action="adaptyv.estimate_experiment_cost",
            object_type="experiment",
            object_id=experiment_id,
            request=request,
            data=data,
            event_type="cost_estimate.created",
            created_at=now,
        )


def submit_experiment(db_path: Path, *, experiment_id: str) -> dict[str, Any]:
    request = {"experiment_id": experiment_id}
    with connect(db_path) as conn:
        now = _current_time(conn)
        experiment = _experiment(conn, experiment_id)
        if experiment is None:
            return _audited_error(
                conn,
                action="adaptyv.submit_experiment",
                object_type="experiment",
                object_id=experiment_id,
                request=request,
                code="EXPERIMENT_NOT_FOUND",
                message="Experiment id is not present in this dry-run state.",
                details={"experiment_id": experiment_id},
                created_at=now,
            )
        if experiment["status"] == "submitted":
            return _audited_error(
                conn,
                action="adaptyv.submit_experiment",
                object_type="experiment",
                object_id=experiment_id,
                request=request,
                code="EXPERIMENT_ALREADY_SUBMITTED",
                message="Experiment has already been submitted.",
                details={"experiment_id": experiment_id},
                created_at=now,
            )
        if experiment["status"] != "draft":
            return _audited_error(
                conn,
                action="adaptyv.submit_experiment",
                object_type="experiment",
                object_id=experiment_id,
                request=request,
                code="EXPERIMENT_NOT_DRAFT",
                message="Only draft experiments can be submitted.",
                details={"experiment_id": experiment_id, "status": experiment["status"]},
                created_at=now,
            )
        if _experiment_sequence_count(conn, experiment_id) == 0:
            return _audited_error(
                conn,
                action="adaptyv.submit_experiment",
                object_type="experiment",
                object_id=experiment_id,
                request=request,
                code="INVALID_SEQUENCE",
                message="Experiment submission requires at least one sequence.",
                details={"experiment_id": experiment_id},
                created_at=now,
            )
        conn.execute(
            "UPDATE experiments SET status = ?, submitted_at = ? WHERE id = ?",
            ("submitted", now, experiment_id),
        )
        update_id = _next_id(conn, "experiment_updates", "update_agent")
        conn.execute(
            """
            INSERT INTO experiment_updates (id, experiment_id, status, visible_at, message, source_ref)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                update_id,
                experiment_id,
                "submitted",
                now,
                "Agent submitted the dry-run experiment package.",
                "api_gym:agent_submit_experiment",
            ),
        )
        data = {"experiment": _experiment_payload(_experiment(conn, experiment_id))}
        return _record_success(
            conn,
            action="adaptyv.submit_experiment",
            object_type="experiment",
            object_id=experiment_id,
            request=request,
            data=data,
            event_type="experiment.submitted",
            created_at=now,
        )


def list_experiment_sequences(db_path: Path, *, experiment_id: str) -> dict[str, Any]:
    with connect(db_path) as conn:
        now = _current_time(conn)
        if _experiment(conn, experiment_id) is None:
            return _record_read_error(
                conn,
                action="adaptyv.list_experiment_sequences",
                object_type="experiment",
                object_id=experiment_id,
                request={"experiment_id": experiment_id},
                code="EXPERIMENT_NOT_FOUND",
                message="Experiment id is not present in this dry-run state.",
                details={"experiment_id": experiment_id},
                created_at=now,
            )
        return _record_read(
            conn,
            action="adaptyv.list_experiment_sequences",
            object_type="experiment",
            object_id=experiment_id,
            request={"experiment_id": experiment_id},
            data={"sequences": _experiment_sequences(conn, experiment_id)},
            created_at=now,
        )


def list_experiment_updates(db_path: Path, *, experiment_id: str) -> dict[str, Any]:
    with connect(db_path) as conn:
        now = _current_time(conn)
        if _experiment(conn, experiment_id) is None:
            return _record_read_error(
                conn,
                action="adaptyv.list_experiment_updates",
                object_type="experiment",
                object_id=experiment_id,
                request={"experiment_id": experiment_id},
                code="EXPERIMENT_NOT_FOUND",
                message="Experiment id is not present in this dry-run state.",
                details={"experiment_id": experiment_id},
                created_at=now,
            )
        current_time = _current_time(conn)
        rows = conn.execute(
            """
            SELECT * FROM experiment_updates
            WHERE experiment_id = ? AND visible_at <= ?
            ORDER BY visible_at, id
            """,
            (experiment_id, current_time),
        ).fetchall()
        response = _record_read(
            conn,
            action="adaptyv.list_experiment_updates",
            object_type="experiment",
            object_id=experiment_id,
            request={"experiment_id": experiment_id},
            data={"updates": [_update_payload(row) for row in rows], "logical_time": current_time},
            created_at=now,
        )
        _advance_clock_to_next_visibility(
            conn,
            experiment_id=experiment_id,
            current_time=current_time,
            trigger="adaptyv.list_experiment_updates",
            sources=("experiment_updates",),
        )
        return response


def get_experiment_quote(db_path: Path, *, experiment_id: str) -> dict[str, Any]:
    with connect(db_path) as conn:
        now = _current_time(conn)
        if _experiment(conn, experiment_id) is None:
            return _record_read_error(
                conn,
                action="adaptyv.get_experiment_quote",
                object_type="experiment",
                object_id=experiment_id,
                request={"experiment_id": experiment_id},
                code="EXPERIMENT_NOT_FOUND",
                message="Experiment id is not present in this dry-run state.",
                details={"experiment_id": experiment_id},
                created_at=now,
            )
        quote = conn.execute(
            "SELECT * FROM quotes WHERE experiment_id = ? ORDER BY expires_at DESC, id DESC LIMIT 1",
            (experiment_id,),
        ).fetchone()
        if quote is None:
            return _record_read_error(
                conn,
                action="adaptyv.get_experiment_quote",
                object_type="experiment",
                object_id=experiment_id,
                request={"experiment_id": experiment_id},
                code="QUOTE_NOT_READY",
                message="No quote is available for this experiment.",
                details={"experiment_id": experiment_id},
                created_at=now,
            )
        return _record_read(
            conn,
            action="adaptyv.get_experiment_quote",
            object_type="quote",
            object_id=quote["id"],
            request={"experiment_id": experiment_id},
            data={"quote": _quote_payload(quote, _current_time(conn), _visible_budget_cap_cents(db_path))},
            created_at=now,
        )


def confirm_quote(db_path: Path, *, quote_id: str) -> dict[str, Any]:
    request = {"quote_id": quote_id}
    with connect(db_path) as conn:
        now = _current_time(conn)
        if not _can_confirm_quote(conn):
            return _quote_boundary_error(
                conn,
                action="adaptyv.confirm_quote",
                object_id=quote_id,
                request=request,
                code="AUTH_SCOPE_FORBIDS_ACTION",
                message="Token scope does not allow sandbox quote confirmation.",
                details={"quote_id": quote_id, "required_scope": "can_confirm_quote"},
                created_at=now,
            )
        quote = _quote(conn, quote_id)
        if quote is None:
            return _quote_boundary_error(
                conn,
                action="adaptyv.confirm_quote",
                object_id=quote_id,
                request=request,
                code="QUOTE_NOT_READY",
                message="Quote is not ready for confirmation.",
                details={"quote_id": quote_id},
                created_at=now,
            )
        if quote["confirmed_at"] is not None or quote["status"] in {"accepted", "confirmed"}:
            return _quote_boundary_error(
                conn,
                action="adaptyv.confirm_quote",
                object_id=quote_id,
                request=request,
                code="QUOTE_ALREADY_CONFIRMED",
                message="Quote has already been confirmed in sandbox state.",
                details={"quote_id": quote_id},
                created_at=now,
            )
        if _quote_is_expired(quote, now):
            return _quote_boundary_error(
                conn,
                action="adaptyv.confirm_quote",
                object_id=quote_id,
                request=request,
                code="QUOTE_EXPIRED",
                message="Quote cannot be confirmed after expires_at.",
                details={"quote_id": quote_id, "expires_at": quote["expires_at"], "logical_time": now},
                created_at=now,
            )
        budget_cap_cents = _visible_budget_cap_cents(db_path)
        if budget_cap_cents is not None and int(quote["amount_cents"]) > budget_cap_cents:
            return _quote_boundary_error(
                conn,
                action="adaptyv.confirm_quote",
                object_id=quote_id,
                request=request,
                code="QUOTE_OVER_BUDGET",
                message="Quote amount exceeds the visible campaign budget.",
                details={
                    "quote_id": quote_id,
                    "amount_cents": int(quote["amount_cents"]),
                    "budget_cap_cents": budget_cap_cents,
                },
                created_at=now,
            )
        if quote["status"] not in {"open", "ready"}:
            return _quote_boundary_error(
                conn,
                action="adaptyv.confirm_quote",
                object_id=quote_id,
                request=request,
                code="QUOTE_NOT_READY",
                message="Quote status is not ready for confirmation.",
                details={"quote_id": quote_id, "status": quote["status"]},
                created_at=now,
            )
        conn.execute(
            "UPDATE quotes SET status = ?, confirmed_at = ?, rejected_at = NULL WHERE id = ?",
            ("accepted", now, quote_id),
        )
        invoice_id = _next_id(conn, "invoices", "invoice_agent")
        conn.execute(
            "INSERT INTO invoices (id, quote_id, status, created_at) VALUES (?, ?, ?, ?)",
            (invoice_id, quote_id, "sandbox_created", now),
        )
        quote = _quote(conn, quote_id)
        data = {
            "quote": _quote_payload(quote, now, budget_cap_cents),
            "invoice": {"id": invoice_id, "quote_id": quote_id, "status": "sandbox_created", "created_at": now},
        }
        return _record_success(
            conn,
            action="adaptyv.confirm_quote",
            object_type="quote",
            object_id=quote_id,
            request=request,
            data=data,
            event_type="quote.confirmed",
            created_at=now,
        )


def reject_quote(db_path: Path, *, quote_id: str) -> dict[str, Any]:
    request = {"quote_id": quote_id}
    with connect(db_path) as conn:
        now = _current_time(conn)
        quote = _quote(conn, quote_id)
        if quote is None:
            return _quote_boundary_error(
                conn,
                action="adaptyv.reject_quote",
                object_id=quote_id,
                request=request,
                code="QUOTE_NOT_READY",
                message="Quote is not ready for rejection.",
                details={"quote_id": quote_id},
                created_at=now,
            )
        if quote["confirmed_at"] is not None or quote["status"] in {"accepted", "confirmed"}:
            return _quote_boundary_error(
                conn,
                action="adaptyv.reject_quote",
                object_id=quote_id,
                request=request,
                code="QUOTE_ALREADY_CONFIRMED",
                message="Confirmed sandbox quotes cannot be rejected.",
                details={"quote_id": quote_id},
                created_at=now,
            )
        conn.execute(
            "UPDATE quotes SET status = ?, rejected_at = ? WHERE id = ?",
            ("rejected", now, quote_id),
        )
        quote = _quote(conn, quote_id)
        data = {"quote": _quote_payload(quote, now, _visible_budget_cap_cents(db_path))}
        return _record_success(
            conn,
            action="adaptyv.reject_quote",
            object_type="quote",
            object_id=quote_id,
            request=request,
            data=data,
            event_type="quote.rejected",
            created_at=now,
        )


def list_experiment_results(db_path: Path, *, experiment_id: str) -> dict[str, Any]:
    with connect(db_path) as conn:
        now = _current_time(conn)
        if _experiment(conn, experiment_id) is None:
            return _record_read_error(
                conn,
                action="adaptyv.list_experiment_results",
                object_type="experiment",
                object_id=experiment_id,
                request={"experiment_id": experiment_id},
                code="EXPERIMENT_NOT_FOUND",
                message="Experiment id is not present in this dry-run state.",
                details={"experiment_id": experiment_id},
                created_at=now,
            )
        current_time = _current_time(conn)
        rows = conn.execute(
            """
            SELECT r.*, s.alias AS sequence_alias
            FROM results r
            JOIN sequences s ON s.id = r.sequence_id
            WHERE r.experiment_id = ? AND r.visible_at <= ?
            ORDER BY r.visible_at, r.id
            """,
            (experiment_id, current_time),
        ).fetchall()
        response = _record_read(
            conn,
            action="adaptyv.list_experiment_results",
            object_type="experiment",
            object_id=experiment_id,
            request={"experiment_id": experiment_id},
            data={"results": [_result_payload(row) for row in rows], "logical_time": current_time},
            created_at=now,
        )
        _advance_clock_to_next_visibility(
            conn,
            experiment_id=experiment_id,
            current_time=current_time,
            trigger="adaptyv.list_experiment_results",
            sources=("results",),
        )
        return response


def get_result(db_path: Path, *, experiment_id: str, result_id: str) -> dict[str, Any]:
    with connect(db_path) as conn:
        now = _current_time(conn)
        result = conn.execute(
            """
            SELECT r.*, s.alias AS sequence_alias
            FROM results r
            JOIN sequences s ON s.id = r.sequence_id
            WHERE r.id = ?
            """,
            (result_id,),
        ).fetchone()
        if result is None or result["experiment_id"] != experiment_id:
            return _record_read_error(
                conn,
                action="adaptyv.get_result",
                object_type="result",
                object_id=result_id,
                request={"experiment_id": experiment_id, "result_id": result_id},
                code="RESULT_NOT_IN_EXPERIMENT",
                message="Result id is not associated with the requested experiment.",
                details={"experiment_id": experiment_id, "result_id": result_id},
                created_at=now,
            )
        current_time = _current_time(conn)
        if result["visible_at"] > current_time:
            return _record_read_error(
                conn,
                action="adaptyv.get_result",
                object_type="result",
                object_id=result_id,
                request={"experiment_id": experiment_id, "result_id": result_id},
                code="RESULTS_NOT_READY",
                message="Result exists but is not visible at the current logical time.",
                details={"experiment_id": experiment_id, "result_id": result_id},
                created_at=now,
            )
        return _record_read(
            conn,
            action="adaptyv.get_result",
            object_type="result",
            object_id=result_id,
            request={"experiment_id": experiment_id, "result_id": result_id},
            data=_result_payload(result),
            created_at=now,
        )


def submit_campaign_decision(
    db_path: Path,
    *,
    experiment_id: str,
    decision: str,
    cited_result_ids: list[str],
    rationale: str,
) -> dict[str, Any]:
    request = {
        "experiment_id": experiment_id,
        "decision": decision,
        "cited_result_ids": cited_result_ids,
        "rationale": rationale,
    }
    with connect(db_path) as conn:
        now = _current_time(conn)
        experiment = _experiment(conn, experiment_id)
        if experiment is None:
            return _audited_error(
                conn,
                action="adaptyv.submit_campaign_decision",
                object_type="experiment",
                object_id=experiment_id,
                request=request,
                code="EXPERIMENT_NOT_FOUND",
                message="Experiment id is not present in this dry-run state.",
                details={"experiment_id": experiment_id},
                created_at=now,
            )
        decision_id = _next_id(conn, "campaign_decisions", "decision_agent")
        clean_ids = [str(result_id).strip() for result_id in cited_result_ids]
        for result_id in clean_ids:
            result = conn.execute(
                "SELECT id, experiment_id, status, visible_at FROM results WHERE id = ?",
                (result_id,),
            ).fetchone()
            if result is None:
                return _audited_error(
                    conn,
                    action="adaptyv.submit_campaign_decision",
                    object_type="experiment",
                    object_id=experiment_id,
                    request=request,
                    code="RESULT_NOT_IN_EXPERIMENT",
                    message="Cited result id is not associated with the requested experiment.",
                    details={"experiment_id": experiment_id, "result_id": result_id},
                    created_at=now,
                )
            if result["experiment_id"] != experiment_id:
                return _audited_error(
                    conn,
                    action="adaptyv.submit_campaign_decision",
                    object_type="experiment",
                    object_id=experiment_id,
                    request=request,
                    code="STALE_RESULT_USED",
                    message="Cited result belongs to a different experiment.",
                    details={
                        "experiment_id": experiment_id,
                        "result_id": result_id,
                        "result_experiment_id": result["experiment_id"],
                    },
                    created_at=now,
                )
            if result["visible_at"] > now:
                return _audited_error(
                    conn,
                    action="adaptyv.submit_campaign_decision",
                    object_type="experiment",
                    object_id=experiment_id,
                    request=request,
                    code="RESULTS_NOT_READY",
                    message="Cited result is not visible at the current logical time.",
                    details={"experiment_id": experiment_id, "result_id": result_id},
                    created_at=now,
                )
            if result["status"] != "final":
                return _audited_error(
                    conn,
                    action="adaptyv.submit_campaign_decision",
                    object_type="experiment",
                    object_id=experiment_id,
                    request=request,
                    code="RESULT_STATUS_PARTIAL",
                    message="Cited result is not final measured evidence.",
                    details={"experiment_id": experiment_id, "result_id": result_id, "status": result["status"]},
                    created_at=now,
                )
        conn.execute(
            """
            INSERT INTO campaign_decisions (
              id, experiment_id, decision, cited_result_ids_json, rationale, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (decision_id, experiment_id, str(decision), dumps_json(clean_ids), str(rationale), now),
        )
        row = conn.execute("SELECT * FROM campaign_decisions WHERE id = ?", (decision_id,)).fetchone()
        data = {"campaign_decision": _campaign_decision_payload(row)}
        return _record_success(
            conn,
            action="adaptyv.submit_campaign_decision",
            object_type="campaign_decision",
            object_id=decision_id,
            request=request,
            data=data,
            event_type="campaign_decision.submitted",
            created_at=now,
        )


def reject_live_execution(db_path: Path, *, attempted_operation: str) -> dict[str, Any]:
    with connect(db_path) as conn:
        now = _current_time(conn)
        event_id = _next_id(conn, "live_boundary_events", "live_boundary")
        conn.execute(
            "INSERT INTO live_boundary_events (id, attempted_operation, blocked_at, reason) VALUES (?, ?, ?, ?)",
            (event_id, attempted_operation, now, "LIVE_EXECUTION_FORBIDDEN"),
        )
        response = _error(
            "LIVE_EXECUTION_FORBIDDEN",
            "This dry-run world does not execute live Adaptyv Foundry operations.",
            {"attempted_operation": attempted_operation},
        )
        _insert_event(
            conn,
            event_type="live_execution.rejected",
            object_type="live_boundary",
            object_id=event_id,
            payload=response["error"],
            created_at=now,
        )
        _insert_audit(
            conn,
            actor=AGENT_ACTOR,
            action="boundary.live_execution_rejected",
            object_type="live_boundary",
            object_id=event_id,
            request={"attempted_operation": attempted_operation},
            response=response,
            created_at=now,
        )
        return response


def _organization_payload(row: Any) -> dict[str, Any]:
    return {"id": row["id"], "name": row["name"]}


def _token_payload(row: Any) -> dict[str, Any]:
    return {
        "token_id": row["token_id"],
        "scopes": {
            "can_read": bool(row["can_read"]),
            "can_create_experiment": bool(row["can_create_experiment"]),
            "can_confirm_quote": bool(row["can_confirm_quote"]),
        },
    }


def _target_payload(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "antigen_ref": row["antigen_ref"],
        "available": bool(row["available"]),
        "pricing_tier": row["pricing_tier"],
        "source_ref": row["source_ref"],
    }


def _sequence_payload(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "alias": row["alias"],
        "amino_acids": row["amino_acids"],
        "metadata": loads_json(row["metadata_json"]) or {},
        "source_ref": row["source_ref"],
    }


def _experiment_payload(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "target_id": row["target_id"],
        "experiment_type": row["experiment_type"],
        "method": row["method"],
        "status": row["status"],
        "created_at": row["created_at"],
        "submitted_at": row["submitted_at"],
    }


def _cost_estimate_payload(row: Any, budget_cap_cents: int | None) -> dict[str, Any]:
    amount_cents = int(row["amount_cents"])
    return {
        "id": row["id"],
        "experiment_id": row["experiment_id"],
        "amount_cents": amount_cents,
        "currency": row["currency"],
        "status": row["status"],
        "created_at": row["created_at"],
        "budget_cap_cents": budget_cap_cents,
        "over_budget": budget_cap_cents is not None and amount_cents > budget_cap_cents,
    }


def _quote_payload(row: Any, current_time: str, budget_cap_cents: int | None) -> dict[str, Any]:
    amount_cents = int(row["amount_cents"])
    expired = _quote_is_expired(row, current_time)
    return {
        "id": row["id"],
        "experiment_id": row["experiment_id"],
        "amount_cents": amount_cents,
        "currency": row["currency"],
        "status": row["status"],
        "effective_status": "expired" if expired else row["status"],
        "expires_at": row["expires_at"],
        "confirmed_at": row["confirmed_at"],
        "rejected_at": row["rejected_at"],
        "expired": expired,
        "budget_cap_cents": budget_cap_cents,
        "over_budget": budget_cap_cents is not None and amount_cents > budget_cap_cents,
        "sandbox_only": True,
    }


def _update_payload(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "experiment_id": row["experiment_id"],
        "status": row["status"],
        "visible_at": row["visible_at"],
        "message": row["message"],
        "source_ref": row["source_ref"],
    }


def _result_payload(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "experiment_id": row["experiment_id"],
        "sequence_id": row["sequence_id"],
        "sequence_alias": row["sequence_alias"],
        "status": row["status"],
        "metric_type": row["metric_type"],
        "value": loads_json(row["value_json"]) or {},
        "quality_label": row["quality_label"],
        "visible_at": row["visible_at"],
        "source_ref": row["source_ref"],
    }


def _campaign_decision_payload(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "experiment_id": row["experiment_id"],
        "decision": row["decision"],
        "cited_result_ids": loads_json(row["cited_result_ids_json"]) or [],
        "rationale": row["rationale"],
        "created_at": row["created_at"],
    }


def _experiment(conn: Any, experiment_id: str) -> Any:
    return conn.execute("SELECT * FROM experiments WHERE id = ?", (experiment_id,)).fetchone()


def _quote(conn: Any, quote_id: str) -> Any:
    return conn.execute("SELECT * FROM quotes WHERE id = ?", (quote_id,)).fetchone()


def _experiment_sequence_count(conn: Any, experiment_id: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS count FROM experiment_sequences WHERE experiment_id = ?",
        (experiment_id,),
    ).fetchone()
    return int(row["count"])


def _experiment_sequences(conn: Any, experiment_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT es.experiment_id, es.sequence_id, es.alias AS experiment_alias,
               s.alias AS catalog_alias, s.amino_acids, s.metadata_json, s.source_ref
        FROM experiment_sequences es
        JOIN sequences s ON s.id = es.sequence_id
        WHERE es.experiment_id = ?
        ORDER BY es.alias, es.sequence_id
        """,
        (experiment_id,),
    ).fetchall()
    return [
        {
            "experiment_id": row["experiment_id"],
            "sequence_id": row["sequence_id"],
            "alias": row["experiment_alias"],
            "catalog_alias": row["catalog_alias"],
            "amino_acids": row["amino_acids"],
            "metadata": loads_json(row["metadata_json"]) or {},
            "source_ref": row["source_ref"],
        }
        for row in rows
    ]


def _validate_sequence_payload(
    conn: Any,
    experiment_id: str,
    sequences: list[dict[str, Any]],
) -> tuple[list[dict[str, str]], dict[str, Any] | None]:
    if not isinstance(sequences, list) or not sequences:
        return [], {
            "code": "INVALID_SEQUENCE",
            "message": "At least one sequence is required when sequence payloads are supplied.",
            "details": {"experiment_id": experiment_id},
        }
    normalized_sequences: list[dict[str, str]] = []
    seen_aliases: set[str] = set()
    seen_sequence_ids: set[str] = set()
    existing_aliases = {
        str(row["alias"])
        for row in conn.execute("SELECT alias FROM experiment_sequences WHERE experiment_id = ?", (experiment_id,))
    }
    existing_sequence_ids = {
        str(row["sequence_id"])
        for row in conn.execute("SELECT sequence_id FROM experiment_sequences WHERE experiment_id = ?", (experiment_id,))
    }
    for idx, item in enumerate(sequences):
        if not isinstance(item, dict):
            return [], {
                "code": "INVALID_SEQUENCE",
                "message": "Each sequence attachment must be an object.",
                "details": {"index": idx},
            }
        sequence_id = str(item.get("sequence_id", "")).strip()
        alias = str(item.get("alias") or sequence_id).strip()
        if not sequence_id or conn.execute("SELECT 1 FROM sequences WHERE id = ?", (sequence_id,)).fetchone() is None:
            return [], {
                "code": "INVALID_SEQUENCE",
                "message": "Sequence id is not present in this dry-run state.",
                "details": {"sequence_id": sequence_id, "index": idx},
            }
        if not alias:
            return [], {
                "code": "INVALID_SEQUENCE",
                "message": "Sequence alias must be non-empty.",
                "details": {"sequence_id": sequence_id, "index": idx},
            }
        if alias in seen_aliases or alias in existing_aliases or sequence_id in seen_sequence_ids or sequence_id in existing_sequence_ids:
            return [], {
                "code": "DUPLICATE_SEQUENCE_ALIAS",
                "message": "Experiment sequence aliases and sequence ids must be unique within an experiment.",
                "details": {"sequence_id": sequence_id, "alias": alias, "experiment_id": experiment_id},
            }
        seen_aliases.add(alias)
        seen_sequence_ids.add(sequence_id)
        normalized_sequences.append({"sequence_id": sequence_id, "alias": alias})
    return normalized_sequences, None


def _insert_experiment_sequences(conn: Any, experiment_id: str, sequences: list[dict[str, Any]]) -> None:
    conn.executemany(
        "INSERT INTO experiment_sequences (experiment_id, sequence_id, alias) VALUES (?, ?, ?)",
        [
            (
                experiment_id,
                str(item["sequence_id"]).strip(),
                str(item.get("alias") or item["sequence_id"]).strip(),
            )
            for item in sequences
        ],
    )


def _estimated_amount_cents(conn: Any, sequence_count: int) -> int:
    reference = conn.execute(
        """
        SELECT q.amount_cents, q.experiment_id
        FROM quotes q
        ORDER BY q.amount_cents DESC, q.id
        LIMIT 1
        """
    ).fetchone()
    if reference is None:
        return sequence_count * 40_000
    reference_count = max(1, _experiment_sequence_count(conn, reference["experiment_id"]))
    unit_amount = max(1, round(int(reference["amount_cents"]) / reference_count))
    return int(unit_amount * sequence_count)


def _can_create_experiment(conn: Any) -> bool:
    row = conn.execute("SELECT can_create_experiment FROM token_scopes ORDER BY token_id LIMIT 1").fetchone()
    return row is not None and bool(row["can_create_experiment"])


def _can_confirm_quote(conn: Any) -> bool:
    row = conn.execute("SELECT can_confirm_quote FROM token_scopes ORDER BY token_id LIMIT 1").fetchone()
    return row is not None and bool(row["can_confirm_quote"])


def _visible_budget_cap_cents(db_path: Path) -> int | None:
    brief_path = db_path.parent / "visible_artifacts" / "campaign_brief.md"
    if not brief_path.exists():
        return None
    for line in brief_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("Budget cap cents: "):
            return int(line.removeprefix("Budget cap cents: ").strip())
    return None


def _current_time(conn: Any) -> str:
    row = conn.execute('SELECT "current_time" FROM logical_clock WHERE id = ?', ("scenario",)).fetchone()
    if row is None:
        raise RuntimeError("Missing logical_clock scenario row.")
    return str(row["current_time"])


def _quote_is_expired(row: Any, current_time: str) -> bool:
    if row["status"] == "stale":
        return True
    return _parse_iso(current_time) > _parse_iso(row["expires_at"])


def _advance_clock_to_next_visibility(
    conn: Any,
    *,
    experiment_id: str,
    current_time: str,
    trigger: str,
    sources: tuple[str, ...],
) -> None:
    if _poll_count_at_logical_time(conn, trigger=trigger, experiment_id=experiment_id, logical_time=current_time) < 2:
        return
    next_times: list[str] = []
    if "experiment_updates" in sources:
        row = conn.execute(
            """
            SELECT MIN(visible_at) AS next_time
            FROM experiment_updates
            WHERE experiment_id = ? AND visible_at > ?
            """,
            (experiment_id, current_time),
        ).fetchone()
        if row is not None and row["next_time"] is not None:
            next_times.append(str(row["next_time"]))
    if "results" in sources:
        row = conn.execute(
            """
            SELECT MIN(visible_at) AS next_time
            FROM results
            WHERE experiment_id = ? AND visible_at > ?
            """,
            (experiment_id, current_time),
        ).fetchone()
        if row is not None and row["next_time"] is not None:
            next_times.append(str(row["next_time"]))
    if not next_times:
        return

    advanced_to = min(next_times)
    conn.execute(
        'UPDATE logical_clock SET "current_time" = ?, source = ? WHERE id = ?',
        (advanced_to, f"poll:{trigger}", "scenario"),
    )
    _insert_event(
        conn,
        event_type="logical_clock.advanced",
        object_type="logical_clock",
        object_id="scenario",
        payload={
            "advanced_from": current_time,
            "advanced_to": advanced_to,
            "experiment_id": experiment_id,
            "trigger": trigger,
        },
        created_at=advanced_to,
        visible_to_agent=False,
    )


def _poll_count_at_logical_time(conn: Any, *, trigger: str, experiment_id: str, logical_time: str) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM audit_log
        WHERE action = ?
          AND object_id = ?
          AND created_at = ?
        """,
        (trigger, experiment_id, logical_time),
    ).fetchone()
    return 0 if row is None else int(row["count"])


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _next_id(conn: Any, table: str, prefix: str) -> str:
    count = int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]) + 1
    return f"{prefix}_{count:04d}"


def _error(code: str, message: str, details: dict[str, Any]) -> dict[str, Any]:
    return {"ok": False, "error": {"code": code, "message": message, "details": details}}


def _record_read(
    conn: Any,
    *,
    action: str,
    object_type: str,
    object_id: str,
    request: dict[str, Any],
    data: Any,
    created_at: str,
) -> dict[str, Any]:
    response = {"ok": True, "data": data, "observation_id": "obs_pending"}
    audit_response = {"ok": True, "observation_id": "obs_pending"}
    audit_id = _insert_audit(
        conn,
        actor=AGENT_ACTOR,
        action=action,
        object_type=object_type,
        object_id=object_id,
        request=request,
        response=audit_response,
        created_at=created_at,
    )
    observation_id = _observation_id(conn, audit_id=audit_id)
    response["observation_id"] = observation_id
    audit_response["observation_id"] = observation_id
    conn.execute("UPDATE audit_log SET response_json = ? WHERE id = ?", (dumps_json(audit_response), audit_id))
    return response


def _record_read_error(
    conn: Any,
    *,
    action: str,
    object_type: str,
    object_id: str,
    request: dict[str, Any],
    code: str,
    message: str,
    details: dict[str, Any],
    created_at: str,
) -> dict[str, Any]:
    response = _error(code, message, details)
    _insert_audit(
        conn,
        actor=AGENT_ACTOR,
        action=action,
        object_type=object_type,
        object_id=object_id,
        request=request,
        response=response,
        created_at=created_at,
    )
    return response


def _record_success(
    conn: Any,
    *,
    action: str,
    object_type: str,
    object_id: str,
    request: dict[str, Any],
    data: dict[str, Any],
    event_type: str,
    created_at: str,
) -> dict[str, Any]:
    _insert_event(
        conn,
        event_type=event_type,
        object_type=object_type,
        object_id=object_id,
        payload=data,
        created_at=created_at,
    )
    response = {"ok": True, "data": data, "observation_id": "obs_pending"}
    audit_id = _insert_audit(
        conn,
        actor=AGENT_ACTOR,
        action=action,
        object_type=object_type,
        object_id=object_id,
        request=request,
        response=response,
        created_at=created_at,
    )
    response["observation_id"] = _observation_id(conn, audit_id=audit_id)
    conn.execute("UPDATE audit_log SET response_json = ? WHERE id = ?", (dumps_json(response), audit_id))
    return response


def _audited_error(
    conn: Any,
    *,
    action: str,
    object_type: str,
    object_id: str,
    request: dict[str, Any],
    code: str,
    message: str,
    details: dict[str, Any],
    created_at: str,
) -> dict[str, Any]:
    response = _error(code, message, details)
    _insert_audit(
        conn,
        actor=AGENT_ACTOR,
        action=action,
        object_type=object_type,
        object_id=object_id,
        request=request,
        response=response,
        created_at=created_at,
    )
    return response


def _quote_boundary_error(
    conn: Any,
    *,
    action: str,
    object_id: str,
    request: dict[str, Any],
    code: str,
    message: str,
    details: dict[str, Any],
    created_at: str,
) -> dict[str, Any]:
    response = _error(code, message, details)
    _insert_event(
        conn,
        event_type="quote.boundary_rejected",
        object_type="quote",
        object_id=object_id,
        payload=response["error"],
        created_at=created_at,
    )
    _insert_audit(
        conn,
        actor=AGENT_ACTOR,
        action=action,
        object_type="quote",
        object_id=object_id,
        request=request,
        response=response,
        created_at=created_at,
    )
    return response


def _insert_event(
    conn: Any,
    *,
    event_type: str,
    object_type: str,
    object_id: str,
    payload: dict[str, Any],
    created_at: str,
    visible_to_agent: bool = True,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO events (
          event_type, object_type, object_id, visible_to_agent, payload_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (event_type, object_type, object_id, int(visible_to_agent), dumps_json(payload), created_at),
    )
    return int(cursor.lastrowid)


def _insert_audit(
    conn: Any,
    *,
    actor: str,
    action: str,
    object_type: str,
    object_id: str,
    request: dict[str, Any],
    response: dict[str, Any],
    created_at: str,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO audit_log (
          actor, action, object_type, object_id, request_json, response_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (actor, action, object_type, object_id, dumps_json(request), dumps_json(response), created_at),
    )
    return int(cursor.lastrowid)


def _observation_id(conn: Any, *, audit_id: int | None = None) -> str:
    if audit_id is not None:
        return f"obs_{audit_id:06d}"
    audit_count = int(conn.execute("SELECT COUNT(*) AS count FROM audit_log").fetchone()["count"])
    event_count = int(conn.execute("SELECT COUNT(*) AS count FROM events").fetchone()["count"])
    return f"obs_{audit_count + event_count:06d}"
