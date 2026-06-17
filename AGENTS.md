# Agent Instructions

Read in this order:

1. `docs/product-definition.md`
2. `README.md`
3. The relevant world README under `worlds/<world>/README.md`
4. The relevant world spec under `worlds/<world>/spec.json`
5. Existing tests for the world or CLI surface being changed

This repo is `datalox-api-gym`.

Primary model:

```text
source substrate -> world package -> world session -> MCP/action interface -> verifier outcome -> run_export evidence
```

Business rules:

- API Gym owns world specs, world sessions, state backends, action contracts,
  dynamics backends, observation contracts, hidden verifier execution, tool
  traces, and run exports.
- API Gym does not own dataset manifests, train/dev/test split assignment,
  dataset quality labels, dataset validation reports, or model training
  recipes.
- Use `api-gym session create`, `api-gym session check-tools`, and
  `api-gym session finalize` as the canonical agent-host lifecycle.
- MCP is the action channel. The session manifest is the lifecycle contract.
- Agents must not receive hidden verifier state or direct access to mutable
  state files such as `state.sqlite`.
- Verifiers check world state and workflow invariants, not transcript text.
- Do not add live provider execution to a dry-run world unless there is an
  explicit live-gate policy and user approval.
- Do not guess provider semantics. Ground behavior from source docs, explicit
  contracts, provider test-mode probes, or recorded evidence.
- Prefer structured, agent-readable errors with stable codes.
- Keep implementation small and file-system based until a real backend is
  necessary.

Drift rule:

If a change starts building dataset packaging, split assignment, quality labels,
or validation reports, move it to `datalox-rollout-collector`. If a change
starts building generic replay hashing or replay lookup, move it to the replay
engine.
