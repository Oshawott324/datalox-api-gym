# Datalox API Gym

Datalox API Gym packages resettable fake APIs for training and evaluating
tool-using agents.

An API Gym world is a stateful fake business system with seeded scenarios,
model-visible tools, hidden verifier state, side effects, and exportable run
evidence. It gives agents practice worlds for API workflows instead of another
connector catalog.

Phase 1 includes `billing_support_v0`, a SQLite-backed billing-support world
with duplicate-payment refund, retryable failed invoice, and refund-policy
scenarios.

## Start

- [Quickstart](./guide/quickstart.md)
- [Stateful fake APIs](./concepts/stateful-fake-apis.md)
- [Billing Support v0](./worlds/billing-support-v0.md)
- [UniteLabs chat demo](./demos/unitelabs-chat-demo.md)
- [Benchmarks](./benchmarks.md)
