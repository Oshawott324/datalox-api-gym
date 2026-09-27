"""Integrity and admission checks for local OT-2 CAD inspection artifacts."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

INVENTORY_SCHEMA = "datalox.ot2-cad-inventory.v1"
CONVERSION_SCHEMA = "datalox.ot2-cad-conversion.v1"
COVERAGE_SCHEMA = "datalox.ot2-cad-coverage.v1"
COMPONENT_MAP_SCHEMA = "datalox.ot2-cad-component-map.v1"


class AssetAdmissionError(ValueError):
    """Raised when source or derived evidence fails a hard admission check."""


class AssetDigestMismatch(AssetAdmissionError):
    """Raised before parsing when local bytes differ from the source inventory."""


@dataclass(frozen=True)
class SourceAsset:
    """One exact source capture declared by ``sources/assets.jsonl``."""

    asset_id: str
    local_filename: str
    sha256: str
    byte_count: int
    source_refs: tuple[Mapping[str, Any], ...]
    units: str
    coordinate_frame: str
    distribution: str
    coverage: str
    collision_admission: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "SourceAsset":
        required = {
            "id",
            "local_filename",
            "sha256",
            "bytes",
            "source_refs",
            "units",
            "coordinate_frame",
            "distribution",
            "coverage",
            "collision_admission",
        }
        missing = sorted(required.difference(value))
        if missing:
            raise AssetAdmissionError(f"Source asset is missing fields: {missing}")
        digest = str(value["sha256"])
        try:
            digest_bytes = bytes.fromhex(digest)
        except ValueError as error:
            raise AssetAdmissionError(
                "Source asset sha256 is not hexadecimal"
            ) from error
        if len(digest_bytes) != 32:
            raise AssetAdmissionError("Source asset sha256 must contain 32 bytes")
        byte_count = int(value["bytes"])
        if byte_count <= 0:
            raise AssetAdmissionError("Source asset byte count must be positive")
        refs = value["source_refs"]
        if not isinstance(refs, list) or not refs:
            raise AssetAdmissionError("Source asset must contain source_refs")
        return cls(
            asset_id=str(value["id"]),
            local_filename=str(value["local_filename"]),
            sha256=digest,
            byte_count=byte_count,
            source_refs=tuple(refs),
            units=str(value["units"]),
            coordinate_frame=str(value["coordinate_frame"]),
            distribution=str(value["distribution"]),
            coverage=str(value["coverage"]),
            collision_admission=str(value["collision_admission"]),
        )

    def provenance(self) -> dict[str, Any]:
        return {
            "id": self.asset_id,
            "local_filename": self.local_filename,
            "sha256": self.sha256,
            "bytes": self.byte_count,
            "source_refs": list(self.source_refs),
            "declared_units": self.units,
            "coordinate_frame": self.coordinate_frame,
            "distribution": self.distribution,
            "declared_coverage": self.coverage,
            "declared_collision_admission": self.collision_admission,
        }


def load_source_assets(path: Path) -> tuple[SourceAsset, ...]:
    """Load a strict JSONL source inventory without interpreting CAD semantics."""

    records: list[SourceAsset] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise AssetAdmissionError(
                f"Invalid JSON on source inventory line {line_number}"
            ) from error
        if not isinstance(value, dict):
            raise AssetAdmissionError(
                f"Source inventory line {line_number} must be an object"
            )
        records.append(SourceAsset.from_mapping(value))
    if not records:
        raise AssetAdmissionError("Source inventory is empty")
    ids = [record.asset_id for record in records]
    filenames = [record.local_filename for record in records]
    if len(ids) != len(set(ids)):
        raise AssetAdmissionError("Source inventory contains duplicate asset ids")
    if len(filenames) != len(set(filenames)):
        raise AssetAdmissionError("Source inventory contains duplicate local filenames")
    return tuple(records)


def sha256_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    byte_count = 0
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            byte_count += len(chunk)
            digest.update(chunk)
    return byte_count, digest.hexdigest()


def verify_source_asset(record: SourceAsset, path: Path) -> dict[str, Any]:
    """Verify source bytes before any format-specific parser sees them."""

    byte_count, digest = sha256_file(path)
    if byte_count != record.byte_count or digest != record.sha256:
        raise AssetDigestMismatch(
            "Asset differs from pinned source: "
            f"{record.asset_id}; expected bytes={record.byte_count}, "
            f"sha256={record.sha256}; observed bytes={byte_count}, sha256={digest}"
        )
    return {
        "id": record.asset_id,
        "path": str(path),
        "bytes": byte_count,
        "sha256": digest,
        "digest_verified": True,
    }


def require_finite(values: Iterable[float], *, field: str) -> tuple[float, ...]:
    converted = tuple(float(value) for value in values)
    if not converted or not all(math.isfinite(value) for value in converted):
        raise AssetAdmissionError(f"{field} must contain only finite coordinates")
    return converted


def validate_solid_for_collision(component: Mapping[str, Any]) -> None:
    """Reject geometry that cannot support a source-faithful solid query."""

    if component.get("topology") != "solid":
        raise AssetAdmissionError(
            f"Component {component.get('component_id')} is not a solid"
        )
    if component.get("source_units_status") != "declared":
        raise AssetAdmissionError(
            f"Component {component.get('component_id')} has unresolved source units"
        )
    if component.get("valid") is not True:
        raise AssetAdmissionError(
            f"Component {component.get('component_id')} is not a valid solid"
        )


def validate_dxf_for_mm_geometry(dxf: Mapping[str, Any]) -> None:
    """Reject a drawing whose source does not establish a millimeter conversion."""

    if dxf.get("units_status") != "declared":
        raise AssetAdmissionError("DXF source units are unresolved")
    require_finite((dxf.get("conversion_to_mm"),), field="DXF unit conversion factor")
    if dxf.get("modelspace_bounds_mm") is None:
        raise AssetAdmissionError("DXF has no millimeter bounds")


def validate_inventory(inventory: Mapping[str, Any]) -> None:
    """Validate the format-independent invariants of a generated inventory."""

    if inventory.get("schema") != INVENTORY_SCHEMA:
        raise AssetAdmissionError("Unsupported OT-2 CAD inventory schema")
    sources = inventory.get("sources")
    if not isinstance(sources, list) or not sources:
        raise AssetAdmissionError("Inventory must retain source provenance")
    for source in sources:
        if source.get("digest_verified") is not True:
            raise AssetAdmissionError("Inventory contains an unverified source")
    step = inventory.get("step")
    dxf = inventory.get("dxf")
    if not isinstance(step, dict) or not isinstance(dxf, dict):
        raise AssetAdmissionError("Inventory must include STEP and DXF inspections")
    for component in step.get("components", []):
        bounds = component.get("bounds_mm")
        transform = component.get("transform_to_source_model_mm")
        if bounds is not None:
            require_finite((*bounds["min"], *bounds["max"]), field="STEP bounds")
        if transform is not None:
            require_finite(
                (item for row in transform for item in row), field="STEP transform"
            )
    bounds = dxf.get("modelspace_bounds_mm")
    if bounds is not None:
        require_finite((*bounds["min"], *bounds["max"]), field="DXF bounds")
