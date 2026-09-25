"""Inspect locally acquired, digest-pinned OT-2 assets without repairing them."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import trimesh

PACK = Path(__file__).resolve().parent / "sources"


def inspect_assets(directory: Path) -> dict:
    records = [json.loads(line) for line in (PACK / "assets.jsonl").read_text().splitlines()]
    findings = []
    for record in records:
        path = directory / record["local_filename"]
        raw = path.read_bytes()
        if len(raw) != record["bytes"] or hashlib.sha256(raw).hexdigest() != record["sha256"]:
            raise ValueError(f"Asset differs from pinned source: {record['id']}")
        finding = {"id": record["id"], "digest_verified": True, "collision_admission": record["collision_admission"]}
        if path.suffix == ".stl":
            mesh = trimesh.load_mesh(path, process=True)
            finding["inspection"] = {
                "vertices": len(mesh.vertices), "faces": len(mesh.faces),
                "bounds_in_source_units": mesh.bounds.tolist(),
                "watertight": bool(mesh.is_watertight), "is_volume": bool(mesh.is_volume),
                "processing": "Trimesh standard vertex processing only; no hole filling, rescaling or solid repair",
            }
        findings.append(finding)
    return {"assets": findings, "complete_instrument_scene": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = inspect_assets(args.directory)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as output:
        output.write(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
