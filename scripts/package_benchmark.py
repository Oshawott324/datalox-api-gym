#!/usr/bin/env python
"""Package LabLongRun-Bench v0 tasks as a benchmark artifact.

Usage:
  python scripts/package_benchmark.py --verify-all
  python scripts/package_benchmark.py --output lablongrun-bench-v0/
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from api_gym.worlds.pylabrobot_lab_v0.sampler import SCENARIOS, sample_episode
from api_gym.worlds.pylabrobot_lab_v0.verifier import verify_run


def main() -> None:
    parser = argparse.ArgumentParser(description="Package LabLongRun-Bench v0")
    parser.add_argument("--verify-all", action="store_true", help="Sample+verify all scenarios")
    parser.add_argument("--output", type=str, default="lablongrun-bench-v0",
                        help="Output directory for packaged benchmark")
    args = parser.parse_args()

    if args.verify_all:
        verify_all_scenarios()
    elif args.output:
        package_benchmark(args.output)
    else:
        print("Use --verify-all to test all scenarios, or --output to package.")
        print(f"Available scenarios: {len(SCENARIOS)}")


def verify_all_scenarios() -> None:
    """Verify that all chatterbox scenarios can be sampled without errors."""
    chatterbox_scenarios = [k for k in sorted(SCENARIOS) if not k.endswith("_ot2")]
    passed = 0
    failed = 0
    for scenario in chatterbox_scenarios:
        td = Path(tempfile.mkdtemp(prefix=f"{scenario}_"))
        try:
            ep = sample_episode(scenario=scenario, seed=42, out_dir=td)
            # Just verify sampling succeeds and produces valid state
            assert ep.lab_state.deck is not None, "deck is None"
            assert ep.task.get("scenario") == scenario
            print(f"  {scenario}: PASS (tip_count={ep.lab_state.deck_info.get('tip_count', 'N/A')})")
            passed += 1
        except Exception as e:
            print(f"  {scenario}: FAIL - {e}")
            failed += 1
    print(f"\n{passed} sampled, {failed} failed out of {len(chatterbox_scenarios)}")


def package_benchmark(output_dir: str) -> None:
    """Package benchmark artifacts."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    tasks = []
    for key in sorted(k for k in SCENARIOS if not k.endswith("_ot2")):
        td = Path(tempfile.mkdtemp(prefix=f"{key}_"))
        ep = sample_episode(scenario=key, seed=42, out_dir=td)
        tasks.append(ep.task)
    (out / "tasks.jsonl").write_text(
        "\n".join(json.dumps(t, ensure_ascii=False) for t in tasks) + "\n",
        encoding="utf-8",
    )
    print(f"Packaged {len(tasks)} tasks to {out / 'tasks.jsonl'}")


if __name__ == "__main__":
    main()
