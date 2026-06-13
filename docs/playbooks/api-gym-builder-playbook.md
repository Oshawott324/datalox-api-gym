# API Gym Builder Playbook

This playbook is for contributors who need to help build `datalox-api-gym`.
It explains what we are building, how to expand API source packs, and how to
turn selected API substrate into Gym-like dry-run worlds.

## 1. What We Are Building

Datalox API Gym packages source-backed dry-run worlds for agents.

An API Gym world is a resettable, stateful action system:

```text
World = source substrate
      + mutable episode state
      + actions
      + dynamics
      + observations
      + verifier
      + evidence
```

The product pipeline is:

```text
source substrate
  -> world package
  -> world session
  -> MCP/action interface
  -> agent rollout
  -> verifier outcome
  -> run_export evidence
```

API Gym is not:

- a live API aggregator
- a connector catalog
- a fake provider implementation
- a training dataset packager
- a place to store train/dev/test splits, dataset labels, or model recipes

API Gym is:

- source substrate for API and workflow behavior
- resettable stateful worlds for agents
- action contracts exposed through MCP or host adapters
- dynamics and observation systems
- hidden verifier execution
- run evidence for downstream testing, evaluation, training, and audit

## 2. The Core Boundary

Keep these layers separate:

```text
source_packs/apis/<provider>/<version>
  raw and normalized provider facts
  operation catalog
  response cases for dry-run API gating
  world candidate notes

worlds/<world_id>
  selected subset of source packs
  explicit state model
  action contract
  dynamics backend
  observations
  hidden verifier
  source_refs.json

runs/<run_id>
  session_manifest.json
  task package
  mutable episode state
  tool trace
  verifier result
  run_export.json
```

Do not copy broad provider samples into `worlds/<world_id>/evidence`. A world
only cites the specific source records it selected through
`worlds/<world_id>/source_refs.json`.

## 3. Building API Source Packs

Source packs live under:

```text
source_packs/apis/<provider>/<version>/
```

Use a new provider/version folder only when there is real source material:

```text
source_packs/apis/stripe/2026-06-12/
  source_pack.json
  docs_index.jsonl
  operations.jsonl
  schemas.jsonl
  examples.jsonl
  response_cases.jsonl
  observed_errors.jsonl
  world_candidates.jsonl
  raw/
```

List only files that exist and contain at least one row. The
`api-gym source-pack validate` command fails if `source_pack.json.records`
points to a missing or empty file.

### Source Material

Use one or more of:

- official OpenAPI specs
- official docs pages
- official examples
- safe test-mode probe outputs
- recorded observations from approved non-production runs
- documented error pages

Do not infer provider semantics from vibes, blog posts, or our world code. If a
provider behavior is not sourced, record it as unknown.

### `source_pack.json`

Minimum shape:

```json
{
  "schema_version": "api_gym.api_source_pack.v0",
  "source_pack_id": "api.example.2026-06-13",
  "provider": "example",
  "version": "2026-06-13",
  "status": "normalized",
  "source_types": ["openapi", "docs"],
  "records": {
    "docs_index": "docs_index.jsonl",
    "operations": "operations.jsonl",
    "schemas": "schemas.jsonl",
    "examples": "examples.jsonl",
    "response_cases": "response_cases.jsonl",
    "observed_errors": "observed_errors.jsonl",
    "world_candidates": "world_candidates.jsonl"
  },
  "live_execution": {
    "allowed": false,
    "reason": "Source substrate only; no live provider action is executed by API Gym."
  }
}
```

### `operations.jsonl`

One normalized operation per line:

```json
{"id":"operation:createRefund","source_pack_id":"api.example.2026-06-13","operation_id":"createRefund","method":"POST","path":"/v1/refunds","summary":"Create a refund.","source_refs":[{"kind":"docs","url":"https://docs.example.invalid/refunds"}],"agent_notes":["Mutation operation. Dry-run gating needs concrete success and failure cases before HTTP serving."]}
```

Rules:

- Use stable `operation:<name>` ids.
- Preserve provider path and method.
- Cite the exact source.
- Do not claim side effects that are not in the source.

### `response_cases.jsonl`

Response cases are the dry-run gate surface. An agent can call an
original-shaped provider API, while Datalox returns a selected sampled response
case instead of calling the live provider.

```json
{"id":"response_case:createRefund:success","source_pack_id":"api.example.2026-06-13","operation_ref":"operation:createRefund","case":"success","status":200,"response_mode":"body_excerpt","source_refs":[{"kind":"docs","url":"https://docs.example.invalid/refunds"}],"body_excerpt":{"id":"re_123","object":"refund","status":"succeeded"}}
```

Use these response modes:

- `body`: exact concrete body from a source or approved recording
- `body_excerpt`: concrete excerpt that preserves source fields without
  pretending to be a full fixture
- `body_shape`: sourced response shape when no concrete body is captured yet
- `error_shape`: sourced provider error shape

Concrete `body` or `body_excerpt` cases are best for HTTP gating. Shape-only
cases are still useful source substrate, but a runtime must not invent concrete
wire behavior from `status: "2xx"` or a vague shape.

### Response Coverage Target

For each important operation, aim for:

- one success case
- one validation or invalid request case
- one auth or permission case when documented
- one not-found or conflict case when relevant
- one rate-limit or retryable error case when documented
- one idempotency, duplicate, or already-done case for mutations when relevant

For each provider pack, aim for:

```text
6-10 operations
3-5 response cases for important operations
at least one list/search operation
at least one get/read operation
at least one create/update operation
at least one workflow transition operation
at least one permission/error case
at least one rate-limit/conflict case when documented
```

### `world_candidates.jsonl`

World candidate rows explain how the source pack could become a future world.
They are not runtime contracts.

```json
{"id":"world_candidate:refund_support_v0","source_pack_id":"api.example.2026-06-13","candidate_world":"refund_support_v0","operation_refs":["operation:createRefund"],"design_status":"candidate","notes":["Could support a refund triage world when paired with support ticket and billing state."],"not_world_contract":true}
```

## 4. Expanding API Breadth

Do not add random providers just to increase count. Expand by workflow surface.

Recommended order:

1. Deepen current packs with concrete response cases.
2. Add adjacent APIs that combine into realistic workflows.
3. Add harder stateful APIs where dry-run value is high.
4. Build worlds only after selected source records are strong enough.

Good expansion lanes:

```text
developer workflow:
  GitHub, GitLab, Jira, Linear, Slack

commerce and business ops:
  Shopify, WooCommerce, QuickBooks, Xero, NetSuite

support and customer ops:
  Zendesk, Freshdesk, Help Scout, Intercom, Salesforce, HubSpot

payments and billing:
  Stripe, PayPal, Square, Chargebee

incident and observability:
  PagerDuty, Datadog, Sentry

identity and admin:
  Okta, Auth0

lab and science:
  UniteLabs, Benchling, Opentrons, vendor APIs with explicit contracts
```

Prefer APIs where real calls are expensive, slow, risky, or side-effectful:

- refunds and payments
- support ticket mutation
- CRM ownership or status changes
- lab instrument or workflow commands
- security admin actions
- incident escalation
- inventory and order changes

## 5. Turning Source Packs Into Gym Worlds

A source pack is not a world. A world begins under:

```text
worlds/<world_id>/
```

Every world needs:

```text
spec.json
README.md
source_refs.json
state model
action contract
dynamics backend
observation contract
hidden verifier
session lifecycle support
tests
```

The design question is not "can we mock this API?" The question is:

```text
Can an agent enter a resettable episode, take actions, observe state changes,
and be judged by hidden workflow invariants?
```

### World Design Steps

1. Pick a narrow workflow.

   Example: "refund a duplicate payment while updating the support ticket" is
   better than "clone Stripe and Zendesk."

2. Select source records.

   Use `source_refs.json` to cite operations, schemas, response cases, and
   observed errors. Do not copy broad provider evidence into the world.

3. Define mutable episode state.

   State should include only what the episode needs: tickets, invoices,
   customers, labware, protocol decisions, workflow notes, etc.

4. Define actions.

   Actions should look like agent tools, not internal helper functions. Each
   action needs input schema, state effects, observation shape, and stable
   agent-readable errors.

5. Define dynamics.

   Dynamics decide what changes after an action. They may be deterministic
   business logic, a gated provider response, a simulator, or a replayed
   observation. Do not call live providers unless a live-gate policy exists and
   the user explicitly approves it.

6. Define observations.

   Observations are what the agent sees after each action. They should be
   enough for the agent to continue, but must not expose hidden verifier state.

7. Define the hidden verifier.

   Verifiers check final world state and workflow invariants. They do not grade
   transcript text.

8. Export evidence.

   Finalization writes `run_export.json`. Downstream dataset packaging belongs
   outside API Gym.

## 6. Runtime Pattern For Original-Shaped API Calls

The intended source-pack gate pattern is:

```text
agent calls original-shaped API
  -> Datalox gate matches provider + method + path
  -> gate chooses a sourced response case
  -> gate returns dry-run response
  -> optional world/session layer records evidence and verifies outcome
```

Use the CLI for inspection:

```bash
api-gym source-pack respond \
  --provider stripe \
  --method POST \
  --path /v1/invoices/in_123/pay \
  --case success
```

Use HTTP gating only for response cases with concrete integer statuses and
concrete response bodies or excerpts. The gate must not make up a `200` from
`status: "2xx"`.

## 7. Contributor Task Templates

Use these tasks to delegate work.

### Task: Add One Provider Source Pack

```text
Goal:
  Add source_packs/apis/<provider>/<version> as source substrate only.

Inputs:
  Official docs/OpenAPI/examples/error docs.

Required files:
  source_pack.json
  docs_index.jsonl
  operations.jsonl
  schemas.jsonl when schemas are explicit
  examples.jsonl when concrete examples exist
  response_cases.jsonl
  observed_errors.jsonl when errors are documented
  world_candidates.jsonl

Rules:
  Do not add runtime code.
  Do not add a world.
  Do not execute live provider APIs.
  Cite every operation and response case.
  Every operation must have at least one response case.

Validation:
  api-gym source-pack validate source_packs/apis/<provider>/<version>
  python -m pytest tests/test_source_packs.py -q
```

### Task: Deepen One Existing Provider Pack

```text
Goal:
  Improve response coverage for source_packs/apis/<provider>/<version>.

Focus:
  Convert shape-only success cases into concrete sourced body/body_excerpt rows.
  Add documented errors for validation, auth, not found, conflict, and rate limit.
  Add mutation edge cases such as duplicate, already refunded, locked, or stale state.

Rules:
  Do not invent examples.
  Do not smooth provider differences.
  Preserve stable ids unless the old id is wrong.

Validation:
  api-gym source-pack validate source_packs/apis/<provider>/<version>
  python -m pytest tests/test_source_packs.py -q
```

### Task: Propose One World Candidate

```text
Goal:
  Add candidate rows that describe a possible world without creating it.

Output:
  world_candidates.jsonl rows with operation_refs and notes.

Rules:
  Candidate rows are planning evidence, not runtime contracts.
  Do not create MCP tools or state backends.
  Explain what state and verifier would be needed later.
```

### Task: Build One Minimal World

```text
Goal:
  Create worlds/<world_id> from selected source records.

Required:
  README.md
  spec.json
  source_refs.json
  state backend
  action contract
  dynamics backend
  hidden verifier
  tests

Rules:
  Agent must not see hidden verifier state.
  Agent must not directly access mutable state files.
  Verifier checks state and workflow invariants, not transcript wording.
  Source_refs must cite selected source records.

Validation:
  api-gym session create --world <world_id> --scenario <scenario> --seed 1 --out runs/<demo> --json
  api-gym session check-tools --run runs/<demo>
  api-gym session finalize --run runs/<demo> --json
  python -m pytest -q
```

## 8. Quality Bar

A source pack is acceptable when:

- it validates cleanly
- every operation has a response case
- every provider claim has source evidence
- no broad provider evidence is copied into a world
- no live execution is enabled
- response cases distinguish concrete examples from shapes
- errors are stable and agent-readable

A world is acceptable when:

- it has resettable episode state
- actions are explicit and agent-facing
- dynamics are deterministic or explicitly sourced
- observations do not leak hidden verifier state
- verifier checks world state and invariants
- session create, check-tools, and finalize work
- run evidence is exported
- tests cover success and failure paths

## 9. What Not To Do

Do not:

- build a generic API aggregator inside API Gym
- call production provider APIs from a dry-run world
- put broad sampled APIs under `worlds/`
- expose `state.sqlite` or verifier internals to agents
- validate success by transcript text
- create placeholder provider packs without source evidence
- repair missing provider semantics with local compatibility hacks
- turn run exports into dataset manifests inside this repo

If work starts looking like dataset packaging, move it to
`datalox-rollout-collector`. If work starts looking like generic replay hashing
or replay lookup, move it to the replay engine.

## 10. Fast Start For A New Contributor

Run:

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
```

Read:

```text
docs/product-definition.md
README.md
source_packs/apis/README.md
source_packs/apis/schema.md
this playbook
```

Then pick one task:

```text
add one provider source pack
deepen one provider source pack
propose one world candidate
build one minimal world from selected source records
```

Before handing off, run:

```bash
api-gym source-pack validate source_packs/apis/<provider>/<version>
python -m pytest -q
```
