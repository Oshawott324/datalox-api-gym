# Stateful Fake APIs

A stateful fake API world models business state and side effects across calls.
It is more than schema-shaped responses.

Agents should encounter customers, subscriptions, invoices, payments, refunds,
support tickets, CRM records, email threads, permission boundaries, idempotency
keys, and realistic failure states. Valid tool calls mutate hidden world state.
The verifier checks the final outcome against that hidden state and the task
policy.

Datalox API Gym is distinct from API aggregators and official provider
sandboxes. Aggregators connect agents to real APIs. Provider sandboxes test
provider integrations. API Gym supplies resettable practice worlds for agent
training and evaluation.
