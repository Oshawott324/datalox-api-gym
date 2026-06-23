from __future__ import annotations

from pathlib import Path

from api_gym.session import create_world_session


def test_session_manifest_advertises_http_when_available(tmp_path: Path) -> None:
    manifest = create_world_session(
        world="billing_support_v0",
        scenario="duplicate_payment_refund",
        seed=61,
        out_dir=tmp_path / "billing-session",
    )

    assert manifest["http"] == {
        "available": True,
        "recommended_command": ["api-gym", "serve", "--run", manifest["run_dir"]],
        "recommended_base_url": "http://127.0.0.1:8080",
        "trace_path": str(Path(manifest["run_dir"]) / "traces" / "http_requests.jsonl"),
    }
    assert "Start the HTTP server only when the task or host needs provider-shaped HTTP." in manifest[
        "integration_instructions"
    ]


def test_session_manifest_marks_http_unavailable_for_mcp_only_world(tmp_path: Path) -> None:
    manifest = create_world_session(
        world="unitelabs_plate_qc_v0",
        scenario="plate_transfer_qc",
        seed=62,
        out_dir=tmp_path / "unitelabs-session",
    )

    assert manifest["http"] == {
        "available": False,
        "reason": "World 'unitelabs_plate_qc_v0' does not expose an HTTP app.",
    }
