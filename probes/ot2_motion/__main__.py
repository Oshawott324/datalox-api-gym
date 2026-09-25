"""Run the fixed Phase 0 experiment and retain its explicit claim boundaries."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from importlib.metadata import version
from pathlib import Path
import platform
import subprocess
import sys
import time

from api_gym.instrument_models.geometry.collision import Body, Box, Sphere, overlaps, sweep


def run_probe() -> dict:
    reference_process = subprocess.run(
        [sys.executable, "-m", "probes.ot2_motion.reference"],
        check=True, capture_output=True, text=True, timeout=120,
    )
    if "Traceback" in reference_process.stderr or "RuntimeWarning" in reference_process.stderr:
        raise RuntimeError("Native simulator emitted an execution/cleanup error: " + reference_process.stderr)
    reference = json.loads(reference_process.stdout)
    # This is an authored mathematical obstruction, not claimed rack/trash CAD.
    wall = Body(Box((0.01, 30, 40)), (140, 74.24, 20))
    cases = []
    durations = []
    for case in reference["cases"]:
        queries = []
        for segment in case["segments"]:
            start = time.perf_counter()
            result = sweep(Body(Sphere(0.5), tuple(segment["start_mm"])), tuple(segment["reported_end_mm"]), wall)
            durations.append((time.perf_counter() - start) * 1000)
            queries.append(asdict(result))
        cases.append({"id": case["id"], "segment_queries": queries, "intersects_authored_wall": any(x["intersects"] for x in queries)})
    thin_wall = Body(Box((0.01, 10, 10)), (0, 0, 0))
    thin = {
        "start_intersects": overlaps(Body(Sphere(0.5), (-5, 0, 0)), thin_wall),
        "end_intersects": overlaps(Body(Sphere(0.5), (5, 0, 0)), thin_wall),
        "sweep": asdict(sweep(Body(Sphere(0.5), (-5, 0, 0)), (5, 0, 0), thin_wall)),
    }
    by_id = {case["id"]: case for case in cases}
    passed = (
        not thin["start_intersects"] and not thin["end_intersects"] and thin["sweep"]["intersects"]
        and not by_id["raised_cross_plate"]["intersects_authored_wall"]
        and by_id["direct_cross_plate"]["intersects_authored_wall"]
    )
    return {
        "phase": "P0", "feasibility_passed": passed,
        "physical_validation": "not performed", "instrument_geometry_admission": "pending",
        "geometry_scope": "fixed-orientation boxes/spheres; closed linear segments; authored fixtures",
        "probe_body": {"shape": "sphere", "radius_mm": 0.5, "is_pipette_model": False},
        "obstacle": asdict(wall), "reference": reference, "cases": cases, "thin_obstacle": thin,
        "timing_ms": {"samples": len(durations), "max": max(durations)},
        "system": {"platform": platform.platform(), "python": platform.python_version()},
        "dependencies": {name: version(name) for name in ("opentrons", "opentrons-shared-data", "python-fcl", "numpy", "scipy", "trimesh")},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = run_probe()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as output:
        output.write(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({"output": str(args.out), "feasibility_passed": result["feasibility_passed"]}))
    return 0 if result["feasibility_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
