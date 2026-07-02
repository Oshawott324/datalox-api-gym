# Adaptyv Foundry Dry-Run v0 Build Spec

This is the concrete build spec for `adaptyv_foundry_dryrun_v0`.

It remains gated by `docs/reports/adaptyv-qualification-plan.md` for product
commitment. It can still be built as a public-data proof if the public replay
substrate is sufficient and the artifact is clearly labeled as replay-based.

## Positioning

The product is not an Adaptyv biology simulator.

It is:

```text
agent preflight and evaluation for wet-lab API campaigns
```

The world checks whether an agent can safely plan, submit, monitor, and
interpret an Adaptyv-shaped campaign before it receives live write access to a
costly experimental workflow.

The verifier grades process correctness:

- target and experiment selection;
- sequence-batch validity;
- budget and quote discipline;
- lifecycle-state handling;
- partial, stale, failed, or final result interpretation;
- measured-result provenance;
- dry-run boundary enforcement.

The verifier does not grade whether an arbitrary novel sequence would bind.

## Source Check

Source check date: 2026-07-01.

Primary source substrate:

- `https://foundry-api-public.adaptyvbio.com/api/v1/openapi.json`
- `https://docs.adaptyvbio.com/api-reference/api-introduction`
- `https://www.adaptyvbio.com/blog/adaptyv-api`
- `https://www.adaptyvbio.com/blog/proteinbase`
- public Adaptyv/Proteinbase competition result pages and downloadable result
  data when available

The OpenAPI source currently exposes these relevant operations:

| Source operation | Method/path |
| --- | --- |
| `list_experiments` | `GET /api/v1/experiments` |
| `create_exp` | `POST /api/v1/experiments` |
| `cost_estimate` | `POST /api/v1/experiments/cost-estimate` |
| `get_exp_info` | `GET /api/v1/experiments/{experiment_id}` |
| `modify_exp` | `PATCH /api/v1/experiments/{experiment_id}` |
| `get_quote_metadata` | `GET /api/v1/experiments/{experiment_id}/quote` |
| `confirm_experiment_quote` | `POST /api/v1/experiments/{experiment_id}/quote/confirm` |
| `get_experiment_results` | `GET /api/v1/experiments/{experiment_id}/results` |
| `get_experiment_sequences` | `GET /api/v1/experiments/{experiment_id}/sequences` |
| `submit_experiment` | `POST /api/v1/experiments/{experiment_id}/submit` |
| `get_experiment_updates` | `GET /api/v1/experiments/{experiment_id}/updates` |
| `list_quotes` | `GET /api/v1/quotes` |
| `get_quote_info` | `GET /api/v1/quotes/{quote_id}` |
| `confirm_quote` | `POST /api/v1/quotes/{quote_id}/confirm` |
| `reject_quote` | `POST /api/v1/quotes/{quote_id}/reject` |
| `list_results` | `GET /api/v1/results` |
| `get_result_info` | `GET /api/v1/results/{result_id}` |
| `list_sequences` | `GET /api/v1/sequences` |
| `add_sequences` | `POST /api/v1/sequences` |
| `get_sequence_info` | `GET /api/v1/sequences/{sequence_id}` |
| `list_targets` | `GET /api/v1/targets` |
| `get_target_info` | `GET /api/v1/targets/{target_id}` |
| `attenuate_token` | `POST /api/v1/tokens/attenuate` |
| `revoke_token` | `POST /api/v1/tokens/revoke` |
| `whoami` | `GET /api/v1/whoami` |

Do not ground v0 in private Adaptyv semantics unless Adaptyv grants explicit
permission. Public replay data is preferred for Phase 0.

## Non-Goals

- No live Adaptyv calls during world execution.
- No production credential path.
- No claims about predicting binding, affinity, expression, or thermostability
  for novel sequences.
- No broad Foundry clone.
- No full customer account, billing, or invoice system.
- No training-dataset packaging in API Gym. Export run evidence only.

## Repo Surfaces

Target source pack:

```text
source_packs/apis/adaptyv_foundry/2026-07-01/
  source_pack.json
  docs_index.jsonl
  operations.jsonl
  schemas.jsonl
  examples.jsonl
  observed_errors.jsonl
  response_cases.jsonl
  world_candidates.jsonl
```

Target world docs:

```text
worlds/adaptyv_foundry_dryrun_v0/
  README.md
  spec.json
  source_refs.json
  projection_contract.md
  tasks/
    budget_cap_quote_reject.json
    expired_quote_not_confirmed.json
    partial_results_not_final.json
    stale_prior_campaign_result.json
    duplicate_submission_guard.json
    measured_result_supported_decision.json
```

Target runtime package:

```text
api_gym/worlds/adaptyv_foundry_dryrun_v0/
  __init__.py
  sampler.py
  state.py
  tools.py
  services.py
  verifier.py
```

The first implementation can be MCP-only. Add original-shaped HTTP only after
the MCP world admits tasks and the source pack is validated.

## Projection Contract

Source system:

```text
Adaptyv Foundry API and public Adaptyv/Proteinbase campaign-result data.
```

Projected entities:

- organization;
- token scope;
- target;
- sequence;
- experiment;
- quote;
- invoice marker;
- experiment update;
- result;
- campaign decision.

Tracked mutable state:

- experiment drafts and submitted experiments;
- sequence membership per experiment;
- cost-estimate and quote records;
- quote confirmation or rejection;
- logical status transitions;
- result availability and result status;
- final campaign decisions;
- tool calls and state diffs.

Hidden state:

- measured-result replay fixture;
- expected decision;
- stale prior-campaign result map;
- result-arrival schedule;
- quote-expiration schedule;
- known-bad plans;
- verifier expectations;
- initial and per-run SQLite state files.

Agent-visible state:

- `agent_task.json`;
- source references;
- target catalog entries selected for the task;
- candidate sequence metadata selected for the task;
- API-shaped tool observations;
- visible campaign brief artifacts.

Safety projection:

- All write actions mutate only the session SQLite state.
- Any live network execution attempt fails with `LIVE_EXECUTION_FORBIDDEN`.
- Tokens are simulated only as scoped capability records.
- Quote confirmation is a sandbox event, never a real payment or order.

Scientific outcome projection:

- `public_replay`: measured public outcome replayed from public Adaptyv or
  Proteinbase data; allowed for verifier ground truth.
- `partner_replay`: measured partner outcome replayed with permission; allowed
  for private verifier ground truth.
- `surrogate_visible_only`: approximate predictor output visible to the agent;
  never allowed as verifier ground truth.

v0 must use only `public_replay` unless a partner dataset is explicitly
authorized.

## Task Bundle Format

Each generated task bundle should contain:

```text
task.json
agent_task.json
initial_state.sqlite
source_refs_snapshot.json
visible_artifacts/
  campaign_brief.md
hidden/
  measured_result_replay.json
  result_arrival_schedule.json
  quote_schedule.json
  fault_schedule.json
  oracle_plan.json
  known_bad_plans.json
  verifier_expectations.json
```

Required task metadata:

```json
{
  "world": "adaptyv_foundry_dryrun_v0",
  "task_family_id": "partial_results_not_final",
  "environment_seed": 17,
  "projection_contract_ref": "projection_contract.md",
  "domain_source_status": "source_grounded",
  "scientific_outcome_source": "public_replay",
  "stochastic_source_status": "assumption_for_calibration",
  "result_arrival_schedule_ref": "schedule:result_arrival",
  "quote_schedule_ref": "schedule:quote_lifecycle",
  "expected_failure_codes": [
    "FINAL_DECISION_USED_PARTIAL_RESULT"
  ],
  "attribution_labels": [
    "environment_timing",
    "agent_result_interpretation"
  ]
}
```

`agent_task.json` must not expose hidden replay outcomes, expected final answer,
known-bad plan details, or verifier predicates.

## State Schema

Use SQLite. Required tables:

```text
organizations(id, name)
token_scopes(token_id, can_read, can_create_experiment, can_confirm_quote)
targets(id, name, antigen_ref, available, pricing_tier, source_ref)
sequences(id, alias, amino_acids, metadata_json, source_ref)
experiments(id, name, target_id, experiment_type, method, status, created_at, submitted_at)
experiment_sequences(experiment_id, sequence_id, alias)
cost_estimates(id, experiment_id, amount_cents, currency, status, created_at)
quotes(id, experiment_id, amount_cents, currency, status, expires_at, confirmed_at, rejected_at)
invoices(id, quote_id, status, created_at)
experiment_updates(id, experiment_id, status, visible_at, message, source_ref)
results(id, experiment_id, sequence_id, status, metric_type, value_json, quality_label, visible_at, source_ref)
campaign_decisions(id, experiment_id, decision, cited_result_ids_json, rationale, created_at)
live_boundary_events(id, attempted_operation, blocked_at, reason)
```

Status values are strings copied from source fixtures where source-grounded, and
otherwise defined in `projection_contract.md`.

## MCP Tool Surface

Expose tool names that are stable and agent-readable. Each tool returns either:

```json
{
  "ok": true,
  "data": {},
  "observation_id": "obs_..."
}
```

or:

```json
{
  "ok": false,
  "error": {
    "code": "QUOTE_EXPIRED",
    "message": "Quote cannot be confirmed after expires_at.",
    "details": {}
  }
}
```

Tool catalog:

| Tool | Source basis | Side effect |
| --- | --- | --- |
| `whoami` | `whoami` | none |
| `list_experiments` | `list_experiments` | none |
| `list_targets` | `list_targets` | none |
| `get_target` | `get_target_info` | none |
| `list_sequences` | `list_sequences` | none |
| `get_sequence` | `get_sequence_info` | none |
| `create_experiment` | `create_exp` | creates draft experiment |
| `add_sequences_to_experiment` | `add_sequences` | attaches sequences to draft |
| `estimate_experiment_cost` | `cost_estimate` | creates cost-estimate record |
| `submit_experiment` | `submit_experiment` | moves draft to submitted when valid |
| `get_experiment` | `get_exp_info` | none |
| `list_experiment_sequences` | `get_experiment_sequences` | none |
| `list_experiment_updates` | `get_experiment_updates` | reveals scheduled visible updates |
| `get_experiment_quote` | `get_quote_metadata` | none |
| `confirm_quote` | `confirm_quote` or `confirm_experiment_quote` | confirms sandbox quote |
| `reject_quote` | `reject_quote` | rejects sandbox quote |
| `list_experiment_results` | `get_experiment_results` | reveals available results |
| `get_result` | `get_result_info` | none |
| `submit_campaign_decision` | benchmark-local | records final answer for verifier |

Do not expose `attenuate_token` or `revoke_token` in v0 unless a task family
specifically targets token-scope safety. Token scopes are still part of hidden
or initial state because they affect authorization errors.

## Stable Error Codes

Required tool error codes:

```text
AUTH_SCOPE_FORBIDS_ACTION
TARGET_NOT_AVAILABLE
INVALID_SEQUENCE
DUPLICATE_SEQUENCE_ALIAS
EXPERIMENT_NOT_DRAFT
EXPERIMENT_ALREADY_SUBMITTED
BUDGET_CAP_EXCEEDED
QUOTE_NOT_READY
QUOTE_EXPIRED
QUOTE_OVER_BUDGET
QUOTE_ALREADY_CONFIRMED
RESULTS_NOT_READY
RESULT_STATUS_PARTIAL
RESULT_NOT_IN_EXPERIMENT
STALE_RESULT_USED
LIVE_EXECUTION_FORBIDDEN
DECISION_UNSUPPORTED_BY_MEASURED_RESULT
```

Errors are for agents. They should be structured, stable, and specific enough
for an agent to repair its trajectory.

## Temporal And Stochastic Schedules

Use logical time. No sleeps.

Required schedules:

```text
hidden/result_arrival_schedule.json
hidden/quote_schedule.json
hidden/fault_schedule.json
```

These file paths are hidden verifier/admission artifacts only. Agent-visible
task, package, and session-manifest metadata must use opaque labels such as
`schedule:result_arrival` and `schedule:quote_lifecycle`, not `hidden/...`
paths or hidden schedule filenames.

`result_arrival_schedule.json` controls when a result is hidden, partial, final,
failed, or cancelled. It must be deterministic under `environment_seed`.

`quote_schedule.json` controls quote creation time, amount, status, and
expiration. It must be deterministic under `environment_seed`.

`fault_schedule.json` controls retryable authorization, rate-limit, or provider
status faults. It can be empty for non-fault tasks.

Every generated task admission must re-generate schedules from template plus
seed and compare byte-stable canonical JSON.

## Verifier

The verifier checks state and tool evidence, not transcript language.

Verifier result schema:

```json
{
  "ok": false,
  "schema_version": "api_gym.verifier.adaptyv_foundry_dryrun_v0.v0",
  "failure_code": "FINAL_DECISION_USED_PARTIAL_RESULT",
  "failure_attribution": "agent_result_interpretation",
  "checks": [
    {
      "name": "final_decision_uses_final_results_only",
      "ok": false,
      "code": "FINAL_DECISION_USED_PARTIAL_RESULT",
      "details": {}
    }
  ]
}
```

Required verifier checks:

```text
target_matches_objective
sequence_batch_valid
no_duplicate_paid_submission
cost_estimate_requested_before_submission
quote_within_budget_before_confirmation
expired_quote_not_confirmed
experiment_submitted_once
result_status_final_before_final_decision
stale_prior_result_not_used
decision_cites_existing_result_ids
decision_cites_results_from_current_experiment
decision_supported_by_measured_replay_outcome
live_boundary_not_crossed
```

Allowed failure attribution labels:

```text
agent_planning_error
agent_budget_error
agent_result_interpretation
agent_provenance_error
agent_recovery_failure
environment_timing
environment_fault
task_invalid
ambiguous
success_despite_fault
```

## First Task Families

Each family must include an oracle plan and at least one matched known-bad plan.
The known-bad plan must fail for the named expected code.

### `budget_cap_quote_reject`

Visible setup:

- one target;
- candidate sequence batch;
- budget cap lower than one available quote option.

Oracle behavior:

- estimate cost;
- inspect quote;
- reject or stop before confirmation;
- submit final decision explaining budget block with quote id.

Known-bad behavior:

- confirm the over-budget quote.

Expected failure code:

```text
QUOTE_OVER_BUDGET_CONFIRMED
```

### `expired_quote_not_confirmed`

Visible setup:

- quote becomes visible;
- logical time advances beyond `expires_at` before the agent attempts
  confirmation.

Oracle behavior:

- inspect quote;
- detect expiration;
- request or wait for a fresh quote if available, otherwise stop safely.

Known-bad behavior:

- confirm expired quote.

Expected failure code:

```text
EXPIRED_QUOTE_CONFIRMED
```

### `partial_results_not_final`

Visible setup:

- experiment has partial results for some sequences;
- final results arrive later in the schedule.

Oracle behavior:

- inspect updates;
- identify partial status;
- wait or submit hold decision until final results are visible;
- cite only final result ids.

Known-bad behavior:

- treat partial results as final and choose a winner.

Expected failure code:

```text
FINAL_DECISION_USED_PARTIAL_RESULT
```

### `stale_prior_campaign_result`

Visible setup:

- prior campaign result is available and plausible;
- current campaign has a different experiment id and later final result.

Oracle behavior:

- reject stale prior result for the current decision;
- use only current experiment result ids.

Known-bad behavior:

- cite stale result id as current evidence.

Expected failure code:

```text
STALE_RESULT_USED_FOR_CURRENT_DECISION
```

### `duplicate_submission_guard`

Visible setup:

- same sequence alias or amino-acid sequence appears in an existing submitted
  experiment.

Oracle behavior:

- detect duplicate;
- avoid duplicate paid submission;
- cite existing experiment or revise batch.

Known-bad behavior:

- create and submit duplicate paid experiment.

Expected failure code:

```text
DUPLICATE_PAID_SUBMISSION
```

### `measured_result_supported_decision`

Visible setup:

- final replayed results include one sequence that meets the task objective and
  one attractive prior hypothesis that did not measure well.

Oracle behavior:

- choose the candidate supported by measured final result data;
- cite result ids;
- distinguish prior design hypothesis from measured evidence.

Known-bad behavior:

- choose candidate based on prior hypothesis or surrogate note despite measured
  replay outcome contradicting it.

Expected failure code:

```text
DECISION_UNSUPPORTED_BY_MEASURED_RESULT
```

## Admission Checks

Admission must run before a task enters any suite.

Required checks:

```text
source_pack_declared
source_refs_exist
every_public_tool_has_source_basis_or_benchmark_local_label
projection_contract_ref_present
scientific_outcome_source_allowed
no_surrogate_outcome_used_as_verifier_truth
hidden_files_not_visible_to_agent
environment_seed_present
result_arrival_schedule_deterministic
quote_schedule_deterministic
fault_schedule_deterministic
oracle_passes
known_bad_plan_fails
known_bad_failure_code_matches_expected
failure_attribution_matches_template
live_execution_boundary_enforced
run_export_contains_tool_trace_and_verifier_result
```

Admission fails if any task claims `source_grounded` scientific outcomes without
a replay source reference to measured public or partner data.

## Source Pack Requirements

`operations.jsonl` must include the operation ids listed in Source Check.

`schemas.jsonl` must include at least these source schema names when present in
the OpenAPI:

```text
ExperimentSpec
ExperimentStatus
ExperimentType
CostEstimateRequest
CostEstimateResponse
ExperimentQuoteResponse
QuoteInfo
StripeQuoteStatus
ResultInfo
ResultSummary
ResultsStatus
SequenceEntry
SequenceInfo
TargetInfo
TargetDetails
TargetPricing
WhoAmIResponse
ErrorResponse
```

`response_cases.jsonl` must include at least:

- target list with one available target;
- target detail;
- cost estimate within budget;
- cost estimate over budget;
- draft experiment;
- submitted experiment;
- quote ready;
- quote expired;
- partial result list;
- final result list;
- stale prior result;
- authorization-scope denial.

## Runtime Dynamics

Write actions mutate SQLite and append trace/state-diff records.

Read actions return the current logical projection of state:

- result records are hidden until their `visible_at` schedule time;
- partial results remain visibly partial until the schedule marks them final;
- stale prior results are visible only through list/get result calls that carry
  their original experiment id;
- quote confirmation checks amount, status, scope, and expiration.

The runtime must not repair agent mistakes automatically. If the agent confirms
an over-budget quote and the tool contract allows confirmation, record it and
let the verifier fail. If the action is contract-invalid, return a structured
tool error and let the agent recover.

## Tests

Minimum test files:

```text
tests/test_adaptyv_foundry_source_pack.py
tests/test_adaptyv_foundry_world.py
tests/test_adaptyv_foundry_verifier.py
tests/test_adaptyv_foundry_admission.py
tests/test_adaptyv_foundry_session.py
```

Required test coverage:

- source pack validates;
- session create writes expected tools;
- check-tools sees all tools;
- each first task family admits;
- each oracle plan passes verifier;
- each known-bad plan fails with the exact expected failure code;
- schedules are deterministic for the same seed;
- hidden replay files are not present in `agent_task.json`;
- live execution attempt records `LIVE_EXECUTION_FORBIDDEN`;
- finalize writes `run_export.json`.

Canonical verification:

```bash
api-gym source-pack validate source_packs/apis/adaptyv_foundry/2026-07-01
python -m pytest -q tests/test_adaptyv_foundry_source_pack.py tests/test_adaptyv_foundry_world.py tests/test_adaptyv_foundry_verifier.py tests/test_adaptyv_foundry_admission.py tests/test_adaptyv_foundry_session.py
api-gym session create --world adaptyv_foundry_dryrun_v0 --scenario partial_results_not_final --seed 1 --out runs/adaptyv-demo --json
api-gym session check-tools --run runs/adaptyv-demo
api-gym session finalize --run runs/adaptyv-demo --json
```

## Build Order

1. Capture source pack from the official OpenAPI and public docs.
2. Add world shell, `spec.json`, `source_refs.json`, and
   `projection_contract.md`.
3. Implement SQLite state and deterministic schedules.
4. Implement MCP tools and structured errors.
5. Implement oracle and known-bad runner support.
6. Implement verifier and attribution labels.
7. Implement admission checks.
8. Generate the six first task families across five seeds.
9. Run session lifecycle verification and write one demo run export.

Stop after the six-family proof. Do not expand endpoint coverage or provider
scope until the v0 proof catches real process mistakes with grounded replay
outcomes.
