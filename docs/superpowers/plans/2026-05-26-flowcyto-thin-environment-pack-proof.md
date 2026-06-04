# FlowCyto Thin Environment Pack Proof Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first thin FlowCyto environment pack proof: one stateful scientific vertical slice that can be replayed and exported without turning the backend into a report-writing lab platform.

**Architecture:** `datalox-flow-cyto-mcp` owns the live scientific workspace and deterministic validation. `datalox-replay-fixtures` owns the published fixture pack/set. `datalox-agent-replay` owns `datalox run`, replay, and export. The agent authors the report; the backend only validates and persists structured report JSON with evidence refs.

**Tech Stack:** TypeScript, MCP tools, file-backed `flowcyto.workspace.json`, deterministic JSON artifacts, Datalox replay bundles, fixture-set manifests, Vitest.

---

## Corrected Step 2 Scope

This plan supersedes the older broad Step 2 wording that called for 10 tasks and `write_report`.

Do not implement a backend report writer. Implement `submit_report`, where the agent provides report content and the environment validates required fields, evidence references, and workspace revision before storing the artifact.

Target tool path:

```text
open_fcs
-> get_plot_context
-> upsert_gate
-> compute_gate_stats
-> validate_gate_qc
-> submit_report
```

Initial fixture-set scope:

```text
1 success task
1 stale-revision failure task
1 report-validation failure task
```

Deferred:

```text
10 tasks
5 recovery runs
5 failure runs
preference export
full FlowJo-style statistics
Docker/runtime packaging
reward design
```

## Repo Ownership

```text
/Users/yifanjin/datalox-flow-cyto-mcp
  live domain environment:
  sample data, workspace state, MCP tools, stats, QC validation, report artifact validation

/Users/yifanjin/datalox-replay-fixtures
  published fixture library:
  fixture pack, fixture set, task specs, verifier specs, splits, catalog

/Users/yifanjin/datalox-agent-replay
  replay/export engine:
  datalox run, datalox eval, datalox export sft, replay bundle verification
```

## Phase 1: FlowCyto Thin Vertical Slice

**Files:**

- Modify: `/Users/yifanjin/datalox-flow-cyto-mcp/src/mcp/server.ts`
- Create or modify: `/Users/yifanjin/datalox-flow-cyto-mcp/src/core/qc.ts`
- Modify: `/Users/yifanjin/datalox-flow-cyto-mcp/tests/core.test.ts`

- [x] **Step 1: Add failing tests for the successful vertical slice**

Add tests that exercise:

```text
open_fcs -> get_plot_context -> upsert_gate -> compute_gate_stats -> validate_gate_qc -> submit_report
```

Expected failure before implementation:

```text
tools/list does not include compute_gate_stats, validate_gate_qc, submit_report
```

- [x] **Step 2: Implement `compute_gate_stats`**

Minimal behavior:

```text
input: workspace_path, sample_id, gate_id
output:
  ok: true
  workspacePath
  revision
  sampleId
  gateId
  stats:
    totalEvents
    sampledEvents
    insideEvents
    populationPercent
    axes
    source: "preview_sample"
  evidenceRef
  nextAction.tool = "validate_gate_qc"
```

Use existing preview/context data. Do not implement full FlowJo statistics.

- [x] **Step 3: Implement `validate_gate_qc`**

Minimal behavior:

```text
input: workspace_path, sample_id, gate_id, stats_ref?, thresholds?
output:
  ok: boolean
  validation:
    status: "pass" | "fail"
    evidenceRefs
    checks[]
  nextAction.tool = "submit_report" when pass
```

Checks:

```text
gate exists
sample exists
gate uses known x/y channels
polygon has at least 3 vertices
populationPercentEstimate is inside configured min/max when provided
```

- [x] **Step 4: Implement `submit_report`**

Minimal behavior:

```text
input:
  workspace_path
  expected_revision
  report:
    title
    summary
    gate_id
    stats_ref
    qc_ref
    caveats[]
output:
  ok: true | false
  reportId
  reportPath
  validation:
    status
    missingFields[]
    missingEvidenceRefs[]
```

Rules:

```text
backend never generates title, summary, or caveats
expected_revision must match the workspace revision
required fields must exist
evidence refs must match current gate/stats/qc evidence refs
evidence refs must be backed by file-backed evidence records produced by prior tools
on success, save agent-authored JSON under the workspace directory
```

- [x] **Step 5: Add failure tests**

Add one stale revision test:

```text
submit_report expected_revision = current revision - 1
=> ok false, error_code stale_revision
```

Add one invalid report test:

```text
submit_report missing summary or evidence refs
=> ok false, error code missing_report_field
```

- [x] **Step 6: Verify FlowCyto**

Run:

```bash
npm run check
npm test
```

Expected:

```text
exit 0
```

## Phase 2: Minimal FlowCyto Task Specs

**Files:**

- Create: `/Users/yifanjin/datalox-flow-cyto-mcp/tasks/flowcyto-gating-qc-basic/*.json`
- Modify: `/Users/yifanjin/datalox-flow-cyto-mcp/tests/core.test.ts`

- [x] **Step 1: Add three task specs**

Create:

```text
flowcyto-gating-qc-success.json
flowcyto-gating-qc-stale-revision-failure.json
flowcyto-gating-qc-report-validation-failure.json
```

Each spec must include:

```text
sample_ref
channel_pair
target_population
validator_thresholds
required_report_fields
expected_error_code when failure task
```

- [x] **Step 2: Add a schema/shape test**

Test that all three task specs include the required fields and reference existing sample fixture files.

- [x] **Step 3: Verify FlowCyto**

Run:

```bash
npm run check
npm test
```

## Phase 3: Minimal Replay Fixture World

**Files:**

- Create: `/Users/yifanjin/datalox-replay-fixtures/fixtures/flowcyto-gating-qc-basic/`
- Create: `/Users/yifanjin/datalox-replay-fixtures/fixture-sets/flowcyto-gating-qc-basic/`
- Modify: `/Users/yifanjin/datalox-replay-fixtures/catalog.json`

- [x] **Step 1: Add fixture pack**

Create a fixture pack for:

```text
flowcyto-gating-qc-basic@2026-06.0
```

It must include a verified replay bundle with a tool catalog containing the FlowCyto tool path and tool I/O records for at least the success vertical slice.

- [x] **Step 2: Add fixture set**

Create a fixture set with:

```text
1 success task
1 stale-revision failure task
1 report-validation failure task
splits.json
eval-prompts.jsonl
tasks/*.json
verifiers/*.json
scaffolds/*.json
README.md
expected-behavior.md
```

- [x] **Step 3: Verify replay-fixtures**

Run:

```bash
npm run fixtures:validate
npm run fixture-sets:validate
npm run catalog:generate
npm test
```

## Phase 4: Agent Replay Consumer Verification

**Files:**

- Modify only if needed: `/Users/yifanjin/datalox-agent-replay/docs/flowcyto-environment-pack-plan.html`
- Modify only if needed: `/Users/yifanjin/datalox-agent-replay/docs/runtime-adapter-roadmap.html`

- [x] **Step 1: Verify one prompt-driven run**

Run against a local or stub OpenAI-compatible endpoint:

```bash
datalox run \
  --fixture-set flowcyto-gating-qc-basic@2026-06.0 \
  --base-url http://127.0.0.1:8000/v1 \
  --model <model> \
  --api-key <key> \
  --prompt "Gate the main population and submit a QC report." \
  --out runs/flowcyto-qc \
  --json
```

- [x] **Step 2: Verify SFT export**

Run:

```bash
datalox export sft \
  --run runs/flowcyto-qc \
  --out exports/flowcyto-qc.sft.jsonl \
  --json
```

- [x] **Step 3: Verify Agent Replay**

Run:

```bash
npm run check
npm test
```

## Final Pass Criteria

- [x] FlowCyto backend never generates final report text.
- [x] Agent-authored report JSON is validated and persisted.
- [x] At least three domain tools are required before final answer.
- [x] Wrong revision returns structured `stale_revision`.
- [x] Bad report returns structured `missing_report_field`.
- [x] Replay bundle verifies.
- [x] Fixture set installs/resolves.
- [x] `datalox run` produces `datalox_run.v1`.
- [x] `datalox export sft` produces valid `sft_frame.v1`.
