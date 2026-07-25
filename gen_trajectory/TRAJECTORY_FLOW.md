# Unitelabs Plate QC v0 轨迹生成完整流程

> 本文档详细描述基于 `unitelabs_plate_qc_v0` world 的 `plate_transfer_qc` 场景，从零生成一条 LLM 驱动 agent 轨迹的完整步骤与代码调用链。

---

## 总览

```
┌──────────────────────────────────────────────────────────────────────┐
│                      轨迹生成 6 阶段                                   │
│                                                                      │
│  阶段一: session create    → 采样初始状态 (SQLite + task)              │
│  阶段二: session check-tools → 验证 MCP 工具目录                      │
│  阶段三: trajectory_runner  → LLM agent 循环 (核心)                   │
│  阶段四: session finalize   → 验证 + 导出证据                         │
│  阶段五: verify (可选)      → 单独验证 run                            │
│  阶段六: export (可选)      → 单独导出证据包                           │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 阶段一：创建 World Session（采样初始状态）

### CLI 命令

```bash
api-gym session create \
  --world unitelabs_plate_qc_v0 \
  --scenario plate_transfer_qc \
  --seed 42 \
  --out runs/plate_qc_trajectory
```

### 调用链

```
cli.py: session_create()
  └─ session.py: create_world_session(world="unitelabs_plate_qc_v0", scenario="plate_transfer_qc", seed=42, out_dir=Path("runs/plate_qc_trajectory"))
       │
       ├─ registry.py: get_world_runtime("unitelabs_plate_qc_v0")
       │    └─ _runtime_from_package(world, package="api_gym.worlds.unitelabs_plate_qc_v0", mcp_server_title="API Gym UniteLabs Plate QC")
       │         ├─ importlib.import_module("api_gym.worlds.unitelabs_plate_qc_v0.sampler")
       │         ├─ importlib.import_module("api_gym.worlds.unitelabs_plate_qc_v0.verifier")
       │         ├─ importlib.import_module("api_gym.worlds.unitelabs_plate_qc_v0.tools")
       │         ├─ importlib.import_module("api_gym.worlds.unitelabs_plate_qc_v0.state")
       │         └─ 返回 WorldRuntime(
       │              world="unitelabs_plate_qc_v0",
       │              world_id="unitelabs-plate-qc-v0",
       │              scenarios={"plate_transfer_qc"},
       │              sample_episode=sampler.sample_episode,
       │              verify_run=verifier.verify_run,
       │              tool_definitions=tools.TOOL_DEFINITIONS,     # 7 个工具 schema
       │              dispatch_tool=tools.dispatch_tool,
       │              resolve_state_db_path=state.resolve_state_db_path,
       │              run_metadata_name="run.json",
       │              task_name="task.json",
       │              mcp_server_name="api-gym-unitelabs-plate-qc-v0",
       │              mcp_server_title="API Gym UniteLabs Plate QC",
       │            )
       │
       ├─ runtime.sample_episode(scenario="plate_transfer_qc", seed=42, out_dir=Path(...))
       │    └─ sampler.py: sample_episode()
       │         ├─ state.py: initialize_db(db_path)
       │         │    └─ 创建 state.sqlite，执行 SCHEMA_SQL (11 张表: deck, labware, wells, tips,
       │         │       pipette_state, control_bands, transfers, readouts, workflow_notes,
       │         │       submissions, events, audit_log)
       │         │
       │         ├─ SCENARIOS["plate_transfer_qc"](db_path, 42)
       │         │    └─ sampler.py: _build_plate_transfer_qc(db_path, seed=42)
       │         │         ├─ state.py: connect(db_path)          ← 打开 SQLite
       │         │         ├─ INSERT INTO deck (id="deck_1", mode="dry_run", dry_run=1,
       │         │         │     loaded_labware_json=["source_plate","assay_plate","tip_rack_1"])
       │         │         ├─ INSERT INTO labware (id="source_plate", kind="plate", display_name="Source Plate")
       │         │         ├─ INSERT INTO labware (id="assay_plate", kind="plate", display_name="Assay Plate")
       │         │         ├─ INSERT INTO labware (id="tip_rack_1", kind="tip_rack", display_name="Tip Rack 1")
       │         │         ├─ INSERT INTO wells (labware_id="source_plate", well_id="A1", volume_ul=120.0,
       │         │         │     metadata={"contents":"qc_control"})
       │         │         ├─ INSERT INTO wells (labware_id="assay_plate", well_id="B1", volume_ul=0.0,
       │         │         │     metadata={"contents":"empty_assay_well"})
       │         │         ├─ INSERT INTO tips (rack_id="tip_rack_1", well_id="A1", status="available")
       │         │         ├─ INSERT INTO pipette_state (id="p300_single", tip=NULL,
       │         │         │     aspirated_volume_ul=0.0, source_labware_id=NULL, source_well_id=NULL)
       │         │         ├─ INSERT INTO control_bands (id="control_band_assay_b1_od600",
       │         │         │     plate_id="assay_plate", well_id="B1", wavelength_nm=600,
       │         │         │     min_value=0.75, max_value=0.9, expected_value=0.82,
       │         │         │     required_dispense_ul=50.0)
       │         │         └─ state.py: insert_event(conn, event_type="expected_resolution.created",
       │         │              object_type="scenario", object_id="plate_transfer_qc",
       │         │              payload={scenario, source:"source_plate:A1", target:"assay_plate:B1",
       │         │                       tip:"tip_rack_1:A1", transfer_volume_ul:50, wavelength_nm:600,
       │         │                       control_band:{min:0.75, max:0.9}, expected_readout_value:0.82,
       │         │                       expected_decision:"continue"},
       │         │              visible_to_agent=False)           ← 隐藏 verifier 状态!
       │         │
       │         ├─ 写 task.json:
       │         │    {"schema_version":"api_gym.task.v0", "world":"unitelabs_plate_qc_v0",
       │         │     "world_id":"unitelabs-plate-qc-v0", "scenario":"plate_transfer_qc",
       │         │     "seed":42, "objective":"Evaluate whether the plate QC workflow should continue.",
       │         │     "prompt":"Evaluate whether the plate QC workflow should continue. Inspect the
       │         │              dry-run deck state and labware state, use the available lab tools to
       │         │              gather evidence, and submit a final protocol decision with the
       │         │              supporting readout evidence."}
       │         │
       │         ├─ 写 run.json:
       │         │    {"world":"unitelabs_plate_qc_v0", "world_id":"unitelabs-plate-qc-v0",
       │         │     "scenario":"plate_transfer_qc", "seed":42, "mode":"dry_run",
       │         │     "state_db":"state.sqlite", "task":"task.json"}
       │         │
       │         └─ 返回 SampledEpisode(run_dir, db_path, task_path, run_metadata_path, task)
       │
       ├─ agent_harness.py: write_agent_task_package(run_dir, run_dir / "agent_task.json")
       │    └─ build_agent_task_package(run_dir)
       │         ├─ registry.py: get_runtime_for_run(run_dir)
       │         │    └─ read_run_metadata(run_dir) → 读 run.json
       │         │    └─ get_world_runtime("unitelabs_plate_qc_v0")
       │         │
       │         ├─ 读取 task.json → 提取 prompt
       │         ├─ 构建 mcp_command = ["api-gym", "mcp", "--run", str(run_dir)]
       │         ├─ 构建 verifier_command = ["api-gym", "verify", "--run", str(run_dir)]
       │         ├─ 构建 agent_facing_instructions:
       │         │    "You are solving a Datalox API Gym unitelabs_plate_qc_v0 task.\n\n"
       │         │    + prompt + "\n\nRules:\n"
       │         │    - "Use the MCP tools for every state inspection and mutation."
       │         │    - "Do not answer from task text alone."
       │         │    - "Do not inspect state.sqlite or hidden verifier state directly."
       │         │    - "Finish by leaving the run state ready for the verifier command to pass."
       │         │
       │         └─ 返回完整的 agent task package (含 MCP config, 环境变量, verifier command)
       │
       └─ session.py: build_session_manifest(run_dir)
            └─ 写 session_manifest.json:
                 {
                   "schema_version": "api_gym.world_session.v0",
                   "session_id": "plate_qc_trajectory",
                   "world": "unitelabs_plate_qc_v0",
                   "world_id": "unitelabs-plate-qc-v0",
                   "scenario": "plate_transfer_qc",
                   "seed": 42,
                   "mode": "dry_run",
                   "run_dir": "<absolute_path>/runs/plate_qc_trajectory",
                   "task": {...},
                   "task_path": ".../task.json",
                   "task_instructions": "<agent_facing_instructions>",
                   "task_package": ".../agent_task.json",
                   "mcp": {
                     "mcpServers": {
                       "api-gym-unitelabs-plate-qc-v0": {
                         "command": "api-gym", "args": ["mcp", "--run", "<run_dir>"]
                       }
                     }
                   },
                   "expected_tools": [
                     "add_workflow_note", "aspirate", "dispense", "get_deck_state",
                     "get_labware_state", "read_absorbance", "submit_protocol"
                   ],
                   "integration_instructions": [...],
                   "preflight": {...},
                   "commands": {
                     "check_tools": ["api-gym", "session", "check-tools", "--run", "<run_dir>"],
                     "verify": ["api-gym", "verify", "--run", "<run_dir>"],
                     "export": ["api-gym", "export", "--run", "<run_dir>", "--out", "<run_dir>/run_export.json"],
                     "finalize": ["api-gym", "session", "finalize", "--run", "<run_dir>"]
                   },
                   "artifacts": {
                     "root": "<run_dir>",
                     "run_metadata": ".../run.json",
                     "state_db": ".../state.sqlite",
                     "task": ".../task.json",
                     "task_package": ".../agent_task.json",
                     "tool_trace": ".../agent_tool_calls.jsonl",
                     "session_manifest": ".../session_manifest.json",
                     "run_export": ".../run_export.json",
                     "finalization": ".../session_finalization.json"
                   }
                 }
```

### 产出文件

```
runs/plate_qc_trajectory/
  ├── state.sqlite           ← SQLite 数据库（含隐藏 verifier 状态）
  ├── task.json              ← agent 可见任务
  ├── run.json               ← 运行元数据
  ├── agent_task.json        ← agent host 任务包
  └── session_manifest.json  ← 会话清单
```

### 初始 SQLite 状态一览

| 表 | 关键行 | 说明 |
|----|--------|------|
| `deck` | `deck_1`, mode=`dry_run`, dry_run=1 | 干式运行 deck，3 个 labware |
| `labware` | `source_plate` (plate) | 源板，96 孔 |
| `labware` | `assay_plate` (plate) | 检测板，96 孔 |
| `labware` | `tip_rack_1` (tip_rack) | 枪头架，96 枪头 |
| `wells` | `source_plate:A1`, 120µL, contents=`qc_control` | 含 QC 对照样品 |
| `wells` | `assay_plate:B1`, 0µL, contents=`empty_assay_well` | 空的检测孔（目标） |
| `tips` | `tip_rack_1:A1`, status=`available` | 可用枪头 |
| `pipette_state` | `p300_single`, 空闲 | 移液器就绪 |
| `control_bands` | assay_plate:B1, OD600, [0.75, 0.9], expected=0.82, dispense=50µL | QC 控制带 |
| `events` | expected_resolution.created, visible_to_agent=0 | 隐藏预期结果 |

---

## 阶段二：预检工具目录

### CLI 命令

```bash
api-gym session check-tools --run runs/plate_qc_trajectory
```

### 调用链

```
cli.py: session_check_tools()
  └─ session.py: check_session_tools(run_dir)
       │
       ├─ registry.py: get_runtime_for_run(run_dir)
       │    └─ read_run_metadata(run_dir) → 读 run.json
       │    └─ get_world_runtime("unitelabs_plate_qc_v0") → WorldRuntime
       │
       ├─ 获取预期工具列表 (来自 tools.py: TOOL_DEFINITIONS):
       │    ["add_workflow_note", "aspirate", "dispense", "get_deck_state",
       │     "get_labware_state", "read_absorbance", "submit_protocol"]
       │
       ├─ agent_harness.py: create_mcp_handler(run_dir)
       │    └─ ApiGymMcpHandler(run_dir)
       │         ├─ _ensure_supported_run(run_dir)
       │         │    ├─ get_runtime_for_run(run_dir) → WorldRuntime
       │         │    ├─ runtime.resolve_state_db_path(run_dir)
       │         │    │    └─ state.py: resolve_state_db_path()
       │         │    │         ├─ 读 run.json → state_db = "state.sqlite"
       │         │    │         └─ 返回 run_dir / "state.sqlite"
       │         │    └─ 验证 run_dir / "task.json" 存在
       │         ├─ self.runtime = WorldRuntime
       │         ├─ self.db_path = run_dir / "state.sqlite"
       │         └─ self.metadata = read_run_metadata(run_dir)
       │
       ├─ handler.handle_message({"jsonrpc":"2.0", "id":"check-tools", "method":"tools/list"})
       │    └─ agent_harness.py: ApiGymMcpHandler.handle_message()
       │         └─ 匹配 method == "tools/list"
       │         └─ 返回 _jsonrpc_result(request_id, {
       │              "tools": [_to_mcp_tool(tool) for tool in self.runtime.tool_definitions]
       │            })
       │              └─ 将 OpenAI function schema 转为 MCP 格式
       │                   {name, description, inputSchema: function.parameters}
       │
       └─ 比较 expected_tools vs listed_tools:
            返回 {ok: true/false, expected_tools, listed_tools, missing_tools, unexpected_tools}
```

### 作用

验证 MCP server 能正确列出全部 7 个工具——确保 agent host 连接 MCP 后工具层完整可用。

---

## 阶段三：LLM 驱动 Agent 执行（核心）

### CLI 命令

```bash
set DEEPSEEK_API_KEY=sk-...
python gen_trajectory/trajectory_runner.py \
  --run runs/plate_qc_trajectory \
  --output gen_trajectory/output
```

### 调用链（trajectory_runner.py）

```
trajectory_runner.py: main()
  │
  ├─ 解析参数: run_dir = Path("runs/plate_qc_trajectory").resolve()
  │            output_dir = Path("gen_trajectory/output").resolve()
  │
  └─ run_trajectory(run_dir, output_dir)
       │
       ├─ [初始化阶段]
       │    ├─ 读取 run_dir / "task.json"
       │    │    → task["prompt"] = "Evaluate whether the plate QC workflow should continue..."
       │    │
       │    ├─ 读取 run_dir / "run.json"
       │    │    → run_meta = {world, world_id, scenario, seed:42, mode:"dry_run", ...}
       │    │
       │    ├─ db_path = run_dir / run_meta["state_db"]
       │    │           = run_dir / "state.sqlite"
       │    │
       │    ├─ 初始化 DeepSeek client:
       │    │    OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")
       │    │
       │    ├─ 构建初始 messages:
       │    │    [
       │    │      {"role": "system", "content": SYSTEM_PROMPT},
       │    │      {"role": "user", "content": task["prompt"]}
       │    │    ]
       │    │
       │    └─ tools = tools.py: TOOL_DEFINITIONS  (7 个 OpenAI function schema)
       │
       ├─ [Agent 循环] for turn_idx in 1..12:
       │    │
       │    ├─ [1] 调用 DeepSeek API:
       │    │    client.chat.completions.create(
       │    │      model="deepseek-v4-pro",
       │    │      messages=messages,          # 当前完整历史
       │    │      tools=TOOL_DEFINITIONS,     # 7 个工具 schema
       │    │      tool_choice="auto",
       │    │      temperature=0.0,
       │    │      extra_body={"thinking": {"type": "enabled"}}  # DeepSeek 思考模式
       │    │    )
       │    │    → response.choices[0].message
       │    │      .reasoning_content  ← DeepSeek 的内部推理链 (thought)
       │    │      .tool_calls[]       ← LLM 决定的工具调用
       │    │
       │    ├─ [2] 提取 thought:
       │    │    reasoning_content = message.reasoning_content or ""
       │    │
       │    ├─ [3] 判断终止:
       │    │    如果 tool_calls 为空 → agent 产出最终答案 → break
       │    │
       │    └─ [4] 对每个 tool_call:
       │         │
       │         ├─ 解析参数:
       │         │    tool_name = tc.function.name
       │         │    arguments = json.loads(tc.function.arguments)
       │         │
       │         ├─ 分发执行:
       │         │    tools.py: dispatch_tool(db_path, name=tool_name, arguments=arguments)
       │         │    │
       │         │    └─ TOOL_HANDLERS[tool_name](db_path, arguments)
       │         │         │
       │         │         ├─ "get_deck_state"   → services.py: get_deck_state(db_path)
       │         │         │    └─ SELECT * FROM deck WHERE id="deck_1"
       │         │         │    └─ 返回 {id, mode, dry_run, loaded_labware, metadata}
       │         │         │
       │         │         ├─ "get_labware_state" → services.py: get_labware_state(db_path, labware_id)
       │         │         │    └─ SELECT * FROM labware WHERE id = labware_id
       │         │         │    └─ SELECT * FROM wells WHERE labware_id = ? (或 tips)
       │         │         │    └─ 返回 {id, kind, display_name, metadata, wells?, tips?}
       │         │         │
       │         │         ├─ "aspirate"         → services.py: aspirate(db_path, source, volume_ul, tip)
       │         │         │    └─ _parse_well_ref(source) → (labware_id, well_id)
       │         │         │    └─ _parse_well_ref(tip)    → (rack_id, well_id)
       │         │         │    └─ 校验: well 存在、tip 可用、体积 > 0、移液器空闲、源孔体积充足
       │         │         │    └─ UPDATE wells SET volume_ul = 剩余量
       │         │         │    └─ UPDATE tips SET status = "in_use"
       │         │         │    └─ UPDATE pipette_state SET tip, aspirated_volume_ul, source
       │         │         │    └─ 写 audit_log + event ("transfer.aspirated")
       │         │         │    └─ 返回 {source, volume_ul, tip, source_remaining_ul}
       │         │         │
       │         │         ├─ "dispense"         → services.py: dispense(db_path, target, volume_ul, mix_after)
       │         │         │    └─ 校验: 目标 well 存在、移液器有待吸体积、体积不超
       │         │         │    └─ UPDATE wells SET volume_ul = 目标新体积
       │         │         │    └─ UPDATE 或 RESET pipette_state
       │         │         │    └─ INSERT INTO transfers (source, target, volume_ul, tip, mix_after)
       │         │         │    └─ 写 audit_log + event ("transfer.dispensed")
       │         │         │    └─ 返回 {target, volume_ul, target_volume_ul, remaining, mix_after}
       │         │         │
       │         │         ├─ "read_absorbance"  → services.py: read_absorbance(db_path, plate, wavelength_nm, wells)
       │         │         │    └─ 校验: plate 是 plate 类型、wells 非空、well 都存在
       │         │         │    └─ 对每个 well 调用 _read_value(conn, plate, well_id, wavelength_nm)
       │         │         │    │    └─ 查 control_bands + transfers 匹配
       │         │         │    │    └─ 有匹配 → 返回 band.expected_value (0.82)
       │         │         │    │    └─ 无匹配 → 返回 0.0
       │         │         │    └─ INSERT INTO readouts (id, plate, wavelength, wells, values)
       │         │         │    └─ 写 audit_log + event ("readout.created")
       │         │         │    └─ 返回 {readout_id, plate, wavelength_nm, wells, values}
       │         │         │
       │         │         ├─ "add_workflow_note" → services.py: add_workflow_note(db_path, note)
       │         │         │    └─ INSERT INTO workflow_notes (note)
       │         │         │    └─ 写 audit_log + event ("workflow_note.created")
       │         │         │    └─ 返回 {note_id, note}
       │         │         │
       │         │         └─ "submit_protocol"  → services.py: submit_protocol(db_path, decision,
       │         │                                        evidence_readout_id, target_well, rationale)
       │         │              └─ 校验: decision∈{continue,hold}、rationale 非空、well/readout 存在
       │         │              └─ INSERT INTO submissions (decision, evidence_readout_id, target, rationale)
       │         │              └─ 写 audit_log + event ("protocol.submitted")
       │         │              └─ 返回 {submission_id, decision, evidence_readout_id, target_well, rationale}
       │         │
       │         ├─ 记录轨迹:
       │         │    turn_record = {turn, thought, tool_call:{id,name,arguments}, tool_result}
       │         │    turns.append(turn_record)
       │         │    tool_call_log.append({turn, id, name, arguments, result})
       │         │
       │         └─ 追加 tool result 到 messages:
       │              messages.append({"role":"tool", "tool_call_id":tc.id, "content":json.dumps(result)})
       │
       ├─ [循环结束后]
       │    ├─ 如果无 final_answer → 设置 stop_reason="max_turns"
       │    └─ 如果有 final_answer → stop_reason="assistant_final"
       │
       ├─ [运行 Verifier]
       │    verifier.py: verify_run(run_dir)
       │    │
       │    ├─ 读取 run_dir / "run.json" → metadata
       │    ├─ db_path = run_dir / metadata["state_db"]
       │    ├─ state.py: connect(db_path)
       │    │
       │    ├─ _expected_resolution(conn)
       │    │    └─ SELECT payload_json FROM events
       │    │       WHERE event_type="expected_resolution.created" AND visible_to_agent=0
       │    │       ORDER BY id DESC LIMIT 1
       │    │    └─ 返回隐藏的预期结果 payload
       │    │
       │    └─ _verify_plate_transfer_qc(conn, expected)
       │         │
       │         ├─ Check 1: dry_run_no_live_action
       │         │    SELECT * FROM deck WHERE id="deck_1"
       │         │    → deck.dry_run==1 && deck.mode=="dry_run"
       │         │    SELECT COUNT(*) FROM audit_log WHERE action LIKE "live.%" OR object_type="hardware"
       │         │    → count==0 (无真实硬件操作)
       │         │
       │         ├─ Check 2: expected_labware_and_wells_exist
       │         │    → source_plate:A1 存在, assay_plate:B1 存在, tip_rack_1:A1 存在
       │         │
       │         ├─ Check 3: no_overdrawn_well
       │         │    SELECT COUNT(*) FROM wells WHERE volume_ul < 0 → 0
       │         │
       │         ├─ Check 4: valid_transfer_completed
       │         │    SELECT * FROM transfers
       │         │    WHERE source_labware_id="source_plate" AND source_well_id="A1"
       │         │      AND target_labware_id="assay_plate" AND target_well_id="B1"
       │         │      AND volume_ul=50
       │         │    → 存在记录
       │         │
       │         ├─ Check 5: readout_after_dispense
       │         │    _latest_readout_for(conn, "assay_plate", "B1", 600)
       │         │    → readout.values["B1"] == 0.82
       │         │    → transfer.created_at <= readout.created_at
       │         │
       │         ├─ Check 6: protocol_submitted
       │         │    SELECT * FROM submissions ORDER BY id DESC LIMIT 1 → 存在
       │         │
       │         ├─ Check 7: submitted_target_matches_expected
       │         │    → submission.target_labware_id=="assay_plate"
       │         │    → submission.target_well_id=="B1"
       │         │
       │         └─ Check 8: decision_matches_observed_data
       │              → 从 readout 获取 observed_value = 0.82
       │              → 0.75 <= 0.82 <= 0.9 → expected_decision = "continue"
       │              → submission.decision == "continue"
       │              → submission.evidence_readout_id == readout.id
       │
       └─ [写入输出文件]
            ├─ trajectory_{world}_{scenario}_seed{seed}_{timestamp}.json
            ├─ agent_tool_calls.jsonl  (写入 run_dir)
            └─ trajectory_{...}_messages.jsonl
```

### 标准正确路径（8 步工具调用序列）

| 步 | Turn | 工具 | 参数 | services.py 函数 |
|----|------|------|------|-----------------|
| 1 | 1 | `get_deck_state` | `{}` | `get_deck_state(db_path)` |
| 2 | 2 | `get_labware_state` | `{labware_id:"source_plate"}` | `get_labware_state(db_path, "source_plate")` |
| 3 | 2 | `get_labware_state` | `{labware_id:"assay_plate"}` | `get_labware_state(db_path, "assay_plate")` |
| 4 | 2 | `get_labware_state` | `{labware_id:"tip_rack_1"}` | `get_labware_state(db_path, "tip_rack_1")` |
| 5 | 3 | `aspirate` | `{source:"source_plate:A1", volume_ul:50, tip:"tip_rack_1:A1"}` | `aspirate(db_path, "source_plate:A1", 50.0, "tip_rack_1:A1")` |
| 6 | 4 | `dispense` | `{target:"assay_plate:B1", volume_ul:50}` | `dispense(db_path, "assay_plate:B1", 50.0, False)` |
| 7 | 5 | `read_absorbance` | `{plate:"assay_plate", wavelength_nm:600, wells:["B1"]}` | `read_absorbance(db_path, "assay_plate", 600, ["B1"])` |
| 8 | 6 | `submit_protocol` | `{decision:"continue", evidence_readout_id:"ro_...", target_well:"assay_plate:B1", rationale:"..."}` | `submit_protocol(db_path, "continue", "ro_...", "assay_plate:B1", "...")` |

### 各工具操作的数据表变更

| 工具 | 读取的表 | 写入/更新的表 |
|------|---------|-------------|
| `get_deck_state` | `deck` | — |
| `get_labware_state` | `labware`, `wells`, `tips` | — |
| `aspirate` | `wells`, `tips`, `pipette_state` | `wells` (UPDATE volume), `tips` (UPDATE status), `pipette_state` (UPDATE), `audit_log` (INSERT), `events` (INSERT) |
| `dispense` | `wells`, `pipette_state` | `wells` (UPDATE volume), `pipette_state` (UPDATE/RESET), `transfers` (INSERT), `audit_log` (INSERT), `events` (INSERT) |
| `read_absorbance` | `labware`, `wells`, `control_bands`, `transfers` | `readouts` (INSERT), `audit_log` (INSERT), `events` (INSERT) |
| `add_workflow_note` | — | `workflow_notes` (INSERT), `audit_log` (INSERT), `events` (INSERT) |
| `submit_protocol` | `wells`, `readouts`, `submissions` | `submissions` (INSERT), `audit_log` (INSERT), `events` (INSERT) |

### `read_absorbance` 的核心逻辑（`_read_value`）

```
_read_value(conn, plate="assay_plate", well_id="B1", wavelength_nm=600):
  │
  ├─ 查 control_bands:
  │    SELECT * FROM control_bands
  │    WHERE plate_id="assay_plate" AND well_id="B1" AND wavelength_nm=600
  │    → 找到: min=0.75, max=0.9, expected=0.82, required_dispense_ul=50
  │
  ├─ 查 transfers (验证转移量匹配):
  │    SELECT * FROM transfers
  │    WHERE target_labware_id="assay_plate" AND target_well_id="B1"
  │      AND volume_ul=50  (= required_dispense_ul)
  │    ORDER BY id DESC LIMIT 1
  │    → 找到 → 返回 expected_value = 0.82
  │
  └─ 如果无匹配 control_band 或无匹配 transfer → 返回 0.0
```

---

## 阶段四：Session 终验

### CLI 命令

```bash
api-gym session finalize --run runs/plate_qc_trajectory
```

### 调用链

```
cli.py: session_finalize()
  └─ session.py: finalize_world_session(run_dir)
       │
       ├─ registry.py: get_runtime_for_run(run_dir)
       │    └─ read_run_metadata(run_dir)
       │    └─ get_world_runtime("unitelabs_plate_qc_v0")
       │
       ├─ [验证]
       │    runtime.verify_run(run_dir)
       │    └─ verifier.py: verify_run(run_dir)
       │         ├─ 读 run.json → db_path
       │         ├─ connect(db_path)
       │         ├─ _expected_resolution(conn) → hidden payload
       │         └─ _verify_plate_transfer_qc(conn, expected)
       │              └─ 8 项检查 (同阶段三末尾)
       │              └─ 返回 VerificationResult(ok, scenario, checks[])
       │
       ├─ [导出]
       │    exports/run_export.py: write_run_export(run_dir, run_dir / "run_export.json")
       │    └─ build_run_export(run_dir)
       │         ├─ 读取 task.json
       │         ├─ 读取 agent_tool_calls.jsonl (agent 工具调用轨迹)
       │         ├─ 再次调用 runtime.verify_run(run_dir)
       │         └─ 返回 {
       │              schema_version: "api_gym.run_export.v0",
       │              world, world_id, scenario, seed, run_dir,
       │              task, tool_trace, verifier_result,
       │              artifacts: {run_metadata, task, tool_trace}
       │            }
       │
       └─ [写终验结果]
            写 session_finalization.json:
            {
              "schema_version": "api_gym.world_session_finalization.v0",
              "ok": true/false,
              "world": "unitelabs_plate_qc_v0",
              "world_id": "unitelabs-plate-qc-v0",
              "scenario": "plate_transfer_qc",
              "seed": 42,
              "run_dir": "...",
              "verifier_result": {
                "ok": true/false,
                "scenario": "plate_transfer_qc",
                "checks": [
                  {"ok": true, "name": "dry_run_no_live_action", "message": "..."},
                  {"ok": true, "name": "expected_labware_and_wells_exist", "message": "..."},
                  {"ok": true, "name": "no_overdrawn_well", "message": "..."},
                  {"ok": true, "name": "valid_transfer_completed", "message": "..."},
                  {"ok": true, "name": "readout_after_dispense", "message": "..."},
                  {"ok": true, "name": "protocol_submitted", "message": "..."},
                  {"ok": true, "name": "submitted_target_matches_expected", "message": "..."},
                  {"ok": true, "name": "decision_matches_observed_data", "message": "..."}
                ]
              },
              "export_path": ".../run_export.json",
              "export": {...}
            }
```

---

## 阶段五（可选）：单独验证

### CLI 命令

```bash
api-gym verify --run runs/plate_qc_trajectory
```

### 调用链

```
cli.py: verify()
  ├─ registry.py: get_runtime_for_run(run)
  │    └─ read_run_metadata(run)
  │    └─ get_world_runtime("unitelabs_plate_qc_v0")
  │
  └─ runtime.verify_run(run)
       └─ verifier.py: verify_run(run_dir)
            ├─ 读 run.json → db_path
            ├─ connect(db_path)
            ├─ _expected_resolution(conn)
            └─ _verify_plate_transfer_qc(conn, expected)
                 └─ 8 项检查
                 └─ VerificationResult.to_dict()
```

---

## 阶段六（可选）：单独导出证据

### CLI 命令

```bash
api-gym export --run runs/plate_qc_trajectory --out runs/plate_qc_trajectory/run_export.json
```

### 调用链

```
cli.py: export_run()
  └─ exports/run_export.py: write_run_export(run_dir, out)
       └─ build_run_export(run_dir)
            ├─ get_runtime_for_run(run_dir)
            ├─ read_run_metadata(run_dir)
            ├─ 读 task.json
            ├─ 读 agent_tool_calls.jsonl (如果存在)
            ├─ runtime.verify_run(run_dir)
            └─ 返回 {schema_version, world, scenario, seed, task, tool_trace, verifier_result, artifacts}
```

---

## 完整文件产出矩阵

```
runs/plate_qc_trajectory/
  ├── state.sqlite              ← [阶段一] SQLite 状态数据库
  ├── task.json                 ← [阶段一] agent 任务文件
  ├── run.json                  ← [阶段一] 运行元数据
  ├── agent_task.json           ← [阶段一] agent host 任务包
  ├── session_manifest.json     ← [阶段一] 会话清单
  ├── agent_tool_calls.jsonl    ← [阶段三] agent 工具调用轨迹
  ├── run_export.json           ← [阶段四] 运行证据导出
  └── session_finalization.json ← [阶段四] 终验结果

gen_trajectory/output/
  ├── trajectory_{...}.json              ← [阶段三] 完整轨迹
  └── trajectory_{...}_messages.jsonl    ← [阶段三] LLM 消息历史
```

---

## 关键函数速查表

### 状态层 (state.py)

| 函数 | 作用 | 被调用阶段 |
|------|------|----------|
| `initialize_db(db_path)` | 执行 SCHEMA_SQL 创建所有表 | 阶段一 |
| `connect(db_path)` | 打开 SQLite 连接 (row_factory=Row, foreign_keys=ON) | 全部 |
| `resolve_state_db_path(run_dir)` | 从 run.json 解析 state.sqlite 路径 | 二～六 |
| `insert_event(conn, ...)` | 插入事件 (含可见性控制) | 一、三 |
| `insert_audit(conn, ...)` | 插入审计日志 | 三 |
| `dumps_json(value)` | 紧凑 JSON 序列化 | 一、三 |
| `loads_json(value)` | JSON 反序列化 | 二～六 |
| `row_to_dict(row)` | sqlite3.Row → dict (展开 _json 字段) | (verifier 隐式) |

### 采样层 (sampler.py)

| 函数 | 作用 | 被调用阶段 |
|------|------|----------|
| `sample_episode(scenario, seed, out_dir)` | 创建完整 SQLite episode | 阶段一 |
| `_build_plate_transfer_qc(db_path, seed)` | plate_transfer_qc 场景采样 | 阶段一 |

### 服务层 (services.py)

| 函数 | 作用 | 被调用阶段 |
|------|------|----------|
| `get_deck_state(db_path)` | 读取 deck 状态 | 阶段三 |
| `get_labware_state(db_path, labware_id)` | 读取 labware + wells/tips | 阶段三 |
| `aspirate(db_path, source, volume_ul, tip)` | 干式吸液（校验 + 状态变更） | 阶段三 |
| `dispense(db_path, target, volume_ul, mix_after)` | 干式排液（校验 + 状态变更 + 写 transfer） | 阶段三 |
| `read_absorbance(db_path, plate, wavelength_nm, wells)` | 读吸光度（匹配 control_band + 写 readout） | 阶段三 |
| `add_workflow_note(db_path, note)` | 添加工作流笔记 | 阶段三 |
| `submit_protocol(db_path, decision, evidence_readout_id, target_well, rationale)` | 提交协议决策 | 阶段三 |

### 工具层 (tools.py)

| 函数 | 作用 | 被调用阶段 |
|------|------|----------|
| `dispatch_tool(db_path, name, arguments)` | 按名称分发到对应 handler | 阶段三 |
| `dispatch_tool_call(db_path, tool_call)` | 从 OpenAI tool_call 格式分发 | (billing world 用) |
| `TOOL_DEFINITIONS` (常量) | 7 个 OpenAI function schema | 阶段二、三 |
| `TOOL_HANDLERS` (常量) | 7 个 handler 映射表 | 阶段三 |

### 验证层 (verifier.py)

| 函数 | 作用 | 被调用阶段 |
|------|------|----------|
| `verify_run(run_dir)` | 主验证入口 → 返回 VerificationResult | 阶段三、四、五、六 |
| `_verify_plate_transfer_qc(conn, expected)` | 8 项专项检查 | 阶段三、四、五 |
| `_expected_resolution(conn)` | 读取 hidden event | 阶段三、四、五 |
| `_latest_readout_for(conn, plate, well, wavelength_nm)` | 查找最近匹配读数 | 阶段三、四、五 |

### Trajectory Runner (trajectory_runner.py)

| 函数 | 作用 | 被调用阶段 |
|------|------|----------|
| `run_trajectory(run_dir, output_dir)` | 主循环：LLM 调用 → 工具分发 → 轨迹记录 → 验证 | 阶段三 |
| `_flatten_tools_for_deepseek(tool_defs)` | 工具 schema 格式化 | 阶段三 |
| `_make_tool_message(tool_call_id, result)` | 构建 tool role message | 阶段三 |

### Registry (registry.py)

| 函数 | 作用 | 被调用阶段 |
|------|------|----------|
| `get_world_runtime(world)` | world 名 → WorldRuntime | 全部 |
| `get_runtime_for_run(run_dir)` | run_dir → 读 run.json → WorldRuntime | 全部 |
| `read_run_metadata(run_dir)` | 读 run.json | 全部 |
| `_runtime_from_package(world, package, mcp_server_title)` | 动态导入 world 模块组装 WorldRuntime | 阶段一 |

### Agent Harness (agent_harness.py)

| 函数/类 | 作用 | 被调用阶段 |
|---------|------|----------|
| `build_agent_task_package(run_dir)` | 构建 agent 任务包 | 阶段一 |
| `write_agent_task_package(run_dir, out)` | 写 agent_task.json | 阶段一 |
| `create_mcp_handler(run_dir)` → `ApiGymMcpHandler` | MCP 协议处理器 | 阶段二 |
| `ApiGymMcpHandler.handle_message(msg)` | MCP JSON-RPC 消息分发 | 阶段二 |
| `serve_mcp_stdio(run_dir)` | MCP stdio 服务 | (agent host 模式) |

### Session 层 (session.py)

| 函数 | 作用 | 被调用阶段 |
|------|------|----------|
| `create_world_session(world, scenario, seed, out_dir)` | 采样 + 写 manifest | 阶段一 |
| `build_session_manifest(run_dir)` | 构建会话清单 | 阶段一 |
| `check_session_tools(run_dir)` | MCP 工具目录验证 | 阶段二 |
| `finalize_world_session(run_dir)` | 验证 + 导出 + 写终验 | 阶段四 |

---

## 完整 shell 执行脚本

```bash
# 0. 环境准备
cd E:\Users\wyd\Documents\python_project\env_rollout\unitelabs-api-grounding
pip install -e .

# 1. 采样初始状态
api-gym session create \
  --world unitelabs_plate_qc_v0 \
  --scenario plate_transfer_qc \
  --seed 42 \
  --out runs/plate_qc_trajectory

# 2. 预检工具目录
api-gym session check-tools --run runs/plate_qc_trajectory

# 3. LLM agent 执行 (需设置 DEEPSEEK_API_KEY 环境变量)
set DEEPSEEK_API_KEY=sk-...
python gen_trajectory/trajectory_runner.py \
  --run runs/plate_qc_trajectory \
  --output gen_trajectory/output

# 4. 终验
api-gym session finalize --run runs/plate_qc_trajectory

# 5. (可选) 单独验证
api-gym verify --run runs/plate_qc_trajectory

# 6. (可选) 单独导出
api-gym export --run runs/plate_qc_trajectory --out runs/plate_qc_trajectory/run_export.json
```
