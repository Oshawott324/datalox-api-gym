# Unitelabs Plate QC v0 轨迹生成 Web Demo 实施方案

## Context

用户需要一个网页 demo，将 `unitelabs_plate_qc_v0` 的完整轨迹生成流程（session create → check-tools → agent execution → finalize）以可视化方式展示。需要交互式操作（设置 seed、逐步执行、查看状态变化）。

## 总体架构

```
┌──────────────────────────────────────────────────────────────┐
│                    浏览器 (Frontend)                           │
│  gen_trajectory/demo/static/index.html                       │
│  - 控制面板（seed 输入、阶段按钮）                              │
│  - 阶段进度条（4 阶段）                                        │
│  - 工具调用可视化（8 步，含参数/结果/SQL 变更）                  │
│  - SQLite 状态面板（表格展示）                                  │
│  - Verifier 检查结果（8 项）                                    │
└─────────────┬──────────────────────────────────────────────┘
              │ HTTP JSON API
┌─────────────▼──────────────────────────────────────────────┐
│              后端 (FastAPI Server)                             │
│  gen_trajectory/demo/server.py                                │
│  - POST /api/demo/start       创建 session                   │
│  - POST /api/demo/check-tools 验证工具                        │
│  - POST /api/demo/run-step    执行一步 oracle                 │
│  - POST /api/demo/run-all     执行全部 oracle 步骤             │
│  - POST /api/demo/finalize    终验 + 导出                     │
│  - GET  /api/demo/state       查看当前 SQLite 状态             │
│  - GET  /api/demo/trajectory  查看完整轨迹                     │
│  - GET  /                         静态页面                      │
└─────────────┬──────────────────────────────────────────────┘
              │ 直接调用
┌─────────────▼──────────────────────────────────────────────┐
│              现有模块 (只读复用)                                 │
│  api_gym.worlds.unitelabs_plate_qc_v0.sampler               │
│  api_gym.worlds.unitelabs_plate_qc_v0.services               │
│  api_gym.worlds.unitelabs_plate_qc_v0.tools                  │
│  api_gym.worlds.unitelabs_plate_qc_v0.verifier               │
│  api_gym.worlds.unitelabs_plate_qc_v0.state                  │
│  api_gym.session (create_world_session, finalize)             │
│  api_gym.exports.run_export (write_run_export)                │
└──────────────────────────────────────────────────────────────┘
```

## 目录结构

```
gen_trajectory/demo/
  ├── IMPLEMENTATION_PLAN.md   ← 本文件
  ├── server.py                ← FastAPI 后端
  └── static/
        └── index.html         ← 前端页面 (HTML + CSS + JS)
```

## 新建文件

### 1. `gen_trajectory/demo/server.py` — FastAPI 后端

- 启动一个 Uvicorn 服务，同时提供 API 端点 + 静态页面
- 维护一个 `DemoSession` 对象，封装当前 run_dir、db_path、tool call 历史、state snapshots
- API 端点：

| 端点 | 功能 | 调用的现有函数 |
|------|------|-------------|
| `POST /api/demo/start` | 采样 episode | `sampler.sample_episode()`, `session.build_session_manifest()` |
| `POST /api/demo/check-tools` | 验证 MCP 工具 | `session.check_session_tools()` |
| `POST /api/demo/run-step` | 执行一步 oracle | `tools.dispatch_tool()` + 状态快照 |
| `POST /api/demo/run-all` | 一键执行全部 | 循环 `tools.dispatch_tool()` |
| `POST /api/demo/finalize` | 验证 + 导出 | `session.finalize_world_session()` |
| `GET /api/demo/state` | 读取 SQLite 全部表 | `state.connect()` + 遍历所有表 |
| `GET /api/demo/trajectory` | 返回累积轨迹 | 内存中的 trajectory 对象 |

#### Oracle 步骤序列（硬编码在 server.py 中）

```python
ORACLE_STEPS = [
    {
        "name": "get_deck_state",
        "arguments": {},
        "thought": "先检查 deck 状态，了解有哪些 labware 加载在干式运行 deck 上。"
    },
    {
        "name": "get_labware_state",
        "arguments": {"labware_id": "source_plate"},
        "thought": "检查源板（source_plate）的孔内容、体积和元数据。"
    },
    {
        "name": "get_labware_state",
        "arguments": {"labware_id": "assay_plate"},
        "thought": "检查检测板（assay_plate）——确认目标孔 B1 是空的，体积为 0。"
    },
    {
        "name": "get_labware_state",
        "arguments": {"labware_id": "tip_rack_1"},
        "thought": "检查枪头架，确认 A1 位置的枪头可用。"
    },
    {
        "name": "aspirate",
        "arguments": {"source": "source_plate:A1", "volume_ul": 50, "tip": "tip_rack_1:A1"},
        "thought": "从源板 A1 孔吸取 50µL QC 对照样品，使用 tip_rack_1 的 A1 枪头。"
    },
    {
        "name": "dispense",
        "arguments": {"target": "assay_plate:B1", "volume_ul": 50},
        "thought": "将 50µL 样品排入检测板的 B1 孔。完成后移液器回到空闲状态。"
    },
    {
        "name": "read_absorbance",
        "arguments": {"plate": "assay_plate", "wavelength_nm": 600, "wells": ["B1"]},
        "thought": "读取检测板 B1 孔在 600nm (OD600) 波长下的吸光度。这是 plate QC 的标准波长。"
    },
    {
        "name": "submit_protocol",
        "arguments": {
            "decision": "continue",
            "evidence_readout_id": "<从第 7 步结果动态获取>",
            "target_well": "assay_plate:B1",
            "rationale": "OD600 读数为 0.82，位于控制带 [0.75, 0.9] 范围内，QC 通过，建议继续工作流。"
        },
        "thought": "根据 OD600 读数 0.82 在控制带 [0.75, 0.9] 范围内，提交 'continue' 决策。"
    },
]
```

- `submit_protocol` 的 `evidence_readout_id` 需动态注入：第 7 步返回的 `result["data"]["readout_id"]`。

#### SQLite 状态快照

```python
def snapshot_state(db_path: Path) -> dict:
    """读取所有表的所有行，返回 {table_name: [row_dict, ...]}"""
    tables = [
        "deck", "labware", "wells", "tips", "pipette_state",
        "control_bands", "transfers", "readouts", "workflow_notes",
        "submissions", "events", "audit_log"
    ]
    with connect(db_path) as conn:
        return {
            table: [row_to_dict(row) for row in conn.execute(f"SELECT * FROM {table}")]
            for table in tables
        }
```

#### DemoSession 类设计

```python
class DemoSession:
    run_dir: Path          # 当前 run 目录
    db_path: Path          # state.sqlite 路径
    step_index: int        # 当前 oracle 步骤索引 (0-7)
    tool_history: list     # 已执行的工具调用记录
    state_snapshots: list  # 每次工具调用前的状态快照
    trajectory: dict       # 累积的轨迹数据
```

### 2. `gen_trajectory/demo/static/index.html` — 前端页面

纯静态单页，CSS + JS 全部内嵌，零外部依赖。

**布局设计（4 区域）：**

```
┌─────────────────────────────────────────────────────────┐
│  🧪 UniteLabs Plate QC v0 — Trajectory Demo            │
│  [Seed: 42] [Start] [Check Tools] [▶ Run All] [Finalize]│
│  ● Stage 1 ──● Stage 2 ──○ Stage 3 ──○ Stage 4         │
└─────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────┐
│                                                         │
│  [主内容区 — 根据当前阶段动态切换]                          │
│                                                         │
│  Stage 1: SQLite 初始状态 (12 张表折叠面板) + task prompt  │
│  Stage 2: 7 个工具定义卡片 + check-tools 验证结果          │
│  Stage 3: 工具调用时间线 (逐步/一键) + 执行中的状态变化      │
│  Stage 4: 8 项 Verifier 检查 + run_export 摘要            │
│                                                         │
└─────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────┐
│  Status: Stage 3 — Step 5/8 | Total tool calls: 5       │
└─────────────────────────────────────────────────────────┘
```

**Stage 3 工具调用卡片样式：**

```
  ○ get_deck_state ─────── ✓ ok
  │
  ○ get_labware_state ──── ✓ ok  (source_plate)
  │
  ○ get_labware_state ──── ✓ ok  (assay_plate)
  │
  ○ get_labware_state ──── ✓ ok  (tip_rack_1)
  │
  ○ aspirate ───────────── ✓ ok  (50µL)
  │
  ● dispense ───────────── ⟳ executing...
  │
  ○ read_absorbance ────── pending
  │
  ○ submit_protocol ────── pending
```

**深色主题配色：**
- 背景: `#0d1117` (GitHub dark)
- 卡片: `#161b22`
- 边框: `#30363d`
- 主色: `#58a6ff` (蓝)
- 通过: `#3fb950` (绿)
- 失败: `#f85149` (红)
- 文字: `#c9d1d9`

## 实施步骤

### Step 1: 创建 `server.py`
- 实现 `DemoSession` 类
- 实现 7 个 API 端点
- 内嵌 8 步 oracle 序列 + 动态 readout_id 注入
- 实现 `snapshot_state()` 全表快照
- FastAPI 静态文件挂载

### Step 2: 创建 `static/index.html`
- HTML 结构（控制栏、阶段指示器、主内容区、状态栏）
- CSS（深色主题、时间线、卡片、表格样式）
- JS 逻辑：
  - `apiCall(endpoint, method, body)` — 通用 Fetch 封装
  - `startSession(seed)` — POST /api/demo/start
  - `checkTools()` — POST /api/demo/check-tools
  - `runNextStep()` — POST /api/demo/run-step
  - `runAllSteps()` — POST /api/demo/run-all
  - `finalizeSession()` — POST /api/demo/finalize
  - `renderStage1/2/3/4()` — 各阶段渲染
  - `renderTimeline()` — 工具调用时间线
  - `renderStateTables()` — SQLite 状态表格
  - `renderVerifierChecks()` — Verifier 检查结果

### Step 3: 测试
- 启动 demo server：`python gen_trajectory/demo/server.py`
- 浏览器打开 `http://127.0.0.1:8080`
- 用 seed=42 跑完整流程，确认 8 项 verifier 全部通过
- 换 seed=99 再跑一次确认仍通过

## 可复用的现有函数

| 函数 | 路径 | 用途 |
|------|------|------|
| `sample_episode()` | `api_gym.worlds.unitelabs_plate_qc_v0.sampler` | 采样 episode |
| `dispatch_tool()` | `api_gym.worlds.unitelabs_plate_qc_v0.tools` | 分发单步工具调用 |
| `verify_run()` | `api_gym.worlds.unitelabs_plate_qc_v0.verifier` | 运行 8 项检查 |
| `connect()` / `row_to_dict()` | `api_gym.worlds.unitelabs_plate_qc_v0.state` | SQLite 连接和行解析 |
| `write_run_export()` | `api_gym.exports.run_export` | 导出 run 证据 |
| `build_session_manifest()` | `api_gym.session` | 构建 session manifest |
| `check_session_tools()` | `api_gym.session` | 验证 MCP 工具 |
| `finalize_world_session()` | `api_gym.session` | 终验 + 导出 |

## 验证方式

```bash
cd E:\Users\wyd\Documents\python_project\env_rollout\unitelabs-api-grounding

# 启动 demo server
python gen_trajectory/demo/server.py

# 浏览器打开 http://127.0.0.1:8080
# 1. 在 seed 输入框输入 42，点击 "Start"
# 2. 查看 Stage 1 的初始 SQLite 状态（可展开每张表）
# 3. 点击 "Check Tools"，确认 7 个工具全部列出
# 4. 点击 "逐步执行"，观察每步工具调用和 SQLite 变化
#    或者点击 "▶ Run All" 一次性执行全部 8 步
# 5. 点击 "Finalize"，确认 8 项 verifier 全部绿色通过
```

## 不做的

- 不集成到 CLI (`api-gym demo`) — 保持独立脚本，降低耦合
- 不实时连接 LLM — 使用 oracle 保证 demo 稳定可复现
- 不做用户认证/多用户支持 — 单用户本地 demo
- 不引入外部前端框架/构建工具 — 纯 HTML+CSS+JS，零依赖
