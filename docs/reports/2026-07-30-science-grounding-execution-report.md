# Science Grounding Execution Report

Date: 2026-07-30
Repository cutoff:
`c74884096a99eceaae778a62c9eb54ffdffd3372`
Runtime compatibility pin:
`9fc984a3622a7a46e309f44c9f1181156e37ba13`

## Scope

This report is the completion record for the science-grounding work committed
from `a6638e4` through `c748840`. It separates provider-executed evidence,
projection conformance, world admission, agent verifier outcomes, and blocked
composition. A pass in one lane does not imply a pass in another.

The report does not claim that StarAMR or any AMR analysis ran, that a private
provider was accessed, or that the model results form a statistically
meaningful leaderboard.

## Completion Checklist

| Item | Outcome | Exact basis |
| --- | --- | --- |
| eLabFTW behavior | **Complete for the admitted behavior program** | Commit `a6638e456e517b7b788621d847377558b1361694`; disposable eLabFTW 5.6.10 create/list/get, successful PATCH, byte-identical duplicate PATCH, native invalid-target HTTP 400, and resulting-state readback were captured. "Complete" applies to this exact program, not the complete eLabFTW API. |
| Cromwell success | **Complete for the admitted behavior program** | Commit `2d7aae6e701383da64e651bbe149fa6c8680ac4e`; Cromwell 92 service read, distinct duplicate submissions, missing-source rejection, transient polling, outputs, logs, and terminal `Succeeded` metadata. |
| Cromwell failure | **Complete for the admitted behavior program** | Commit `2a5441863249437b5d32e6ed7b882e36e6123396`; distinct duplicate submissions, transient polling, terminal `Failed`, empty outputs, logs, terminal-abort HTTP 404, and metadata with return code `23` and `retryableFailure=false`. |
| Cromwell abort | **Complete for the admitted behavior program** | Commit `55ee40b917880b35554e32c38c117f0c26fbe9ac`; submit, transient `404`/`Submitted`/`Running`, successful and duplicate abort, unknown-workflow abort HTTP 404, `Aborting`, terminal `Aborted`, outputs, logs, and metadata. |
| First eLabFTW-Cromwell world | **Complete and admitted** | `science_elabftw_cromwell_v0`, introduced at `c780d9fd4525d5784fcf45116cb03d82c2599eb0`, task contracts completed at `17675848dad5af5ff05d9eead72d6c2e1e355b2a`, and runtime response-digest evidence added at `20dd88a5755e7a60953a021028e0f40c34ceed7c`. It has six families, twelve episodes, ten tools, thirteen reference trajectories, twelve exact-code negative trajectories, and three parity cases. |
| Codex baseline | **4/6 valid verifier passes** | Frozen API Gym `20dd88a5755e7a60953a021028e0f40c34ceed7c` and runtime `9fc984a3622a7a46e309f44c9f1181156e37ba13`; six valid, zero excluded, zero retries. Exact failures: `world.science_elabftw_cromwell_v0.analysis.required_failure_recovery` and `world.science_elabftw_cromwell_v0.analysis.required_stale_recovery`. |
| Claude Sonnet baseline | **5/6 valid verifier passes** | Same frozen commits; six valid, zero excluded, no timeout. The transient family failed with verifier code `analysis.required_transient_observation` and audit code `world.science_elabftw_cromwell_v0.analysis.required_transient_observation`. |
| Five historical upstream fixes | **3 `demonstrated`, 1 `same_result`, 1 `test_patch_incompatible`** | Exact before/after reconstruction and focused upstream tests; commit-level results are listed below. |
| Galaxy public pack | **Complete at its public, credential-free scope** | Commit `0c71c023c36e56e080105ff51e3bd5d4db2cd8d2`; 19 provider-observed GET operations, 43 contract-shaped candidates, and 0 provider-observed writes. |
| Local Galaxy control/data lifecycle | **Provider-executed sequence passed** | Commit `c74884096a99eceaae778a62c9eb54ffdffd3372`; history creation, FASTA upload, `queued -> running -> ok`, dataset and `upload1` provenance reads, exact 44-byte readback, and history purge completed. |
| Galaxy projection conformance | **Passed** | `galaxy_generated_fields_v1`, seed `20260730`, trace digest `sha256:454d36a3aa422fa58e1316fc39b52b8fa2bf5cd3d3425e5c85844bb205bb4906`, zero mismatches. This is projection evidence, not an additional provider execution. |
| StarAMR/tool-stack gate | **Blocked** | Every one of the five exact required tool versions returned HTTP 404. Workflow import and invocation were not attempted, no StarAMR or AMR analysis ran, and no Galaxy science world was composed. |
| Private provider promotion | **Not started** | No actual private tenant, sandbox, credential, or partner capture exists. Public documentation or a pointer to private documentation is not access and is insufficient for promotion. |

## What Pass Means

| Gate | Pass definition used here |
| --- | --- |
| Provider behavior capture | The pinned disposable fixture passed identity and boundary checks; the exact recipe executed; request/response and resulting-state evidence was sanitized; immutable artifact digests were recorded. It does not mean arbitrary provider behavior, production equivalence, or reset equivalence. |
| Historical upstream fix | `demonstrated` means the exact test-only patch failed on the first parent in the changed behavior and passed at the fix commit, while all BEFORE production blobs remained the first-parent blobs. `same_result` and `test_patch_incompatible` are classifications, not demonstrated fixes. |
| World admission | The deterministic builder, bundle hashes and structure, reference trajectories, exact-code negatives, parity cases, hidden verifier, and runtime admission checks all passed with the pinned runtime. It does not establish scientific correctness. |
| Agent episode | A valid, non-excluded harness run ended with the hidden world verifier returning `passed=true`. A failed verifier outcome can still be a valid measurement. |
| Public source pack | Provider-observed records and contract-shaped candidates are counted separately, and the pack validates structurally. Contract candidates and projection self-tests do not become provider evidence. |
| Connected Galaxy lifecycle | The exact captured control/data sequence completed against the pinned local service and cleanup evidence was recorded. It does not include StarAMR workflow execution. |
| Projection conformance | The bounded projection matched the selected captured reference trace after only the declared generated-field normalization. Projection unit tests and self-tests establish projection behavior, not provider behavior. |
| Galaxy science-world composition | This gate has not passed. It requires the exact StarAMR tool stack, provider-executed workflow import and invocation, terminal outputs and provenance, a sanitized trace, projection conformance, reset evidence, and world admission. |

## World And Model Results

The first six-family eLabFTW-Cromwell world is
[`worlds/science_elabftw_cromwell_v0`](../../worlds/science_elabftw_cromwell_v0/README.md).
Its families are:

1. `analysis_nominal_v1`
2. `analysis_transient_visibility_v1`
3. `analysis_existing_run_resume_v1`
4. `analysis_failure_recovery_v1`
5. `analysis_superseded_abort_v1`
6. `analysis_stale_revision_v1`

The world is a two-service analysis-control and qualification-evidence handoff.
Its captured WDL programs do not perform biological analysis, and its result
record is required to make no biological or scientific inference.

### Codex

The artifact at `/tmp/datalox-evals/codex-20dd88a/summary.json` records Codex
`0.146.0-alpha.3`, model `gpt-5.4-mini`, a 240-second timeout, MCP-only tools,
no shell tool, no unified exec, no retries, six valid runs, no exclusions, and
four verifier passes. The failed families and exact codes are:

| Family | Exact failure code |
| --- | --- |
| `analysis_failure_recovery_v1` | `world.science_elabftw_cromwell_v0.analysis.required_failure_recovery` |
| `analysis_stale_revision_v1` | `world.science_elabftw_cromwell_v0.analysis.required_stale_recovery` |

### Claude Sonnet

The accepted artifact at
`/tmp/datalox-evals/claude-sonnet-20dd88a-mcp-v1/` records Claude Code
`2.1.181`, requested model `sonnet`, six sequential runs, a 240-second hard
timeout, six valid runs, no exclusions, no timeouts, and five verifier passes.

The exact no-shell, deferred-MCP harness used:

```text
--setting-sources ""
--strict-mcp-config
--tools "ToolSearch,mcp__datalox__*"
--allowedTools "ToolSearch,mcp__datalox__*"
--disable-slash-commands
--no-chrome
--no-session-persistence
```

Each stream initialized with `ToolSearch` as the only advertised tool and
loaded Datalox MCP tools on demand. The verification report found no forbidden
tool in any run. No shell-capable tool was exposed. All 159 artifact checks
passed. The sole failed family was `analysis_transient_visibility_v1`, with
verifier code `analysis.required_transient_observation` and fully qualified
audit code
`world.science_elabftw_cromwell_v0.analysis.required_transient_observation`.

Earlier Claude harness attempts are not part of the Sonnet 5/6 result:

- `/tmp/datalox-evals/claude-20dd88a`: seed 0 was invalid and excluded because
  the init event exposed `mcp_servers=[]` and `tools=[]`; five seeds were not
  attempted.
- `/tmp/datalox-evals/claude-20dd88a-mcp-v2`: seed 0 was invalid and excluded
  because Datalox remained `pending` and `tools=[]`; five seeds were not
  attempted.
- `/tmp/datalox-evals/claude-20dd88a-mcp-v3`: seed 0 was invalid and excluded
  for the same pending-server/empty-tool condition; five seeds were not
  attempted.
- `/tmp/datalox-evals/claude-20dd88a-mcp-v4` is a valid six-run Claude Haiku
  baseline, not a Sonnet run, and is not included in the Sonnet result.

These six-episode, one-run-per-family measurements are useful integration
baselines. They are not statistically meaningful model rankings or a
leaderboard.

## Historical Upstream Validation

The artifact at `/tmp/datalox-upstream-unit-validation-v1/` reconstructed
BEFORE as each fix's first parent plus only the exact published test-file diff,
and AFTER as the clean fix commit. The verification script exited `0`.

| Provider | Exact fix commit | Classification | Exact result |
| --- | --- | --- | --- |
| eLabFTW | `689227307af3640fa3ecdd0da79d32e9bcb36aa1` | `demonstrated` | BEFORE: 6 tests, 15 assertions, 1 changed-test failure. AFTER: 6 tests, 21 assertions, passed. |
| eLabFTW | `a920df5219d8ac97980d2e849bd4fc533a217553` | `demonstrated` | BEFORE: 30 tests, 86 assertions, 1 changed-test error and 1 changed-test failure. AFTER: 30 tests, 90 assertions, passed. |
| eLabFTW | `41ae147ea5033c7f91355927f40836c558c52851` | `same_result` | The exact sequential overlap test passed on both parent and fix: 33 tests, 106 assertions. It did not reproduce concurrent overlap. |
| Cromwell | `063911695ffe93be183b419e17669fb956d475ab` | `demonstrated` | BEFORE: 5 tests, 3 added `Containers` coercion failures. AFTER: all 5 passed. |
| Cromwell | `9f610ee31936923eb328604e7f2a416dd8655c71` | `test_patch_incompatible` | BEFORE test compilation failed because `GcpBatchExitCode.GenericFailure` did not exist in the parent, so the changed spec did not execute. AFTER: 26 tests passed, which alone is not a demonstration. |

## Galaxy Evidence

### Public source pack

[`source_packs/apis/galaxy/2026-07-21`](../../source_packs/apis/galaxy/2026-07-21/source_pack.json)
contains 62 normalized operations:

- 19 provider-observed credential-free GET operations;
- 43 contract-shaped candidates;
- 24 write candidates;
- 0 provider-observed writes.

The public pack does not ground successful authenticated/private reads or any
write. Its local-shadow declarations and self-tests remain local construction
evidence.

### Connected local sequence

[`connected_history_fasta_v1`](../../source_packs/apis/galaxy/2026-07-30/behavior_cases/connected_history_fasta_v1/README.md)
records one disposable, loopback-only Galaxy 26.1.rc1 sequence:

```text
create history
  -> submit input.fa through upload1
  -> observe queued
  -> observe running
  -> observe terminal ok
  -> read dataset
  -> read upload1 provenance
  -> read back the exact 44 bytes
  -> purge history
```

The input and readback digest is
`sha256:d044ffc156b7f0a06cd252ec80ab8f0c0ef40ee57bbe3b0d4139f70bd8cbd39c`.
History purge succeeded. Disposable-user deletion returned HTTP 403, after
which fixture teardown still removed the container and its named volume.

The committed
[`projection_report.json`](../../source_packs/apis/galaxy/2026-07-30/conformance/projection_report.json)
has `passed=true` and no mismatches for the selected representative trace.
That report says the bounded projection conforms to the capture under the
declared normalization; it is not a second provider run.

### StarAMR blocker

The pinned local Galaxy image returned HTTP 404 for every exact tool required
by `AMR Gene Detection (release v1.1.7)`:

1. `toolshed.g2.bx.psu.edu/repos/iuc/staramr/staramr_search/0.11.0+galaxy3`
2. `toolshed.g2.bx.psu.edu/repos/iuc/amrfinderplus/amrfinderplus/3.12.8+galaxy0`
3. `toolshed.g2.bx.psu.edu/repos/iuc/abricate/abricate/1.0.1`
4. `toolshed.g2.bx.psu.edu/repos/iuc/tooldistillator/tooldistillator/1.0.4+galaxy0`
5. `toolshed.g2.bx.psu.edu/repos/iuc/tooldistillator_summarize/tooldistillator_summarize/1.0.4+galaxy0`

Therefore:

- StarAMR workflow import was not attempted;
- StarAMR workflow invocation was not attempted;
- StarAMR and AMR analysis did not run;
- no StarAMR output or scientific result exists;
- no eLabFTW-Galaxy AMR science world was composed.

## Immutable Pins

| Surface | Pin |
| --- | --- |
| API Gym status cutoff | `c74884096a99eceaae778a62c9eb54ffdffd3372` |
| Agent-evaluation API Gym | `20dd88a5755e7a60953a021028e0f40c34ceed7c` |
| Gated runtime | `9fc984a3622a7a46e309f44c9f1181156e37ba13` |
| eLabFTW fixture | `elabftw/elabimg:5.6.10@sha256:a4dd2264b6fa40bb250ca68d3845afa442bb15c29aed95cd444786084eb30e67` |
| eLabFTW MySQL fixture | `mysql:8.4@sha256:8dbcf531a03aade657e181b9cf2f1d1803ce621a1d55610cb44cb531ab7d7db6` |
| Cromwell release | version `92`, tag commit `e94341fdb32f0526b4338f9e1206a84b936dfcac`, JAR `sha256:e0e3a050d4124e81369a79059e5774142b2f06bd89df4a0b035f559db85cedf5` |
| Galaxy fixture source | commit `3d62013917dfc9e285c2be923b7b5b2034469d6f` |
| Galaxy local image | `sha256:8e5b825e2d064707caa9f564bd5280bef0a79b666ccfee116ae7c311657eec62` |
| Galaxy OCI index | `sha256:100a37301e5f4fb3ac560be5cec7ec5629400673cef8511ea2a8c17b4c8b7399` |
| Historical Cromwell test base | `m.daocloud.io/docker.io/library/eclipse-temurin@sha256:52e47dff911bd9d49fceb1b67b486854fd7e2d90d31e15a306a41acd0b2895b2` |
| Historical Cromwell derived test image | `sha256:be70bb16a2411f7446aec846a24011a912ab5991e371eb910123036a0874645a` |

The Galaxy receipt records that the OCI index was supplied by the capture
request and was not independently verified locally. The local image ID and
source commit were inspected.

## Artifact Locations

Committed evidence:

- [`worlds/science_elabftw_cromwell_v0`](../../worlds/science_elabftw_cromwell_v0/README.md)
- [`source_packs/apis/elabftw/2026-07-30`](../../source_packs/apis/elabftw/2026-07-30/behavior_cases/experiments_patch_complete_v1/README.md)
- [`source_packs/apis/cromwell/2026-07-30`](../../source_packs/apis/cromwell/2026-07-30/behavior_cases/workflow_success_v1/README.md)
- [`source_packs/apis/galaxy/2026-07-21`](../../source_packs/apis/galaxy/2026-07-21/source_pack.json)
- [`source_packs/apis/galaxy/2026-07-30`](../../source_packs/apis/galaxy/2026-07-30/behavior_cases/connected_history_fasta_v1/README.md)

Machine-local execution artifacts:

- `/tmp/datalox-evals/codex-20dd88a/summary.json`
- `/tmp/datalox-evals/claude-sonnet-20dd88a-mcp-v1/aggregate.json`
- `/tmp/datalox-evals/claude-sonnet-20dd88a-mcp-v1/verification_report.json`
- `/tmp/datalox-upstream-unit-validation-v1/summary.json`
- `/tmp/datalox-upstream-unit-validation-v1/README.md`

The `/tmp` artifacts are not committed and must be treated as machine-local,
ephemeral evidence. This report records their current contents but does not
turn them into durable repository artifacts.

## Known Limitations

- "Complete behavior" means complete for each exact admitted recipe, not broad
  eLabFTW or Cromwell API coverage.
- The eLabFTW-Cromwell world uses capture-derived projections plus
  benchmark-defined timing, revisions, joins, and qualification meaning.
- The captured Cromwell WDL programs do not perform biological analysis.
- Provider production equivalence and reset equivalence are not claimed.
- Galaxy's 85-poll duration is captured observation; the projection claims
  only ordered `queued -> running -> ok`, not provider timing semantics.
- The Galaxy run proves a FASTA upload lifecycle, not StarAMR availability,
  workflow execution, AMR analysis, or scientific correctness.
- The Galaxy OCI index was not independently verified locally.
- Projection conformance and projection self-tests do not add provider
  evidence.
- The model baselines are pinned to API Gym `20dd88a`, before the two Galaxy
  commits. They were not rerun at `c748840`.
- No private provider was promoted because no actual private access exists.
- The upstream historical-fix classifications test those exact commits and
  focused tests; they do not establish general provider quality.

## Next Exact Prerequisites

1. Build a disposable Galaxy fixture that contains all five exact required
   StarAMR workflow tool versions, with immutable Galaxy, Tool Shed wrapper,
   container, database, and reference-data pins.
2. Require a fail-closed preflight in which all five exact tool IDs resolve at
   the pinned versions before workflow import is allowed.
3. Import the exact `AMR Gene Detection (release v1.1.7)` workflow, invoke it
   with a pinned immutable input, and capture terminal status, outputs,
   completeness, provenance, native failures, and teardown. Repeat the
   connected sequence and prove reset before promotion.
4. Sanitize and commit that provider-executed trace, then make the bounded
   Galaxy projection pass differential conformance. Projection tests remain
   projection evidence.
5. If the original three-service AMR architecture remains the target, execute
   and conform the pinned MinIO current/stale artifact lifecycle before world
   composition.
6. Compose the eLabFTW-artifact-Galaxy world only after those provider gates
   pass. Admit oracle, exact-code empty and required negatives, at least one
   alternative recovery, reset, hidden-state boundaries, and verifier latency.
7. Obtain scientific review of the selected AMR workflow's identity,
   freshness, completeness, provenance, and interpretation obligations before
   making a scientific-validity claim.
8. Promote any private provider only after actual authorized access produces
   a sanitizable sandbox or partner capture. Documentation alone is not a
   substitute.
