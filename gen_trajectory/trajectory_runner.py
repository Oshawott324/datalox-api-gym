"""
LLM-driven trajectory runner for unitelabs_plate_qc_v0 world.

Uses DeepSeek v4-pro with thinking mode enabled to generate a real agent
trajectory — the LLM decides every tool call based on the task prompt and
prior tool results.

Output:
  - trajectory.json   : full trajectory with thoughts, tool calls, results
  - tool_calls.jsonl  : one line per tool invocation
  - messages.jsonl    : complete LLM message history
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# Fix Windows console encoding for Unicode characters (e.g. µ)
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from typing import Any

from openai import OpenAI

# ── Ensure the project is importable ────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api_gym.worlds.unitelabs_plate_qc_v0.tools import (
    TOOL_DEFINITIONS,
    dispatch_tool,
)
from api_gym.worlds.unitelabs_plate_qc_v0.verifier import verify_run

# ── Configuration ────────────────────────────────────────────────────────────
MODEL = "deepseek-v4-pro"
BASE_URL = "https://api.deepseek.com"
API_KEY_ENV = "DEEPSEEK_API_KEY"
MAX_TURNS = 12
TEMPERATURE = 0.0

SYSTEM_PROMPT = """\
You are a lab automation agent solving a Datalox API Gym unitelabs_plate_qc_v0 task.

The environment is a DRY-RUN lab deck — no real hardware is connected.
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
6. After obtaining a valid readout, submit the protocol decision with
   the readout evidence.

Rules:
- Use the provided tools for every state inspection and mutation.
- Do not answer from task text alone — you MUST call tools to inspect state.
- Do not attempt to read state.sqlite or any hidden verifier state.
- When you have enough evidence, submit a final protocol decision using
  submit_protocol with the supporting readout evidence.
- Think step by step before each tool call.
"""


def _load_api_key() -> str:
    key = os.environ.get(API_KEY_ENV)
    if not key:
        print(f"ERROR: Environment variable {API_KEY_ENV} is not set.")
        print(f"Usage: set {API_KEY_ENV}=sk-... && python trajectory_runner.py --run <run_dir>")
        sys.exit(1)
    return key


def _flatten_tools_for_deepseek(tool_defs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """DeepSeek expects OpenAI-compatible tool format (top-level 'type: function')."""
    return tool_defs  # Already in OpenAI format


def _make_tool_message(tool_call_id: str, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": json.dumps(result, ensure_ascii=False),
    }


def run_trajectory(run_dir: Path, output_dir: Path) -> dict[str, Any]:
    """Run the LLM agent loop and record the full trajectory."""

    # ── Load task ────────────────────────────────────────────────────────
    task_path = run_dir / "task.json"
    if not task_path.exists():
        raise FileNotFoundError(f"task.json not found at {task_path}")
    task = json.loads(task_path.read_text(encoding="utf-8"))
    user_prompt = task["prompt"]

    # ── Load run metadata ────────────────────────────────────────────────
    run_meta_path = run_dir / "run.json"
    run_meta = json.loads(run_meta_path.read_text(encoding="utf-8")) if run_meta_path.exists() else {}

    # ── State DB path ────────────────────────────────────────────────────
    db_path = run_dir / run_meta.get("state_db", "state.sqlite")
    if not db_path.exists():
        raise FileNotFoundError(f"State database not found at {db_path}")

    # ── Initialize DeepSeek client ───────────────────────────────────────
    api_key = _load_api_key()
    client = OpenAI(api_key=api_key, base_url=BASE_URL)

    # ── Build initial messages ───────────────────────────────────────────
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    tools = _flatten_tools_for_deepseek(TOOL_DEFINITIONS)

    # ── Trajectory recording ─────────────────────────────────────────────
    turns: list[dict[str, Any]] = []
    tool_call_log: list[dict[str, Any]] = []
    final_answer: dict[str, Any] | None = None
    stop_reason = "max_turns"

    # ── Agent loop ───────────────────────────────────────────────────────
    for turn_idx in range(1, MAX_TURNS + 1):
        print(f"\n{'='*60}")
        print(f"Turn {turn_idx}/{MAX_TURNS}")
        print(f"{'='*60}")

        # --- Call LLM ---
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tools,
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

            # Record the final assistant message
            messages.append({"role": "assistant", "content": content})
            break

        # --- Process tool calls ---
        # Add assistant message with tool_calls to history
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

            # Dispatch against the real SQLite state
            result = dispatch_tool(db_path, name=tool_name, arguments=arguments)

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

    # ── If max turns reached without final answer ────────────────────────
    if final_answer is None:
        final_answer = {
            "content": None,
            "stop_reason": "max_turns",
            "turns": MAX_TURNS,
        }
        stop_reason = "max_turns"

    # ── Run verifier ─────────────────────────────────────────────────────
    verifier_result = verify_run(run_dir).to_dict()
    ok_str = "PASS" if verifier_result["ok"] else "FAIL"
    print(f"\nVerifier [{ok_str}]:")
    for check in verifier_result["checks"]:
        status = "✅" if check["ok"] else "❌"
        print(f"  {status} {check['name']}")

    # ── Build trajectory ─────────────────────────────────────────────────
    trajectory = {
        "schema_version": "datalox.trajectory.v0",
        "branch": "api-grounding",
        "world": run_meta.get("world", "unitelabs_plate_qc_v0"),
        "world_id": run_meta.get("world_id", "unitelabs-plate-qc-v0"),
        "scenario": run_meta.get("scenario", "plate_transfer_qc"),
        "seed": run_meta.get("seed"),
        "mode": run_meta.get("mode", "dry_run"),
        "model": MODEL,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "task": task,
        "turns": turns,
        "final_answer": final_answer,
        "total_turns": len(turns),
        "verifier_result": verifier_result,
    }

    # ── Write outputs ────────────────────────────────────────────────────
    output_dir.mkdir(parents=True, exist_ok=True)

    # Unique filename per run: trajectory_<world>_<scenario>_<seed>_<timestamp>.json
    ts = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
    world_name = run_meta.get("world", "unknown")
    scenario_name = run_meta.get("scenario", "unknown")
    seed_val = run_meta.get("seed", 0)
    base_name = f"trajectory_{world_name}_{scenario_name}_seed{seed_val}_{ts}"

    traj_path = output_dir / f"{base_name}.json"
    traj_path.write_text(json.dumps(trajectory, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nTrajectory saved to {traj_path}")

    # tool_calls.jsonl (in run_dir for verifier compatibility)
    tc_path = run_dir / "agent_tool_calls.jsonl"
    with open(tc_path, "w", encoding="utf-8") as f:
        for tc in tool_call_log:
            f.write(json.dumps(tc, ensure_ascii=False) + "\n")
    print(f"Tool calls saved to {tc_path}")

    # messages.jsonl
    msg_path = output_dir / f"{base_name}_messages.jsonl"
    with open(msg_path, "w", encoding="utf-8") as f:
        for msg in messages:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")
    print(f"Messages saved to {msg_path}")

    return trajectory


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Run LLM-driven agent trajectory")
    parser.add_argument("--run", required=True, help="Path to the run directory (created by session create)")
    parser.add_argument("--output", default=None, help="Output directory for trajectory files (default: gen_trajectory/output)")
    args = parser.parse_args()

    run_dir = Path(args.run).resolve()
    if not run_dir.exists():
        print(f"ERROR: Run directory does not exist: {run_dir}")
        sys.exit(1)

    output_dir = Path(args.output) if args.output else Path(__file__).resolve().parent / "output"
    output_dir = output_dir.resolve()

    print(f"Run dir:    {run_dir}")
    print(f"Output dir: {output_dir}")
    print(f"Model:      {MODEL}")
    print(f"Max turns:  {MAX_TURNS}")

    trajectory = run_trajectory(run_dir, output_dir)

    # Summary
    print(f"\n{'='*60}")
    print("TRAJECTORY SUMMARY")
    print(f"{'='*60}")
    print(f"Total turns: {trajectory['total_turns']}")
    if trajectory["final_answer"]["stop_reason"] == "assistant_final":
        print("Agent stopped by producing a final answer.")
    else:
        print(f"Agent stopped due to {trajectory['final_answer']['stop_reason']}.")
    print(f"Tools used: {[t['tool_call']['name'] for t in trajectory['turns']]}")


if __name__ == "__main__":
    main()
