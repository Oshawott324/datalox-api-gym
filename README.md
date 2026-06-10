# Datalox API Gym

Datalox API Gym provides resettable fake APIs for training and evaluating
tool-using agents.

The product object is an API world: a stateful fake business system with seeded
scenarios, model-visible tool contracts, side effects, hidden verifier state,
and exportable run evidence. Agents can practice workflows repeatedly without
touching production services.

Datalox API Gym is not an API aggregator. Aggregators connect agents to real
APIs. API Gym gives agents resettable practice worlds for API workflows.

Datalox API Gym is also not a replacement for official provider sandboxes.
Provider sandboxes are useful for integration testing against a provider's own
surface. API Gym focuses on agent training and evaluation: sampled tasks,
per-episode reset, cross-service fake APIs, hidden verifiers, replay evidence,
and compact training/eval exports.

Phase 1 implements the first concrete world:

```text
billing_support_v0
  fake_billing_api
  fake_support_api
  fake_crm_api
  fake_email_api
```

The world uses one SQLite database per sampled run. The first scenarios are:

- `duplicate_payment_refund`
- `failed_invoice_retryable`
- `refund_not_allowed_policy`

The operation-level reality map is documented at
`worlds/billing_support_v0/reality-map.md`.

## Quickstart

```bash
python -m pip install -e '.[dev]'
api-gym sample --world billing_support_v0 --scenario duplicate_payment_refund --seed 1 --out runs/demo
api-gym task --run runs/demo --out runs/demo/agent_task.json
api-gym serve --run runs/demo --port 8080
api-gym resolve --run runs/demo --policy oracle
api-gym verify --run runs/demo
api-gym run --run runs/demo --model qwen --base-url http://localhost:8000/v1 --api-key EMPTY
api-gym run-host --run runs/demo -- <agent-host-command>
api-gym eval --world billing_support_v0 --scenarios duplicate_payment_refund,failed_invoice_retryable,refund_not_allowed_policy --seeds 1,2,3 --model qwen --base-url http://localhost:8000/v1 --api-key EMPTY --out runs/billing-eval.jsonl
api-gym report --input runs/billing-eval.jsonl
python -m pytest -q
```

`sample` writes `runs/demo/state.sqlite`, `runs/demo/task.json`, and
`runs/demo/run.json`. The prompt in `task.json` is agent-visible. The expected
resolution is hidden in SQLite verifier state.

The fake service operations are Python functions under
`api_gym.worlds.billing_support_v0.services`. They expose support ticket
updates, invoice retries, payment lookup, and refund creation with structured
`ok/data` or `ok/error` responses for agents.

Phase 2 exposes the same causal service functions through:

- FastAPI endpoints served by `api-gym serve`
- OpenAI-compatible function schemas in
  `api_gym.worlds.billing_support_v0.tools`
- a scripted oracle resolver via `api-gym resolve --policy oracle`
- an OpenAI-compatible runner via `api-gym run`
- an OpenAI-compatible eval suite via `api-gym eval` and `api-gym report`

Phase 4 adds an agent-host harness for real tool-using hosts such as coding
agents and local agent runners:

- `api-gym task --run runs/demo` prints an agent-facing task package with the
  task instructions, world/scenario metadata, verifier command, and recommended
  MCP stdio config.
- `api-gym mcp --run runs/demo` serves the billing-support tools over MCP
  stdio for one sampled run. Hosts should launch this command from their MCP
  configuration; it is a protocol server, not an interactive shell.
- `api-gym run-host --run runs/demo -- <agent-host-command>` sets
  `API_GYM_RUN_DIR`, `API_GYM_TASK_JSON`, `API_GYM_MCP_COMMAND`, and
  `API_GYM_VERIFY_COMMAND`, executes the host command, then runs the verifier
  and writes `runs/demo/host_result.json`.

The real-agent workflow is:

```bash
api-gym sample --world billing_support_v0 --scenario duplicate_payment_refund --seed 1 --out runs/demo
api-gym task --run runs/demo --out runs/demo/agent_task.json

# Configure the agent host with the recommended_mcp_config from agent_task.json.
# The host should use tools for state inspection and mutation, not answer from text alone.
api-gym run-host --run runs/demo -- <agent-host-command>

api-gym verify --run runs/demo
```

MCP tool calls append `runs/demo/agent_tool_calls.jsonl` with timestamp, tool
name, arguments, and result. Hidden verifier state is not exposed through MCP.

## Optional Live Model Smoke

Live model eval is opt-in. Start a cheap local OpenAI-compatible server first,
then point API Gym at it:

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

The eval command samples fresh SQLite-backed runs and uses the same
OpenAI-compatible runner and tool dispatcher as `api-gym run`. Failed model
tasks are recorded as `passed: false` rows; the command exits nonzero only for
infrastructure failures such as invalid inputs or an unreachable endpoint.

## Layout

```text
api_gym/                 Python package surfaces
worlds/                  World specs, tasks, seeds, and policies
tests/                   Smoke tests
website/                 VitePress documentation scaffold
```

## Public API Inspiration

Billing behavior is intentionally narrow but grounded in public provider
patterns:

- Stripe refund creation requires a charge or PaymentIntent and only refunds
  the remaining unrefunded amount; refund reasons include `duplicate` and
  `requested_by_customer`: https://docs.stripe.com/api/refunds/create
- Stripe Billing models failed invoice retries with invoice payment attempts,
  `attempt_count`, `next_payment_attempt`, and hard decline handling:
  https://docs.stripe.com/billing/revenue-recovery/smart-retries
- Zendesk ticket updates combine comments, status changes, and tags:
  https://developer.zendesk.com/api-reference/ticketing/tickets/tickets/
  and ticket comments can be public or private:
  https://developer.zendesk.com/api-reference/ticketing/tickets/ticket_comments/
