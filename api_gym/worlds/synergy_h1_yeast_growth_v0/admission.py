"""Admission checks for the Synergy H1 workflow and its plan mutations."""

from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

from .plans import MUTANTS, NEAR_MISSES, Plan, oracle_plan
from .sampler import CONTRACT, SCENARIO, sample_episode
from .tools import dispatch_tool
from .verifier import verify_run


def execute_plan(run_dir: Path, plan: Plan) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for item in plan:
        result = dispatch_tool(run_dir, name=item["name"], arguments=item["arguments"])
        results.append({"name": item["name"], "arguments": item["arguments"], "result": result})
    return results


def _run_case(*, out_dir: Path, case_id: str, plan: Plan, expected_codes: tuple[str, ...]) -> dict[str, Any]:
    episode = sample_episode(scenario=SCENARIO, seed=17, out_dir=out_dir / case_id)
    started = time.perf_counter()
    tool_results = execute_plan(episode.run_dir, plan)
    verification = verify_run(episode.run_dir)
    elapsed_s = time.perf_counter() - started
    failures = tuple(check["name"] for check in verification.checks if not check["ok"])
    tool_errors = [
        item for item in tool_results if not bool(item["result"].get("ok"))
    ]
    expected_ok = not expected_codes
    ok = (
        verification.ok is expected_ok
        and Counter(failures) == Counter(expected_codes)
        and not tool_errors
    )
    return {
        "case_id": case_id,
        "ok": ok,
        "verifier_ok": verification.ok,
        "expected_failure_codes": list(expected_codes),
        "failed_check_names": list(failures),
        "tool_errors": tool_errors,
        "tool_calls": len(tool_results),
        "elapsed_s": round(elapsed_s, 4),
    }


def _sources_resolve() -> dict[str, Any]:
    source_path = Path(__file__).with_name("source_refs.json")
    sources = json.loads(source_path.read_text(encoding="utf-8"))
    required_ids = set(CONTRACT["source_refs"].values())
    missing = sorted(required_ids - set(sources))
    malformed = sorted(
        source_id
        for source_id in required_ids & set(sources)
        if not str(sources[source_id].get("url", "")).startswith("https://")
    )
    return {"ok": not missing and not malformed, "missing": missing, "malformed": malformed}


def run_admission_checks(*, out_dir: Path) -> dict[str, Any]:
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    base = oracle_plan()
    cases = [_run_case(out_dir=out_dir, case_id="oracle", plan=base, expected_codes=())]
    empty_codes = tuple(name for name in (
        "temperature_stabilized_before_series",
        "continuous_orbital_shaking",
        "correct_wavelength",
        "required_replicates_present",
        "measurement_cadence_complete",
        "kinetic_duration_complete",
        "decision_supported_by_complete_series",
    ))
    cases.append(_run_case(out_dir=out_dir, case_id="empty_plan", plan=[], expected_codes=empty_codes))
    for case in MUTANTS:
        cases.append(
            _run_case(
                out_dir=out_dir,
                case_id=case.case_id,
                plan=case.transform(base),
                expected_codes=case.expected_failure_codes,
            )
        )
    for case in NEAR_MISSES:
        cases.append(
            _run_case(
                out_dir=out_dir,
                case_id=case.case_id,
                plan=case.transform(base),
                expected_codes=(),
            )
        )
    sources = _sources_resolve()
    return {
        "ok": all(case["ok"] for case in cases) and sources["ok"],
        "summary": {
            "cases": len(cases),
            "passed": sum(case["ok"] for case in cases),
            "mutants": len(MUTANTS),
            "near_misses": len(NEAR_MISSES),
            "tool_calls": sum(case["tool_calls"] for case in cases),
            "elapsed_s": round(sum(case["elapsed_s"] for case in cases), 4),
        },
        "sources": sources,
        "cases": cases,
    }
