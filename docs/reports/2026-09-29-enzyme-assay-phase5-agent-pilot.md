# Enzyme activity Phase 5 external-agent pilot

Phase 5 produced five supported reports from six final-contract episodes. The
nominal, delayed-transfer, interrupted-series, reagent-background, and
plate-lineage families passed the independent verifier. The high-activity
fresh-reaction recovery failed: the agent correctly rejected the first trace
and began a fresh factor-2 reaction on plate 2, but stopped after its first of
seven liquid transfers and submitted an unresolved report while a usable result
was still feasible.

This is a small functionality pilot inside the authored model. It is not a
physical validation, a success-rate estimate, a time-savings claim, or evidence
of training value.

## Frozen pilot configuration

- API Gym base commit: `f39ec165c2f0b8541069eb9508631e492d730053`
- gated-runtime commit: `87691ba1417c6ae8eab46b46588158798d3a2d3b`
- controller/test interpreter: CPython 3.12.5
- native worker: `opentrons==9.1.1` and
  `opentrons-shared-data==9.1.1`
- host: Codex CLI 0.141.0 through the enforced Datalox host wrapper
- model: `gpt-5.5`, low reasoning; the attempted cheaper
  `gpt-5.4-mini` was not available to this ChatGPT-authenticated CLI
- per-episode limits: 70 MCP calls, 900 wall-clock seconds, 15,000,000
  recorded tokens, and 500,000 non-cached tokens
- agent input: the public task, MCP schemas and returned public observations;
  arithmetic used ordinary Python in an otherwise empty temporary workspace

The read-only host sandbox did not technically deny reads outside the temporary
workspace. Trace audit found no access to API Gym or runtime source, seeds,
private fixtures, the run database, or verifier implementation. Four eligible
runs opened only the wrapper-selected public Datalox host-guidance skill before
the assay. Exact wrapped prompts, model events, public tool results, native
receipts, final responses, run exports, and visualizations remain under
`runs/enzyme_activity_phase5/gpt-5.5-low/`, which is intentionally ignored by
Git because it contains full local trajectories.

## Final-contract cohort

| Family | Verifier | Submitted rate | Absolute model error | MCP calls | Authoritative world operations | Modeled tips | Plates used | Logical time (s) | Operator requests | Recorded / non-cached tokens |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Nominal | pass | 0.0375038341 | 0 | 36 | 31 | 6 | 1 | 195.0 | 1 | 4,250,644 / 169,364 |
| High-activity recovery | fail | — | — | 38 | 36 | 7 | 2 | 195.0 | 1 | 4,161,078 / 180,534 |
| Delayed acquisition | pass | 0.0344577605 | 0 | 51 | 33 | 6 | 1 | 306.0 | 1 | 5,872,414 / 210,206 |
| Interrupted series | pass | 0.0353558828 | 0 | 35 | 32 | 6 | 1 | 186.0 | 1 | 4,103,441 / 190,481 |
| Reagent background | pass | 0.0365048718 | 0 | 36 | 32 | 6 | 1 | 186.0 | 1 | 4,436,095 / 174,207 |
| Sample/plate lineage | pass | 0.0334680067 | 0 | 37 | 32 | 6 | 1 | 186.0 | 1 | 4,353,910 / 193,782 |

The five accepted numerical reports matched the verifier's independently
recomputed rate at the stored precision. Across the cohort, the agent made 233
MCP invocations: six successful `get_task` calls, 196 authoritative world
operations, and 31 non-authoritative attempts. The latter comprised validation
rejections and 12 generic shadow `gate_request` calls in the delayed episode.
There were no unnecessary experimental repeats. The high-activity plate-2
attempt was scientifically necessary but incomplete.

Modeled consumable and workflow totals were 37 tips, 37 dispenses, seven assay
plates touched, six reader jobs, six operator requests, and 1,254 logical
seconds. Aggregate model accounting was 27,177,582 recorded tokens, including
1,118,574 non-cached tokens. Dollar cost is unavailable from the
ChatGPT-authenticated CLI, so no price is inferred.

## Failures preserved during bring-up

The initial failed runs were retained rather than replaced. They exposed and
led to root fixes for:

1. implementation schemas that drifted from `world/tools.json`, preventing MCP
   startup;
2. missing explicit MCP subprocess environment and tool-approval configuration
   in the external host harness;
3. public observations that omitted valid tip addresses and public task
   material that omitted reaction composition, the factor-1 assay baseline,
   the 0.02–1.5 fit interval, and terminal report semantics; and
4. a high-activity condition that still admitted a 90-second in-range window
   for some valid preparation orders.

After these fixes, MCP startup and public contract tests passed. The final
recovery failure is attributed to model behavior, not infrastructure: all
required public information and resources were present, but the agent stopped
well below its call and token caps. This is the main Phase 5 result to carry
forward. A future pilot should test a lower-context host or a planning policy
that budgets the complete second preparation before beginning it; that policy
belongs in the agent harness, not API Gym.

## Evidence selection

The six cohort directories are:

- `enzyme-activity-nominal-01-attempt-06`
- `enzyme-activity-high-01-attempt-03`
- `enzyme-activity-delayed-01`
- `enzyme-activity-interrupted-01`
- `enzyme-activity-background-01`
- `enzyme-activity-lineage-01`

Each contains `rollout_config.json`, `wrapper_result.json`,
`mcp_server_stderr.log`, `phase5_result.json`, `run_export.json`, and the final
response. Passing episodes also contain `visualization.json`.

## Verification

- API Gym enzyme suite with the pinned native worker: 80 passed.
- API Gym instrument-model suite in the composed controller environment: 96
  passed and four optional checks skipped.
- Relevant gated-runtime worker, lifecycle, MCP, and visualization slice: 57
  passed and 12 optional checks skipped.
- Ruff checks for the changed Python files and `git diff --check` passed.

An additional full gated-runtime baseline run produced 5,369 passes and 123
skips, with 25 failures and 14 setup errors in unrelated provider worlds and
generated-artifact checks. Those failures predate this pilot checkout and
include manifests referring to absent `skills/SKILL.md` files and stale
generated provider artifacts. No gated-runtime file was changed for Phase 5;
the pinned enzyme integration slice above is green.
