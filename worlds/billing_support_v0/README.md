# Billing Support v0

`billing_support_v0` is a deterministic API Gym world for billing-support
workflows. It models correlated billing, support, CRM, and email state in one
SQLite database per run.

The goal is not an endpoint catalog or a Stripe/Zendesk clone. The goal is a
small stateful action system where agents inspect business state, perform
deterministic side effects, and get verified against hidden world state.

## World Contract

Source substrate:

- public Stripe refund and invoice retry documentation
- public Zendesk ticket and comment documentation
- optional provider probes recorded under `evidence/`

Episode state:

- `state.sqlite` per sampled run
- customers, accounts, subscriptions, invoices, payments, refunds
- tickets, ticket messages, emails, events, policies, audit log

Actions:

- inspect customers, invoices, payments, and tickets
- create refunds
- retry invoices
- add ticket replies
- close, tag, or escalate tickets

Dynamics:

- deterministic Python service functions in
  `api_gym.worlds.billing_support_v0.services`
- SQLite mutations with auditable events

Observations:

- structured tool responses
- structured errors for invalid business actions
- tool trace rows in `agent_tool_calls.jsonl`

Verifier:

- reads final SQLite state
- checks the scenario-specific expected resolution
- does not trust transcript text as proof

Evidence:

- `run.json`
- `task.json`
- `agent_task.json`
- `agent_tool_calls.jsonl`
- `verifier_result.json` when written by verifier commands
- `run_export.json` when exported or finalized

## Scenarios

- `duplicate_payment_refund`: a paid invoice has one legitimate card payment
  and one duplicate extra payment. The agent must refund the duplicate payment
  only and publicly reply to the support ticket.
- `failed_invoice_retryable`: a subscription invoice failed with a retryable
  decline. The agent must retry the invoice, record the successful payment
  state, reply, and solve the ticket.
- `refund_not_allowed_policy`: an old paid invoice is outside the configured
  refund window. The agent must not create a refund and must explain policy or
  escalate the ticket for billing review.

## Session Handoff

Create one local session:

```bash
api-gym session create \
  --world billing_support_v0 \
  --scenario duplicate_payment_refund \
  --seed 1 \
  --out runs/billing-demo \
  --json
```

The session manifest is the integration contract. It contains:

- `task` and `task_instructions` for the agent
- `mcp` config for the tool server
- `expected_tools` for preflight validation
- `commands.check_tools`
- `commands.finalize`
- artifact paths for task, trace, export, and finalization output

Before rollout:

```bash
api-gym session check-tools --run runs/billing-demo
```

After the agent stops:

```bash
api-gym session finalize --run runs/billing-demo --json
```

Finalize runs the verifier and writes `run_export.json`.

## Manual Debug Path

The lower-level flow is useful while editing the world:

```bash
api-gym sample --world billing_support_v0 --scenario duplicate_payment_refund --seed 1 --out runs/demo
api-gym task --run runs/demo --out runs/demo/agent_task.json
api-gym mcp --run runs/demo
api-gym verify --run runs/demo
api-gym export --run runs/demo --out runs/demo/run_export.json
```

Billing-only debug helpers:

```bash
api-gym serve --run runs/demo --port 8080
api-gym resolve --run runs/demo --policy oracle
api-gym run --run runs/demo --model qwen --base-url http://localhost:8000/v1 --api-key EMPTY
```

## Public API Grounding

The world intentionally follows public provider patterns without copying full
provider APIs:

- Stripe refund creation requires a charge or PaymentIntent, caps refunds to
  the remaining unrefunded amount, and supports reasons such as `duplicate` and
  `requested_by_customer`: https://docs.stripe.com/api/refunds/create
- Stripe invoice retry behavior includes failed payment attempts,
  `attempt_count`, `next_payment_attempt`, and hard decline handling:
  https://docs.stripe.com/billing/revenue-recovery/smart-retries
- Zendesk ticket updates can change comments, statuses, tags, assignees, and
  priorities:
  https://developer.zendesk.com/api-reference/ticketing/tickets/tickets/
- Zendesk ticket comments may be public or private:
  https://developer.zendesk.com/api-reference/ticketing/tickets/ticket_comments/

See [reality-map.md](reality-map.md) for modeled operations, preserved causal
semantics, and omitted details.

## Evidence Grounding

Observed provider instances live in `evidence/`:

- `evidence/observed_instances.jsonl` contains doc-derived or live-probed
  provider behavior rows.
- `evidence/normalized_cases.jsonl` maps those rows into fake-world-relevant
  cases that can drive implementation decisions.
- `evidence/probes/stripe_refund_instances.py` captures raw Stripe test-mode
  refund behavior under `evidence/raw/`.

Run the Stripe probe only with a test secret key:

```bash
STRIPE_SECRET_KEY=sk_test_... \
  python worlds/billing_support_v0/evidence/probes/stripe_refund_instances.py
```

The probe refuses non-test keys by default. When no provider key is available,
keep rows labeled `source_type: docs` and cite official docs URLs instead of
inventing behavior.

## Collector Boundary

`run_export.json` is upstream evidence. Dataset rows, labels, splits,
manifests, and validation reports belong in `datalox-rollout-collector`, not in
this world.
