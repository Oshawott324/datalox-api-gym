# Long-Horizon Lab Agent Directions

Internal planning note for Yifan and Zheng.

The current PyLabRobot/OT-2 demo proves that API Gym can run a real dry-run
lab workflow with tool traces, mutable lab state, and verifier evidence. The
next step should not be another demo. It should be a deeper artifact that can
stand as a benchmark, paper direction, or Hugging Face release.

The main constraint: do not claim novelty on "we verify final state." State
verification is necessary, but it is no longer enough as the headline. The
novelty has to come from long horizon, timed dynamics, process invariants,
failure attribution, grounded dry-run semantics, or training signal from state
diffs.

## Current Decision Update: 2026-07-01

The next serious build should not be an Opentrons-only world.

Opentrons is a strong source pack for physical lab automation because it has
public API/schema evidence and local simulation/execution tooling. But the
benchmark identity should be a multi-provider lab operations workflow:

```text
lab_campaign_ops_v0
  = ELN/LIMS task state
  + robot/protocol dry-run
  + instrument/readout data
  + result upload or decision record
  + hidden verifier over cross-system consistency
```

This reframes `LabLongRun-Wet` as the calibration kernel, not the final public
benchmark identity.

The current recommended build is:

```text
lab_campaign_ops_v0
  source packs:
    opentrons_http_v1
    benchling_assay_v1
    tetrascience_context_v1
```

Task unit:

```text
objective
  + declared provider-shaped tool families
  + source-backed request/response fixtures
  + isolated sandbox state
  + hidden verifier
  + exact known-bad failure admission
```

Examples of stronger task families:

- OD600 QC campaign handoff across ELN, robot analysis, instrument data, and
  assay-result upload.
- Plate-map mismatch where ELN worklist and robot protocol disagree.
- Stale instrument data uploaded to a current assay.
- Robot protocol analysis error that must be repaired or refused.
- Wrong sample/entity result upload despite valid-looking data.
- Dry-run boundary violation where an agent attempts live execution.

The detailed next-build doc is:

```text
docs/reports/lab-campaign-ops-v0-next-build.md
```

Implication:

- Do not scale to 1,000 Opentrons variants.
- Do not ask Zheng to invent biology or provider semantics.
- Do use Zheng or a coding agent for source-pack schema, task generation,
  sandbox state, admission, verifier, and export machinery.
- Do use Yifan/domain review for provider selection, workflow semantics, and
  public claims.

## Decision Zheng Should Make

Pick one primary research anchor:

1. Long-horizon timed/stochastic lab benchmark.
2. Agent-vs-environment failure attribution under stochastic dynamics.
3. Temporal/provenance verifier engine for dry-run worlds.
4. State-diff process rewards for training long-horizon agents.
5. Lab-scaffold realism as a benchmark design standard.

The strongest path is probably:

```text
LabLongRun-Bench
  + timed/resource/stochastic lab runtime
  + verifier-backed agent-vs-environment failure attribution
  + state-diff/process-invariant evidence
```

This would make the current demo a teaser, not the contribution.

The deeper framing is projection, not simulation:

```text
controlled dry-run projection of a costly scientific workflow
  + documented structural/action/state assumptions
  + documented temporal/stochastic assumptions
  + seeded replay
  + hidden verifier and failure attribution
```

Detailed plan:

```text
docs/reports/lablongrun-projection-stochastic-plan.md
```

## Adaptyv Qualification Branch

There is one branch worth qualifying before expanding OT-2/liquid-handling
tasks: an Adaptyv Foundry API dry-run world.

This should be gated by demand validation, not built speculatively. The core
question is:

> When customers let agents or scripts interact with the Foundry API, do those
> agents ever waste real submissions, quotes, budget, or multi-week cycles
> because they made a bad planning, tool-use, or result-interpretation decision?

If yes, `adaptyv_foundry_dryrun_v0` may be a stronger API Gym-native wedge than
pipette/deck simulation:

```text
agent designs protein campaign
  -> Foundry API dry-run projection
  -> verifier checks cost, quote, lifecycle, result interpretation, provenance
```

Do not build the full world before this call. The thin proof, if qualified,
should cover only campaign planning, budget/quote discipline, and
result-interpretation correctness.

Detailed qualification plan:

```text
docs/reports/adaptyv-qualification-plan.md
```

## Recommended Solid Build: LabLongRun-Wet v0

If we want this to be more than a toy, do not start by adding more domains.
Build one wet-lab long-horizon slice deeply enough that another lab-agent
builder would recognize the failure modes.

Working title:

```text
LabLongRun-Wet v0:
  source-grounded dry-run tasks for long-horizon liquid-handling agents
```

Core question:

> Can a tool-using agent execute a long wet-lab dry run without violating
> physical, temporal, resource, evidence, or provenance constraints?

This should be the flagship task family:

```text
OD600 serial-dilution QC gate
```

The agent receives a protocol note, plate map, reagent inventory, prior run log,
and allowed lab tools. It must inspect the dry-run deck, execute a serial
dilution or transfer plan across multiple wells, wait or account for required
timing, read OD600, handle one injected issue, and submit a protocol decision
with evidence.

This is stronger than the current `unitelabs_plate_qc_v0` demo because the
agent must maintain state over a whole lab procedure, not just complete one
transfer and one read.

### What v0 Must Include

One world family:

- Extend `unitelabs_plate_qc_v0` or create a sibling lab world.
- Keep the dry-run boundary: no live hardware, no live provider execution.
- Ground tool semantics from public package/docs/contracts where possible:
  PyLabRobot or Opentrons concepts for deck/labware/liquid-handling behavior,
  plus UniteLabs contract evidence for API-shaped workflow/run/log surfaces.

One flagship workflow:

- 96-well source and assay plates.
- Finite tip racks.
- Finite reagent/source volumes.
- Explicit well volume and concentration ledger.
- OD600 readout artifacts with ids and timestamps.
- Protocol decision that must cite fresh readout evidence.

Six scenario templates:

1. Nominal serial dilution and QC decision.
2. Low source volume requiring replanning before overdraw.
3. Tip exhaustion or contaminated-tip risk requiring correct tip handling.
4. Instrument busy/read-delay case requiring the agent to wait or inspect.
5. Stale readout case where the agent must re-read before deciding.
6. Partial dispense/read failure requiring recovery and final attribution.

Target horizon:

- v0: 40 to 80 tool calls per task.
- stretch: 100 to 200 tool calls for 96-well variants.

Do not claim the protocol is scientifically novel. The claim is that the agent
must preserve lab-state correctness across a long, stateful, source-grounded
dry run.

### Required State Model

The world should track at least:

- deck layout and loaded labware
- pipette/tip state
- tip availability and contamination status
- well volumes
- source/reagent depletion
- derived dilution/concentration state
- instrument/readout status
- event time
- readout freshness
- protocol artifacts inspected by the agent
- workflow notes and final protocol decision

This state must remain hidden from the agent except through tools and artifacts.
The verifier can read it directly.

### Required Verifier Claims

The hidden verifier should produce machine-readable violations in these groups:

- `terminal_state`: final volumes, target wells, decision, expected artifacts
- `resource`: no overdraw, no negative volume, no missing tips
- `contamination`: no unsafe tip reuse across incompatible wells
- `temporal`: no read before required timing, no decision from stale readout
- `provenance`: final decision cites the actual readout ids and inspected files
- `recovery`: injected issue was detected and handled rather than ignored
- `live_boundary`: no live hardware/provider execution was attempted

The benchmark should report both final pass/fail and these violation categories.

### Required Experiments

Run small, concrete experiments. Do not wait for a huge dataset.

Minimum:

- 10 tasks across the six scenario templates.
- 3 seeds per task.
- 2 to 3 agent configurations.
- At least one cheap live model for smoke testing.

Report:

- final pass rate
- pass rate by horizon length
- violation rate by category
- recovery success rate
- stale-evidence failure rate
- transcript-review false positive examples
- seeded replay examples for failure attribution

The most important table should show that transcript-level review misses
failures that the state/temporal/provenance verifier catches.

### Paper-Scale Task Count

The 10-task set above is only the calibration pilot. A paper-scale benchmark
should not hand-author 1,000 tasks one by one. It should define a small number
of source-grounded scenario templates, then generate many task instances from
validated parameters.

Target paper scale:

```text
1,000 tasks total
  = 20 scenario templates
  x 50 seeds or parameterizations each
```

Alternative smaller first paper scale:

```text
600 tasks total
  = 12 scenario templates
  x 50 seeds each
```

The generated tasks should vary along controlled axes:

- plate layout
- source and reagent volumes
- target wells
- dilution factors
- QC threshold bands
- required readout timing
- instrument busy windows
- missing/stale prior evidence
- tip availability
- contamination constraints
- injected dispense/read failures
- distractor protocol notes or irrelevant prior logs
- required recovery action
- horizon length

The benchmark should publish difficulty bins, not only a flat task list:

- `short`: 20 to 40 expected tool calls
- `medium`: 40 to 80 expected tool calls
- `long`: 80 to 150 expected tool calls
- `stress`: 150 to 250 expected tool calls

The paper should report performance by bin. If every task is short, the
benchmark does not really test long-horizon lab agents.

### Generation Pattern From Recent Benchmarks

Recent agent benchmarks point to the same construction pattern:

- ClawForge generates executable tasks from scenario templates, grounded slots,
  initialized state, reference trajectories, validators, and metadata.
- AppWorld task generators have setup, solution, and evaluation components:
  setup creates a valid initial state, the solution proves solvability, and
  evaluation checks final database state.
- TaskWeaver/LORE uses a controllable rule-based generator to vary horizon and
  difficulty.
- LabVLA/LabUtopia uses procedural scene generation and OOD perturbations to
  test generalization rather than one fixed scene.
- Odysseys takes the opposite route: human browsing histories for realism, but
  less controllability than generator-backed tasks.

The lesson for LabLongRun-Wet:

> Hand-calibrate templates; generate task instances. Do not hand-write 1,000
> tasks, and do not produce random synthetic tasks without oracle/verifier
> admission.

Hard-coded tasks are acceptable only for:

- the gold calibration set
- debugging individual verifier predicates
- paper examples and qualitative case studies

Paper-scale tasks should be generated from hand-designed templates. Each
template should encode a real lab failure mode and a task construction contract,
not only text variations.

### Task Generator Requirement

To reach 1,000 tasks credibly, we need a task generator, not a pile of JSON
files. But there are two different jobs here:

```text
generator machinery
  -> engineering-owned

biological/lab scenario content
  -> source-backed and domain-reviewed
```

Zheng should own the generator machinery: rendering templates, seeding
parameterizations, creating initial state, running oracle/admission checks,
writing artifacts, and producing suite manifests. Zheng should not invent
biological failure modes or decide which lab protocol variants are meaningful
from scratch.

The biology/lab content should come from:

- public package/docs/contracts for action semantics
- public protocol examples or assay docs where possible
- narrow review from a domain person only when the task content becomes
  scientifically consequential
- partner/customer input if Adaptyv or another live scientific API qualifies

Generator input:

```text
scenario_template
seed
parameter_ranges
fault_policy
difficulty_target
```

Generator output:

```text
task.json
agent_task.json
initial_state.sqlite
protocol_note.md
plate_map.csv
reagent_inventory.csv
prior_run_log.jsonl
expected_oracle_plan.json
verifier_expectations.json
```

Each scenario template must define:

```text
template_id
lab_failure_mode
source_refs
parameter_ranges
initial_state_constraints
visible_artifact_recipe
fault_policy
oracle_strategy
known_bad_plan_strategy
verifier_predicates
difficulty_targets
ood_perturbations
```

Each scenario template should also carry a `domain_source_status`:

```text
source_grounded
domain_reviewed
speculative_calibration_only
```

Rules:

- `source_grounded`: can be used in the public benchmark if citations and
  admission checks pass.
- `domain_reviewed`: preferred for paper-scale or high-value dataset tasks.
- `speculative_calibration_only`: allowed for internal infrastructure testing,
  but should not be counted as a real benchmark task.

Do not use the Ann Arbor researcher network for routine generator engineering.
Use it only for high-leverage review:

- Are these failure modes biologically/lab-operationally plausible?
- Are these protocol variants realistic enough for a public dataset?
- Are there missing failure classes that would make the benchmark look naive?
- Are result-interpretation checks scientifically meaningful?

Until we are building a large valuable dataset, keep expert asks small and
specific.

Each generated task must pass validation before it is admitted:

- initial state is physically possible
- required goal is reachable
- oracle plan passes the verifier
- at least one known bad plan fails the verifier
- expected horizon matches the declared difficulty bin
- no task leaks hidden verifier state into agent-visible artifacts
- no duplicate task under a different seed
- generated artifacts are internally consistent
- generated task maps back to exactly one scenario template and failure mode
- task is not solved by a trivial shortcut that bypasses the intended lab
  process
- verifier predicates are neither vacuous nor impossible

The oracle plan does not need to be agent-visible. It is a benchmark
construction tool used to prove the task is solvable.

The generator should output both task instances and a manifest that records why
each task was admitted:

```text
task_id
template_id
seed
difficulty
expected_horizon
admission_checks
oracle_result_ref
known_bad_result_refs
verifier_predicates
source_refs
```

This admission manifest is important for paper credibility. It lets reviewers
see that the benchmark is not a pile of prompts and that failures are tied to
known lab-state invariants.

### Template Taxonomy For 1,000 Tasks

Use scenario templates rather than disconnected tasks. A realistic v1 taxonomy:

1. nominal serial dilution
2. serial dilution with low source volume
3. serial dilution with finite tip pressure
4. contamination-sensitive transfer
5. missing plate-map evidence
6. stale prior run log
7. stale OD600 readout
8. instrument busy window
9. required incubation delay
10. partial dispense failure
11. failed read requiring retry
12. ambiguous QC band requiring confirmatory read
13. wrong initial deck slot in prior note
14. reagent depletion requiring replanning
15. multi-source pooling
16. duplicate target-well conflict
17. carryover-risk prevention
18. recovery after interrupted plan
19. long 96-well batch with sparse QC reads
20. long 96-well batch with one hidden injected fault

This makes the paper claim stronger: the benchmark is not 1,000 arbitrary
prompts; it is a controlled distribution over long-horizon lab failure modes.

### HF Release Shape

The public artifact should look like a benchmark, not a demo directory:

```text
LabLongRun-Wet-v0/
  README.md
  dataset_card.md
  tasks.jsonl
  source_refs.json
  worlds/unitelabs_or_lablongrun/spec.json
  artifacts/
    protocol_notes/
    plate_maps/
    reagent_inventories/
    prior_run_logs/
  examples/
    successful_run_export.json
    failed_stale_readout_run_export.json
    failed_contamination_run_export.json
  verifier/
    violation_schema.json
    example_verifier_results.jsonl
  trajectories/
    state_diffs.jsonl
    tool_calls.jsonl
```

The dataset card should say plainly:

- dry run only
- no live hardware
- no private partner data
- source-grounded where cited
- scientific outcomes are simulated
- evaluation target is lab-agent process correctness, not biology discovery

### What Makes This Solid

This becomes solid when all of these are true:

- The agent has to inspect external artifacts before acting.
- The run is long enough that memory/state errors happen naturally.
- The environment has resources, timing, and hidden mutable state.
- The verifier checks process invariants, not just a final answer.
- At least one failure requires recovery, not just prevention.
- The release includes trajectories and state diffs, not only scores.
- A lab-agent builder can map the failure modes to real wet-lab automation.

This is the default recommendation unless Zheng finds one fatal grounding issue.

## Baseline We Already Have

API Gym already owns:

- source-backed dry-run worlds
- session manifests
- MCP/action interfaces
- mutable episode state
- hidden verifier execution
- tool traces
- run exports
- dry-run lab workflow examples

That is a useful substrate, but a serious benchmark needs stronger task depth:

- longer horizons
- timing
- resource depletion
- stochastic measurements or faults
- recovery after partial failure
- stale observations
- temporal process checks
- replayable trajectories

## Direction 1: LabLongRun-Bench

One-sentence claim:

> We introduce a dry-run benchmark for long-horizon lab agents where actions are
> timed, stateful, resource-constrained, and verifier-checked over full
> trajectories.

Why it is deeper than the demo:

- The current demo is a single dry-run workflow.
- This direction turns it into a benchmark family.
- The benchmark tests whether agents stay correct across many state-changing
  actions, not whether they can call one tool.

What to build for v0:

- 10 to 20 tasks in one lab automation family.
- 30 to 80 tool calls per task.
- Task families:
  - nominal serial dilution
  - plate transfer with finite tips/reagents
  - OD600 decision workflow
  - recovery after partial dispense or read failure
  - stale-state task where the agent must re-inspect before continuing
- Metrics:
  - final pass rate
  - process violation rate
  - recovery success rate
  - stale-observation violation rate
  - resource misuse rate
  - performance by horizon length

What makes it non-toy:

- Time matters.
- Resources deplete.
- Measurements can be noisy.
- Mistakes compound.
- The agent must inspect, act, recover, and decide.

Risk:

- If timing/noise/faults are invented without grounding, it becomes a more
  elaborate toy.
- Scope must stay narrow enough to ship.

Zheng fit:

- Good if Zheng wants a benchmark/paper contribution with empirical results.
- Needs a clear taxonomy of long-horizon lab-agent failures.

## Direction 2: Agent-Vs-Environment Failure Attribution

One-sentence claim:

> In stochastic long-horizon dry-run environments, failure should not be
> automatically attributed to the agent; seeded replay and counterfactual checks
> can separate agent error from environment dynamics.

Why it is novel:

Most benchmarks treat failure as agent failure. In lab-like settings, a run can
fail because:

- the agent chose the wrong action
- a noisy measurement misled the agent
- a simulated instrument fault occurred
- the agent failed to recover after a fault
- the agent acted correctly but the stochastic run failed anyway

API Gym's resettable seeded runtime can support a more precise evaluation:

```text
same initial state
same environment seed
same fault/noise schedule
replay trajectory
compare counterfactual recovery actions
classify failure source
```

Possible labels:

- `agent_error`
- `environment_fault`
- `agent_recovery_failure`
- `ambiguous`
- `success_despite_fault`

What to build for v0:

- Add stochastic seeds to one lab world.
- Add deterministic replay of fault/noise schedules.
- Add attribution output to verifier results.
- Create 5 to 10 failure-injected scenarios.
- Show examples where naive pass/fail is misleading.

What makes it non-toy:

- Long-running lab systems really do have measurement noise and instrument
  faults.
- Evaluation must ask whether the agent acted correctly given the observations
  it received.

Risk:

- Counterfactual attribution can become too broad if we try to solve general
  causality.
- Keep v0 narrow: seeded replay, fixed fault schedules, and explicit recovery
  choices.

Zheng fit:

- Strong if Zheng wants the most research-shaped contribution.
- This is probably the sharpest "new problem" in the set.

## Direction 3: Temporal/Provenance Verifier Engine

One-sentence claim:

> API Gym verifiers should be composable predicates over state, trajectory,
> timing, provenance, and freshness, not one-off final-state checkers.

Why it matters:

Final-state checks miss process failures. A lab run can end with plausible
outputs while violating important constraints:

- used a stale measurement
- read before incubation completed
- reused a contaminated tip
- made a decision before required evidence existed
- consumed a reagent that was already depleted
- recovered by skipping a required step

What to build for v0:

- A small verifier DSL or structured verifier schema.
- Predicate families:
  - terminal state predicates
  - temporal ordering predicates
  - freshness/staleness predicates
  - resource predicates
  - provenance predicates
- Per-tool-call state diffs as verifier input.
- Human-readable verifier reports for each failed invariant.

Example predicates:

```text
after(transfer(B1 -> B2), read_od600(B2))
fresh(read_od600(B2), used_for=submit_decision)
never(reuse_tip_after_contact(source_plate))
volume(source_well) >= dead_volume
decision.requires(all dilution wells read)
```

What makes it non-toy:

- It evaluates the run as a process, not only a terminal database state.
- It is reusable across dry-run worlds.

Risk:

- "Verifier engine" alone may sound like infrastructure, not a benchmark
  result.
- Best used as the method inside Direction 1 or 2, not necessarily the headline.

Zheng fit:

- Good if Zheng wants clean formalization.
- Can connect to temporal logic, monitorability, and process rewards.

## Direction 4: State-Diff Process Rewards

One-sentence claim:

> Per-action state diffs can turn sparse verifier outcomes into dense process
> rewards for training long-horizon tool-using agents.

Why it matters:

Outcome-only reward is weak for long-horizon workflows. If a run takes 80 tool
calls, a final failure does not tell the agent where it drifted.

API Gym can record:

```text
state_before
tool_call
state_after
state_diff
invariant_delta
progress_delta
```

That creates exact process supervision:

- this action advanced the intended protocol
- this action violated a resource constraint
- this action made evidence stale
- this action recovered from a fault
- this action made the final goal impossible

What to build for v0:

- Define progress/invariant potentials for one lab workflow.
- Emit reward-like labels per tool call.
- Compare:
  - final outcome only
  - process labels from state diffs
- Optional: run a small training or reranking experiment.

What makes it non-toy:

- Long-horizon agents need dense feedback.
- Dry-run state gives the feedback without touching live systems.

Risk:

- Without an actual training or reranking experiment, this stays speculative.
- This should be a second-phase direction unless Zheng wants a training paper.

Zheng fit:

- Good if Zheng wants the training bridge.
- Requires more ML experiment work than the benchmark-only path.

## Direction 5: Lab Scaffold Realism

One-sentence claim:

> For lab agents, realism should mean protocol artifacts, durable lab state,
> constrained instrument actions, resource accounting, and verifier-checked dry
> runs, not generic shell/browser/filesystem access.

Why it matters:

The field increasingly distinguishes simple function calling from full agent
scaffolds. API Gym should not chase generic scaffold realism blindly. It should
define lab-scaffold realism.

Weak lab environment:

```text
prompt -> tool call -> JSON response
```

Stronger lab environment:

```text
session manifest
  -> protocol files and plate maps
  -> MCP lab tools
  -> mutable lab state
  -> instrument readout artifacts
  -> state diffs and event log
  -> hidden verifier
  -> run export
```

What to build for v0:

- Task workspace with files:
  - protocol notes
  - plate map CSV
  - reagent inventory
  - prior run log
  - measurement output artifact
- Agent must inspect artifacts before acting.
- MCP tools mutate hidden lab state.
- Verifier checks both artifact use and lab state.

What makes it non-toy:

- It feels like an actual agent-host session.
- It answers the "simple function calling" critique without adding irrelevant
  browser/shell surfaces.

Risk:

- Scaffold realism is not enough as a paper headline.
- Use it to strengthen Direction 1, not as the only contribution.

Zheng fit:

- Good if Zheng cares about positioning against current agent benchmarks.
- Good for Hugging Face packaging and public credibility.

## Recommended Package

The best coherent package is:

```text
Primary benchmark:
  LabLongRun-Bench

Core method:
  timed/resource/stochastic dry-run runtime
  temporal/provenance verifier predicates
  agent-vs-environment failure attribution

Evidence:
  horizon scaling curves
  process violation taxonomy
  attribution examples
  replayable trajectories

HF artifact:
  tasks.jsonl
  initial_state.json
  protocol artifacts
  allowed_tools.json
  run_exports/
  state_diffs/
  verifier_results/
  example trajectories
```

## Minimal Build Plan

Immediate owner split:

- Zheng owns the benchmark machinery:
  - state schema
  - source-ref enforcement
  - verifier violation schema
  - template renderer
  - suite generator
  - oracle/admission harness
  - baseline runs
- Yifan owns the research/product/domain boundary:
  - source-grounding choices
  - which biological/lab failure modes are allowed into the benchmark
  - public positioning
  - outreach to lab-agent builders for failure-mode validation
  - deciding when to use Ann Arbor researcher review
  - dataset card language
  - release checklist

Domain content rule:

- Zheng may encode a domain template after a written task spec exists.
- Zheng should not originate biology/lab task semantics from intuition.
- Calibration templates can be used to test machinery, but should be marked
  `speculative_calibration_only` unless source-grounded or domain-reviewed.

First three decisions before coding:

1. Extend `unitelabs_plate_qc_v0` or create `lablongrun_wet_v0`.
   - Prefer a sibling world if the new state model needs tips, time, and
     dilution ledgers that would make the existing demo world messy.
2. Choose the grounding source for liquid-handling semantics.
   - Prefer one primary source, such as PyLabRobot or Opentrons docs/examples,
     then cite the exact docs or examples in `source_refs.json`.
3. Choose the flagship workflow.
   - Prefer OD600 serial-dilution QC because the current demo already has
     source/assay plates, OD600 readout, and a final protocol decision.

Week 1:

- Pick OD600 serial-dilution QC as the workflow family.
- Define 6 calibration task templates with 40 to 80 expected tool calls.
- Implement the task generator interface:
  - template id
  - seed
  - difficulty target
  - fault policy
  - parameter ranges
- Add explicit resource accounting:
  - tips
  - reagent volume
  - well volume
  - instrument availability
- Add per-action state diff export.
- Write `violation_schema.json` before writing all verifier checks.
- Generate 30 pilot tasks and keep only tasks that pass oracle/verifier
  validation.

Week 2:

- Add discrete event time:
  - action durations
  - readout delay
  - incubation delay
  - instrument busy state
- Add 3 temporal verifier predicates.
- Add stale-observation checks.
- Expand to 12 scenario templates.
- Generate 300 validated tasks across short, medium, and long bins.

Week 3:

- Add fixed-seed stochastic readout/fault model.
- Add fault-injected variants for at least 8 templates.
- Add attribution labels:
  - agent error
  - environment fault
  - recovery failure
- Generate 600 validated tasks.

Week 4:

- Run baseline agents.
- Produce horizon scaling table.
- Generate the 1,000-task release candidate.
- Package HF artifact from generated task artifacts and run exports.
- Write dataset card and short technical report.

Do not expand beyond one wet-lab workflow family before this four-week package
exists. Breadth can come after the first artifact is credible.

## What To Avoid

- Do not claim "state verification" as the novel idea.
- Do not add browser/shell just to look like other benchmarks.
- Do not model realism that cannot be grounded or justified.
- Do not spread across many domains.
- Do not name private partners or non-public data in public artifacts without
  explicit approval.
- Do not make stochasticity arbitrary; use explicit documented assumptions even
  if real logs are not available yet.

## Public Claim If This Works

> We introduce a dry-run benchmark for long-horizon lab agents in timed,
> stochastic, resource-constrained environments. The benchmark records tool
> traces, state diffs, temporal process violations, and verifier outcomes, and
> it supports failure attribution between agent behavior and environment
> dynamics through seeded replay.

## Zheng Review Questions

1. Which direction has the cleanest research claim?
2. Which direction can be grounded with the data and code we can actually get?
3. Which direction can ship as a v0 HF artifact in one month?
4. Which direction creates product value even if the paper takes longer?
5. Which direction would a reviewer see as more than "state-based checking"?
