"""
Demo server: multi-world trajectory visualisation.

Supports:
  - unitelabs_plate_qc_v0  (custom SQLite backend)
  - pylabrobot_lab_v0      (PyLabRobot + ChatterBox backend)

Start with:   python gen_trajectory/demo/server.py
Then open:   http://127.0.0.1:8080
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

# ── World imports ──────────────────────────────────────────────────────────

from api_gym.worlds.unitelabs_plate_qc_v0.sampler import sample_episode as unitelabs_sample
from api_gym.worlds.unitelabs_plate_qc_v0.tools import TOOL_DEFINITIONS as UNITELABS_TOOLS
from api_gym.worlds.unitelabs_plate_qc_v0.tools import dispatch_tool as unitelabs_dispatch
from api_gym.worlds.unitelabs_plate_qc_v0.verifier import verify_run as unitelabs_verify
from api_gym.worlds.unitelabs_plate_qc_v0.state import connect, row_to_dict

from api_gym.worlds.pylabrobot_lab_v0.sampler import sample_episode as plr_sample
from api_gym.worlds.pylabrobot_lab_v0.tools import TOOL_DEFINITIONS as PLR_TOOLS
from api_gym.worlds.pylabrobot_lab_v0.tools import dispatch_tool as plr_dispatch
from api_gym.worlds.pylabrobot_lab_v0.verifier import verify_run as plr_verify

# OT-2 Visualizer backend
from api_gym.worlds.pylabrobot_lab_v0.sampler import (
    _build_plate_transfer_qc_ot2,
    _build_serial_dilution_qc_ot2,
)
from api_gym.worlds.pylabrobot_lab_v0.services_ot2 import (
    aspirate as ot2_aspirate,
    dispense as ot2_dispense,
    discard_tips as ot2_discard_tips,
    get_deck_state as ot2_get_deck_state,
    get_labware_state as ot2_get_labware_state,
    read_absorbance as ot2_read_absorbance,
    add_workflow_note as ot2_add_workflow_note,
    submit_protocol as ot2_submit_protocol,
)

from api_gym.session import build_session_manifest, check_session_tools
from api_gym.exports.run_export import write_run_export

# ── LLM configuration ──────────────────────────────────────────────────────

MODEL = "deepseek-v4-pro"
BASE_URL = "https://api.deepseek.com"
MAX_TURNS = 20
TEMPERATURE = 0.0

SYSTEM_PROMPT_UNITELABS = """\
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

SYSTEM_PROMPT_PLR = """\
You are a lab automation agent solving a Datalox API Gym pylabrobot_lab_v0 task.

The environment is a DRY-RUN lab deck backed by PyLabRobot — no real hardware
is connected. The deck has standard SBS-format plates with VolumeTracker for
liquid tracking, and chatterbox simulation backends.

STANDARD LAB PROCEDURE for plate QC:
1. Always inspect the deck state first to see what labware is loaded.
2. Inspect each labware object (source plate, target/assay plate, tip rack)
   to understand well contents, volumes, and available tips.
3. Use standard transfer volumes — typically 50 uL for QC assays.
4. OD600 (600 nm) is the standard wavelength for absorbance measurements.
5. Match your aspirate/dispense volume exactly.
6. Reference format for wells: 'labware_name:well_id'
   (e.g. 'source_plate:A1', 'tip_rack_01:A1').
7. After obtaining a valid readout, submit the protocol decision.

Rules:
- Use the provided tools for every state inspection and mutation.
- Do not answer from task text alone — you MUST call tools to inspect state.
- Do not attempt to read lab_state.json or any hidden verifier state.
- When you have enough evidence, submit a final protocol decision using
  submit_protocol with the supporting readout evidence.
- Think step by step before each tool call.
"""

# ── OT-2 helper functions ─────────────────────────────────────────────────


_OT2_SCENARIOS = {
    "plate_transfer_qc": None,
    "serial_dilution_qc": None,
    "multi_sample_qc": None,
    "concentration_gradient_qc": None,
    "limited_tips_qc": None,
    "low_reagent_qc": None,
    "instrument_busy_qc": None,
    "stale_deck_qc": None,
    "borderline_qc": None,
    "cross_contamination_qc": None,
}
_OT2_SCENARIOS["plate_transfer_qc"] = _build_plate_transfer_qc_ot2
_OT2_SCENARIOS["serial_dilution_qc"] = _build_serial_dilution_qc_ot2
# New scenarios
from api_gym.worlds.pylabrobot_lab_v0.sampler import (
    _build_multi_sample_qc_ot2,
    _build_concentration_gradient_qc_ot2,
    _build_limited_tips_qc_ot2,
    _build_low_reagent_qc_ot2,
    _build_instrument_busy_qc_ot2,
    _build_stale_deck_qc_ot2,
    _build_borderline_qc_ot2,
    _build_cross_contamination_qc_ot2,
)
_OT2_SCENARIOS["multi_sample_qc"] = _build_multi_sample_qc_ot2
_OT2_SCENARIOS["concentration_gradient_qc"] = _build_concentration_gradient_qc_ot2
_OT2_SCENARIOS["limited_tips_qc"] = _build_limited_tips_qc_ot2
_OT2_SCENARIOS["low_reagent_qc"] = _build_low_reagent_qc_ot2
_OT2_SCENARIOS["instrument_busy_qc"] = _build_instrument_busy_qc_ot2
_OT2_SCENARIOS["stale_deck_qc"] = _build_stale_deck_qc_ot2
_OT2_SCENARIOS["borderline_qc"] = _build_borderline_qc_ot2
_OT2_SCENARIOS["cross_contamination_qc"] = _build_cross_contamination_qc_ot2


def _ot2_sample(*, scenario: str, seed: int, out_dir: Path) -> Any:
    """Sample an OT-2 visual episode."""
    from api_gym.worlds.pylabrobot_lab_v0.state import register_state
    builder = _OT2_SCENARIOS.get(scenario)
    if builder is None:
        raise ValueError(f"Unknown OT-2 scenario: {scenario}")
    task, lab_state = builder(out_dir, seed)
    out_dir.mkdir(parents=True, exist_ok=True)
    import json
    (out_dir / "task.json").write_text(json.dumps(task, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    run_meta = {"world": "pylabrobot_lab_v0_ot2", "world_id": "pylabrobot-lab-v0-ot2",
                "scenario": scenario, "seed": seed, "mode": "dry_run"}
    (out_dir / "run.json").write_text(json.dumps(run_meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lab_state.save(out_dir / "lab_state.json")
    register_state(out_dir, lab_state)
    return type("Episode", (), {"run_dir": out_dir, "task": task, "lab_state": lab_state})()


def _ot2_dispatch(run_dir: Path, *, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Dispatch tool call to OT-2 service functions."""
    from api_gym.worlds.pylabrobot_lab_v0.state import get_state
    lab_state = get_state(run_dir)

    # Map arguments to correct parameter names for OT-2 service functions
    if name == "aspirate":
        return ot2_aspirate(lab_state,
                            source=arguments["source"],
                            volume_ul=float(arguments["volume_ul"]),
                            tip_ref=arguments["tip"])
    elif name == "dispense":
        return ot2_dispense(lab_state,
                            target=arguments["target"],
                            volume_ul=float(arguments["volume_ul"]),
                            mix_after=bool(arguments.get("mix_after", False)))
    elif name == "get_deck_state":
        return ot2_get_deck_state(lab_state)
    elif name == "get_labware_state":
        return ot2_get_labware_state(lab_state, labware_id=arguments["labware_id"])
    elif name == "read_absorbance":
        return ot2_read_absorbance(lab_state,
                                   plate_id=arguments["plate_id"],
                                   wavelength_nm=int(arguments["wavelength_nm"]),
                                   wells=[str(w) for w in arguments["wells"]])
    elif name == "discard_tips":
        return ot2_discard_tips(lab_state)
    elif name == "add_workflow_note":
        return ot2_add_workflow_note(lab_state, note=arguments["note"])
    elif name == "submit_protocol":
        return ot2_submit_protocol(lab_state,
                                   decision=arguments["decision"],
                                   evidence_readout_id=arguments["evidence_readout_id"],
                                   target_well=arguments["target_well"],
                                   rationale=arguments["rationale"])
    else:
        return {"ok": False, "error": {"code": "unknown_tool", "message": f"Unknown tool: {name}"}}


def _ot2_start_visualizer(lh: Any) -> Any:
    """Start the OT-2 visualizer for a LiquidHandler instance."""
    from api_gym.worlds.pylabrobot_lab_v0.state_ot2 import OT2VisualizerSession
    vis = OT2VisualizerSession(lh)
    vis.start()
    return vis


def _ot2_stop_visualizer(vis: Any) -> None:
    """Stop the OT-2 visualizer."""
    if vis is not None:
        vis.stop()


# ── STAR dispatch helpers ──────────────────────────────────────────────────

from api_gym.worlds.pylabrobot_star_v0.tools import dispatch_tool as star_dispatch
from api_gym.worlds.pylabrobot_star_v0.tools import TOOL_DEFINITIONS as STAR_TOOLS
from api_gym.worlds.pylabrobot_star_v0.sampler import sample_episode as star_sample
from api_gym.worlds.pylabrobot_star_v0.verifier import verify_run as star_verify

SYSTEM_PROMPT_STAR = """\
You are a lab automation agent operating a Hamilton STAR liquid handler.

The environment is a DRY-RUN STAR deck with STARChatterboxBackend — no real
hardware is connected. The deck uses a carrier-based layout:
- Plate carriers hold plates and troughs at numbered sites.
- Tip carriers hold tip racks at numbered sites.
- Optionally, a 96-channel head and an iSWAP robotic arm may be installed.

Available tools include single-channel pipetting, 96-head parallel operations,
and plate movement via the iSWAP arm.

STANDARD PROCEDURE:
1. Inspect the deck state first to see what carriers and labware are loaded.
2. Inspect individual labware (plates, tip racks, troughs) for well volumes.
3. Use reference format: 'labware_name:well_id' (e.g. 'source_plate:A1').
4. OD600 (600 nm) is the standard absorbance wavelength.
5. Match aspirate/dispense volumes exactly.
6. Discard tips when they are potentially contaminated.
7. After obtaining valid readouts, submit the protocol decision.

Rules:
- Use the provided tools for every state inspection and mutation.
- Do not answer from task text alone — you MUST call tools.
- When you have enough evidence, submit via submit_protocol.
- Think step by step before each tool call.
"""


# ── World registry ────────────────────────────────────────────────────────

WORLDS = {
    "unitelabs_plate_qc_v0": {
        "label": "UniteLabs Plate QC v0 (SQLite)",
        "sample_episode": unitelabs_sample,
        "tool_definitions": UNITELABS_TOOLS,
        "dispatch_tool": unitelabs_dispatch,
        "verify_run": unitelabs_verify,
        "system_prompt": SYSTEM_PROMPT_UNITELABS,
        "state_backend": "sqlite",
    },
    "pylabrobot_lab_v0": {
        "label": "PyLabRobot Lab v0 (ChatterBox)",
        "sample_episode": plr_sample,
        "tool_definitions": PLR_TOOLS,
        "dispatch_tool": plr_dispatch,
        "verify_run": plr_verify,
        "system_prompt": SYSTEM_PROMPT_PLR,
        "state_backend": "pylabrobot",
    },
    "pylabrobot_lab_v0_ot2": {
        "label": "PyLabRobot OT-2 Visualizer",
        "sample_episode": _ot2_sample,
        "tool_definitions": PLR_TOOLS,
        "dispatch_tool": _ot2_dispatch,
        "verify_run": plr_verify,
        "system_prompt": SYSTEM_PROMPT_PLR,
        "state_backend": "ot2_visualizer",
        "has_visualizer": True,
    },
    "pylabrobot_star_v0": {
        "label": "PyLabRobot STAR (ChatterBox)",
        "sample_episode": star_sample,
        "tool_definitions": STAR_TOOLS,
        "dispatch_tool": star_dispatch,
        "verify_run": star_verify,
        "system_prompt": SYSTEM_PROMPT_STAR,
        "state_backend": "pylabrobot",
    },
}

SUPPORTED_WORLDS = list(WORLDS.keys())

UNITELABS_TABLES_SNAPSHOT = [
    "deck", "labware", "wells", "tips", "pipette_state",
    "control_bands", "transfers", "readouts", "workflow_notes",
    "submissions", "events", "audit_log",
]

# ── In-memory session store ────────────────────────────────────────────────


class DemoSession:
    """Holds the live state for one demo run."""

    def __init__(self, run_dir: Path, api_key: str, world: str) -> None:
        self.run_dir = run_dir
        self.world = world
        self.world_cfg = WORLDS[world]

        # Dispatch path: SQLite world uses db_path, PLR uses run_dir
        self.db_path = run_dir / "state.sqlite"
        self.task_path = run_dir / "task.json"

        # LLM client
        self.api_key = api_key
        self.client: Any = None

        # LLM conversation state
        self.messages: list[dict[str, Any]] = []

        # Progress tracking
        self.turn_index: int = 0
        self.tool_history: list[dict[str, Any]] = []
        self.state_snapshots: list[dict[str, Any]] = []
        self.final_answer: dict[str, Any] | None = None
        self.stop_reason: str = "pending"

        # Visualizer (OT-2 mode only)
        self.visualizer: Any = None

        # Trajectory metadata
        self.world_meta: dict[str, Any] = {}
        self.task: dict[str, Any] = {}
        self.manifest: dict[str, Any] = {}
        self.check_tools_result: dict[str, Any] | None = None
        self.finalize_result: dict[str, Any] | None = None
        self.verifier_result: dict[str, Any] | None = None
        self.export_payload: dict[str, Any] | None = None

        run_meta_path = run_dir / "run.json"
        if run_meta_path.exists():
            self.world_meta = json.loads(run_meta_path.read_text(encoding="utf-8"))
        if self.task_path.exists():
            self.task = json.loads(self.task_path.read_text(encoding="utf-8"))

    def init_client(self) -> None:
        if self.client is not None:
            return
        try:
            from openai import OpenAI
        except ImportError:
            raise HTTPException(500, "pip install openai")
        self.client = OpenAI(api_key=self.api_key, base_url=BASE_URL)

    def init_messages(self) -> None:
        if self.messages:
            return
        task_prompt = self.task.get("prompt", "")
        self.messages = [
            {"role": "system", "content": self.world_cfg["system_prompt"]},
            {"role": "user", "content": task_prompt},
        ]


_session: DemoSession | None = None

# ── FastAPI app ────────────────────────────────────────────────────────────

app = FastAPI(title="Datalox API Gym — Trajectory Demo")

STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/")
async def root():
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
<h1>Datalox API Gym — Trajectory Demo</h1><p>Backend running. Frontend missing.</p>
</body></html>"""


@app.get("/api/demo/worlds")
async def demo_worlds() -> dict[str, Any]:
    """List available worlds."""
    return {
        "ok": True,
        "worlds": [
            {"id": w, "label": c["label"], "state_backend": c["state_backend"]}
            for w, c in WORLDS.items()
        ],
    }


@app.get("/api/demo/scenarios")
async def demo_scenarios(world: str = "pylabrobot_lab_v0") -> dict[str, Any]:
    """List available scenarios for a given world."""
    if world not in WORLDS:
        raise HTTPException(400, f"Unknown world '{world}'.")
    try:
        cfg = WORLDS[world]
        # Try to get scenarios from the sample_episode function's module
        import inspect
        mod = inspect.getmodule(cfg["sample_episode"])
        if mod and hasattr(mod, "SCENARIOS"):
            scenarios = sorted(mod.SCENARIOS.keys())
        else:
            scenarios = []
    except Exception:
        scenarios = []
    return {"ok": True, "world": world, "scenarios": scenarios}


# ── API endpoints ──────────────────────────────────────────────────────────


@app.post("/api/demo/start")
async def demo_start(payload: dict[str, Any]) -> dict[str, Any]:
    global _session

    seed = int(payload.get("seed", 42))
    scenario = str(payload.get("scenario", "plate_transfer_qc"))
    world = str(payload.get("world", "unitelabs_plate_qc_v0"))

    if world not in WORLDS:
        raise HTTPException(400, f"Unknown world '{world}'. Supported: {SUPPORTED_WORLDS}")

    api_key = os.environ.get("DEEPSEEK_API_KEY", "") or "sk-353c00831093487ca08314983ec3317f"
    if not api_key:
        raise HTTPException(400, "DEEPSEEK_API_KEY environment variable is not set.")

    cfg = WORLDS[world]

    base_dir = PROJECT_ROOT / "runs" / "demo_web"
    base_dir.mkdir(parents=True, exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix=f"{world}_seed{seed}_", dir=base_dir))

    episode = cfg["sample_episode"](scenario=scenario, seed=seed, out_dir=run_dir)

    _session = DemoSession(run_dir, api_key, world)
    _session.init_messages()

    # Snapshot initial state for replay
    _snapshot_initial_state(_session)

    # Start OT-2 visualizer if applicable
    visualizer_url = None
    if cfg.get("has_visualizer"):
        try:
            from api_gym.worlds.pylabrobot_lab_v0.state import get_state
            lab_state = get_state(run_dir)
            if lab_state.liquid_handler is not None:
                _session.visualizer = _ot2_start_visualizer(lab_state.liquid_handler)
                visualizer_url = "http://127.0.0.1:1337"
        except Exception as e:
            print(f"[OT-2 Visualizer] Failed to start: {e}")

    # Initial state snapshot
    initial_state = _snapshot_state(_session)
    _session.state_snapshots.append({"label": "initial", "step": 0, "state": initial_state})

    return {
        "ok": True,
        "world": world,
        "world_label": cfg["label"],
        "run_dir": str(run_dir),
        "task": _session.task,
        "scenario": scenario,
        "seed": seed,
        "state_backend": cfg["state_backend"],
        "initial_state": initial_state,
        "model": MODEL,
        "max_turns": MAX_TURNS,
        "visualizer_url": visualizer_url,
    }


@app.post("/api/demo/check-tools")
async def demo_check_tools() -> dict[str, Any]:
    global _session
    if _session is None:
        raise HTTPException(400, "No active session.")
    td = _session.world_cfg["tool_definitions"]
    tool_defs_by_name = {
        t["function"]["name"]: {
            "name": t["function"]["name"],
            "description": t["function"].get("description", ""),
            "inputSchema": t["function"].get("parameters", {}),
        }
        for t in td
    }
    names = sorted(tool_defs_by_name.keys())
    return {
        "ok": True,
        "world": _session.world,
        "expected_tools": names,
        "listed_tools": names,
        "missing_tools": [],
        "unexpected_tools": [],
        "tool_definitions": [tool_defs_by_name[n] for n in names],
    }


@app.post("/api/demo/run-step")
async def demo_run_step() -> dict[str, Any]:
    global _session
    if _session is None:
        raise HTTPException(400, "No active session.")
    if _session.stop_reason != "pending":
        return {
            "ok": True, "done": True,
            "turn": _session.turn_index,
            "tool_names": [], "tool_results": [],
            "stop_reason": _session.stop_reason,
            "final_answer": _session.final_answer,
        }

    _session.init_client()

    turn_num = _session.turn_index + 1
    if turn_num > MAX_TURNS:
        _session.stop_reason = "max_turns"
        _session.final_answer = {"content": None, "stop_reason": "max_turns", "turns": _session.turn_index}
        return {
            "ok": True, "done": True,
            "turn": _session.turn_index,
            "tool_names": [], "tool_results": [],
            "stop_reason": "max_turns",
            "final_answer": _session.final_answer,
        }

    tools = _session.world_cfg["tool_definitions"]
    dispatch_fn = _session.world_cfg["dispatch_tool"]
    dispatch_path = _session.run_dir  # Both worlds accept a Path

    try:
        response = _session.client.chat.completions.create(
            model=MODEL, messages=_session.messages, tools=tools,
            tool_choice="auto", stream=False, temperature=TEMPERATURE,
            extra_body={"thinking": {"type": "enabled"}},
        )
    except Exception as exc:
        raise HTTPException(500, f"LLM API call failed: {exc}")

    choice = response.choices[0]
    message = choice.message
    reasoning_content = getattr(message, "reasoning_content", None) or ""
    tool_calls = getattr(message, "tool_calls", None) or []

    assistant_msg: dict[str, Any] = {"role": "assistant", "content": message.content or ""}
    if reasoning_content:
        assistant_msg["reasoning_content"] = reasoning_content

    turn_records: list[dict[str, Any]] = []
    all_tool_names: list[str] = []

    if tool_calls:
        tc_list = []
        for tc in tool_calls:
            tc_list.append({
                "id": tc.id, "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            })
        assistant_msg["tool_calls"] = tc_list
        _session.messages.append(assistant_msg)

        for tc in tool_calls:
            tool_name = tc.function.name
            all_tool_names.append(tool_name)
            try:
                arguments = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                arguments = {}

            before_state = _snapshot_state(_session)
            result = dispatch_fn(dispatch_path, name=tool_name, arguments=arguments)
            after_state = _snapshot_state(_session)
            diff = _compute_diff(_session.world, before_state, after_state)

            _session.messages.append({
                "role": "tool", "tool_call_id": tc.id, "name": tool_name,
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
            _session.state_snapshots.append({
                "label": f"after_turn{turn_num}_{tool_name}",
                "step": _session.turn_index + 1,
                "state": after_state,
            })
            reasoning_content = ""
    else:
        _session.messages.append({"role": "assistant", "content": message.content or ""})
        _session.final_answer = {
            "content": message.content or "", "stop_reason": "assistant_final", "turns": turn_num,
        }
        _session.stop_reason = "assistant_final"

    _session.turn_index = turn_num

    result: dict[str, Any] = {
        "ok": True, "turn": turn_num,
        "tool_names": all_tool_names, "tool_results": turn_records,
        "done": _session.stop_reason != "pending",
        "stop_reason": _session.stop_reason,
    }
    if _session.final_answer is not None:
        result["final_answer"] = _session.final_answer
    return result


@app.post("/api/demo/run-all")
async def demo_run_all() -> dict[str, Any]:
    global _session
    if _session is None:
        raise HTTPException(400, "No active session.")

    all_turns = []
    while _session.stop_reason == "pending" and _session.turn_index < MAX_TURNS:
        turn_result = await demo_run_step()
        all_turns.append(turn_result)
        if turn_result.get("done"):
            break

    finalize_result = await _run_finalize()

    return {
        "ok": True, "total_turns": len(all_turns), "turns": all_turns,
        "stop_reason": _session.stop_reason,
        "final_answer": _session.final_answer,
        "verifier_result": _session.verifier_result,
        "finalize_result": finalize_result,
    }


@app.post("/api/demo/finalize")
async def demo_finalize() -> dict[str, Any]:
    global _session
    if _session is None:
        raise HTTPException(400, "No active session.")
    return await _run_finalize()


async def _run_finalize() -> dict[str, Any]:
    global _session
    assert _session is not None

    verifier_result = _session.world_cfg["verify_run"](_session.run_dir).to_dict()
    _session.verifier_result = verifier_result

    export_path = _session.run_dir / "run_export.json"
    try:
        export_payload = write_run_export(_session.run_dir, export_path)
    except Exception:
        export_payload = {}
    _session.export_payload = export_payload

    result = {
        "ok": bool(verifier_result["ok"]),
        "scenario": verifier_result.get("scenario"),
        "checks": verifier_result.get("checks", []),
        "export_path": str(export_path),
    }
    _session.finalize_result = result
    return result


@app.get("/api/demo/state")
async def demo_state() -> dict[str, Any]:
    global _session
    if _session is None:
        raise HTTPException(400, "No active session.")
    state = _snapshot_state(_session)
    return {
        "ok": True, "run_dir": str(_session.run_dir),
        "turn_index": _session.turn_index,
        "stop_reason": _session.stop_reason,
        "state": state,
    }


@app.get("/api/demo/trajectory")
async def demo_trajectory() -> dict[str, Any]:
    global _session
    if _session is None:
        raise HTTPException(400, "No active session.")
    return {
        "ok": True, "world_meta": _session.world_meta, "task": _session.task,
        "tool_history": _session.tool_history,
        "turn_index": _session.turn_index, "max_turns": MAX_TURNS,
        "stop_reason": _session.stop_reason,
        "final_answer": _session.final_answer,
        "verifier_result": _session.verifier_result,
        "finalize_result": _session.finalize_result,
    }


@app.get("/api/demo/messages")
async def demo_messages() -> dict[str, Any]:
    global _session
    if _session is None:
        raise HTTPException(400, "No active session.")
    tools = _session.world_cfg["tool_definitions"]
    return {
        "ok": True, "message_count": len(_session.messages),
        "turn_index": _session.turn_index,
        "stop_reason": _session.stop_reason,
        "tool_definitions_count": len(tools),
        "tool_names": [t["function"]["name"] for t in tools],
    }


_replay_port = 1337

@app.post("/api/demo/replay-init")
async def demo_replay_init() -> dict[str, Any]:
    """Reset state to initial snapshot, then replay will re-apply operations."""
    global _session
    if _session is None:
        raise HTTPException(400, "No active session.")
    history = list(_session.tool_history)
    if not history:
        raise HTTPException(400, "No tool history to replay.")

    # Restore initial state from snapshot
    _restore_initial_state(_session)

    _session._replay_history = history
    _session._replay_index = 0
    return {"ok": True, "total_steps": len(history),
            "steps": [{"tool": h.get("tool_call", {}).get("name", "?"),
                        "args": h.get("tool_call", {}).get("arguments", {})}
                       for h in history]}


def _snapshot_initial_state(sess: DemoSession) -> None:
    """Record initial state generically — walk all deck resources."""
    cfg = sess.world_cfg
    if cfg.get("state_backend") not in ("pylabrobot", "ot2_visualizer"):
        sess._initial_snapshot = {}
        return
    from api_gym.worlds.pylabrobot_lab_v0.state import get_state
    try:
        lab_state = get_state(sess.run_dir)
        wells: dict[str, float] = {}
        tips: dict[str, bool] = {}
        for resource in lab_state.deck.children if lab_state.deck else []:
            _walk_resource(resource, resource.name, wells, tips)
        sess._initial_snapshot = {"wells": wells, "tips": tips}
    except Exception:
        sess._initial_snapshot = {}


def _walk_resource(resource: Any, path: str, wells: dict, tips: dict) -> None:
    """Recursively walk a resource tree, recording well volumes and tip states."""
    # Check if this resource has children (plates, tip racks)
    if hasattr(resource, "children"):
        for child in resource.children:
            child_path = f"{path}/{child.name}"
            # Well with volume tracker
            if hasattr(child, "tracker") and hasattr(child.tracker, "get_used_volume"):
                wells[child_path] = child.tracker.get_used_volume()
            # Tip spot
            if hasattr(child, "has_tip"):
                tips[child_path] = True
            # Recurse deeper
            _walk_resource(child, child_path, wells, tips)


def _restore_initial_state(sess: DemoSession) -> None:
    """Restore state from generic snapshot."""
    snap = getattr(sess, "_initial_snapshot", None)
    if not snap:
        return
    cfg = sess.world_cfg
    if cfg.get("state_backend") not in ("pylabrobot", "ot2_visualizer"):
        return
    from api_gym.worlds.pylabrobot_lab_v0.state import get_state
    try:
        lab_state = get_state(sess.run_dir)
        wells = snap.get("wells", {})
        tips = snap.get("tips", {})
        for resource in lab_state.deck.children if lab_state.deck else []:
            _restore_resource(resource, resource.name, wells, tips)
        lab_state._pending_volume_ul = 0.0
    except Exception:
        pass


def _restore_resource(resource: Any, path: str, wells: dict, tips: dict) -> None:
    """Recursively restore a resource tree from snapshot."""
    if hasattr(resource, "children"):
        for child in resource.children:
            child_path = f"{path}/{child.name}"
            if child_path in wells and hasattr(child, "tracker") and child.tracker:
                child.tracker.set_volume(wells[child_path])
            if child_path in tips and hasattr(child, "_has_tip"):
                child._has_tip = True
            _restore_resource(child, child_path, wells, tips)


@app.post("/api/demo/replay-step")
async def demo_replay_step() -> dict[str, Any]:
    """Replay one recorded tool operation."""
    global _session
    if _session is None:
        raise HTTPException(400, "No active session.")
    history = getattr(_session, "_replay_history", [])
    idx = getattr(_session, "_replay_index", 0)
    if idx >= len(history):
        return {"ok": True, "done": True, "message": "Replay complete."}

    record = history[idx]
    tc = record.get("tool_call", {})
    name = tc.get("name", "?")
    args = tc.get("arguments", {})
    cfg = WORLDS[_session.world]
    result = cfg["dispatch_tool"](_session.run_dir, name=name, arguments=args)
    _session._replay_index = idx + 1

    return {"ok": True, "step": idx + 1, "total": len(history),
            "tool": name, "tool_ok": result.get("ok", False), "done": idx + 1 >= len(history)}


@app.get("/api/demo/health")
async def demo_health() -> dict[str, Any]:
    return {
        "ok": True, "session_active": _session is not None,
        "turn_index": _session.turn_index if _session else 0,
        "max_turns": MAX_TURNS, "model": MODEL,
        "supported_worlds": SUPPORTED_WORLDS,
        "stop_reason": _session.stop_reason if _session else "no_session",
    }


# ── State snapshot helpers ──────────────────────────────────────────────────


def _snapshot_state(sess: DemoSession) -> dict[str, Any]:
    """Take a state snapshot.  For SQLite worlds, read all tables.
    For PyLabRobot, return LabState metadata."""
    if sess.world_cfg["state_backend"] == "sqlite":
        if sess.db_path.exists():
            return _snapshot_sqlite(sess.db_path)
        return {}
    else:
        # PyLabRobot world: return transfers, readouts, submissions
        return {
            "transfers": sess.tool_history,
            "turn_index": sess.turn_index,
            "stop_reason": sess.stop_reason,
        }


def _snapshot_sqlite(db_path: Path) -> dict[str, list[dict[str, Any]]]:
    if not db_path.exists():
        return {}
    snapshot: dict[str, list[dict[str, Any]]] = {}
    with connect(db_path) as conn:
        for table in UNITELABS_TABLES_SNAPSHOT:
            try:
                rows = conn.execute(f"SELECT * FROM {table}").fetchall()
                snapshot[table] = [row_to_dict(row) for row in rows]
            except Exception:
                snapshot[table] = []
    return snapshot


def _compute_diff(world: str, before: dict[str, Any],
                  after: dict[str, Any]) -> dict[str, Any]:
    """Compute diff between two state snapshots."""
    if world == "pylabrobot_lab_v0":
        return {}

    diff: dict[str, Any] = {}
    for table in UNITELABS_TABLES_SNAPSHOT:
        before_rows = before.get(table, [])
        after_rows = after.get(table, [])
        if len(before_rows) != len(after_rows):
            diff[table] = {
                "changed": True,
                "before_count": len(before_rows),
                "after_count": len(after_rows),
                "new_rows": after_rows[len(before_rows):],
            }
        elif before_rows != after_rows:
            changed = []
            for i, (br, ar) in enumerate(zip(before_rows, after_rows)):
                if br != ar:
                    changed.append(i)
            if changed:
                diff[table] = {
                    "changed": True,
                    "before_count": len(before_rows),
                    "after_count": len(after_rows),
                    "changed_row_indices": changed,
                }
    return diff


# ── Entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    print("Datalox API Gym — Trajectory Demo (Multi-World)")
    print(f"   Worlds: {', '.join(SUPPORTED_WORLDS)}")
    print(f"   Model:  {MODEL}")
    print("   Open http://127.0.0.1:8080")
    print()
    uvicorn.run(app, host="127.0.0.1", port=8080, log_level="info")
