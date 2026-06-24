"""
LLM-driven trajectory runner for pylabrobot_lab_v0 world.

Uses DeepSeek v4-pro with thinking mode to generate a real agent
trajectory against the PyLabRobot-backed dry-run lab deck.

Same architecture as trajectory_runner.py, but dispatches tools
against pylabrobot_lab_v0's LabState (Deck + VolumeTracker) instead
of unitelabs_plate_qc_v0's SQLite.

Output:
  - trajectory_pylabrobot_{scenario}_seed{seed}_{timestamp}.json
  - trajectory_pylabrobot_{...}_messages.jsonl
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# Fix Windows console encoding for Unicode characters
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from typing import Any

# ── Ensure the project is importable ────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from openai import OpenAI

from api_gym.worlds.pylabrobot_lab_v0.sampler import sample_episode
from api_gym.worlds.pylabrobot_lab_v0.tools import TOOL_DEFINITIONS, dispatch_tool
from api_gym.worlds.pylabrobot_lab_v0.verifier import verify_run

# ── Configuration ────────────────────────────────────────────────────────
MODEL = "deepseek-v4-pro"
BASE_URL = "https://api.deepseek.com"
MAX_TURNS = 12
TEMPERATURE = 0.0

SYSTEM_PROMPT = """\
You are a lab automation agent solving a Datalox API Gym pylabrobot_lab_v0 task.

The environment is a DRY-RUN lab deck backed by PyLabRobot — no real hardware
is connected. The deck has standard SBS-format plates with VolumeTracker for
liquid tracking, and chatterbox simulation backends.

You have access to lab tools for inspecting the deck, manipulating liquids,
reading absorbance, and submitting protocol decisions.

STANDARD LAB PROCEDURE for plate QC:
1. Always inspect the deck state first to see what labware is loaded.
2. Inspect each labware object (source plate, target/assay plate, tip rack)
   to understand well contents, volumes, and available tips.
3. Use standard transfer volumes — typically 50 uL for QC assays.
4. OD600 (600 nm) is the standard wavelength for absorbance measurements
   in plate QC workflows. Always try 600 nm first.
5. Match your aspirate/dispense volume exactly. If you aspirate 50 uL,
   dispense exactly 50 uL.
6. Reference format for wells: 'labware_name:well_id'
   (e.g. 'source_plate:A1', 'tip_rack_01:A1').
7. After obtaining a valid readout, submit the protocol decision with
   the readout evidence.

Rules:
- Use the provided tools for every state inspection and mutation.
- Do not answer from task text alone — you MUST call tools to inspect state.
- Do not attempt to read lab_state.json or any hidden verifier state.
- When you have enough evidence, submit a final protocol decision using
  submit_protocol with the supporting readout evidence.
- Think step by step before each tool call.
"""


def _load_api_key() -> str:
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        print(f"ERROR: DEEPSEEK_API_KEY environment variable is not set.")
        sys.exit(1)
    return key


def _make_tool_message(tool_call_id: str, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": json.dumps(result, ensure_ascii=False),
    }


def run_trajectory(run_dir: Path, output_dir: Path) -> dict[str, Any]:
    """Run the LLM agent loop against a pylabrobot_lab_v0 episode."""

    # ── Load task ──────────────────────────────────────────────────────
    task_path = run_dir / "task.json"
    if not task_path.exists():
        raise FileNotFoundError(f"task.json not found at {task_path}")
    task = json.loads(task_path.read_text(encoding="utf-8"))
    user_prompt = task["prompt"]

    # ── Load run metadata ──────────────────────────────────────────────
    run_meta_path = run_dir / "run.json"
    run_meta = json.loads(run_meta_path.read_text(encoding="utf-8")) if run_meta_path.exists() else {}

    # ── Initialize DeepSeek client ─────────────────────────────────────
    api_key = _load_api_key()
    client = OpenAI(api_key=api_key, base_url=BASE_URL)

    # ── Build initial messages ─────────────────────────────────────────
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    # ── Trajectory recording ───────────────────────────────────────────
    turns: list[dict[str, Any]] = []
    tool_call_log: list[dict[str, Any]] = []
    final_answer: dict[str, Any] | None = None
    stop_reason = "max_turns"

    # ── Agent loop ─────────────────────────────────────────────────────
    for turn_idx in range(1, MAX_TURNS + 1):
        print(f"\n{'='*60}")
        print(f"Turn {turn_idx}/{MAX_TURNS}")
        print(f"{'='*60}")

        # --- Call LLM ---
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOL_DEFINITIONS,
            tool_choice="auto",
            stream=False,
            temperature=TEMPERATURE,
            extra_body={"thinking": {"type": "enabled"}},
        )

        choice = response.choices[0]
        message = choice.message

        # --- Extract reasoning (DeepSeek thinking) ---
        reasoning_content = getattr(message, "reasoning_content", None) or ""

        # --- Extract tool calls ---
        tool_calls = getattr(message, "tool_calls", None) or []

        if not tool_calls:
            # Agent finished — record final answer
            content = message.content or ""
            safe_content = content[:200].encode("ascii", errors="replace").decode("ascii")
            print(f"FINAL ANSWER: {safe_content}...")
            final_answer = {
                "content": content,
                "stop_reason": "assistant_final",
                "turns": turn_idx,
            }
            stop_reason = "assistant_final"

            messages.append({"role": "assistant", "content": content})
            break

        # --- Process tool calls ---
        assistant_msg: dict[str, Any] = {
            "role": "assistant",
            "content": message.content or "",
        }
        tc_list = []
        for tc in tool_calls:
            tc_list.append({
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            })
        assistant_msg["tool_calls"] = tc_list
        if reasoning_content:
            assistant_msg["reasoning_content"] = reasoning_content
        messages.append(assistant_msg)

        # --- Dispatch each tool call ---
        for tc in tool_calls:
            tool_name = tc.function.name
            try:
                arguments = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                arguments = {}

            print(f"  TOOL: {tool_name}({json.dumps(arguments)})")

            # Dispatch against the in-memory LabState (resolved via run_dir)
            result = dispatch_tool(run_dir, name=tool_name, arguments=arguments)

            ok_str = "OK" if result.get("ok") else "ERROR"
            print(f"  RESULT [{ok_str}]: {json.dumps(result, ensure_ascii=False)[:200]}")

            # Append tool result to messages
            messages.append(_make_tool_message(tc.id, result))

            # Record in trajectory
            turn_record = {
                "turn": turn_idx,
                "thought": reasoning_content if reasoning_content else f"Calling {tool_name}",
                "tool_call": {
                    "id": tc.id,
                    "name": tool_name,
                    "arguments": arguments,
                },
                "tool_result": result,
            }
            turns.append(turn_record)

            # Record in tool call log
            tool_call_log.append({
                "turn": turn_idx,
                "id": tc.id,
                "name": tool_name,
                "arguments": arguments,
                "result": result,
            })

            # Reset reasoning for subsequent tool calls in same turn
            reasoning_content = ""

    # ── If max turns reached without final answer ──────────────────────
    if final_answer is None:
        final_answer = {
            "content": None,
            "stop_reason": "max_turns",
            "turns": MAX_TURNS,
        }
        stop_reason = "max_turns"

    # ── Run verifier ───────────────────────────────────────────────────
    verifier_result = verify_run(run_dir).to_dict()
    ok_str = "PASS" if verifier_result["ok"] else "FAIL"
    print(f"\nVerifier [{ok_str}]:")
    for check in verifier_result["checks"]:
        status = "✅" if check["ok"] else "❌"
        print(f"  {status} {check['name']}")

    # ── Build trajectory ───────────────────────────────────────────────
    trajectory = {
        "schema_version": "datalox.trajectory.v0",
        "world": run_meta.get("world", "pylabrobot_lab_v0"),
        "world_id": run_meta.get("world_id", "pylabrobot-lab-v0"),
        "scenario": run_meta.get("scenario", "plate_transfer_qc"),
        "seed": run_meta.get("seed"),
        "mode": run_meta.get("mode", "dry_run"),
        "model": MODEL,
        "backend": "PyLabRobot + ChatterBox",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "task": task,
        "turns": turns,
        "final_answer": final_answer,
        "total_turns": len(turns),
        "verifier_result": verifier_result,
    }

    # ── Write outputs ──────────────────────────────────────────────────
    output_dir.mkdir(parents=True, exist_ok=True)

    ts = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
    world_name = run_meta.get("world", "pylabrobot_lab_v0")
    scenario_name = run_meta.get("scenario", "plate_transfer_qc")
    seed_val = run_meta.get("seed", 0)
    prefix = f"trajectory_pylabrobot_{world_name}_{scenario_name}_seed{seed_val}_{ts}"

    traj_path = output_dir / f"{prefix}.json"
    traj_path.write_text(
        json.dumps(trajectory, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nTrajectory saved to {traj_path}")

    # messages.jsonl
    msg_path = output_dir / f"{prefix}_messages.jsonl"
    with open(msg_path, "w", encoding="utf-8") as f:
        for msg in messages:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")
    print(f"Messages saved to {msg_path}")

    return trajectory


def main():
    import argparse
    import tempfile

    parser = argparse.ArgumentParser(
        description="Run LLM-driven agent trajectory against pylabrobot_lab_v0"
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Deterministic scenario seed (default: 42).",
    )
    parser.add_argument(
        "--scenario", default="plate_transfer_qc",
        help="Scenario name (default: plate_transfer_qc).",
    )
    parser.add_argument(
        "--out", default=None,
        help="Optional run directory (temp dir is used if not specified).",
    )
    parser.add_argument(
        "--output", default=None,
        help="Output directory for trajectory files (default: gen_trajectory/output).",
    )
    args = parser.parse_args()

    # ── Create the episode (registers LabState in same process) ──────
    if args.out:
        run_dir = Path(args.out).resolve()
        run_dir.mkdir(parents=True, exist_ok=True)
    else:
        base = PROJECT_ROOT / "runs" / "demo_web"
        base.mkdir(parents=True, exist_ok=True)
        run_dir = Path(tempfile.mkdtemp(
            prefix=f"plr_{args.scenario}_seed{args.seed}_", dir=base
        ))

    print(f"Sampling episode: scenario={args.scenario}, seed={args.seed}")
    episode = sample_episode(scenario=args.scenario, seed=args.seed, out_dir=run_dir)
    print(f"  Deck: {episode.lab_state.deck_info['deck_name']}")
    print(f"  Plates: {episode.lab_state.deck_info['plate_name']}, {episode.lab_state.deck_info['source_plate_name']}")
    print(f"  Tips: {episode.lab_state.deck_info['tip_rack_name']} ({episode.lab_state.deck_info['tip_count']} available)")

    output_dir = (
        Path(args.output)
        if args.output
        else Path(__file__).resolve().parent / "output"
    ).resolve()

    print(f"\nRun dir:    {run_dir}")
    print(f"Output dir: {output_dir}")
    print(f"Model:      {MODEL}")
    print(f"Backend:    PyLabRobot + ChatterBox (dry-run)")
    print(f"Max turns:  {MAX_TURNS}")

    trajectory = run_trajectory(run_dir, output_dir)

    # Summary
    print(f"\n{'='*60}")
    print("TRAJECTORY SUMMARY")
    print(f"{'='*60}")
    print(f"World:       {trajectory['world']}")
    print(f"Scenario:    {trajectory['scenario']}")
    print(f"Seed:        {trajectory['seed']}")
    print(f"Total turns: {trajectory['total_turns']}")
    if trajectory["final_answer"]["stop_reason"] == "assistant_final":
        print("Agent stopped by producing a final answer.")
    else:
        print(f"Agent stopped due to {trajectory['final_answer']['stop_reason']}.")
    print(f"Tools used:  {[t['tool_call']['name'] for t in trajectory['turns']]}")
    print(f"Verifier:    {'PASS' if trajectory['verifier_result']['ok'] else 'FAIL'}")


if __name__ == "__main__":
    main()
