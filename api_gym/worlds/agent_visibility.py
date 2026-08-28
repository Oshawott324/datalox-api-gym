"""Fail-closed construction helpers for agent-visible world packages."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Iterable


def scan_agent_visible_files(
    source_root: Path,
    relative_files: Iterable[str],
    *,
    forbidden_tokens: Iterable[str],
    forbidden_json_keys: Iterable[str],
) -> dict[str, Any]:
    """Scan the complete declared public surface for hidden references and keys."""

    root = source_root.resolve()
    files = [_resolve_public_file(root, relative) for relative in relative_files]
    tokens = tuple(token.lower() for token in forbidden_tokens)
    forbidden_keys = frozenset(forbidden_json_keys)
    token_findings: dict[str, list[str]] = {}
    key_findings: dict[str, list[str]] = {}

    for path in files:
        relative = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        found_tokens = sorted(token for token in tokens if token in text.lower())
        if found_tokens:
            token_findings[relative] = found_tokens
        if path.suffix == ".json":
            found_keys = sorted(_recursive_keys(json.loads(text)) & forbidden_keys)
            if found_keys:
                key_findings[relative] = found_keys

    return {
        "scanned_files": [path.relative_to(root).as_posix() for path in files],
        "forbidden_tokens": token_findings,
        "evaluator_keys": key_findings,
    }


def materialize_agent_workspace(
    source_root: Path,
    out: Path,
    *,
    relative_files: Iterable[str],
    manifest: dict[str, Any],
    clean: bool = False,
) -> Path:
    """Copy an explicit public-file allowlist into a standalone workspace."""

    root = source_root.resolve()
    files = [_resolve_public_file(root, relative) for relative in relative_files]
    out_dir = out.resolve()
    if clean and out_dir.exists():
        shutil.rmtree(out_dir)
    if out_dir.exists() and any(out_dir.iterdir()):
        raise FileExistsError(
            f"Agent workspace already exists and is not empty: {out_dir}"
        )
    out_dir.mkdir(parents=True, exist_ok=True)

    file_records = []
    for source in files:
        relative = source.relative_to(root)
        destination = out_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        content = destination.read_bytes()
        file_records.append(
            {
                "path": relative.as_posix(),
                "sha256": hashlib.sha256(content).hexdigest(),
                "size_bytes": len(content),
            }
        )

    reserved_manifest_keys = {"content_sha256", "files"}
    if reserved_manifest_keys & set(manifest):
        raise ValueError(
            "Agent workspace manifest may not override content-address fields."
        )
    manifest_payload = dict(manifest)
    manifest_payload["files"] = sorted(file_records, key=lambda item: item["path"])
    canonical_files = json.dumps(
        manifest_payload["files"], sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    manifest_payload["content_sha256"] = hashlib.sha256(canonical_files).hexdigest()
    manifest_path = out_dir / "agent_visible_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return out_dir


def workspace_file_inventory(root: Path) -> dict[str, list[str]]:
    """Return regular files and symlinks without following external paths."""

    root = root.resolve()
    files = sorted(
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
    )
    symlinks = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_symlink()
    )
    return {"files": files, "symlinks": symlinks}


def _resolve_public_file(root: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
        raise ValueError(
            f"Agent-visible path must be a safe relative file path: {relative!r}"
        )
    path = root / candidate
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ValueError(
            f"Agent-visible path must name an existing file: {relative!r}"
        ) from exc
    if resolved != path or root not in resolved.parents or not path.is_file():
        raise ValueError(
            f"Agent-visible path must name a regular non-symlink file: {relative!r}"
        )
    return path


def _recursive_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        keys = set(value)
        for item in value.values():
            keys.update(_recursive_keys(item))
        return keys
    if isinstance(value, list):
        keys: set[str] = set()
        for item in value:
            keys.update(_recursive_keys(item))
        return keys
    return set()
