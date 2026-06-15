"""
Demo server: web-based trajectory visualisation for unitelabs_plate_qc_v0.

Uses a real LLM (DeepSeek) for agent execution — the model decides every
tool call autonomously.  Requires a DeepSeek API key.

Start with:
    set DEEPSEEK_API_KEY=sk-...
    python gen_trajectory/demo/server.py

Then open http://127.0.0.1:8080 in a browser.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

# Fix Windows console encoding for Unicode characters (e.g. emoji)
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Ensure the project root is importable ──────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from api_gym.worlds.unitelabs_plate_qc_v0.sampler import sample_episode
from api_gym.worlds.unitelabs_plate_qc_v0.tools import TOOL_DEFINITIONS, dispatch_tool
from api_gym.worlds.unitelabs_plate_qc_v0.verifier import verify_run
from api_gym.worlds.unitelabs_plate_qc_v0.state import connect, row_to_dict
from api_gym.session import build_session_manifest, check_session_tools
from api_gym.exports.run_export import write_run_export

# ── LLM configuration ──────────────────────────────────────────────────────

MODEL = "deepseek-v4-pro"
BASE_URL = "https://api.deepseek.com"
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

TABLES_FOR_SNAPSHOT = [
    "deck", "labware", "wells", "tips", "pipette_state",
    "control_bands", "transfers", "readouts", "workflow_notes",
    "submissions", "events", "audit_log",
]

# ── In-memory session store ────────────────────────────────────────────────


class DemoSession:
    """Holds the live state for one demo run."""

    def __init__(self, run_dir: Path, api_key: str) -> None:
        self.run_dir = run_dir
        self.db_path = run_dir / "state.sqlite"
        self.task_path = run_dir / "task.json"

        # LLM client
        self.api_key = api_key
        self.client: Any = None  # OpenAI client, lazily initialised

        # LLM conversation state
        self.messages: list[dict[str, Any]] = []

        # Progress tracking
        self.turn_index: int = 0
        self.tool_history: list[dict[str, Any]] = []
        self.state_snapshots: list[dict[str, Any]] = []
        self.final_answer: dict[str, Any] | None = None
        self.stop_reason: str = "pending"

        # Trajectory metadata
        self.world_meta: dict[str, Any] = {}
        self.task: dict[str, Any] = {}
        self.manifest: dict[str, Any] = {}
        self.check_tools_result: dict[str, Any] | None = None
        self.finalize_result: dict[str, Any] | None = None
        self.verifier_result: dict[str, Any] | None = None
        self.export_payload: dict[str, Any] | None = None

        # Load metadata
        run_meta_path = run_dir / "run.json"
        if run_meta_path.exists():
            self.world_meta = json.loads(run_meta_path.read_text(encoding="utf-8"))
        if self.task_path.exists():
            self.task = json.loads(self.task_path.read_text(encoding="utf-8"))

    def init_client(self) -> None:
        """Lazy-init the OpenAI client (import only when needed)."""
        if self.client is not None:
            return
        try:
            from openai import OpenAI
        except ImportError:
            raise HTTPException(
                500,
                "The 'openai' package is required for LLM agent execution. "
                "Install it with: pip install openai",
            )
        self.client = OpenAI(api_key=self.api_key, base_url=BASE_URL)

    def init_messages(self) -> None:
        """Build the initial message list (system + user)."""
        if self.messages:
            return
        task_prompt = self.task.get("prompt", "")
        self.messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": task_prompt},
        ]


# Global session — single-user demo, one session at a time
_session: DemoSession | None = None

# ── FastAPI app ────────────────────────────────────────────────────────────

app = FastAPI(title="UniteLabs Plate QC v0 — Trajectory Demo")

# Static files
STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/")
async def root():
    """Serve the demo frontend."""
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        from fastapi.responses import HTMLResponse
        return HTMLResponse(_placeholder_html())
    return FileResponse(str(index_path))


def _placeholder_html() -> str:
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>Demo</title></head>
<body style="font-family:sans-serif;max-width:600px;margin:80px auto;">
<h1>UniteLabs Plate QC v0 — Trajectory Demo</h1>
<p>Backend is running. The frontend (<code>static/index.html</code>) is not built yet.</p>
<p>Endpoints available at <code>/api/demo/*</code></p>
</body></html>"""


# ── API endpoints ──────────────────────────────────────────────────────────


@app.post("/api/demo/start")
async def demo_start(payload: dict[str, Any]) -> dict[str, Any]:
    """Create a fresh sampled episode.

    Accepts {seed: int, api_key: str, scenario?: str}.
    The api_key can also be read from the DEEPSEEK_API_KEY env var.
    """
    global _session

    seed = int(payload.get("seed", 42))
    scenario = str(payload.get("scenario", "plate_transfer_qc"))
    api_key = os.environ.get("DEEPSEEK_API_KEY", "") or "sk-353c00831093487ca08314983ec3317f"
    if not api_key:
        raise HTTPException(400, "DEEPSEEK_API_KEY environment variable is not set.")

    # Create a fresh run directory
    base_dir = PROJECT_ROOT / "runs" / "demo_web"
    base_dir.mkdir(parents=True, exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix=f"seed{seed}_", dir=base_dir))

    # Sample the episode
    episode = sample_episode(scenario=scenario, seed=seed, out_dir=run_dir)

    # Build session manifest
    manifest = build_session_manifest(run_dir)

    # Initialise demo session
    _session = DemoSession(run_dir, api_key)
    _session.manifest = manifest
    _session.init_messages()

    # Take initial state snapshot
    initial_state = snapshot_state(_session.db_path)
    _session.state_snapshots.append(
        {"label": "initial", "step": 0, "state": initial_state}
    )

    return {
        "ok": True,
        "run_dir": str(run_dir),
        "db_path": str(_session.db_path),
        "task": _session.task,
        "manifest_summary": {
            "world": manifest.get("world"),
            "scenario": manifest.get("scenario"),
            "seed": manifest.get("seed"),
            "expected_tools": manifest.get("expected_tools"),
        },
        "initial_state_tables": list(initial_state.keys()),
        "initial_state_row_counts": {
            table: len(rows) for table, rows in initial_state.items()
        },
        "model": MODEL,
        "max_turns": MAX_TURNS,
    }


@app.post("/api/demo/check-tools")
async def demo_check_tools() -> dict[str, Any]:
    """Verify the MCP server lists all 7 expected tools."""
    global _session
    if _session is None:
        raise HTTPException(400, "No active session. Call /api/demo/start first.")

    result = check_session_tools(_session.run_dir)
    _session.check_tools_result = result

    # Enrich with full tool definitions (name, description, inputSchema)
    tool_defs_by_name = {
        td["function"]["name"]: {
            "name": td["function"]["name"],
            "description": td["function"].get("description", ""),
            "inputSchema": td["function"].get("parameters", {}),
        }
        for td in TOOL_DEFINITIONS
    }
    result["tool_definitions"] = [
        tool_defs_by_name.get(name, {"name": name, "description": "", "inputSchema": {}})
        for name in result["listed_tools"]
    ]
    return result


@app.post("/api/demo/run-step")
async def demo_run_step() -> dict[str, Any]:
    """Execute one LLM turn: call the model, dispatch any tool calls, return results.

    One step = one LLM API call. The model may request multiple tool calls
    in one response; all are dispatched and recorded as part of this turn.
    If the model returns no tool calls, it has produced a final answer.
    """
    global _session
    if _session is None:
        raise HTTPException(400, "No active session. Call /api/demo/start first.")
    if _session.stop_reason != "pending":
        return {
            "ok": True,
            "done": True,
            "turn": _session.turn_index,
            "tool_names": [],
            "tool_results": [],
            "stop_reason": _session.stop_reason,
            "final_answer": _session.final_answer,
        }

    _session.init_client()

    turn_num = _session.turn_index + 1
    if turn_num > MAX_TURNS:
        _session.stop_reason = "max_turns"
        _session.final_answer = {
            "content": None, "stop_reason": "max_turns", "turns": _session.turn_index,
        }
        return {
            "ok": True, "done": True,
            "turn": _session.turn_index,
            "tool_names": [],
            "tool_results": [],
            "stop_reason": "max_turns",
            "final_answer": _session.final_answer,
        }

    # ── Call the LLM ──────────────────────────────────────────────────
    try:
        response = _session.client.chat.completions.create(
            model=MODEL,
            messages=_session.messages,
            tools=TOOL_DEFINITIONS,
            tool_choice="auto",
            stream=False,
            temperature=TEMPERATURE,
            extra_body={"thinking": {"type": "enabled"}},
        )
    except Exception as exc:
        raise HTTPException(500, f"LLM API call failed: {exc}")

    choice = response.choices[0]
    message = choice.message

    # Extract DeepSeek reasoning
    reasoning_content = getattr(message, "reasoning_content", None) or ""

    # Extract tool calls
    tool_calls = getattr(message, "tool_calls", None) or []

    # ── Build assistant message for history ────────────────────────────
    assistant_msg: dict[str, Any] = {
        "role": "assistant",
        "content": message.content or "",
    }
    if reasoning_content:
        assistant_msg["reasoning_content"] = reasoning_content

    turn_records: list[dict[str, Any]] = []
    all_tool_names: list[str] = []

    if tool_calls:
        # Serialise tool_calls into the message
        tc_list = []
        for tc in tool_calls:
            tc_list.append({
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            })
        assistant_msg["tool_calls"] = tc_list
        _session.messages.append(assistant_msg)

        # Dispatch each tool call
        for tc in tool_calls:
            tool_name = tc.function.name
            all_tool_names.append(tool_name)
            try:
                arguments = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                arguments = {}

            # Snapshot BEFORE
            before_state = snapshot_state(_session.db_path)

            # Dispatch
            result = dispatch_tool(_session.db_path, name=tool_name, arguments=arguments)

            # Snapshot AFTER
            after_state = snapshot_state(_session.db_path)
            diff = _compute_diff(before_state, after_state)

            # Append tool result to messages
            _session.messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "name": tool_name,
                "content": json.dumps(result, sort_keys=True, ensure_ascii=False),
            })

            turn_records.append({
                "turn": turn_num,
                "thought": reasoning_content if reasoning_content else f"Calling {tool_name}",
                "tool_call": {"id": tc.id, "name": tool_name, "arguments": arguments},
                "tool_result": result,
                "state_diff": diff,
            })
            _session.tool_history.append(turn_records[-1])

            # Save state snapshot
            _session.state_snapshots.append({
                "label": f"after_turn{turn_num}_{tool_name}",
                "step": _session.turn_index + 1,
                "state": after_state,
            })

            # Reset reasoning for subsequent tool calls in same turn
            reasoning_content = ""

    else:
        # No tool calls — agent produced a final answer
        _session.messages.append({
            "role": "assistant",
            "content": message.content or "",
        })
        _session.final_answer = {
            "content": message.content or "",
            "stop_reason": "assistant_final",
            "turns": turn_num,
        }
        _session.stop_reason = "assistant_final"

    _session.turn_index = turn_num

    result: dict[str, Any] = {
        "ok": True,
        "turn": turn_num,
        "tool_names": all_tool_names,
        "tool_results": turn_records,
        "done": _session.stop_reason != "pending",
        "stop_reason": _session.stop_reason,
    }
    if _session.final_answer is not None:
        result["final_answer"] = _session.final_answer
    return result


@app.post("/api/demo/run-all")
async def demo_run_all() -> dict[str, Any]:
    """Execute LLM turns until the agent finishes or max_turns is reached.

    After the agent stops, automatically runs the verifier.
    """
    global _session
    if _session is None:
        raise HTTPException(400, "No active session. Call /api/demo/start first.")

    all_turns = []
    while _session.stop_reason == "pending" and _session.turn_index < MAX_TURNS:
        turn_result = await demo_run_step()
        all_turns.append(turn_result)
        if turn_result.get("done"):
            break

    # Auto-finalise
    finalize_result = await _run_finalize()

    return {
        "ok": True,
        "total_turns": len(all_turns),
        "turns": all_turns,
        "stop_reason": _session.stop_reason,
        "final_answer": _session.final_answer,
        "verifier_result": _session.verifier_result,
        "finalize_result": finalize_result,
    }


@app.post("/api/demo/finalize")
async def demo_finalize() -> dict[str, Any]:
    """Verify the episode and export evidence."""
    global _session
    if _session is None:
        raise HTTPException(400, "No active session. Call /api/demo/start first.")

    return await _run_finalize()


async def _run_finalize() -> dict[str, Any]:
    """Internal: run verifier + export, store on session."""
    global _session
    assert _session is not None

    verifier_result = verify_run(_session.run_dir).to_dict()
    _session.verifier_result = verifier_result

    export_path = _session.run_dir / "run_export.json"
    export_payload = write_run_export(_session.run_dir, export_path)
    _session.export_payload = export_payload

    result = {
        "ok": bool(verifier_result["ok"]),
        "scenario": verifier_result.get("scenario"),
        "checks": verifier_result.get("checks", []),
        "export_path": str(export_path),
        "export_summary": {
            "world": export_payload.get("world"),
            "scenario": export_payload.get("scenario"),
            "tool_trace_count": len(export_payload.get("tool_trace", [])),
        },
    }
    _session.finalize_result = result
    return result


@app.get("/api/demo/state")
async def demo_state() -> dict[str, Any]:
    """Return the current full SQLite state."""
    global _session
    if _session is None:
        raise HTTPException(400, "No active session. Call /api/demo/start first.")

    state = snapshot_state(_session.db_path)
    return {
        "ok": True,
        "run_dir": str(_session.run_dir),
        "turn_index": _session.turn_index,
        "stop_reason": _session.stop_reason,
        "tables": list(state.keys()),
        "state": state,
    }


@app.get("/api/demo/trajectory")
async def demo_trajectory() -> dict[str, Any]:
    """Return the accumulated trajectory data."""
    global _session
    if _session is None:
        raise HTTPException(400, "No active session. Call /api/demo/start first.")

    return {
        "ok": True,
        "world_meta": _session.world_meta,
        "task": _session.task,
        "messages": [
            {k: v for k, v in m.items() if k != "reasoning_content"}
            for m in _session.messages
        ],
        "tool_history": _session.tool_history,
        "turn_index": _session.turn_index,
        "max_turns": MAX_TURNS,
        "stop_reason": _session.stop_reason,
        "final_answer": _session.final_answer,
        "verifier_result": _session.verifier_result,
        "finalize_result": _session.finalize_result,
    }


@app.get("/api/demo/messages")
async def demo_messages() -> dict[str, Any]:
    """Debug: return the current LLM conversation messages."""
    global _session
    if _session is None:
        raise HTTPException(400, "No active session. Call /api/demo/start first.")
    return {
        "ok": True,
        "message_count": len(_session.messages),
        "turn_index": _session.turn_index,
        "stop_reason": _session.stop_reason,
        "messages": [
            {k: v for k, v in m.items() if k not in ("reasoning_content",)}
            for m in _session.messages
        ],
        "tool_definitions_count": len(TOOL_DEFINITIONS),
        "tool_names": [td["function"]["name"] for td in TOOL_DEFINITIONS],
    }


@app.get("/api/demo/health")
async def demo_health() -> dict[str, Any]:
    """Health check."""
    return {
        "ok": True,
        "session_active": _session is not None,
        "turn_index": _session.turn_index if _session else 0,
        "max_turns": MAX_TURNS,
        "model": MODEL,
        "stop_reason": _session.stop_reason if _session else "no_session",
    }


# ── State snapshot helpers ──────────────────────────────────────────────────


def snapshot_state(db_path: Path) -> dict[str, list[dict[str, Any]]]:
    """Read every row from every table and return structured JSON."""
    if not db_path.exists():
        return {}
    snapshot: dict[str, list[dict[str, Any]]] = {}
    with connect(db_path) as conn:
        for table in TABLES_FOR_SNAPSHOT:
            try:
                rows = conn.execute(f"SELECT * FROM {table}").fetchall()
                snapshot[table] = [row_to_dict(row) for row in rows]
            except Exception:
                snapshot[table] = []
    return snapshot


def _compute_diff(
    before: dict[str, list[dict[str, Any]]],
    after: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Return a compact diff showing which tables changed and how."""
    diff: dict[str, Any] = {}
    for table in TABLES_FOR_SNAPSHOT:
        before_rows = before.get(table, [])
        after_rows = after.get(table, [])
        before_count = len(before_rows)
        after_count = len(after_rows)

        if before_count != after_count:
            diff[table] = {
                "changed": True,
                "before_count": before_count,
                "after_count": after_count,
                "new_rows": after_rows[before_count:],
            }
        elif before_rows != after_rows:
            changed_indices = []
            for i, (br, ar) in enumerate(zip(before_rows, after_rows)):
                if br != ar:
                    changed_indices.append(i)
            if changed_indices:
                diff[table] = {
                    "changed": True,
                    "before_count": before_count,
                    "after_count": after_count,
                    "changed_row_indices": changed_indices,
                    "before_rows": [before_rows[i] for i in changed_indices],
                    "after_rows": [after_rows[i] for i in changed_indices],
                }
    return diff


# ── Entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    print("UniteLabs Plate QC v0 — Trajectory Demo (LLM Agent)")
    print(f"   Model: {MODEL}")
    print("   Open http://127.0.0.1:8080 in your browser")
    print("   Press Ctrl+C to stop")
    print()
    uvicorn.run(app, host="127.0.0.1", port=8080, log_level="info")
