# Quickstart

Install the package in editable mode and run the tests:

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
```

Run a billing-support episode through the local surfaces:

```bash
api-gym sample --world billing_support_v0 --scenario duplicate_payment_refund --seed 1 --out runs/demo
api-gym task --run runs/demo --out runs/demo/agent_task.json
api-gym serve --run runs/demo --port 8080
api-gym resolve --run runs/demo --policy oracle
api-gym verify --run runs/demo
api-gym run --run runs/demo --model qwen --base-url http://localhost:8000/v1 --api-key EMPTY
```

The run directory contains:

- `state.sqlite`: per-run SQLite state
- `task.json`: agent-visible task prompt
- `run.json`: world/scenario/seed metadata

The verifier checks SQLite state, not transcript text.

## Real Agent Host Workflow

Use Phase 4 when an agent host such as Codex, Claude Code, OpenHands, or a
local runner should solve the sampled run through tools:

```bash
api-gym sample --world billing_support_v0 --scenario duplicate_payment_refund --seed 1 --out runs/demo
api-gym task --run runs/demo --out runs/demo/agent_task.json
```

Give the host the `agent_facing_instructions` from `agent_task.json` and
configure its MCP client with `recommended_mcp_config`. The MCP server command
inside that config is:

```bash
api-gym mcp --run runs/demo
```

The task package rule is explicit: the host must use tools for state inspection
and mutation, and must not answer from text alone.

For a generic host command, let API Gym set the run environment and verify after
the host exits:

```bash
api-gym run-host --run runs/demo -- <agent-host-command>
api-gym verify --run runs/demo
```

`run-host` exports `API_GYM_RUN_DIR`, `API_GYM_TASK_JSON`,
`API_GYM_MCP_COMMAND`, and `API_GYM_VERIFY_COMMAND`, then writes
`runs/demo/host_result.json`. MCP tool calls are recorded in
`runs/demo/agent_tool_calls.jsonl`.

## Optional Live Eval Smoke

Start a cheap local OpenAI-compatible server before running live eval:

```bash
export OPENAI_BASE_URL=http://127.0.0.1:8000/v1
export OPENAI_API_KEY=EMPTY

api-gym eval \
  --world billing_support_v0 \
  --scenarios duplicate_payment_refund,failed_invoice_retryable,refund_not_allowed_policy \
  --seeds 1,2,3 \
  --model Qwen/Qwen2.5-7B-Instruct \
  --base-url "$OPENAI_BASE_URL" \
  --api-key "$OPENAI_API_KEY" \
  --out runs/billing-eval.jsonl

api-gym report --input runs/billing-eval.jsonl
```

Live eval is opt-in. The command records one JSONL row per sampled task and
does not fail the process just because a model fails a verifier.
