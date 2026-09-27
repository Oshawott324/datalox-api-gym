from __future__ import annotations

import math
from pathlib import Path

import pytest

from api_gym.instrument_models.opentrons_ot2_v0.assets import (
    AssetAdmissionError,
    AssetDigestMismatch,
    SourceAsset,
    sha256_file,
    validate_dxf_for_mm_geometry,
    validate_solid_for_collision,
)
from probes.ot2_motion.import_cad import inspect_dxf, inspect_step

cadquery = pytest.importorskip(
    "cadquery", reason="Install probes/ot2_motion/cad-requirements.lock"
)
ezdxf = pytest.importorskip(
    "ezdxf", reason="Install probes/ot2_motion/cad-requirements.lock"
)


def _source(path: Path, *, units: str = "test fixture") -> SourceAsset:
    byte_count, digest = sha256_file(path)
    return SourceAsset(
        asset_id=f"test:{path.stem}",
        local_filename=path.name,
        sha256=digest,
        byte_count=byte_count,
        source_refs=({"kind": "synthetic_test", "url": "local:test"},),
        units=units,
        coordinate_frame="synthetic fixture frame",
        distribution="test only",
        coverage="synthetic fixture",
        collision_admission="not admitted",
    )


def _dimensions(component: dict) -> tuple[float, float, float]:
    bounds = component["bounds_mm"]
    return tuple(bounds["max"][axis] - bounds["min"][axis] for axis in range(3))


def test_step_assembly_preserves_components_transforms_and_inch_units(tmp_path):
    path = tmp_path / "synthetic-inch-assembly.step"
    assembly = cadquery.Assembly(name="synthetic-inch-assembly")
    assembly.add(
        cadquery.Workplane("XY").box(1, 2, 3),
        name="one-inch-body",
        loc=cadquery.Location((2, 3, 4)),
    )
    assembly.add(
        cadquery.Workplane("XY").box(0.5, 0.25, 0.125),
        name="rotated-body",
        loc=cadquery.Location((6, 0, 0), (0, 0, 1), 90),
    )
    assembly.export(str(path), unit="INCH", outputUnit="INCH")

    result = inspect_step(path, _source(path, units="inch"))

    assert result["source_length_units"] == ["INCH"]
    assert result["target_length_unit"] == "millimeter"
    assert result["has_assembly_hierarchy"] is True
    assert result["assembly_node_count"] == 1
    assert result["component_count"] == 2
    by_name = {
        component["source_label"]: component for component in result["components"]
    }
    assert set(by_name) == {"one-inch-body", "rotated-body"}
    assert _dimensions(by_name["one-inch-body"]) == pytest.approx((25.4, 50.8, 76.2))
    first_transform = by_name["one-inch-body"]["transform_to_source_model_mm"]
    assert [first_transform[axis][3] for axis in range(3)] == pytest.approx(
        (50.8, 76.2, 101.6)
    )
    second_transform = by_name["rotated-body"]["transform_to_source_model_mm"]
    assert second_transform[0][:2] == pytest.approx((0.0, -1.0), abs=1e-12)
    assert second_transform[1][:2] == pytest.approx((1.0, 0.0), abs=1e-12)
    assert second_transform[0][3] == pytest.approx(152.4)
    assert all(component["valid"] for component in result["components"])


def test_step_open_shell_is_inventoried_but_rejected_for_solid_query(tmp_path):
    path = tmp_path / "synthetic-open-shell.step"
    assembly = cadquery.Assembly(name="synthetic-open-shell")
    assembly.add(cadquery.Face.makePlane(10, 20), name="open-face")
    assembly.export(str(path), unit="MM", outputUnit="MM")

    result = inspect_step(path, _source(path, units="millimeter"))

    assert result["component_count"] == 1
    component = result["components"][0]
    assert component["topology"] == "shell"
    with pytest.raises(AssetAdmissionError, match="is not a solid"):
        validate_solid_for_collision(component)


def test_dxf_preserves_inches_and_block_insert_transform(tmp_path):
    from ezdxf import units

    path = tmp_path / "synthetic-inch-block.dxf"
    document = ezdxf.new("R2018", units=units.IN)
    block = document.blocks.new(name="SOURCE-BLOCK")
    block.add_line((0, 0), (1, 0))
    document.modelspace().add_blockref(
        "SOURCE-BLOCK",
        (2, 3),
        dxfattribs={"rotation": 90.0, "xscale": 2.0, "yscale": 2.0, "zscale": 2.0},
    )
    document.saveas(path)

    result = inspect_dxf(path, _source(path, units="inch"))

    assert result["insunits_name"] == "Inches"
    assert result["conversion_to_mm"] == pytest.approx(25.4)
    assert result["modelspace_insert_count"] == 1
    assert result["insert_count"] == 1
    transform = result["inserts"][0]["transform_in_owner_units"]
    assert [transform[3][axis] for axis in range(3)] == pytest.approx((2, 3, 0))
    assert transform[0][:2] == pytest.approx((0, 2), abs=1e-12)
    assert transform[1][:2] == pytest.approx((-2, 0), abs=1e-12)


def test_unitless_dxf_is_inventoried_and_rejected_for_mm_geometry(tmp_path):
    from ezdxf.enums import InsertUnits

    path = tmp_path / "synthetic-unitless.dxf"
    document = ezdxf.new("R2018")
    document.units = InsertUnits.Unitless
    document.modelspace().add_line((0, 0), (1, 1))
    document.saveas(path)

    result = inspect_dxf(path, _source(path, units="unresolved"))

    assert result["units_status"] == "unresolved"
    assert result["conversion_to_mm"] is None
    assert result["modelspace_bounds_mm"] is None
    assert result["modelspace_bounds_source_units"] == {
        "min": [0.0, 0.0, 0.0],
        "max": [1.0, 1.0, 0.0],
    }
    with pytest.raises(AssetAdmissionError, match="units are unresolved"):
        validate_dxf_for_mm_geometry(result)


def test_digest_mismatch_is_rejected_before_step_parse(tmp_path):
    path = tmp_path / "changed.step"
    path.write_bytes(b"not a STEP file")
    source = SourceAsset(
        asset_id="test:changed-step",
        local_filename=path.name,
        sha256="0" * 64,
        byte_count=len(path.read_bytes()),
        source_refs=({"kind": "synthetic_test", "url": "local:test"},),
        units="millimeter",
        coordinate_frame="synthetic fixture frame",
        distribution="test only",
        coverage="synthetic fixture",
        collision_admission="not admitted",
    )

    with pytest.raises(AssetDigestMismatch, match="differs from pinned source"):
        inspect_step(path, source)


def test_nonfinite_component_coordinates_are_rejected():
    component = {
        "component_id": "synthetic",
        "topology": "solid",
        "source_units_status": "declared",
        "valid": True,
        "bounds_mm": {"min": [0.0, 0.0, 0.0], "max": [math.inf, 1.0, 1.0]},
    }

    from api_gym.instrument_models.opentrons_ot2_v0.assets import validate_inventory

    with pytest.raises(AssetAdmissionError, match="finite"):
        validate_inventory(
            {
                "schema": "datalox.ot2-cad-inventory.v1",
                "sources": [{"digest_verified": True}],
                "step": {"components": [component]},
                "dxf": {"modelspace_bounds_mm": None},
            }
        )
