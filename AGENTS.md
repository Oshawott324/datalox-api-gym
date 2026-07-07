<!-- DATALOX_PACK:BEGIN -->
## Datalox Pack
If `DATALOX.md` exists in this repo, read it after this file and treat it as the repo-local Datalox contract.
Use reusable local knowledge in `agent-wiki/notes/` and grounded event records in `agent-wiki/events/`.
<!-- DATALOX_PACK:END -->

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

Freeze boundary:

- Runtime authority now lives in `datalox-gated-runtime`: gates, session
  lifecycle, live capture, promotion, replay verification, generic audit/export
  plumbing, and call-path adapters should be built there.
- Do not add new runtime features in this repo. Treat existing source packs and
  worlds as migration assets until they are imported or re-homed.

Business rules:

- API Gym contains existing world specs, world sessions, state backends, action
  contracts, dynamics backends, observation contracts, hidden verifier
  execution, tool traces, and run exports as migration assets.
- API Gym does not own dataset manifests, train/dev/test split assignment,
  dataset quality labels, dataset validation reports, or model training
  recipes.
- For existing, not-yet-migrated worlds, use `api-gym session create`,
  `api-gym session check-tools`, and `api-gym session finalize` as the
  canonical agent-host lifecycle.
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
starts building gates, generic session lifecycle, capture, promotion, replay
verification, generic audit/export plumbing, or call-path adapters, move it to
`datalox-gated-runtime`. If a change starts building generic replay hashing or
replay lookup, move it to the replay engine.
