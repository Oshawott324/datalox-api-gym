# UniteLabs Plate QC v0 — Trajectory Demo

网页化展示 `unitelabs_plate_qc_v0` 的 LLM agent 轨迹生成全流程。

## 启动

```bash
cd E:\Users\wyd\Documents\python_project\env_rollout\unitelabs-api-grounding
python gen_trajectory/demo/server.py
```

浏览器打开 **`http://127.0.0.1:8080`**。

> API Key 已内置在代码中，无需额外设置环境变量。

## 目录结构

```
gen_trajectory/demo/
  ├── README.md              ← 本文件
  ├── IMPLEMENTATION_PLAN.md ← 实施方案
  ├── server.py              ← FastAPI 后端
  └── static/
        └── index.html       ← 前端页面
```

## 操作流程

### Stage 1 — Start

1. 在 **Seed** 输入框填写采样种子（默认 42）
2. 点击 **▶ Start**
3. 展开 Stage 1 查看：
   - 任务 Prompt
   - 初始 SQLite 状态（12 张表，点击可展开）

### Stage 2 — Check Tools

1. 点击 **🔍 Check Tools**
2. 验证结果：确认 7 个工具全部列出、无缺失
3. 查看每个工具的名称、描述、参数 schema

### Stage 3 — LLM Agent Execution

- **⏭ Run Next**：执行一次 LLM turn（模型自主决定调用哪些工具）。每次 turn 可能包含多个 tool call
- **⏩ Run All**：一次性跑完所有 turn，直到 agent 产出最终答案
- 时间线展示：每步显示工具名、参数、结果、SQLite 状态变更

> 标准流程约 6-7 个 LLM turn，8 个 tool call，30 秒内完成。

### Stage 4 — Finalize

1. 点击 **✅ Finalize**（Run All 会自动触发）
2. 查看 8 项 Verifier 检查结果（全部 PASS 即为正确完成）

## API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/demo/start` | POST | 创建 session，参数 `{"seed": 42}` |
| `/api/demo/check-tools` | POST | 验证 MCP 工具 |
| `/api/demo/run-step` | POST | 执行一次 LLM turn |
| `/api/demo/run-all` | POST | 执行全部 turn + 自动终验 |
| `/api/demo/finalize` | POST | 终验 + 导出 |
| `/api/demo/state` | GET | 查看当前 SQLite 状态 |
| `/api/demo/trajectory` | GET | 查看累积轨迹 |
| `/api/demo/messages` | GET | Debug：查看 LLM 对话消息 |
| `/api/demo/health` | GET | 健康检查 |

## 技术栈

- **LLM**: DeepSeek v4-pro（thinking mode enabled）
- **后端**: FastAPI + Uvicorn
- **前端**: 纯 HTML/CSS/JS，零外部依赖
- **状态**: SQLite（每次 Start 创建独立临时数据库）
