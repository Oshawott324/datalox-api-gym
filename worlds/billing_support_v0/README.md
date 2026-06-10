# Billing Support v0

Billing Support v0 is the first concrete Datalox API Gym world. It models a
resettable billing-support miniworld with fake billing, support, CRM, and email
state in one SQLite database per run.

The goal is not an endpoint catalog or a Stripe/Zendesk clone. The goal is a
small stateful API workflow world where agents can inspect correlated billing
and ticket state, perform deterministic side effects, and then be verified
against hidden SQLite state.

## Phase 1 Scenarios

- `duplicate_payment_refund`: a paid invoice has one legitimate card payment
  and one duplicate extra payment. The agent must refund the duplicate payment
  only and publicly reply to the support ticket.
- `failed_invoice_retryable`: a subscription invoice failed with a retryable
  decline. The agent must retry the invoice, record the successful payment
  state, reply, and solve the ticket.
- `refund_not_allowed_policy`: an old paid invoice is outside the configured
  refund window. The agent must not create a refund and must explain policy or
  escalate the ticket for billing review.

## Run Flow

```bash
api-gym sample --world billing_support_v0 --scenario duplicate_payment_refund --seed 1 --out runs/demo
api-gym serve --run runs/demo --port 8080
api-gym resolve --run runs/demo --policy oracle
api-gym verify --run runs/demo
api-gym run --run runs/demo --model qwen --base-url http://localhost:8000/v1 --api-key EMPTY
```

`sample` creates:

- `state.sqlite`: episode state and hidden expected resolution
- `task.json`: agent-visible prompt
- `run.json`: world, scenario, seed, and state file metadata

The service functions live in
`api_gym.worlds.billing_support_v0.services`. The verifier reads the final
SQLite state, not the agent's text transcript.

The HTTP app and OpenAI-compatible tool dispatcher call those service functions
directly. Agents cannot satisfy the verifier with transcript text alone; they
must cause the expected SQLite state changes.

`api-gym run` writes `messages.jsonl`, `tool_calls.jsonl`,
`final_answer.json`, and `verifier_result.json` under the run directory.

## State Tables

The episode database includes:

- `customers`, `accounts`, `subscriptions`
- `invoices`, `payments`, `refunds`
- `tickets`, `ticket_messages`, `emails`
- `events`, `policies`, `audit_log`

## Public API Inspiration

The world intentionally follows public provider patterns without copying their
full APIs:

- Stripe refund semantics: create refunds against a charge or PaymentIntent,
  cap them to remaining unrefunded amount, and use reasons such as `duplicate`
  or `requested_by_customer`: https://docs.stripe.com/api/refunds/create
- Stripe invoice retry semantics: failed invoice payment attempts, retry
  schedules, `attempt_count`, `next_payment_attempt`, and hard decline handling:
  https://docs.stripe.com/billing/revenue-recovery/smart-retries
- Zendesk ticket semantics: tickets are agent-managed support objects that can
  be updated with comments, statuses, and tags:
  https://developer.zendesk.com/api-reference/ticketing/tickets/tickets/
- Zendesk ticket comments: comments represent customer-agent conversation and
  may be public or private:
  https://developer.zendesk.com/api-reference/ticketing/tickets/ticket_comments/

See `reality-map.md` for each modeled operation's source inspiration,
preserved causal semantics, and omitted details.

## Phase 5 Evidence

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
