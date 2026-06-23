from __future__ import annotations

import json
from pathlib import Path

from api_gym.exports.run_export import build_run_export
from api_gym.worlds.billing_support_v0.sampler import sample_episode


def test_run_export_includes_world_source_refs_and_http_trace(tmp_path: Path) -> None:
    episode = sample_episode(
        scenario="duplicate_payment_refund",
        seed=71,
        out_dir=tmp_path / "run",
    )
    trace_path = episode.run_dir / "traces" / "http_requests.jsonl"
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    trace_path.write_text(
        json.dumps(
            {
                "schema_version": "api_gym.world_http_call.v0",
                "method": "GET",
                "path": "/support/tickets/example",
                "status_code": 200,
                "ok": True,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    payload = build_run_export(episode.run_dir)

    assert payload["source_refs"]["path"].endswith("worlds/billing_support_v0/source_refs.json")
    assert payload["source_refs"]["world"] == "billing_support_v0"
    assert len(payload["source_refs"]["source_packs"]) == 3
    assert payload["http_trace"] == [
        {
            "schema_version": "api_gym.world_http_call.v0",
            "method": "GET",
            "path": "/support/tickets/example",
            "status_code": 200,
            "ok": True,
        }
    ]
    assert payload["artifacts"]["http_trace"] == str(trace_path)
