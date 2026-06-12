# Datalox API Gym

Datalox API Gym packages source-backed dry-run worlds for testing, evaluating,
training, and auditing tool-using agents.

An API Gym world is a resettable, stateful action system with source grounding,
episode state, actions, dynamics, observations, hidden verifier state, and
exportable evidence. It gives agent runtimes a safe place to dry-run, test,
evaluate, train, and audit workflows before touching production systems or
physical execution.

```text
source substrate
  -> world package
  -> world session
  -> MCP/action interface
  -> agent rollout
  -> verifier outcome
  -> run_export evidence
```

## Current Worlds

`billing_support_v0` is a deterministic business workflow world for billing and
support tasks.

`unitelabs_plate_qc_v0` is a deterministic dry-run lab workflow world for plate
transfer QC.

## Start

- [Quickstart](./guide/quickstart.md)
- [Agentic World Contract](./concepts/agentic-world-contract.md)
- [Billing Support v0](./worlds/billing-support-v0.md)
- [UniteLabs Chat Demo](./demos/unitelabs-chat-demo.md)
- [Benchmarks](./benchmarks.md)
