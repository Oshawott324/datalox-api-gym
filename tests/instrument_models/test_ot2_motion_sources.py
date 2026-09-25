import json
from pathlib import Path

import pytest

from api_gym.source_packs import validate_source_pack

ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "probes/ot2_motion/sources"


def test_motion_source_inventory_validates():
    assert validate_source_pack(PACK)["ok"]
    pack = json.loads((PACK / "source_pack.json").read_text())
    assert pack["live_execution"]["allowed"] is False
    assert "provider release" in pack["claim_boundary"]


def test_assets_are_pinned_and_not_promoted_as_ready_geometry():
    records = [json.loads(line) for line in (PACK / "assets.jsonl").read_text().splitlines()]
    assert len(records) == 3
    for record in records:
        assert len(bytes.fromhex(record["sha256"])) == 32
        assert record["bytes"] > 0
        assert "ef9ede131ed1d64daf9a0df5b2140a0a8e56b632" in record["source_refs"][0]["url"]
        assert record["collision_admission"].startswith("not admitted")
        assert "local only" in record["distribution"]


def test_asset_inspection_rejects_changed_capture(tmp_path):
    pytest.importorskip("trimesh", reason="Install probes/ot2_motion/requirements.lock")
    from probes.ot2_motion.inspect_assets import inspect_assets

    (tmp_path / "OT-2-detailed.stl").write_bytes(b"not the pinned CAD file")
    with pytest.raises(ValueError, match="Asset differs from pinned source"):
        inspect_assets(tmp_path)
