"""Evaluation helpers for OpenAI-compatible billing_support_v0 agents."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from api_gym.runner.openai_compatible import run_openai_compatible_agent
from api_gym.worlds.billing_support_v0.sampler import SCENARIOS, WORLD, sample_episode


def run_eval_suite(
    *,
    world: str,
    scenarios: list[str],
    seeds: list[int],
    model: str,
    base_url: str,
    api_key: str | None,
    out: Path,
    max_turns: int = 12,
) -> list[dict[str, Any]]:
    """Run one model-backed episode per scenario/seed and write JSONL rows."""
    if world != WORLD:
        raise ValueError(f"Unsupported world '{world}'. Supported worlds: {WORLD}")
    if not scenarios:
        raise ValueError("At least one scenario is required.")
    if not seeds:
        raise ValueError("At least one seed is required.")
    unsupported = sorted(set(scenarios) - set(SCENARIOS))
    if unsupported:
        supported = ", ".join(sorted(SCENARIOS))
        raise ValueError(f"Unsupported scenarios: {', '.join(unsupported)}. Supported scenarios: {supported}")
    if max_turns < 1:
        raise ValueError("max_turns must be at least 1.")

    out = out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    run_root = _run_root_for_output(out)
    run_root.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    with out.open("w", encoding="utf-8") as handle:
        for scenario in scenarios:
            for seed in seeds:
                row = _run_one_eval_task(
                    world=world,
                    scenario=scenario,
                    seed=seed,
                    model=model,
                    base_url=base_url,
                    api_key=api_key,
                    run_root=run_root,
                    max_turns=max_turns,
                )
                rows.append(row)
                handle.write(json.dumps(row, sort_keys=True) + "\n")
                handle.flush()
    return rows


def summarize_eval_report(input_path: Path) -> dict[str, Any]:
    """Summarize an eval JSONL file into pass-rate counts."""
    rows = _read_jsonl(input_path)
    by_scenario_counts: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "passed": 0})
    passed = 0

    for row in rows:
        scenario = str(row["scenario"])
        row_passed = bool(row["passed"])
        passed += int(row_passed)
        by_scenario_counts[scenario]["total"] += 1
        by_scenario_counts[scenario]["passed"] += int(row_passed)

    total = len(rows)
    by_scenario = {
        scenario: {
            "total": counts["total"],
            "passed": counts["passed"],
            "pass_rate": _pass_rate(counts["passed"], counts["total"]),
        }
        for scenario, counts in sorted(by_scenario_counts.items())
    }
    return {"total": total, "passed": passed, "pass_rate": _pass_rate(passed, total), "by_scenario": by_scenario}


def parse_csv_list(value: str) -> list[str]:
    """Parse a comma-separated CLI list and reject empty values."""
    items = [item.strip() for item in value.split(",")]
    if not items or any(not item for item in items):
        raise ValueError("Comma-separated lists cannot contain empty values.")
    return items


def parse_seed_list(value: str) -> list[int]:
    """Parse comma-separated integer seeds."""
    seeds: list[int] = []
    for item in parse_csv_list(value):
        try:
            seeds.append(int(item))
        except ValueError as exc:
            raise ValueError(f"Seed must be an integer: {item}") from exc
    return seeds


def _run_one_eval_task(
    *,
    world: str,
    scenario: str,
    seed: int,
    model: str,
    base_url: str,
    api_key: str | None,
    run_root: Path,
    max_turns: int,
) -> dict[str, Any]:
    run_dir = run_root / scenario / f"seed-{seed}"
    episode = sample_episode(scenario=scenario, seed=seed, out_dir=run_dir)
    result = run_openai_compatible_agent(
        run_dir=episode.run_dir,
        model=model,
        base_url=base_url,
        api_key=api_key,
        max_turns=max_turns,
    )
    final_answer = result["final_answer"]
    verifier_result = result["verifier_result"]
    return {
        "world": world,
        "scenario": scenario,
        "seed": seed,
        "run_dir": str(episode.run_dir),
        "model": model,
        "base_url": base_url,
        "verifier_result": verifier_result,
        "passed": bool(verifier_result["ok"]),
        "final_answer": str(final_answer.get("content", "")),
        "tool_call_count": _jsonl_count(episode.run_dir / "tool_calls.jsonl"),
        "stop_reason": str(final_answer.get("stop_reason", "")),
        "created_at": _utc_now(),
    }


def _run_root_for_output(out: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return out.parent / f"{out.stem}-runs" / timestamp


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"JSONL row {line_number} must be an object.")
            rows.append(row)
    return rows


def _jsonl_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def _pass_rate(passed: int, total: int) -> float:
    return passed / total if total else 0.0


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
