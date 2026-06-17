# Billing Support v0

`billing_support_v0` is a deterministic business workflow world for billing
support tasks.

## World Contract

Source substrate:

- public Stripe refund and invoice retry documentation
- public Zendesk ticket and ticket comment documentation
- optional provider probes under `worlds/billing_support_v0/evidence/`

Episode state:

- one `state.sqlite` per sampled run
- customers, accounts, subscriptions, invoices, payments, refunds
- tickets, messages, emails, events, policies, and audit log rows

Actions:

- inspect customer, invoice, payment, and ticket state
- create refunds
- retry invoices
- reply, tag, close, or escalate tickets

Dynamics:

- deterministic service functions
- SQLite mutations
- auditable event rows

Verifier:

- reads final SQLite state
- checks the scenario-specific expected resolution
- does not use transcript text as proof

Evidence:

- task package
- MCP tool trace
- verifier result
- run export

## Session Flow

```bash
api-gym session create \
  --world billing_support_v0 \
  --scenario duplicate_payment_refund \
  --seed 1 \
  --out runs/billing-demo \
  --json

api-gym session check-tools --run runs/billing-demo
api-gym session finalize --run runs/billing-demo --json
```

The session manifest gives an external agent host the task package, MCP config,
expected tools, commands, and artifact paths.

## Scenarios

- `duplicate_payment_refund`
- `failed_invoice_retryable`
- `refund_not_allowed_policy`

## Provider Grounding

The billing behavior is inspired by Stripe refund and invoice retry patterns:

- https://docs.stripe.com/api/refunds/create
- https://docs.stripe.com/billing/revenue-recovery/smart-retries

The support behavior is inspired by Zendesk ticket update and ticket comment
patterns:

- https://developer.zendesk.com/api-reference/ticketing/tickets/tickets/
- https://developer.zendesk.com/api-reference/ticketing/tickets/ticket_comments/
