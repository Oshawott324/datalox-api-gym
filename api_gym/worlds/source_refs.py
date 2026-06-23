"""Validation for world source_refs.json files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def validate_world_source_refs(world: str, *, repo_root: Path | None = None) -> dict[str, Any]:
    """Validate selected source refs for one world."""
    root = (repo_root or PROJECT_ROOT).resolve()
    world_dir = root / "worlds" / world
    source_refs_path = world_dir / "source_refs.json"
    if not source_refs_path.exists():
        return {
            "ok": False,
            "world": world,
            "missing_source_refs": str(source_refs_path),
            "source_pack_count": 0,
            "world_evidence_count": 0,
            "missing_records": [],
            "missing_world_evidence": [],
        }

    payload = _read_json(source_refs_path)
    source_packs = payload.get("source_packs", [])
    world_evidence = payload.get("world_evidence", [])
    missing_records: list[dict[str, str]] = []
    missing_world_evidence: list[str] = []

    if not isinstance(source_packs, list):
        raise ValueError("source_refs.json source_packs must be a list when present.")
    if not isinstance(world_evidence, list):
        raise ValueError("source_refs.json world_evidence must be a list when present.")

    for source_pack_ref in source_packs:
        if not isinstance(source_pack_ref, dict):
            raise ValueError("Each source_packs entry must be an object.")
        source_pack_id = str(source_pack_ref.get("source_pack_id", ""))
        source_pack_path = _resolve_child(world_dir, str(source_pack_ref.get("path", "")))
        available_record_ids = _source_pack_record_ids(source_pack_path)
        record_ids = source_pack_ref.get("records", [])
        if not isinstance(record_ids, list):
            raise ValueError("source_packs records must be a list when present.")
        for record_id in record_ids:
            if record_id not in available_record_ids:
                missing_records.append({"source_pack_id": source_pack_id, "record_id": str(record_id)})

    for evidence_ref in world_evidence:
        if not isinstance(evidence_ref, dict):
            raise ValueError("Each world_evidence entry must be an object.")
        evidence_path = _resolve_child(world_dir, str(evidence_ref.get("path", "")))
        if not evidence_path.exists():
            missing_world_evidence.append(str(evidence_path))

    return {
        "ok": not missing_records and not missing_world_evidence,
        "world": world,
        "source_pack_count": len(source_packs),
        "world_evidence_count": len(world_evidence),
        "missing_records": missing_records,
        "missing_world_evidence": missing_world_evidence,
    }


def _source_pack_record_ids(source_pack_path: Path) -> set[str]:
    source_pack = _read_json(source_pack_path)
    records = source_pack.get("records")
    if not isinstance(records, dict):
        raise ValueError(f"{source_pack_path} records must be an object.")

    record_ids: set[str] = set()
    for rel_path in records.values():
        if not isinstance(rel_path, str):
            continue
        record_path = _resolve_child(source_pack_path.parent, rel_path)
        if record_path.suffix == ".jsonl" and record_path.exists():
            record_ids.update(_jsonl_ids(record_path))
    return record_ids


def _jsonl_ids(path: Path) -> set[str]:
    ids: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if isinstance(row, dict) and isinstance(row.get("id"), str):
            ids.add(row["id"])
    return ids


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return data


def _resolve_child(parent: Path, rel_path: str) -> Path:
    if not rel_path:
        raise ValueError("source_refs path entries must be non-empty strings.")
    return (parent / rel_path).resolve()
