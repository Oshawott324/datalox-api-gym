# Billing Support v0

Billing Support v0 is the first concrete Datalox API Gym world.

It uses one SQLite state database per sampled run and exposes minimal fake
service operations for:

- `fake_billing_api`
- `fake_support_api`
- `fake_crm_api`
- `fake_email_api`

## Scenarios

- `duplicate_payment_refund`
- `failed_invoice_retryable`
- `refund_not_allowed_policy`

## Flow

```bash
api-gym sample --world billing_support_v0 --scenario failed_invoice_retryable --seed 7 --out /tmp/billing-run
api-gym verify --run /tmp/billing-run
```

`state.sqlite` stores customers, accounts, subscriptions, invoices, payments,
refunds, tickets, ticket messages, emails, events, policies, and audit log
records.

The billing behavior is inspired by Stripe refund and invoice retry patterns:

- https://docs.stripe.com/api/refunds/create
- https://docs.stripe.com/billing/revenue-recovery/smart-retries

The support behavior is inspired by Zendesk ticket update and ticket comment
patterns:

- https://developer.zendesk.com/api-reference/ticketing/tickets/tickets/
- https://developer.zendesk.com/api-reference/ticketing/tickets/ticket_comments/
