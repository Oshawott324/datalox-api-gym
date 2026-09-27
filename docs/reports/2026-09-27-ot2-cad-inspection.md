# OT-2 CAD Source Inspection

Date: 2026-09-27

Status: source inspection complete; full collision scene not admitted.

## Result

The pinned OT-2 STEP and deck DXF can be read reproducibly as structured CAD,
but they do not establish the selected motion scene. The STEP contains 26 valid,
source-labeled solids in one flattened compound. It does not retain an assembly
hierarchy, relative component motion, a critical-point anchor, or an explicit
link from its generic `300uL PIPETTE LEFT` solid to Opentrons software model
`p300_single_v2.1`. No source-labeled tip, selected tip rack, Corning plate, or
trash geometry is present.

The full collision scene therefore remains unavailable. These files support
source inspection and later reviewed mapping; they do not yet support a claim
that a selected P300 GEN2 and attached tip clear the configured labware.

## Pinned Inputs

All inputs come from Opentrons `ot2` revision
`ef9ede131ed1d64daf9a0df5b2140a0a8e56b632`. Their exact byte counts and
SHA-256 digests were checked before a format-specific parser received them.

| Asset | Bytes | SHA-256 | Inspection use |
| --- | ---: | --- | --- |
| `OT-2-detailed.step` | 3,943,530 | `f8bf145b878683337ec0f89b74668bd7e350d674777762fab9befbcd014b42d4` | Structured OCCT/XCAF solid inspection |
| `CNC_DECK_RevA2.dxf` | 1,167,094 | `a0ff2e3c564904f9aeedf5652725f0e0b1af1a82f9211a6acecd46f65bd6a5d8` | Structured ezdxf drawing inspection |
| `OT-2-detailed.stl` | 2,108,684 | `547f4866956b28fa0b6757572e1e36944a4a4127ca75ad25cc20e60edf339089` | Digest verification only; previously found non-watertight |

The STEP header calls the model `Stripped Down MegaModel`, declares STEP AP214,
identifies SolidWorks 2016, and carries a 2018-04-17 file date. These are source
metadata, not a hardware-revision equivalence claim. `RevA2` occurs in the DXF
filename; no additional interpretation was added.

## STEP Findings

OCCT reports `millimetre` as the declared source length unit. Import targeted
millimeters without fit scaling. The file has one free shape, no assembly nodes,
and 26 solids. Every solid has a source label, all 26 pass `BRepCheck_Analyzer`,
and all 26 carry identity placement transforms because their coordinates are
already flattened into the source-model frame.

The 26 labels are:

| Group | Source labels |
| --- | --- |
| Deck and frame | `REMOVABLE DECK`; `OT-2 FRAME` |
| Gantry | `Z-GANTRY BASE`; `Z-GANTRY CARRIAGE`; `Z-GANTRY FRONT COVER`; `Z-GANTRY TOP COVER` |
| Enclosure | `DOOR TOP`; `DOOR BOTTOM`; `LEFT WINDOW`; `RIGHT WINDOW`; `REAR WINDOW`; `TOP WINDOW`; `WINDOW FRAME LEFT`; `WINDOW FRAME RIGHT` |
| Mount positions | `LEFT PIPETTE MOUNT TOP POSITION`; `LEFT PIPETTE MOUNT BOTTOM POSITION`; `RIGHT PIPETTE MOUNT TOP POSITION`; `RIGHT PIPETTE MOUNT BOTTOM POSITION` |
| Pipette candidates | `10uL PIPETTE LEFT`; `10uL PIPETTE RIGHT`; `300uL PIPETTE LEFT`; `300uL PIPETTE RIGHT`; `1000uL PIPETTE LEFT`; `1000uL PIPETTE RIGHT`; `MULTICHANNEL LEFT`; `MULTICHANNEL RIGHT` |

The importer preserves each label, XCAF label entry, component ID, bounds,
volume, topology counts, validity, and transform. The component map assigns no
semantic roles. Mapping by list order or visual resemblance is prohibited.

## DXF Findings

The DXF is version `AC1015` and declares `$INSUNITS=4` (millimeters), so its
conversion factor to millimeters is exactly 1. The model-space bounds are:

```text
minimum: (3.174, -0.27903212353738027, 0.0) mm
maximum: (428.626, 276.226, 0.0) mm
```

It contains 3,706 model-space entities: 2,582 lines, 606 arcs, 165 splines,
108 ellipses, 87 lightweight polylines, 56 circles, 51 dimensions, 29 multiline
texts, 18 inserts, 2 DXF `SOLID` entities, one leader, and one tolerance entity.
The inventory records 75 block/layout records and 25 insert transforms across
model space and block definitions. The ezdxf audit found zero errors and applied
zero fixes. The importer did not explode blocks, recover the file, or alter
units.

The DXF is a 2D deck drawing. Its `SOLID` entity type does not mean a closed 3D
solid and is not admitted as collision material.

## Coverage Decision

| Required body | Finding | Admission consequence |
| --- | --- | --- |
| Selected left `p300_single_v2.1` | Generic left/right `300uL PIPETTE` solids exist, but no source field ties them to this software model or GEN2 revision | Correspondence unresolved; moving body unavailable |
| Attached Opentrons 300 uL tip | No identified source geometry | Missing moving geometry |
| Opentrons 300 uL tip rack, slot 5 | No identified source geometry | Missing static geometry and cavities |
| Corning 96-well 360 uL flat plates, slots 1 and 3 | No identified source geometry | Missing static geometry and well cavities |
| OT-2 deck | STEP `REMOVABLE DECK` and millimeter DXF exist | Present for inspection; not aligned to the software deck frame |
| Frame, windows, and doors | Several source-labeled solids exist | Present but semantic static-body mapping is unreviewed |
| Trash container | No identified source geometry | Missing static geometry |

No component has been exported as collision geometry. No display GLB has been
created. Source and derived CAD remain local because redistribution rights are
unreviewed. The numbered SVG depicts component bounding boxes for inspection;
it is explicitly not a rendering mesh or collision representation.

## Reproduce

Create a separate authoring environment; do not install CAD packages into the
native Opentrons environment:

```bash
uv venv \
  --python 3.12 runs/ot2-cad-authoring/.venv
uv pip install \
  --python runs/ot2-cad-authoring/.venv/bin/python --require-hashes \
  -r probes/ot2_motion/cad-requirements.lock
runs/ot2-cad-authoring/.venv/bin/python -m probes.ot2_motion.import_cad \
  --source-directory /absolute/path/to/pinned-ot2-cad-files \
  --out-root runs/ot2-motion-assets
```

The command creates a directory named by the STEP digest:

```text
runs/ot2-motion-assets/f8bf145b878683337ec0f89b74668bd7e350d674777762fab9befbcd014b42d4/
  inventory.json
  component-map.json
  coverage.json
  component-bounds.svg
  conversion.json
```

Output creation is exclusive. A pre-existing digest directory is an error, so a
retained inspection cannot be overwritten silently. Two independent runs in
different output roots produced byte-identical files for all five artifacts.

## Verification

The authoring environment is pinned to CadQuery 2.8.0, cadquery-ocp
7.9.3.1.1, ezdxf 1.4.4, and transitive dependencies with hashes. A clean
installation from the lock succeeded. Six focused tests passed in that clean
environment in 111.15 seconds; the warmed environment completed them in 3.26
seconds. The native Opentrons environment completed the broader instrument-model
suite with 78 passing tests and one expected CAD-module skip because CAD
dependencies are intentionally absent there. The focused tests cover:

- separate synthetic STEP components and source labels;
- a translated and rotated assembly placement;
- inch STEP-to-millimeter conversion against known box dimensions;
- an open STEP shell that remains inspectable but fails solid admission;
- inch DXF units and block insertion transforms;
- a unitless DXF retained as unresolved, with no millimeter geometry;
- digest rejection before STEP parsing; and
- rejection of nonfinite inventory coordinates.

The implementation follows CadQuery's documented STEP/XCAF unit behavior and
ezdxf's documented `$INSUNITS` and explicit block-transform behavior:

- <https://cadquery.readthedocs.io/en/latest/importexport.html>
- <https://cadquery.readthedocs.io/en/latest/classreference.html#cadquery.Assembly.importStep>
- <https://ezdxf.readthedocs.io/en/stable/concepts/units.html>
- <https://ezdxf.readthedocs.io/en/stable/blocks/insert.html>

## Remaining Evidence

Before whole-instrument collision checks, a reviewer must establish the exact
selected-pipette correspondence and motion anchor, obtain identified tip/rack/
labware/trash geometry, approve a component-role map tied to source digests,
solve and validate the CAD/DXF-to-software-deck transform from sourced landmarks,
and separately admit cavity-preserving collision representations. Physical
measurements and redistribution review remain independent gates.
