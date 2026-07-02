# Adaptyv Foundry Dry-Run v0

`adaptyv_foundry_dryrun_v0` is an MCP-only dry-run world for agent preflight
around Adaptyv Foundry-shaped campaign workflows.

The world is not a biology simulator and does not predict scientific outcomes
for novel sequences. It checks process behavior around target selection,
sequence-batch handling, cost estimates, quote discipline, submission state,
result provenance, and measured replay evidence.

## Source Boundary

The world is grounded in the Adaptyv Foundry source pack at:

```text
../../source_packs/apis/adaptyv_foundry/2026-07-01/source_pack.json
```

Public replay fixtures are used only as verifier-hidden measured outcomes.
The selected public replay subset is recorded in `public_replay_sources.json`.
Runtime execution never calls live Adaptyv endpoints and never handles real
credentials, orders, invoices, or quote confirmations.

## Scenarios

- `budget_cap_quote_reject`
- `expired_quote_not_confirmed`
- `partial_results_not_final`
- `stale_prior_campaign_result`
- `duplicate_submission_guard`
- `measured_result_supported_decision`

## Runtime

Sampling writes a run-local bundle:

```text
run.json
task.json
agent_task.json
state.sqlite
source_refs_snapshot.json
visible_artifacts/campaign_brief.md
hidden/*.json
```

The agent-visible task and campaign brief contain only public setup metadata.
Hidden replay results, oracle plans, known-bad plans, schedules, and verifier
expectations stay under `hidden/` and in non-agent-visible SQLite events.
