# Billing Support v0 Reality Map

This world preserves narrow causal mechanisms from public billing and support
APIs without cloning provider-specific products. The modeled operations are
small enough for agents to reason over, but every mutation changes SQLite state
that the hidden verifier can inspect.

## Billing Operations

### `create_refund`

- Public source inspiration: Stripe refund creation, including refunding a
  charge or PaymentIntent, limiting refunds to the remaining unrefunded amount,
  and using reasons such as `duplicate` or `requested_by_customer`:
  https://docs.stripe.com/api/refunds/create
- Preserved causal semantics: a refund can only be created for an existing
  succeeded payment; the amount must be positive and cannot exceed the payment's
  remaining refundable amount; successful refunds create a refund row, increment
  the payment's `refunded_amount`, and emit refund/payment events.
- Omitted details: asynchronous refund settlement, balance transactions,
  partial network failures, connected accounts, multiple currencies per account,
  provider idempotency keys, disputes, and webhook delivery.

### `retry_invoice`

- Public source inspiration: Stripe Billing retry behavior around failed invoice
  payment attempts, `attempt_count`, `next_payment_attempt`, and hard decline
  handling: https://docs.stripe.com/billing/revenue-recovery/smart-retries
- Preserved causal semantics: only automatically collected unpaid invoices can
  be retried; hard-decline codes block retry; a successful retry creates a new
  succeeded payment, marks the invoice paid, clears the remaining amount, updates
  the latest payment, clears customer delinquency, and emits retry/payment
  events.
- Omitted details: Smart Retries scheduling, payment method ranking,
  subscription lifecycle state machines, dunning emails, taxes, invoice
  finalization, and provider webhook ordering.

### `get_customer`

- Public source inspiration: Stripe billing workflows that connect customers,
  invoices, payments, and refund decisions:
  https://docs.stripe.com/api/refunds/create and
  https://docs.stripe.com/billing/revenue-recovery/smart-retries
- Preserved causal semantics: customer lookup returns account-level billing
  identity plus correlated subscriptions and invoices so an agent can inspect
  state before acting.
- Omitted details: address models, tax settings, invoice settings, payment method
  attachment APIs, customer balance, test clocks, and pagination.

### `get_invoice`

- Public source inspiration: Stripe invoice retry state:
  https://docs.stripe.com/billing/revenue-recovery/smart-retries
- Preserved causal semantics: invoice lookup returns invoice status, amounts,
  retry fields, latest payment, and related payments so retry/refund decisions
  are grounded in billing state.
- Omitted details: invoice line items, discounts, taxes, hosted invoice URLs,
  collection workflows beyond automatic charge, and expansion parameters.

### `get_payment`

- Public source inspiration: Stripe payment and refund relationships:
  https://docs.stripe.com/api/refunds/create
- Preserved causal semantics: payment lookup exposes status, amount, decline
  information, existing refunds, and computed remaining refundable amount.
- Omitted details: authorization/capture flow, payment method networks, payment
  method updates, balance transactions, 3DS/authentication flows, and payment
  intent confirmation states.

## Support Operations

### `get_ticket`

- Public source inspiration: Zendesk ticket retrieval and comment history:
  https://developer.zendesk.com/api-reference/ticketing/tickets/tickets/ and
  https://developer.zendesk.com/api-reference/ticketing/tickets/ticket_comments/
- Preserved causal semantics: ticket lookup returns status, tags, assignee group,
  requester, and ordered conversation messages so an agent can inspect the
  support context before mutating it.
- Omitted details: brands, organizations, custom fields, views, triggers,
  macros, attachments, channel-specific identities, and pagination.

### Ticket Reply

- Public source inspiration: Zendesk ticket comments that may be public or
  private:
  https://developer.zendesk.com/api-reference/ticketing/tickets/ticket_comments/
- Preserved causal semantics: a non-empty agent reply creates a ticket message,
  updates the ticket timestamp, and sends an email record when public.
- Omitted details: rich text, attachments, side conversations, comment redaction,
  email threading, CCs/followers, and trigger execution.

### Ticket Close

- Public source inspiration: Zendesk ticket updates and status transitions:
  https://developer.zendesk.com/api-reference/ticketing/tickets/tickets/
- Preserved causal semantics: closing a ticket marks it solved, records a close
  timestamp, and emits an auditable support event.
- Omitted details: full status lifecycle, satisfaction surveys, reopen windows,
  automations, SLA timers, and solved-to-closed transitions.

### Ticket Tag

- Public source inspiration: Zendesk ticket tag updates:
  https://developer.zendesk.com/api-reference/ticketing/tickets/tickets/
- Preserved causal semantics: adding tags merges normalized tags into ticket
  state and records an event/audit entry, which lets the verifier observe policy
  handling.
- Omitted details: tag indexes, global tag management, trigger side effects,
  deleted tags, and tag-based views.

### Ticket Escalate

- Public source inspiration: Zendesk ticket updates for assignee group, priority,
  status, comments, and tags:
  https://developer.zendesk.com/api-reference/ticketing/tickets/tickets/
- Preserved causal semantics: escalation changes ticket status to pending,
  raises priority, moves the assignee group to billing escalations, adds policy
  review tags, and records the escalation reason.
- Omitted details: group membership, assignment routing, SLA policies,
  notifications to internal teams, approval workflows, and supervisor review
  queues.
