# FlowCyto Visible Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a visible local proof for `flowcyto-gating-qc-basic@2026-06.0` that installs the fixture set, runs an OpenAI-compatible model loop through replayed FlowCyto tools, proves replay misses do not fall back to live tools, and exports one `sft_frame.v1`.

**Architecture:** The demo lives under `examples/flowcyto-gating-qc-demo/`. A deterministic fake OpenAI-compatible server acts as the cheap model endpoint, the existing `datalox` CLI installs/runs/exports the fixture set, and a static HTML report renders the produced artifacts. The demo report is a proof wrapper around real output files, not a parallel runtime.

**Tech Stack:** Node.js ESM scripts, built `dist/src/cli/main.js`, `createReplayToolRuntime`, Vitest for the report-render unit test, fixture catalog from `/Users/yifanjin/datalox-replay-fixtures/catalog.json`.

---

### Task 1: Report Renderer Test

**Files:**
- Create: `tests/flowcytoVisibleDemoReport.test.ts`
- Create: `examples/flowcyto-gating-qc-demo/report.mjs`

- [ ] **Step 1: Write a failing Vitest test**

Create `tests/flowcytoVisibleDemoReport.test.ts` with a temp output directory containing minimal proof JSON and assert that `renderDemoReport` emits the proof headings and a FlowCyto tool timeline.

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```bash
npx vitest run tests/flowcytoVisibleDemoReport.test.ts
```

Expected: fail because `examples/flowcyto-gating-qc-demo/report.mjs` does not exist.

- [ ] **Step 3: Implement `report.mjs`**

Export `renderDemoReport(input)` and `writeDemoReport(input)`. The HTML must include:

- `Fixture Installed`
- `Agent Used FlowCyto Tools`
- `Replay World Only`
- `Run Artifact`
- `SFT Export`

- [ ] **Step 4: Run the focused test and verify it passes**

Run:

```bash
npx vitest run tests/flowcytoVisibleDemoReport.test.ts
```

Expected: pass.

### Task 2: Demo Runner

**Files:**
- Create: `examples/flowcyto-gating-qc-demo/fake-openai-server.mjs`
- Create: `examples/flowcyto-gating-qc-demo/run-demo.mjs`
- Create: `examples/flowcyto-gating-qc-demo/README.md`

- [ ] **Step 1: Implement fake OpenAI-compatible server**

The fake server returns deterministic tool calls in this order:

```text
open_fcs -> get_plot_context -> upsert_gate -> compute_gate_stats -> validate_gate_qc -> submit_report -> final answer
```

- [ ] **Step 2: Implement `run-demo.mjs`**

The runner must:

1. Require built artifacts at `dist/src/cli/main.js`.
2. Install `flowcyto-gating-qc-basic@2026-06.0` from a supplied `--catalog`.
3. Run `datalox run --fixture-set flowcyto-gating-qc-basic@2026-06.0` against the fake OpenAI-compatible server.
4. Export one SFT frame with `datalox export sft`.
5. Call `createReplayToolRuntime(...).callTool(...)` with an unrecorded FlowCyto request and write `replay-miss-proof.json`.
6. Write `terminal.log`.
7. Generate `demo-report.html`.

- [ ] **Step 3: Document the demo command**

The README must show:

```bash
cd /Users/yifanjin/datalox-agent-replay
npm run build
node examples/flowcyto-gating-qc-demo/run-demo.mjs \
  --catalog /Users/yifanjin/datalox-replay-fixtures/catalog.json
open examples/flowcyto-gating-qc-demo/output/demo-report.html
```

### Task 3: Real Demo Verification

**Files:**
- Generated only: `examples/flowcyto-gating-qc-demo/output/**`

- [ ] **Step 1: Run the demo against the real fixture catalog**

Run:

```bash
npm run build
node examples/flowcyto-gating-qc-demo/run-demo.mjs \
  --catalog /Users/yifanjin/datalox-replay-fixtures/catalog.json
```

Expected: JSON summary with `status: "passed"`, `stopReason: "final_answer"`, `frameCount: 1`, and `replayMiss.liveFallback: false`.

- [ ] **Step 2: Inspect output artifacts**

Confirm these files exist:

```text
examples/flowcyto-gating-qc-demo/output/install.json
examples/flowcyto-gating-qc-demo/output/run-result.json
examples/flowcyto-gating-qc-demo/output/run/run.json
examples/flowcyto-gating-qc-demo/output/run/transcript.jsonl
examples/flowcyto-gating-qc-demo/output/export.json
examples/flowcyto-gating-qc-demo/output/flowcyto-qc.sft.jsonl
examples/flowcyto-gating-qc-demo/output/replay-miss-proof.json
examples/flowcyto-gating-qc-demo/output/terminal.log
examples/flowcyto-gating-qc-demo/output/demo-report.html
```

### Task 4: Final Verification

Run:

```bash
npm run check
npm test
git diff --check
```

Expected: all pass.
