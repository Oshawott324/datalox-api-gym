"""Run policies on OT-2 protocol tasks and tabulate the checks.

Examples::

    # Fixed-script baseline on every family and mode, seeds 0-9
    python -m harness.ot2_protocol.runner --policy script --seeds 0-9 --out runs/ot2_protocol/script

    # An OpenAI-compatible model (for DeepSeek set --base-url https://api.deepseek.com)
    python -m harness.ot2_protocol.runner --policy chat --model <model-name> \
        --base-url https://api.deepseek.com --api-key-env DEEPSEEK_API_KEY \
        --extra-body '{}' --seeds 0-9 --out runs/ot2_protocol/deepseek

The agent sees the public task and tool results only. Hidden task state and
check results go to the output directory after each episode.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

from api_gym.worlds.ot2_protocol_v0 import FAMILIES, FAMILY_MODES, Episode, OfficialAnalyzer, make_task, verify
from api_gym.worlds.ot2_protocol_v0.tasks import TaskInstance
from api_gym.worlds.ot2_protocol_v0.tools import openai_tools
from harness.ot2_protocol.policies import (
    CAUTIOUS_PROBE_STEPS,
    ArcScript,
    ChatPolicy,
    Policy,
    ProbeScript,
    StaleOffsetScript,
    timed,
)

SYSTEM_PROMPT = (
    "You operate an Opentrons OT-2 liquid-handling robot through the tools provided. Start by calling get_task, "
    "follow its instruction and rules, and call finish when you are done."
)
MAX_TURNS = 60
MAX_TURNS_WITHOUT_TOOLS = 3


def run_episode(policy: Policy, task: TaskInstance, analyzer: OfficialAnalyzer | None,
                max_turns: int = MAX_TURNS) -> dict[str, Any]:
    episode = Episode(task, analyzer if task.family == "arc_four_slots" else None)
    tools = openai_tools(episode.tool_names)
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT},
                                      {"role": "user", "content": "Begin."}]
    latencies: list[float] = []
    usage: list[dict[str, Any]] = []
    idle_turns = 0
    error = None
    for _ in range(max_turns):
        try:
            step, seconds = timed(policy, messages, tools)
        except Exception as exc:  # noqa: BLE001 - record provider or policy failures as episode failures
            error = f"{type(exc).__name__}: {exc}"
            break
        latencies.append(round(seconds, 3))
        usage.append(step.usage)
        messages.append(step.assistant_message)
        if not step.tool_calls:
            idle_turns += 1
            if idle_turns >= MAX_TURNS_WITHOUT_TOOLS:
                break
            messages.append({"role": "user", "content": "Use the tools. Call finish when you are done."})
            continue
        for call in step.tool_calls:
            result = episode.call(call.name, call.arguments)
            messages.append({"role": "tool", "tool_call_id": call.call_id, "content": json.dumps(result)})
        if episode.log.finished:
            break
    verification = verify(episode)
    return {
        "task_id": task.task_id,
        "family": task.family,
        "mode": task.mode,
        "seed": task.seed,
        "policy": policy.name,
        "passed": verification.passed,
        "failure_codes": verification.failure_codes,
        "checks": verification.checks,
        "metrics": verification.metrics,
        "decision_latencies_s": latencies,
        "usage": usage,
        "policy_error": error,
        "hidden": task.hidden,
        "tool_calls": episode.log.tool_calls,
    }


def summarize(records: list[dict[str, Any]]) -> str:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        groups[(record["policy"], record["family"], record["mode"])].append(record)
    lines = ["| Policy | Family | Mode | Passed | Failure codes | Median s/decision | Median tool calls |",
             "| --- | --- | --- | ---: | --- | ---: | ---: |"]
    for (policy, family, mode), items in sorted(groups.items()):
        codes = Counter(code for item in items for code in item["failure_codes"])
        latencies = [x for item in items for x in item["decision_latencies_s"]]
        calls = [item["metrics"].get("tool_calls", 0) for item in items]
        lines.append(
            f"| {policy} | {family} | {mode} | {sum(i['passed'] for i in items)}/{len(items)} | "
            f"{', '.join(f'{c} x{n}' for c, n in codes.most_common()) or '-'} | "
            f"{statistics.median(latencies) if latencies else 0:.2f} | {statistics.median(calls) if calls else 0:g} |"
        )
    return "\n".join(lines) + "\n"


def _seeds(text: str) -> list[int]:
    if "-" in text:
        start, end = text.split("-", 1)
        return list(range(int(start), int(end) + 1))
    return [int(part) for part in text.split(",")]


def _script_factory(family: str) -> Callable[[], Policy]:
    return {
        "arc_four_slots": lambda: ArcScript(),
        "probe_tube_bottom": lambda: ProbeScript(CAUTIOUS_PROBE_STEPS),
        "stale_offsets": lambda: StaleOffsetScript(),
    }[family]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--policy", choices=["script", "chat"], required=True)
    parser.add_argument("--families", default=",".join(FAMILIES))
    parser.add_argument("--modes", default="official_tools,free_code")
    parser.add_argument("--seeds", default="0-4")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--model")
    parser.add_argument("--base-url")
    parser.add_argument("--api-key-env", default="DEEPSEEK_API_KEY")
    parser.add_argument("--extra-body", default="{}", help="JSON merged into each request, e.g. thinking settings")
    args = parser.parse_args()

    analyzer = OfficialAnalyzer()
    if not OfficialAnalyzer.available():
        raise SystemExit(f"OT-2 analyzer not found at {analyzer.python}; set DATALOX_OT2_ANALYSIS_PYTHON")
    args.out.mkdir(parents=True, exist_ok=True)
    records = []
    with (args.out / "episodes.jsonl").open("w") as handle:
        for family in args.families.split(","):
            for mode in args.modes.split(","):
                if mode not in FAMILY_MODES[family]:
                    continue
                for seed in _seeds(args.seeds):
                    if args.policy == "chat":
                        if not args.model or not args.base_url:
                            raise SystemExit("--model and --base-url are required for --policy chat")
                        policy: Policy = ChatPolicy(args.model, args.base_url, args.api_key_env,
                                                    json.loads(args.extra_body))
                    else:
                        policy = _script_factory(family)()
                    record = run_episode(policy, make_task(family, seed, mode), analyzer)
                    records.append(record)
                    handle.write(json.dumps(record, default=str) + "\n")
                    handle.flush()
                    print(f"{record['task_id']}: {'pass' if record['passed'] else 'fail'} {record['failure_codes']}")
    summary = summarize(records)
    (args.out / "summary.md").write_text(summary)
    print(summary)


if __name__ == "__main__":
    main()
