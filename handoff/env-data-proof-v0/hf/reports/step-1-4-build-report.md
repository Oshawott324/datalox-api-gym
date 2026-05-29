# Step 1-4 Build Report

Updated: 2026-05-29

This report records the concrete build state for the first public
`scientific-data-qc-basic@2026-06.0` fixture-world slice.

## Scope

Primary worlds:

- `fastq-qc-nanopore-fail-001`
- `single-cell-pbmc3k-qc-summary-001`
- `flowcyto-fcs-compensation-metadata-001`
- `protein-structure-ap5a-prep-001`
- `rnaseq-alignment-qualimap-low-mapq-001`

Generated files live under:

```text
handoff/env-data-proof-v0/worlds/<world_id>/
```

## Step 1: Frozen Task Specs

Command:

```bash
node handoff/env-data-proof-v0/tools/scientific-data-tools.mjs build-step1
```

Result:

```text
step1 passed: 5 task specs
```

Output:

- 5 `task.spec.json` files
- Each task has a stable world id, task type, fixture scope, allowed tools,
  expected answer class, expected next action, and output schema reference.

## Step 2: Provenance Records

Command:

```bash
node handoff/env-data-proof-v0/tools/scientific-data-tools.mjs build-step2
```

Result:

```text
step1 passed: 5 task specs
step2 passed: 5 provenance records
```

Output:

- 5 `provenance.json` files
- Each record pins public source URLs, source kind, source access, license
  notes, fixture extraction policy, and the evidence ids later used by tools.

## Step 3: Derived Fixture Artifacts

Command:

```bash
node handoff/env-data-proof-v0/tools/scientific-data-tools.mjs build-step3
```

Result:

```text
step1 passed: 5 task specs
step2 passed: 5 provenance records
step3 passed: derived artifacts and manifests
```

Output:

- 16 derived artifact files
- 5 `artifacts/manifest.json` files
- Artifacts are small text, table, and JSON extracts from real public sources.
  The build does not publish full upstream raw datasets.

## Step 4: Tool Catalogs And Observations

Command:

```bash
node handoff/env-data-proof-v0/tools/scientific-data-tools.mjs build-step4
```

Result:

```text
step1 passed: 5 task specs
step2 passed: 5 provenance records
step3 passed: derived artifacts and manifests
step4 passed: tool catalogs and observations
```

Output:

- 5 `tools/tool-catalog.json` files
- 5 `tools/tool-observations.jsonl` files
- 26 total deterministic tool observations

Observation count by world:

```text
6  flowcyto-fcs-compensation-metadata-001
5  fastq-qc-nanopore-fail-001
5  protein-structure-ap5a-prep-001
5  rnaseq-alignment-qualimap-low-mapq-001
5  single-cell-pbmc3k-qc-summary-001
```

## Non-Claims

This build has not yet produced:

- replay bundles
- baseline failure runs
- teacher/verifier-passing trajectories
- `sft_frame.v1`
- locked train/dev/test evaluation command

Those are Step 5+ work. Step 1-4 only proves that the initial fixture worlds,
source provenance, derived artifacts, and deterministic tool observations can
be built and validated.

## Local Domain Tool Note

The local `/Users/yifanjin/datalox-flow-cyto-mcp` repo already exposes the
right kind of agent-native flow cytometry path for harder follow-up tasks:
`open_fcs`, `get_plot_context`, `upsert_gate`, `compute_gate_stats`,
`validate_gate_qc`, and `submit_report`.

This Step 1-4 slice does not use those tools. The current flowcyto world is a
text/table metadata fixture, not a vision/gating workflow. Step 5+ baseline and
teacher runs should use the existing Flowcyto MCP path if the demo expands into
real gating tasks.
