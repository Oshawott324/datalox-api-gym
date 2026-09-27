"""Inspect digest-pinned OT-2 STEP and DXF sources without repairing geometry."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
from collections import Counter
from importlib.metadata import version
from pathlib import Path
from typing import Any, Iterable, Mapping

from api_gym.instrument_models.opentrons_ot2_v0.assets import (
    COMPONENT_MAP_SCHEMA,
    CONVERSION_SCHEMA,
    COVERAGE_SCHEMA,
    INVENTORY_SCHEMA,
    AssetAdmissionError,
    SourceAsset,
    load_source_assets,
    require_finite,
    sha256_file,
    validate_inventory,
    verify_source_asset,
)

SOURCE_INVENTORY = Path(__file__).resolve().parent / "sources" / "assets.jsonl"
OUTPUT_FILES = (
    "inventory.json",
    "component-map.json",
    "coverage.json",
    "component-bounds.svg",
    "conversion.json",
)


def _json_write_exclusive(path: Path, value: Mapping[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as output:
        output.write(json.dumps(value, indent=2, sort_keys=True, allow_nan=False))
        output.write("\n")


def _matrix_from_trsf(transform: Any) -> list[list[float]]:
    matrix = [
        [float(transform.Value(row, column)) for column in range(1, 5)]
        for row in range(1, 4)
    ]
    matrix.append([0.0, 0.0, 0.0, 1.0])
    require_finite(
        (item for row in matrix for item in row), field="STEP transformation"
    )
    return matrix


def _label_name(label: Any) -> str | None:
    from OCP.TDataStd import TDataStd_Name

    attribute = TDataStd_Name()
    if label.FindAttribute(TDataStd_Name.GetID_s(), attribute):
        value = str(attribute.Get().ToExtString())
        return value if value and value != "NONE" else None
    return None


def _label_entry(label: Any) -> str:
    from OCP.TCollection import TCollection_AsciiString
    from OCP.TDF import TDF_Tool

    entry = TCollection_AsciiString()
    TDF_Tool.Entry_s(label, entry)
    return str(entry.ToCString())


def _sequence_strings(sequence: Any) -> list[str]:
    return [
        str(sequence.Value(index).ToCString())
        for index in range(1, sequence.Length() + 1)
    ]


def _shape_count(shape: Any, kind: Any) -> int:
    from OCP.TopExp import TopExp_Explorer

    explorer = TopExp_Explorer(shape, kind)
    count = 0
    while explorer.More():
        count += 1
        explorer.Next()
    return count


def _shape_bounds(shape: Any) -> dict[str, list[float]]:
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    bounds = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, bounds, False, False)
    if bounds.IsVoid() or bounds.IsOpen():
        raise AssetAdmissionError("STEP shape has void or unbounded coordinates")
    xmin, ymin, zmin, xmax, ymax, zmax = require_finite(
        bounds.Get(), field="STEP bounds"
    )
    return {"min": [xmin, ymin, zmin], "max": [xmax, ymax, zmax]}


def _component_id(source_sha256: str, label_entry: str, instance_path: str) -> str:
    identity = f"{source_sha256}\0{label_entry}\0{instance_path}".encode()
    return f"step-component-{hashlib.sha256(identity).hexdigest()[:16]}"


def _topology_name(shape: Any) -> str:
    from OCP.TopAbs import (
        TopAbs_COMPOUND,
        TopAbs_COMPSOLID,
        TopAbs_FACE,
        TopAbs_SHELL,
        TopAbs_SOLID,
    )

    names = {
        TopAbs_SOLID: "solid",
        TopAbs_SHELL: "shell",
        TopAbs_FACE: "face",
        TopAbs_COMPSOLID: "compsolid",
        TopAbs_COMPOUND: "compound",
    }
    return names.get(shape.ShapeType(), str(shape.ShapeType()))


def inspect_step(path: Path, source: SourceAsset) -> dict[str, Any]:
    """Read STEP through OCCT/XCAF and retain source labels and placements."""

    verify_source_asset(source, path)

    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.Interface import Interface_Static
    from OCP.STEPCAFControl import STEPCAFControl_Reader
    from OCP.TColStd import TColStd_SequenceOfAsciiString
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDF import TDF_Label, TDF_LabelSequence
    from OCP.TDocStd import TDocStd_Document
    from OCP.TopAbs import TopAbs_SHELL, TopAbs_SOLID
    from OCP.TopLoc import TopLoc_Location
    from OCP.XCAFDoc import XCAFDoc_DocumentTool
    from OCP.gp import gp_Trsf

    reader = STEPCAFControl_Reader()
    reader.SetColorMode(True)
    reader.SetNameMode(True)
    reader.SetLayerMode(True)
    reader.SetSHUOMode(True)
    Interface_Static.SetIVal_s("read.stepcaf.subshapes.name", 1)
    Interface_Static.SetCVal_s("xstep.cascade.unit", "MM")
    if reader.ReadFile(str(path)) != IFSelect_RetDone:
        raise AssetAdmissionError(f"OCCT could not read STEP file: {path.name}")

    length_units = TColStd_SequenceOfAsciiString()
    angle_units = TColStd_SequenceOfAsciiString()
    solid_angle_units = TColStd_SequenceOfAsciiString()
    reader.Reader().FileUnits(length_units, angle_units, solid_angle_units)
    declared_length_units = _sequence_strings(length_units)
    if not declared_length_units:
        raise AssetAdmissionError(
            "STEP file has no declared length unit; target-unit conversion is unresolved"
        )

    document = TDocStd_Document(TCollection_ExtendedString("ot2-cad-inspection"))
    if not reader.Transfer(document):
        raise AssetAdmissionError(f"OCCT could not transfer STEP file: {path.name}")
    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    free_labels = TDF_LabelSequence()
    shape_tool.GetFreeShapes(free_labels)
    if free_labels.Length() == 0:
        raise AssetAdmissionError("STEP file contains no free shapes")

    components: list[dict[str, Any]] = []
    assembly_nodes: list[dict[str, Any]] = []
    discovered_solid_instances = 0

    def record_shape(
        shape: Any,
        *,
        label: Any,
        source_label: str | None,
        transform: Any,
        instance_path: str,
        identity_status: str,
    ) -> None:
        nonlocal discovered_solid_instances
        topology = _topology_name(shape)
        if topology not in {"solid", "shell", "face"}:
            return
        if topology == "solid":
            discovered_solid_instances += 1
        placed = shape.Moved(TopLoc_Location(transform))
        valid = bool(BRepCheck_Analyzer(placed).IsValid())
        volume_mm3: float | None = None
        if topology == "solid" and valid:
            properties = GProp_GProps()
            BRepGProp.VolumeProperties_s(placed, properties, True, False, False)
            volume_mm3 = float(properties.Mass())
            require_finite((volume_mm3,), field="STEP volume")
        label_entry = _label_entry(label)
        components.append(
            {
                "component_id": _component_id(
                    source.sha256, label_entry, instance_path
                ),
                "source_label": source_label,
                "source_label_entry": label_entry,
                "instance_path": instance_path,
                "identity_status": identity_status,
                "topology": topology,
                "valid": valid,
                "source_units_status": "declared",
                "bounds_mm": _shape_bounds(placed),
                "transform_to_source_model_mm": _matrix_from_trsf(transform),
                "solid_count": _shape_count(placed, TopAbs_SOLID),
                "shell_count": _shape_count(placed, TopAbs_SHELL),
                "volume_mm3": volume_mm3,
                "collision_admission": "not_admitted",
                "collision_admission_reasons": [
                    "semantic component mapping is not reviewed",
                    "source model is not aligned to the software deck frame",
                    "redistribution rights are not reviewed",
                ],
            }
        )

    def inspect_simple_shape(
        label: Any,
        *,
        transform: Any,
        instance_path: str,
        preferred_name: str | None,
        identity_label: Any,
    ) -> None:
        shape = shape_tool.GetShape_s(label)
        topology = _topology_name(shape)
        if topology in {"solid", "shell", "face"}:
            record_shape(
                shape,
                label=identity_label,
                source_label=preferred_name or _label_name(label),
                transform=transform,
                instance_path=instance_path,
                identity_status="source_label"
                if preferred_name or _label_name(label)
                else "unresolved",
            )
            return

        sublabels = TDF_LabelSequence()
        shape_tool.GetSubShapes_s(label, sublabels)
        solid_labels: list[Any] = []
        standalone_labels: list[Any] = []
        for index in range(1, sublabels.Length() + 1):
            sublabel = sublabels.Value(index)
            subshape = shape_tool.GetShape_s(sublabel)
            subtopology = _topology_name(subshape)
            if subtopology == "solid":
                solid_labels.append(sublabel)
            elif subtopology in {"shell", "face"} and _label_name(sublabel):
                standalone_labels.append(sublabel)

        expected_solids = _shape_count(shape, TopAbs_SOLID)
        if len(solid_labels) != expected_solids:
            raise AssetAdmissionError(
                "STEP contains solids without one source label each; stable component "
                f"identity is unresolved ({len(solid_labels)} labels for "
                f"{expected_solids} solids)"
            )
        for sublabel in solid_labels + standalone_labels:
            subshape = shape_tool.GetShape_s(sublabel)
            name = _label_name(sublabel)
            subpath = f"{instance_path}/{name or _label_entry(sublabel)}"
            record_shape(
                subshape,
                label=sublabel,
                source_label=name,
                transform=transform,
                instance_path=subpath,
                identity_status="source_label" if name else "unresolved",
            )

    def walk_label(
        label: Any,
        *,
        parent_transform: Any,
        parent_path: str,
        preferred_name: str | None = None,
        identity_label: Any | None = None,
    ) -> None:
        local = shape_tool.GetLocation_s(label).Transformation()
        transform = parent_transform.Multiplied(local)
        name = preferred_name or _label_name(label) or _label_entry(label)
        path_value = f"{parent_path}/{name}" if parent_path else name
        if shape_tool.IsReference_s(label):
            referred = TDF_Label()
            if not shape_tool.GetReferredShape_s(label, referred):
                raise AssetAdmissionError("STEP reference does not resolve to a shape")
            walk_label(
                referred,
                parent_transform=transform,
                parent_path=parent_path,
                preferred_name=_label_name(label) or _label_name(referred),
                identity_label=label,
            )
            return
        if shape_tool.IsAssembly_s(label):
            component_labels = TDF_LabelSequence()
            shape_tool.GetComponents_s(label, component_labels)
            assembly_nodes.append(
                {
                    "source_label": _label_name(label),
                    "source_label_entry": _label_entry(label),
                    "instance_path": path_value,
                    "transform_to_source_model_mm": _matrix_from_trsf(transform),
                    "component_count": component_labels.Length(),
                }
            )
            for index in range(1, component_labels.Length() + 1):
                walk_label(
                    component_labels.Value(index),
                    parent_transform=transform,
                    parent_path=path_value,
                )
            return
        if shape_tool.IsSimpleShape_s(label):
            inspect_simple_shape(
                label,
                transform=transform,
                instance_path=path_value,
                preferred_name=preferred_name,
                identity_label=identity_label or label,
            )
            return
        raise AssetAdmissionError(
            f"Unsupported STEP label kind at {_label_entry(label)}"
        )

    identity = gp_Trsf()
    for index in range(1, free_labels.Length() + 1):
        walk_label(free_labels.Value(index), parent_transform=identity, parent_path="")

    components.sort(key=lambda component: component["component_id"])
    labels = [component["source_label"] for component in components]
    return {
        "asset_id": source.asset_id,
        "source_sha256": source.sha256,
        "reader": "OCCT STEPCAFControl_Reader through cadquery-ocp",
        "source_length_units": declared_length_units,
        "source_angle_units": _sequence_strings(angle_units),
        "source_solid_angle_units": _sequence_strings(solid_angle_units),
        "target_length_unit": "millimeter",
        "free_shape_count": free_labels.Length(),
        "assembly_node_count": len(assembly_nodes),
        "has_assembly_hierarchy": bool(assembly_nodes),
        "assembly_nodes": assembly_nodes,
        "component_count": len(components),
        "solid_count": discovered_solid_instances,
        "source_labels_complete_for_solids": all(labels),
        "components": components,
        "geometry_processing": {
            "healing": False,
            "fusing": False,
            "rescaling_to_fit": False,
            "hole_filling": False,
            "meshing": False,
        },
    }


def _dxf_matrix(matrix: Any) -> list[list[float]]:
    values = require_finite(iter(matrix), field="DXF block insertion transform")
    if len(values) != 16:
        raise AssetAdmissionError("DXF insertion transform must contain 16 values")
    return [list(values[index : index + 4]) for index in range(0, 16, 4)]


def inspect_dxf(path: Path, source: SourceAsset) -> dict[str, Any]:
    """Read DXF units, entities, blocks, and insertion transforms with ezdxf."""

    verify_source_asset(source, path)

    import ezdxf
    from ezdxf import bbox, units
    from ezdxf.enums import InsertUnits

    document = ezdxf.readfile(path)
    auditor = document.audit()
    if auditor.fixes or auditor.errors:
        raise AssetAdmissionError(
            "DXF audit found issues; inspection refuses implicit repair: "
            f"fixes={len(auditor.fixes)}, errors={len(auditor.errors)}"
        )
    unit_code = int(document.units)
    unit_name = units.unit_name(unit_code)
    units_declared = unit_code != int(InsertUnits.Unitless)
    to_mm = (
        float(units.conversion_factor(unit_code, units.MM)) if units_declared else None
    )
    if to_mm is not None:
        require_finite((to_mm,), field="DXF unit conversion factor")

    modelspace = document.modelspace()
    entities = list(modelspace)
    extents = bbox.extents(entities, fast=False)
    if not extents.has_data:
        raise AssetAdmissionError("DXF modelspace has no finite geometric extents")
    source_bounds = require_finite(
        (*extents.extmin, *extents.extmax), field="DXF modelspace bounds"
    )

    inserts = []
    block_layouts = [block for block in document.blocks if block.is_block_layout]
    for layout in [document.modelspace(), *block_layouts]:
        layout_name = getattr(layout, "name", "Model")
        for entity in layout:
            if entity.dxftype() != "INSERT":
                continue
            inserts.append(
                {
                    "handle": str(entity.dxf.handle),
                    "owner_layout": str(layout_name),
                    "block_name": str(entity.dxf.name),
                    "transform_in_owner_units": _dxf_matrix(entity.matrix44()),
                    "row_count": int(entity.dxf.row_count),
                    "column_count": int(entity.dxf.column_count),
                }
            )
    inserts.sort(key=lambda item: (item["owner_layout"], item["handle"]))

    blocks = []
    for block in document.blocks:
        base_point = require_finite(
            block.block.dxf.base_point, field="DXF block base point"
        )
        blocks.append(
            {
                "name": str(block.name),
                "handle": str(block.block_record_handle),
                "unit_code": int(block.units),
                "unit_name": units.unit_name(int(block.units)),
                "base_point": list(base_point),
                "entity_count": len(block),
            }
        )
    blocks.sort(key=lambda item: (item["name"], item["handle"]))
    entity_types = Counter(entity.dxftype() for entity in entities)

    mm_bounds = None
    if to_mm is not None:
        mm_bounds = {
            "min": [value * to_mm for value in source_bounds[:3]],
            "max": [value * to_mm for value in source_bounds[3:]],
        }
    return {
        "asset_id": source.asset_id,
        "source_sha256": source.sha256,
        "reader": "ezdxf.readfile",
        "dxf_version": document.dxfversion,
        "insunits_code": unit_code,
        "insunits_name": unit_name,
        "units_status": "declared" if units_declared else "unresolved",
        "conversion_to_mm": to_mm,
        "measurement_header": int(document.header.get("$MEASUREMENT", -1)),
        "modelspace_entity_count": len(entities),
        "modelspace_entity_types": dict(sorted(entity_types.items())),
        "modelspace_bounds_source_units": {
            "min": list(source_bounds[:3]),
            "max": list(source_bounds[3:]),
        },
        "modelspace_bounds_mm": mm_bounds,
        "block_count": len(blocks),
        "blocks": blocks,
        "modelspace_insert_count": entity_types.get("INSERT", 0),
        "insert_count": len(inserts),
        "inserts": inserts,
        "audit": {"errors": 0, "fixes": 0},
        "geometry_processing": {
            "recovery_reader": False,
            "audit_repairs": False,
            "unit_rescaling_to_fit": False,
            "entity_explosion": False,
        },
    }


def build_component_map(step: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": COMPONENT_MAP_SCHEMA,
        "review_status": "not_reviewed",
        "mapping_policy": (
            "Source labels are retained as evidence. No semantic role is assigned "
            "without a reviewed mapping tied to the source digest."
        ),
        "source_sha256": step["source_sha256"],
        "components": [
            {
                "component_id": component["component_id"],
                "source_label": component["source_label"],
                "source_label_entry": component["source_label_entry"],
                "semantic_role": None,
                "review_status": "unassigned",
            }
            for component in step["components"]
        ],
    }


def build_coverage(step: Mapping[str, Any], dxf: Mapping[str, Any]) -> dict[str, Any]:
    labels = sorted(
        component["source_label"]
        for component in step["components"]
        if component["source_label"] is not None
    )
    return {
        "schema": COVERAGE_SCHEMA,
        "complete_instrument_scene": False,
        "collision_checks_available": False,
        "source_labels": labels,
        "required_bodies": [
            {
                "subject": "selected pipette p300_single_v2.1 on the left mount",
                "status": "unresolved_correspondence",
                "evidence": [
                    label
                    for label in labels
                    if label in {"300uL PIPETTE LEFT", "300uL PIPETTE RIGHT"}
                ],
                "reason": (
                    "The STEP labels identify generic 300uL left/right pipette solids, "
                    "but the source does not tie either solid to Opentrons model "
                    "p300_single_v2.1 or define its motion anchor."
                ),
            },
            {
                "subject": "attached Opentrons 300 uL tip",
                "status": "missing_identified_geometry",
                "evidence": [],
                "reason": "No STEP component label or separate admitted source identifies a tip solid.",
            },
            {
                "subject": "Opentrons 300 uL tip rack in slot 5",
                "status": "missing_identified_geometry",
                "evidence": [],
                "reason": "No STEP component label or separate admitted source identifies the selected tip rack.",
            },
            {
                "subject": "Corning 96-well 360 uL flat plates in slots 1 and 3",
                "status": "missing_identified_geometry",
                "evidence": [],
                "reason": "No STEP component label or separate admitted source identifies the selected labware.",
            },
            {
                "subject": "OT-2 deck",
                "status": "source_geometry_present_not_aligned",
                "evidence": [
                    *(["REMOVABLE DECK"] if "REMOVABLE DECK" in labels else []),
                    f"DXF:{dxf['asset_id']}",
                ],
                "reason": (
                    "The STEP has a source-labeled removable deck solid and the DXF has "
                    "declared millimeter geometry. Their relation to the software deck "
                    "frame has not been established."
                ),
            },
            {
                "subject": "fixed frame, windows, and doors",
                "status": "source_geometry_present_unmapped",
                "evidence": [
                    label
                    for label in labels
                    if label
                    in {
                        "OT-2 FRAME",
                        "LEFT WINDOW",
                        "RIGHT WINDOW",
                        "REAR WINDOW",
                        "TOP WINDOW",
                        "DOOR TOP",
                        "DOOR BOTTOM",
                    }
                ],
                "reason": "Source labels exist, but no reviewed static-body mapping or deck alignment exists.",
            },
            {
                "subject": "trash container",
                "status": "missing_identified_geometry",
                "evidence": [],
                "reason": "No STEP component label or separate admitted source identifies trash geometry.",
            },
        ],
        "remaining_admission_work": [
            "review source redistribution rights",
            "review a semantic component map tied to the STEP digest",
            "establish source-backed STEP/DXF-to-software-deck landmarks",
            "obtain identified selected-tip, tip-rack, and labware geometry",
            "establish the selected pipette correspondence and native critical-point anchor",
            "separate moving and static bodies using reviewed evidence",
            "admit collision representations independently from display geometry",
        ],
    }


def _project(point: Iterable[float]) -> tuple[float, float]:
    x, y, z = point
    return x - 0.55 * y, -z + 0.24 * x + 0.18 * y


def write_component_bounds_svg(path: Path, components: list[Mapping[str, Any]]) -> None:
    """Write a numbered bounds view, explicitly not a collision representation."""

    projected: list[tuple[Mapping[str, Any], list[tuple[float, float]]]] = []
    for component in components:
        minimum = component["bounds_mm"]["min"]
        maximum = component["bounds_mm"]["max"]
        corners = [
            _project((x, y, z))
            for x in (minimum[0], maximum[0])
            for y in (minimum[1], maximum[1])
            for z in (minimum[2], maximum[2])
        ]
        projected.append((component, corners))
    all_points = [point for _, points in projected for point in points]
    if not all_points:
        raise AssetAdmissionError("Cannot draw an empty STEP component inventory")
    xs, ys = zip(*all_points)
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    span_x = max_x - min_x
    span_y = max_y - min_y
    if span_x <= 0 or span_y <= 0:
        raise AssetAdmissionError("STEP component bounds cannot be projected")
    width, height = 1600.0, 1100.0
    margin = 70.0
    legend_width = 480.0
    scale = min(
        (width - legend_width - 2 * margin) / span_x,
        (height - 2 * margin) / span_y,
    )

    def screen(point: tuple[float, float]) -> tuple[float, float]:
        return (
            margin + (point[0] - min_x) * scale,
            margin + (point[1] - min_y) * scale,
        )

    edges = (
        (0, 1),
        (0, 2),
        (0, 4),
        (1, 3),
        (1, 5),
        (2, 3),
        (2, 6),
        (3, 7),
        (4, 5),
        (4, 6),
        (5, 7),
        (6, 7),
    )
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="1100" viewBox="0 0 1600 1100">',
        '<rect width="1600" height="1100" fill="#f7f7f5"/>',
        '<text x="70" y="40" font-family="sans-serif" font-size="22" fill="#202020">OT-2 STEP component bounds (source-model frame, millimeters)</text>',
        '<text x="1120" y="40" font-family="sans-serif" font-size="14" fill="#555">Bounds visualization only; not collision geometry</text>',
    ]
    for number, (component, corners) in enumerate(projected, 1):
        points = [screen(point) for point in corners]
        color = f"hsl({(number * 137) % 360} 58% 38%)"
        for start, end in edges:
            x1, y1 = points[start]
            x2, y2 = points[end]
            lines.append(
                f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" stroke="{color}" stroke-width="1.5" opacity="0.65"/>'
            )
        center_x = sum(point[0] for point in points) / 8
        center_y = sum(point[1] for point in points) / 8
        lines.append(
            f'<circle cx="{center_x:.2f}" cy="{center_y:.2f}" r="13" fill="{color}"/>'
        )
        lines.append(
            f'<text x="{center_x:.2f}" y="{center_y + 5:.2f}" text-anchor="middle" font-family="sans-serif" font-size="13" font-weight="bold" fill="white">{number}</text>'
        )
        legend_y = 75 + (number - 1) * 37
        label = html.escape(component["source_label"] or "unlabeled")
        lines.append(
            f'<text x="1130" y="{legend_y}" font-family="sans-serif" font-size="14" fill="#202020">{number}. {label}</text>'
        )
    lines.append("</svg>")
    with path.open("x", encoding="utf-8") as output:
        output.write("\n".join(lines))
        output.write("\n")


def import_cad(
    source_directory: Path,
    out_root: Path,
    *,
    source_inventory: Path = SOURCE_INVENTORY,
) -> Path:
    """Verify all captures, inspect STEP/DXF, and write a local evidence bundle."""

    sources = load_source_assets(source_inventory)
    verified: dict[str, dict[str, Any]] = {}
    for source in sources:
        result = verify_source_asset(source, source_directory / source.local_filename)
        verified[source.asset_id] = result

    step_sources = [
        source
        for source in sources
        if Path(source.local_filename).suffix.lower() in {".step", ".stp"}
    ]
    dxf_sources = [
        source
        for source in sources
        if Path(source.local_filename).suffix.lower() == ".dxf"
    ]
    if len(step_sources) != 1 or len(dxf_sources) != 1:
        raise AssetAdmissionError(
            "Source inventory must contain exactly one STEP and one DXF"
        )
    step_source = step_sources[0]
    dxf_source = dxf_sources[0]

    step = inspect_step(source_directory / step_source.local_filename, step_source)
    dxf = inspect_dxf(source_directory / dxf_source.local_filename, dxf_source)
    source_evidence = []
    for source in sources:
        provenance = source.provenance()
        provenance["digest_verified"] = verified[source.asset_id]["digest_verified"]
        source_evidence.append(provenance)
    inventory = {
        "schema": INVENTORY_SCHEMA,
        "sources": source_evidence,
        "step": step,
        "dxf": dxf,
        "rights": {
            "status": "unreviewed",
            "distribution": "local_only",
            "source_or_derived_cad_redistribution": False,
        },
        "collision_admission": "not_admitted",
    }
    validate_inventory(inventory)
    component_map = build_component_map(step)
    coverage = build_coverage(step, dxf)
    _, source_inventory_sha256 = sha256_file(source_inventory)
    conversion = {
        "schema": CONVERSION_SCHEMA,
        "source_inventory_filename": source_inventory.name,
        "source_inventory_sha256": source_inventory_sha256,
        "output_directory_key": step_source.sha256,
        "tool_versions": {
            "cadquery": version("cadquery"),
            "cadquery-ocp": version("cadquery-ocp"),
            "ezdxf": version("ezdxf"),
        },
        "settings": {
            "target_length_unit": "millimeter",
            "step_reader": "STEPCAFControl_Reader",
            "step_name_mode": True,
            "step_subshape_names": True,
            "dxf_reader": "ezdxf.readfile",
            "dxf_bbox_fast_mode": False,
            "geometry_healing": False,
            "fusing": False,
            "hole_filling": False,
            "rescaling_to_fit": False,
            "collision_export": False,
            "display_geometry_export": False,
        },
        "outputs": list(OUTPUT_FILES),
    }

    destination = out_root / step_source.sha256
    destination.mkdir(parents=True, exist_ok=False)
    try:
        _json_write_exclusive(destination / "inventory.json", inventory)
        _json_write_exclusive(destination / "component-map.json", component_map)
        _json_write_exclusive(destination / "coverage.json", coverage)
        write_component_bounds_svg(
            destination / "component-bounds.svg", step["components"]
        )
        _json_write_exclusive(destination / "conversion.json", conversion)
    except BaseException:
        for name in OUTPUT_FILES:
            (destination / name).unlink(missing_ok=True)
        destination.rmdir()
        raise
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-directory",
        type=Path,
        required=True,
        help="Directory containing files named by sources/assets.jsonl",
    )
    parser.add_argument(
        "--out-root",
        type=Path,
        required=True,
        help="Ignored local root; a STEP-digest directory is created below it",
    )
    parser.add_argument("--source-inventory", type=Path, default=SOURCE_INVENTORY)
    args = parser.parse_args()
    destination = import_cad(
        args.source_directory,
        args.out_root,
        source_inventory=args.source_inventory,
    )
    print(json.dumps({"output_directory": str(destination)}, sort_keys=True))


if __name__ == "__main__":
    main()
