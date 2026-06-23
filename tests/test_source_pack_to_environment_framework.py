from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from api_gym.exports.run_export import build_run_export
from api_gym.server.app import create_app
from api_gym.session import check_session_tools, create_world_session, finalize_world_session
from api_gym.source_packs import validate_source_pack
from api_gym.worlds.source_refs import validate_world_source_refs


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_registered_world_framework_surfaces_work_together(tmp_path: Path) -> None:
    run_dir = tmp_path / "framework-run"

    source_pack_results = [
        validate_source_pack(REPO_ROOT / "source_packs" / "apis" / provider / "2026-06-12")
        for provider in ("stripe", "zendesk", "hubspot")
    ]
    assert [result["ok"] for result in source_pack_results] == [True, True, True]
    assert validate_world_source_refs("billing_support_v0")["ok"] is True

    manifest = create_world_session(
        world="billing_support_v0",
        scenario="duplicate_payment_refund",
        seed=81,
        out_dir=run_dir,
    )
    assert manifest["http"]["available"] is True

    app = create_app(run_dir)
    response = TestClient(app).get("/support/tickets/not-real")
    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert response.json()["error"]["code"] == "ticket_not_found"

    tools = check_session_tools(run_dir)
    assert tools["ok"] is True
    assert "support_get_ticket" in tools["listed_tools"]

    finalization = finalize_world_session(run_dir)
    assert finalization["ok"] is False
    assert finalization["export"]["source_refs"]["world"] == "billing_support_v0"

    export = build_run_export(run_dir)
    assert export["world"] == "billing_support_v0"
    assert export["source_refs"]["world"] == "billing_support_v0"
    assert export["artifacts"]["http_trace"] == str(run_dir / "traces" / "http_requests.jsonl")
    assert len(export["http_trace"]) == 1
    trace = export["http_trace"][0]
    assert trace["schema_version"] == "api_gym.world_http_call.v0"
    assert trace["world"] == "billing_support_v0"
    assert trace["method"] == "GET"
    assert trace["path"] == "/support/tickets/not-real"
    assert trace["query_params"] == {}
    assert trace["request_json"] is None
    assert trace["status_code"] == 200
    assert trace["ok"] is False
    assert trace["error"]["code"] == "ticket_not_found"
