"""
Unified LLM-driven trajectory runner — supports all worlds.

Two-phase tool selection (for worlds with many tools):
  Phase 1: Agent receives a compact "quick reference" catalog and selects
            relevant tools via the `select_tools` meta-tool.
  Phase 2: Only the selected tools' full JSON schemas are sent each turn,
            dramatically reducing prompt tokens.

Usage:
  python gen_trajectory/run.py --world pylabrobot_star_v0 --scenario spin_down_qc --seed 42
  python gen_trajectory/run.py --world pylabrobot_star_v0 --scenario seal_plate_qc --seed 1
  python gen_trajectory/run.py --world pylabrobot_lab_v0 --scenario plate_transfer_qc

  # Disable tool filtering (send all tools every turn, for comparison):
  python gen_trajectory/run.py --world pylabrobot_star_v0 --scenario spin_down_qc --no-tool-filter

Output (written to gen_trajectory/output/):
  - trajectory_{world}_{scenario}_seed{seed}_{timestamp}.json
  - trajectory_{...}_messages.jsonl
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from openai import OpenAI

# ── LLM configuration ───────────────────────────────────────────────────────
MODEL = "deepseek-v4-pro"
BASE_URL = "https://api.deepseek.com"
TEMPERATURE = 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# Tool catalog builder — generates the "quick reference manual"
# ═══════════════════════════════════════════════════════════════════════════════

# Tools that are always included even if not explicitly selected
ALWAYS_INCLUDE = {
    "get_deck_state",
    "get_labware_state",
    "submit_protocol",
    "add_workflow_note",
    "select_tools",  # allow adding more tools later
}

# Minimum tool count to trigger two-phase mode
MIN_TOOLS_FOR_FILTER = 10


def _short_desc(tool: dict[str, Any]) -> str:
    """Extract a one-line summary from a tool's description."""
    desc = tool["function"].get("description", "")
    # Take first line (before \n\n or first period+newline)
    first = desc.split("\n\n")[0].split(".\n")[0].strip()
    if first.endswith("."):
        first = first[:-1]
    if len(first) > 120:
        first = first[:117] + "..."
    return first


def _classify_tool(name: str) -> str:
    """Classify a tool name into an instrument category."""
    if name in ("get_deck_state", "get_labware_state", "get_mounted_tips",
                 "list_workspace_files", "get_workspace_file"):
        return "Inspection & Workspace"
    if any(name.startswith(p) for p in ("aspirate", "dispense", "transfer",
            "pick_up_tips", "drop_tips", "return_tips", "discard_tips", "mix")):
        if "96" in name: return "96-Channel Head"
        return "Single-Channel Pipetting"
    if any(name.startswith(p) for p in ("aspirate96", "dispense96",
            "pick_up_tips96", "discard_tips96", "drop_tips96", "stamp")):
        return "96-Channel Head"
    if any(name.startswith(p) for p in ("move_plate", "move_lid", "move_resource",
            "arm_", "iswap_")):
        return "iSWAP Robotic Arm"
    if name.startswith("centrifuge_"):
        return "Centrifuge"
    if name.startswith("heater_shaker_") or name.startswith("hs_"):
        return "Heater-Shaker"
    if name.startswith("thermocycler_") or name.startswith("tc_") or name.startswith("pcr_"):
        return "Thermocycler"
    if name.startswith("sealer_") or name.startswith("seal_"):
        return "Sealer"
    if name.startswith("peeler_") or name.startswith("peel_"):
        return "Peeler"
    if name.startswith("shaker_"):
        return "Shaker"
    if name.startswith("temp_control_") or name.startswith("tempctrl_"):
        return "Temperature Controller"
    if name.startswith("tilter_"):
        return "Tilter"
    if name.startswith("storage_"):
        return "Storage"
    if name.startswith("powder_"):
        return "Powder Dispenser"
    if name.startswith("barcode_"):
        return "Barcode Scanner"
    if name.startswith("pump_"):
        return "Pump"
    if any(name.startswith(p) for p in ("scale_", "tare_", "weigh_",
            "zero_scale", "gravimetric_")):
        return "Scale"
    if any(name.startswith(p) for p in ("read_", "reader_", "fluorescence_",
            "luminescence_")):
        return "Plate Reader"
    if name in ("add_workflow_note", "submit_protocol"):
        return "Protocol & Submission"
    return "Other"


def build_compact_catalog(tool_definitions: list[dict[str, Any]]) -> str:
    """Build a compact quick-reference catalog grouped by instrument category.

    Each tool gets one line: name + short description.  No JSON schemas.
    """
    # Group by category
    groups: dict[str, list[tuple[str, str]]] = {}
    for t in tool_definitions:
        name = t["function"]["name"]
        cat = _classify_tool(name)
        groups.setdefault(cat, []).append((name, _short_desc(t)))

    # Build catalog text
    lines: list[str] = []
    lines.append("## TOOL QUICK-REFERENCE CATALOG")
    lines.append(f"## {len(tool_definitions)} tools available across {len(groups)} instrument categories")
    lines.append("")
    lines.append("Use select_tools to activate the tools you need for this task.")
    lines.append("You can call select_tools again later if you need more tools.")
    lines.append("")

    # Order: inspection first, protocol last, instruments in between
    cat_order = (
        ["Inspection & Workspace"] +
        sorted(g for g in groups if g not in ("Inspection & Workspace", "Protocol & Submission", "Other")) +
        ["Protocol & Submission"] +
        (["Other"] if "Other" in groups else [])
    )

    for cat in cat_order:
        items = groups.get(cat, [])
        if not items:
            continue
        lines.append(f"### {cat} ({len(items)} tools)")
        for name, desc in sorted(items):
            lines.append(f"- **{name}**: {desc}")
        lines.append("")

    return "\n".join(lines)


def _select_tools_schema() -> dict[str, Any]:
    """Build the select_tools meta-tool definition."""
    return {
        "type": "function",
        "function": {
            "name": "select_tools",
            "description": (
                "Select which tools you need for this task. You MUST call this "
                "first, before any other tool.  Review the task requirements, "
                "identify which instruments and operations are needed, and "
                "provide the complete list of tool names.  You can call this "
                "again later if you discover you need additional tools.\n\n"
                "Include: inspection tools (get_deck_state, get_labware_state), "
                "protocol tools (submit_protocol, add_workflow_note), and all "
                "instrument-specific tools you expect to use."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tool_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Complete list of tool names to activate. "
                            "Example: [\"get_deck_state\", \"get_labware_state\", "
                            "\"centrifuge_go_to_bucket1\", \"centrifuge_lock_bucket\", "
                            "\"centrifuge_close_door\", \"centrifuge_lock_door\", "
                            "\"centrifuge_spin\", \"centrifuge_open_door\", "
                            "\"read_absorbance\", \"submit_protocol\"]"
                        ),
                    }
                },
                "required": ["tool_names"],
                "additionalProperties": False,
            },
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# World registry
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class WorldConfig:
    world: str
    label: str
    max_turns: int
    system_prompt: str
    sample_episode: Callable | None = None
    tool_definitions: list[dict[str, Any]] = field(default_factory=list)
    dispatch_tool: Callable | None = None
    verify_run: Callable | None = None
    dispatch_uses_db_path: bool = False


def _build_world_configs() -> dict[str, WorldConfig]:
    configs: dict[str, WorldConfig] = {}

    # ── pylabrobot_star_v0 ───────────────────────────────────────────────
    try:
        from api_gym.worlds.pylabrobot_star_v0.sampler import sample_episode as star_sample
        from api_gym.worlds.pylabrobot_star_v0.tools import TOOL_DEFINITIONS as STAR_TOOLS
        from api_gym.worlds.pylabrobot_star_v0.tools import dispatch_tool as star_dispatch
        from api_gym.worlds.pylabrobot_star_v0.verifier import verify_run as star_verify

        configs["pylabrobot_star_v0"] = WorldConfig(
            world="pylabrobot_star_v0",
            label="PyLabRobot STAR (ChatterBox)",
            max_turns=40,
            system_prompt="""\
You are a lab automation agent operating a Hamilton STAR liquid handler.
The environment is a DRY-RUN STAR deck — no real hardware is connected.

STANDARD PROCEDURE:
1. Check workspace files for protocol context if relevant.
2. Inspect the deck state to see carriers and labware.
3. Inspect individual labware for well volumes and tip availability.
4. Use reference format: 'labware_name:well_id' (e.g. 'source_plate:A1').
5. OD600 (600 nm) is the standard absorbance wavelength.
6. Pick up tips BEFORE aspirating; return or discard tips after dispensing.
7. Match aspirate/dispense volumes exactly.
8. When you have valid readouts, submit the protocol decision.

Rules:
- Use the provided tools for every state inspection and mutation.
- Do not answer from task text alone — you MUST call tools.
- Think step by step before each tool call.
- When you have enough evidence, submit via submit_protocol.
""",
            sample_episode=star_sample,
            tool_definitions=STAR_TOOLS,
            dispatch_tool=star_dispatch,
            verify_run=star_verify,
        )
    except ImportError as e:
        print(f"[WARN] Cannot load pylabrobot_star_v0: {e}")

    # ── pylabrobot_lab_v0 ────────────────────────────────────────────────
    try:
        from api_gym.worlds.pylabrobot_lab_v0.sampler import sample_episode as plr_sample
        from api_gym.worlds.pylabrobot_lab_v0.tools import TOOL_DEFINITIONS as PLR_TOOLS
        from api_gym.worlds.pylabrobot_lab_v0.tools import dispatch_tool as plr_dispatch
        from api_gym.worlds.pylabrobot_lab_v0.verifier import verify_run as plr_verify

        configs["pylabrobot_lab_v0"] = WorldConfig(
            world="pylabrobot_lab_v0",
            label="PyLabRobot Lab v0 (ChatterBox)",
            max_turns=12,
            system_prompt="""\
You are a lab automation agent solving a Datalox API Gym pylabrobot_lab_v0 task.
The environment is a DRY-RUN lab deck backed by PyLabRobot — no real hardware.

STANDARD LAB PROCEDURE for plate QC:
1. Always inspect the deck state first to see what labware is loaded.
2. Inspect each labware object to understand well contents and volumes.
3. Use standard transfer volumes — typically 50 uL for QC assays.
4. OD600 (600 nm) is the standard wavelength for absorbance measurements.
5. Match your aspirate/dispense volume exactly.
6. Reference format for wells: 'labware_name:well_id'.
7. After obtaining a valid readout, submit the protocol decision.

Rules:
- Use the provided tools for every state inspection and mutation.
- Do not answer from task text alone — you MUST call tools to inspect state.
- Think step by step before each tool call.
- When you have enough evidence, submit via submit_protocol.
""",
            sample_episode=plr_sample,
            tool_definitions=PLR_TOOLS,
            dispatch_tool=plr_dispatch,
            verify_run=plr_verify,
        )
    except ImportError as e:
        print(f"[WARN] Cannot load pylabrobot_lab_v0: {e}")

    # ── unitelabs_plate_qc_v0 ────────────────────────────────────────────
    try:
        from api_gym.worlds.unitelabs_plate_qc_v0.sampler import sample_episode as uni_sample
        from api_gym.worlds.unitelabs_plate_qc_v0.tools import TOOL_DEFINITIONS as UNI_TOOLS
        from api_gym.worlds.unitelabs_plate_qc_v0.tools import dispatch_tool as uni_dispatch
        from api_gym.worlds.unitelabs_plate_qc_v0.verifier import verify_run as uni_verify

        configs["unitelabs_plate_qc_v0"] = WorldConfig(
            world="unitelabs_plate_qc_v0",
            label="UniteLabs Plate QC v0 (SQLite)",
            max_turns=12,
            system_prompt="""\
You are a lab automation agent solving a Datalox API Gym unitelabs_plate_qc_v0 task.
The environment is a DRY-RUN lab deck — no real hardware is connected.

STANDARD LAB PROCEDURE for plate QC:
1. Always inspect the deck state first to see what labware is loaded.
2. Inspect each labware object to understand well contents and volumes.
3. Use standard transfer volumes — typically 50 uL for QC assays.
4. OD600 (600 nm) is the standard wavelength for absorbance measurements.
5. Match your aspirate/dispense volume exactly.
6. After obtaining a valid readout, submit the protocol decision.

Rules:
- Use the provided tools for every state inspection and mutation.
- Do not answer from task text alone — you MUST call tools to inspect state.
- Think step by step before each tool call.
- When you have enough evidence, submit via submit_protocol.
""",
            sample_episode=uni_sample,
            tool_definitions=UNI_TOOLS,
            dispatch_tool=uni_dispatch,
            verify_run=uni_verify,
            dispatch_uses_db_path=True,
        )
    except ImportError as e:
        print(f"[WARN] Cannot load unitelabs_plate_qc_v0: {e}")

    return configs


# ═══════════════════════════════════════════════════════════════════════════════
# Core runner
# ═══════════════════════════════════════════════════════════════════════════════

def _load_api_key() -> str:
    key = os.environ.get("DEEPSEEK_API_KEY", "") or "sk-353c00831093487ca08314983ec3317f"
    if not key:
        print("ERROR: DEEPSEEK_API_KEY environment variable is not set.")
        print("Usage: set DEEPSEEK_API_KEY=sk-... && python gen_trajectory/run.py ...")
        sys.exit(1)
    return key


def _make_tool_message(tool_call_id: str, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": json.dumps(result, ensure_ascii=False),
    }


def _filter_tools(
    tool_definitions: list[dict[str, Any]],
    selected_names: set[str],
) -> list[dict[str, Any]]:
    """Return only tools whose names are in the selected set or always-included."""
    effective = selected_names | ALWAYS_INCLUDE
    filtered = [t for t in tool_definitions if t["function"]["name"] in effective]
    return filtered


def _run_tool_selection_phase(
    client: OpenAI,
    catalog: str,
    system_prompt: str,
    user_prompt: str,
) -> tuple[set[str], dict[str, Any], int, int]:
    """Phase 1: Ask the agent to select tools from the compact catalog.

    Returns: (selected_tool_names, turn_record, prompt_tokens, completion_tokens)
    """
    select_tools_def = _select_tools_schema()

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": (
            f"{catalog}\n\n"
            f"---\n\n"
            f"TASK:\n{user_prompt}\n\n"
            f"---\n\n"
            f"FIRST: call select_tools to activate the tools you need. "
            f"Read the task carefully and identify every instrument and operation "
            f"mentioned. Include inspection tools and submission tools. "
            f"Be thorough — it's better to select a few extra tools than to miss one."
        )},
    ]

    print(f"\n{'='*60}")
    print("PHASE 1 — Tool Selection")
    print(f"{'='*60}")
    print(f"Catalog: {len(catalog):,} chars (~{len(catalog)//4:,} tokens)")
    print(f"Available tools: listed in catalog")

    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        tools=[select_tools_def],
        tool_choice="auto",  # Let model decide — but prompt says it MUST call select_tools
        stream=False,
        temperature=TEMPERATURE,
        extra_body={"thinking": {"type": "enabled"}},
    )

    usage = response.usage
    pt = usage.prompt_tokens if usage else 0
    ct = usage.completion_tokens if usage else 0

    choice = response.choices[0]
    message = choice.message
    reasoning = getattr(message, "reasoning_content", None) or ""

    tool_calls = getattr(message, "tool_calls", None) or []

    if not tool_calls:
        # Agent didn't call select_tools — fall back to all tools
        print("  Agent did not call select_tools — using all tools.")
        all_names = set()  # signal to use all tools
        turn_record = {
            "turn": 0, "phase": "tool_selection",
            "thought": reasoning,
            "tool_call": None,
            "tool_result": {"selected_tools": "ALL (fallback)"},
        }
        return all_names, turn_record, pt, ct

    tc = tool_calls[0]
    tool_name = tc.function.name

    if tool_name != "select_tools":
        print(f"  Agent called '{tool_name}' instead of select_tools — using all tools.")
        turn_record = {
            "turn": 0, "phase": "tool_selection",
            "thought": reasoning,
            "tool_call": {"id": tc.id, "name": tool_name,
                          "arguments": json.loads(tc.function.arguments or "{}")},
            "tool_result": {"selected_tools": "ALL (agent called wrong tool)"},
        }
        return set(), turn_record, pt, ct

    # Parse selected tool names
    try:
        args = json.loads(tc.function.arguments)
        selected = set(args.get("tool_names", []))
    except json.JSONDecodeError:
        selected = set()

    print(f"  Agent selected {len(selected)} tools: {sorted(selected)}")

    turn_record = {
        "turn": 0, "phase": "tool_selection",
        "thought": reasoning,
        "tool_call": {
            "id": tc.id,
            "name": "select_tools",
            "arguments": {"tool_names": sorted(selected)},
        },
    }

    return selected, turn_record, pt, ct


def run_trajectory(
    *,
    world: str,
    scenario: str,
    seed: int = 42,
    out_dir: Path | None = None,
    output_dir: Path | None = None,
    max_turns: int | None = None,
    no_tool_filter: bool = False,
) -> dict[str, Any]:
    """Run an LLM agent loop and record the full trajectory."""
    configs = _build_world_configs()
    if world not in configs:
        supported = ", ".join(sorted(configs))
        raise ValueError(f"Unknown world '{world}'. Supported: {supported}")

    cfg = configs[world]
    effective_max_turns = max_turns if max_turns is not None else cfg.max_turns

    # ── Create run directory ────────────────────────────────────────────
    if out_dir is not None:
        run_dir = out_dir.resolve()
        run_dir.mkdir(parents=True, exist_ok=True)
        episode = cfg.sample_episode(scenario=scenario, seed=seed, out_dir=run_dir)
    else:
        base = PROJECT_ROOT / "runs" / "trajectory"
        base.mkdir(parents=True, exist_ok=True)
        run_dir = Path(tempfile.mkdtemp(
            prefix=f"{world}_{scenario}_seed{seed}_", dir=base
        )).resolve()
        episode = cfg.sample_episode(scenario=scenario, seed=seed, out_dir=run_dir)

    task = episode.task
    user_prompt = task["prompt"] if isinstance(task, dict) else str(task)

    print(f"World:      {cfg.label}")
    print(f"Scenario:   {scenario}")
    print(f"Seed:       {seed}")
    print(f"Run dir:    {run_dir}")
    print(f"Model:      {MODEL}")
    print(f"Max turns:  {effective_max_turns}")

    # ── Resolve dispatch path ───────────────────────────────────────────
    if cfg.dispatch_uses_db_path:
        dispatch_path = run_dir / "state.sqlite"
    else:
        dispatch_path = run_dir

    # ── Initialize DeepSeek client ──────────────────────────────────────
    api_key = _load_api_key()
    client = OpenAI(api_key=api_key, base_url=BASE_URL)

    # ── Token tracking ──────────────────────────────────────────────────
    total_prompt_tokens = 0
    total_completion_tokens = 0

    # ── Trajectory recording ────────────────────────────────────────────
    turns: list[dict[str, Any]] = []
    tool_call_log: list[dict[str, Any]] = []
    selected_tool_names: set[str] = set()  # empty = use all tools

    # ── Phase 1: Tool selection ─────────────────────────────────────────
    enable_filter = (not no_tool_filter
                     and len(cfg.tool_definitions) >= MIN_TOOLS_FOR_FILTER)

    if enable_filter:
        catalog = build_compact_catalog(cfg.tool_definitions)
        selected, sel_turn, sel_pt, sel_ct = _run_tool_selection_phase(
            client, catalog, cfg.system_prompt, user_prompt,
        )
        total_prompt_tokens += sel_pt
        total_completion_tokens += sel_ct
        turns.append(sel_turn)

        if selected:  # non-empty = agent made a selection
            selected_tool_names = selected
            # Merge always-included for display
            effective = selected | ALWAYS_INCLUDE
            filtered = _filter_tools(cfg.tool_definitions, selected)
            print(f"  +{len(ALWAYS_INCLUDE)} always-included: {sorted(ALWAYS_INCLUDE)}")
            print(f"  Effective tools: {len(effective)} → {len(filtered)} full schemas")
        else:
            print("  Using all tools (no selection made).")

    # Determine active tools for the main loop
    if selected_tool_names:
        active_tools = _filter_tools(cfg.tool_definitions, selected_tool_names)
    else:
        active_tools = cfg.tool_definitions

    print(f"  Tool mode: {'filtered' if selected_tool_names else 'all'} "
          f"({len(active_tools)}/{len(cfg.tool_definitions)} tools)")

    # ── Build initial messages for Phase 2 ──────────────────────────────
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": cfg.system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    # If a tool selection phase ran and succeeded, add it to message history
    if enable_filter and selected_tool_names:
        sel_record = turns[-1]
        tc = sel_record["tool_call"]
        if tc is not None:
            # Assistant message with select_tools call
            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": "select_tools",
                        "arguments": json.dumps(tc["arguments"], ensure_ascii=False),
                    },
                }],
            }
            reasoning = sel_record.get("thought", "")
            if reasoning:
                assistant_msg["reasoning_content"] = reasoning
            messages.append(assistant_msg)

            # Tool result: confirmation
            selected_list = sorted(selected_tool_names)
            messages.append(_make_tool_message(tc["id"], {
                "ok": True,
                "data": {
                    "activated_tools": selected_list,
                    "always_available": sorted(ALWAYS_INCLUDE - {"select_tools"}),
                    "total": len(selected_tool_names | ALWAYS_INCLUDE),
                },
            }))

    # ── Phase 2: Main agent loop ────────────────────────────────────────
    final_answer: dict[str, Any] | None = None
    stop_reason = "max_turns"
    phase2_start_turn = len(turns)  # turns already has the selection record

    for turn_idx in range(1, effective_max_turns + 1):
        display_turn = phase2_start_turn + turn_idx
        print(f"\n{'='*60}")
        print(f"Turn {display_turn} [Phase 2, step {turn_idx}/{effective_max_turns}]")
        print(f"{'='*60}")

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=active_tools,
            tool_choice="auto",
            stream=False,
            temperature=TEMPERATURE,
            extra_body={"thinking": {"type": "enabled"}},
        )

        usage = response.usage
        if usage:
            total_prompt_tokens += usage.prompt_tokens or 0
            total_completion_tokens += usage.completion_tokens or 0

        choice = response.choices[0]
        message = choice.message
        reasoning_content = getattr(message, "reasoning_content", None) or ""
        tool_calls = getattr(message, "tool_calls", None) or []

        if not tool_calls:
            content = message.content or ""
            safe_content = content[:200].encode("ascii", errors="replace").decode("ascii")
            print(f"FINAL ANSWER: {safe_content}...")
            final_answer = {
                "content": content,
                "stop_reason": "assistant_final",
                "turns": display_turn,
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

            # --- Handle select_tools during main loop (add more tools) ---
            if tool_name == "select_tools" and enable_filter:
                new_names = set(arguments.get("tool_names", []))
                added = new_names - selected_tool_names
                if added:
                    print(f"  SELECT_TOOLS: adding {len(added)} tools: {sorted(added)}")
                    selected_tool_names |= new_names
                    active_tools = _filter_tools(cfg.tool_definitions, selected_tool_names)
                    print(f"  Active tools now: {len(active_tools)}")
                result = {
                    "ok": True,
                    "data": {
                        "activated_tools": sorted(selected_tool_names),
                        "newly_added": sorted(added),
                        "total_active": len(active_tools),
                    },
                }
                messages.append(_make_tool_message(tc.id, result))
                turns.append({
                    "turn": display_turn,
                    "phase": "tool_selection_update",
                    "thought": reasoning_content,
                    "tool_call": {
                        "id": tc.id, "name": "select_tools",
                        "arguments": {"tool_names": sorted(new_names)},
                    },
                    "tool_result": result,
                })
                continue

            # --- Normal tool dispatch ---
            print(f"  TOOL: {tool_name}({json.dumps(arguments, ensure_ascii=False)[:120]})")

            result = cfg.dispatch_tool(dispatch_path, name=tool_name, arguments=arguments)

            ok_str = "OK" if result.get("ok") else "ERROR"
            result_preview = json.dumps(result, ensure_ascii=False)[:200]
            print(f"  RESULT [{ok_str}]: {result_preview}")

            messages.append(_make_tool_message(tc.id, result))

            turn_record = {
                "turn": display_turn,
                "thought": reasoning_content if reasoning_content else f"Calling {tool_name}",
                "tool_call": {
                    "id": tc.id,
                    "name": tool_name,
                    "arguments": arguments,
                },
                "tool_result": result,
            }
            turns.append(turn_record)

            tool_call_log.append({
                "turn": display_turn,
                "id": tc.id,
                "name": tool_name,
                "arguments": arguments,
                "result": result,
            })

            reasoning_content = ""

    # ── Final answer fallback ───────────────────────────────────────────
    if final_answer is None:
        final_answer = {
            "content": None,
            "stop_reason": "max_turns",
            "turns": len(turns),
        }
        stop_reason = "max_turns"

    # ── Run verifier ────────────────────────────────────────────────────
    verifier_result = cfg.verify_run(run_dir).to_dict()
    ok_str = "PASS" if verifier_result["ok"] else "FAIL"
    print(f"\nVerifier [{ok_str}]:")
    for check in verifier_result.get("checks", []):
        status = "✅" if check["ok"] else "❌"
        name = check.get("name", "?")
        detail = check.get("detail", "")
        line = f"  {status} {name}"
        if detail:
            line += f" — {detail}"
        print(line)

    # ── Build trajectory ────────────────────────────────────────────────
    trajectory = {
        "schema_version": "datalox.trajectory.v0",
        "world": world,
        "scenario": scenario,
        "seed": seed,
        "mode": "dry_run",
        "model": MODEL,
        "tool_filter": {
            "enabled": enable_filter and bool(selected_tool_names),
            "selected_count": len(selected_tool_names) if selected_tool_names else len(cfg.tool_definitions),
            "total_available": len(cfg.tool_definitions),
            "active_count": len(active_tools),
        },
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "task": task,
        "turns": turns,
        "final_answer": final_answer,
        "total_turns": len(turns),
        "verifier_result": verifier_result,
    }

    # ── Write outputs ───────────────────────────────────────────────────
    if output_dir is None:
        output_dir = Path(__file__).resolve().parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    ts = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
    prefix = f"trajectory_{world}_{scenario}_seed{seed}_{ts}"

    traj_path = output_dir / f"{prefix}.json"
    traj_path.write_text(
        json.dumps(trajectory, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nTrajectory saved to {traj_path}")

    msg_path = output_dir / f"{prefix}_messages.jsonl"
    with open(msg_path, "w", encoding="utf-8") as f:
        for msg in messages:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")
    print(f"Messages saved to {msg_path}")

    # ── Token summary ───────────────────────────────────────────────────
    total_tokens = total_prompt_tokens + total_completion_tokens
    print(f"\n{'='*60}")
    print("TOKEN USAGE")
    print(f"{'='*60}")
    print(f"Prompt tokens:      {total_prompt_tokens:>8,}")
    print(f"Completion tokens:  {total_completion_tokens:>8,}")
    print(f"Total tokens:       {total_tokens:>8,}")
    print(f"Total turns:        {len(turns):>8}")
    if len(turns) > 0:
        print(f"Avg tokens/turn:    {total_tokens / len(turns):>8,.0f}")

    return trajectory


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    import argparse
    import inspect

    configs = _build_world_configs()
    world_list = ", ".join(sorted(configs))

    parser = argparse.ArgumentParser(
        description="Run LLM-driven agent trajectory (unified — all worlds)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"Available worlds: {world_list}",
    )
    parser.add_argument(
        "--world", default="pylabrobot_star_v0",
        help=f"World ID (default: pylabrobot_star_v0). Available: {world_list}",
    )
    parser.add_argument(
        "--scenario", default=None,
        help="Scenario name. If omitted, lists available scenarios.",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Deterministic seed (default: 42).",
    )
    parser.add_argument(
        "--max-turns", type=int, default=None,
        help="Override default max turns for this world.",
    )
    parser.add_argument(
        "--no-tool-filter", action="store_true",
        help="Disable tool filtering (send all tools every turn for comparison).",
    )
    parser.add_argument(
        "--out", default=None,
        help="Optional run directory (temp dir used if not specified).",
    )
    parser.add_argument(
        "--output", default=None,
        help="Output directory for trajectory files (default: gen_trajectory/output).",
    )
    parser.add_argument(
        "--list-scenarios", action="store_true",
        help="List available scenarios for the world and exit.",
    )
    args = parser.parse_args()

    if args.world not in configs:
        print(f"ERROR: Unknown world '{args.world}'.")
        print(f"Available: {world_list}")
        sys.exit(1)

    cfg = configs[args.world]

    # ── List scenarios mode ────────────────────────────────────────────
    if args.list_scenarios or args.scenario is None:
        mod = inspect.getmodule(cfg.sample_episode)
        if mod and hasattr(mod, "SCENARIOS"):
            scenarios = sorted(mod.SCENARIOS)
            print(f"Available scenarios for {args.world} ({cfg.label}):")
            for s in scenarios:
                print(f"  {s}")
            print(f"\nTotal: {len(scenarios)}")
        else:
            print(f"No scenario list found for {args.world}.")
        if args.scenario is None:
            print("\nUse --scenario <name> to run a trajectory.")
            sys.exit(0)

    # ── Run trajectory ─────────────────────────────────────────────────
    out_dir = Path(args.out).resolve() if args.out else None
    output_dir = Path(args.output).resolve() if args.output else None

    run_trajectory(
        world=args.world,
        scenario=args.scenario,
        seed=args.seed,
        out_dir=out_dir,
        output_dir=output_dir,
        max_turns=args.max_turns,
        no_tool_filter=args.no_tool_filter,
    )


if __name__ == "__main__":
    main()
