# Agent Trajectory Generation Plan

## Target

Generate a complete LLM-driven agent trajectory for the `unitelabs_plate_qc_v0` world (`plate_transfer_qc` scenario) in the `api-grounding` branch of Datalox API Gym.

## Why This Matters

A real agent trajectory requires **LLM decision-making**: the model receives the task prompt, reasons about what to do, decides which tool to call, interprets the result, and iterates. This is fundamentally different from oracle script execution — the LLM may succeed or fail, and its reasoning path is the valuable artifact.

## Architecture

```
                        ┌─────────────────────┐
                        │   DeepSeek v4-pro    │
                        │   thinking: enabled   │
                        │   tools: 7 tool defs  │
                        └─────────┬───────────┘
                                  │ tool_calls
                                  ▼
┌─────────────────────────────────────────────────────────┐
│                  trajectory_runner.py                    │
│                                                         │
│  1. Load task.json + TOOL_DEFINITIONS                   │
│  2. Loop (max 12 turns):                                │
│     a. Send messages + tools → DeepSeek                 │
│     b. Extract reasoning_content as "thought"           │
│     c. If tool_calls: dispatch_tool() → record turn     │
│     d. If no tool_calls: record final_answer → break    │
│  3. Output trajectory.json + tool_calls.jsonl           │
└─────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────┐
│              api-gym session lifecycle                   │
│                                                         │
│  session create  →  sample initial state                │
│  session check-tools → verify MCP tools                 │
│  trajectory_runner.py → LLM-driven execution            │
│  session finalize → verify + export                     │
└─────────────────────────────────────────────────────────┘
```

## Tech Stack

| Component | Choice |
|-----------|--------|
| LLM API | DeepSeek (`https://api.deepseek.com`) |
| Model | `deepseek-v4-pro` |
| Reasoning | `thinking: enabled` (DeepSeek native) |
| SDK | `openai` Python package |
| Tool dispatch | `api_gym.worlds.unitelabs_plate_qc_v0.tools.dispatch_tool` |
| State | SQLite via session create |
| Verification | `api-gym session finalize` (8 checks) |

## Scenario: plate_transfer_qc

**World:** unitelabs_plate_qc_v0
**Mode:** dry_run
**Initial state:**
- Deck `deck_1` in dry_run mode with 3 labware loaded
- `source_plate` well A1: 120µL qc_control
- `assay_plate` well B1: 0µL (empty, target)
- `tip_rack_1` A1: available
- Pipette `p300_single`: idle
- Control band: assay_plate B1, OD600, [0.75, 0.9], expected 0.82

**Task prompt:**
> Evaluate whether the plate QC workflow should continue. Inspect the dry-run deck state and labware state, use the available lab tools to gather evidence, and submit a final protocol decision with the supporting readout evidence.

**Expected correct path (8 steps):**
1. `get_deck_state()` — inspect deck
2. `get_labware_state("source_plate")` — inspect source
3. `get_labware_state("assay_plate")` — inspect target
4. `get_labware_state("tip_rack_1")` — inspect tips
5. `aspirate(source="source_plate:A1", volume_ul=50, tip="tip_rack_1:A1")` — transfer
6. `dispense(target="assay_plate:B1", volume_ul=50)` — dispense
7. `read_absorbance(plate="assay_plate", wavelength_nm=600, wells=["B1"])` — measure
8. `submit_protocol(decision="continue", evidence_readout_id=..., target_well="assay_plate:B1", rationale=...)` — submit

**Verifier checks (8):**
- `dry_run_no_live_action` — deck stays in dry_run
- `expected_labware_and_wells_exist` — source/target/tip present
- `no_overdrawn_well` — no negative volumes
- `valid_transfer_completed` — 50µL transfer recorded
- `readout_after_dispense` — OD600 readout after transfer
- `protocol_submitted` — submission exists
- `submitted_target_matches_expected` — target is assay_plate:B1
- `decision_matches_observed_data` — decision matches OD600 vs control band

## Output Files

All in `gen_trajectory/output/`:

| File | Description |
|------|-------------|
| `trajectory.json` | Full trajectory with thoughts, tool calls, results, final answer, verifier |
| `tool_calls.jsonl` | One tool call per line |
| `messages.jsonl` | Full LLM message history |
| `session_manifest.json` | Session handoff manifest |
| `verifier_result.json` | Verification checks |
| `run_export.json` | Bundled run evidence |

## Implementation Steps

### Step 1: Environment Setup
```bash
cd unitelabs-api-grounding
pip install -e .
pip install openai
```

### Step 2: Session Create
```bash
api-gym session create \
  --world unitelabs_plate_qc_v0 \
  --scenario plate_transfer_qc \
  --seed 42 \
  --out runs/plate_qc_trajectory
```

### Step 3: Check Tools
```bash
api-gym session check-tools --run runs/plate_qc_trajectory
```

### Step 4: Run trajectory_runner.py
```bash
python gen_trajectory/trajectory_runner.py \
  --run runs/plate_qc_trajectory \
  --api-key $DEEPSEEK_API_KEY
```

### Step 5: Session Finalize
```bash
api-gym session finalize --run runs/plate_qc_trajectory
```

### Step 6: Assemble final trajectory.json
Merge runner output with verifier result.

## Key Design Decisions

1. **DeepSeek `thinking` mode**: The model's `reasoning_content` is captured as the agent's "thought" per turn, providing visibility into the decision process.
2. **Direct tool dispatch**: Uses `dispatch_tool()` from unitelabs_plate_qc_v0.tools, NOT the billing hardcoded runner.
3. **No oracle dependency**: The LLM decides every tool call. If it makes a wrong decision, the trajectory captures that honestly — verifier will show pass/fail.
4. **Session lifecycle integration**: Full create → check-tools → finalize flow, demonstrating api-grounding's session workflow.
5. **Dry-run enforcement**: The verifier's `dry_run_no_live_action` check ensures no real hardware was touched.
