from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_ROOT = REPO_ROOT / "worlds" / "billing_support_v0" / "evidence"
OBSERVED_PATH = EVIDENCE_ROOT / "observed_instances.jsonl"
NORMALIZED_PATH = EVIDENCE_ROOT / "normalized_cases.jsonl"
PROBE_PATH = EVIDENCE_ROOT / "probes" / "stripe_refund_instances.py"


def test_phase5_observed_instances_are_doc_grounded() -> None:
    rows = _read_jsonl(OBSERVED_PATH)

    assert rows
    ids = [row["id"] for row in rows]
    assert len(ids) == len(set(ids))

    for row in rows:
        assert row["schema_version"] == "api_gym.observed_provider_instance.v0"
        assert row["source_type"] in {"docs", "live_probe"}
        assert row["provider"] in {"stripe", "zendesk", "hubspot"}
        assert row["operation"]
        assert row["case"]
        assert isinstance(row["request_shape"], dict)
        assert row.get("response_shape") is not None or row.get("error_shape") is not None

        if row["source_type"] == "docs":
            assert row["source_url"].startswith(("https://docs.stripe.com/", "https://developer.zendesk.com/"))
            grounding_note = row["grounding_note"].lower()
            assert "not observed sandbox behavior" in grounding_note or "doc-derived" in grounding_note

    assert any(row["provider"] == "stripe" and row["operation"] == "refund.create" for row in rows)


def test_phase5_normalized_cases_cite_observed_instances() -> None:
    observed_ids = {row["id"] for row in _read_jsonl(OBSERVED_PATH)}
    rows = _read_jsonl(NORMALIZED_PATH)

    assert rows
    ids = [row["id"] for row in rows]
    assert len(ids) == len(set(ids))

    for row in rows:
        assert row["schema_version"] == "api_gym.normalized_provider_case.v0"
        assert row["world"] == "billing_support_v0"
        assert row["provider"] in {"stripe", "zendesk", "hubspot"}
        assert row["operation"]
        assert row["behavior"]
        assert row["fake_world_implication"]
        assert row["observed_instance_ids"]
        assert set(row["observed_instance_ids"]) <= observed_ids

    assert any(row["case"] == "remaining_amount_cap" for row in rows)
    assert any(row["case"] == "reason_values" for row in rows)


def test_phase5_evidence_files_do_not_contain_stripe_secret_keys() -> None:
    secret_pattern = re.compile(r"sk_(?:live|test)_[A-Za-z0-9]{16,}")
    for path in [OBSERVED_PATH, NORMALIZED_PATH, EVIDENCE_ROOT / "README.md", PROBE_PATH]:
        text = path.read_text(encoding="utf-8")
        assert secret_pattern.search(text) is None


def test_stripe_probe_key_policy_and_missing_key_error(monkeypatch, capsys, tmp_path: Path) -> None:
    probe = _load_probe_module()

    assert probe.is_test_secret_key("sk_test_example")
    assert not probe.is_test_secret_key("sk_live_example")
    assert not probe.is_test_secret_key("rk_test_example")

    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    code = probe.main(["--out-dir", str(tmp_path)])

    captured = capsys.readouterr()
    assert code == 2
    assert "missing_stripe_key" in captured.err
    assert "sk_live_" not in captured.err
    assert "sk_test_example" not in captured.err


def test_stripe_probe_refuses_live_key_without_unsafe_flag(monkeypatch, capsys, tmp_path: Path) -> None:
    probe = _load_probe_module()
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_example")

    code = probe.main(["--out-dir", str(tmp_path)])

    captured = capsys.readouterr()
    assert code == 2
    assert "stripe_key_refused" in captured.err
    assert "sk_live_example" not in captured.err
    assert not list(tmp_path.glob("*.jsonl"))


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _load_probe_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("stripe_refund_instances", PROBE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
