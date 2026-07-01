# LabLongRun-Wet Phase 1 Acceptance Checklist

Phase 1 is not the paper benchmark. It is the smallest end-to-end proof that
the architecture can support a real long-horizon wet-lab benchmark.

The deliverable is one source-grounded OD600 liquid-handling dry-run task with:

- generated task bundle
- isolated sandbox state
- agent-visible tool path
- oracle run through the same tools
- hidden verifier
- failed negative control
- trace, state diff, verifier result, and run export

## Hard Requirements

1. The task is generated, not manually assembled at run time.
2. The task bundle contains:
   - `task.json`
   - `agent_task.json`
   - `initial_state.sqlite`
   - visible protocol artifacts
   - hidden verifier expectations
   - hidden oracle plan
3. The oracle executes through the same tool/dynamics path as an agent.
4. The oracle run passes the verifier.
5. At least one known bad plan fails the verifier.
6. Tool calls are written to `tool_calls.jsonl`.
7. State or semantic diffs are written to `state_diffs.jsonl`.
8. Finalization writes:
   - `verifier_result.json`
   - `run_export.json`
9. Every agent-visible lab action is either:
   - grounded in an explicit public source reference, or
   - marked as benchmark-local in `source_refs.json`.
10. No live hardware, live provider, or production credential path exists.

## Source-Grounding Bar

The prototype may define API Gym runtime contracts itself. It may not casually
invent wet-lab action semantics.

Ground these from public docs/packages where possible:

- labware and deck state
- tip pickup and drop
- aspirate
- dispense
- mix
- delay/wait
- readout or simulated plate-reader behavior

Benchmark-local additions are allowed when explicit:

- trace recording
- state diff emission
- hidden verifier expectations
- seeded fault hooks
- protocol artifact inspection requirements

## Verifier Bar

The verifier should check at least:

- terminal protocol decision
- source and target volumes
- readout was produced in this run
- final decision cited the readout
- no decision was submitted before the required readout
- no live boundary was crossed

Preferred but not required for Phase 1:

- tip lifecycle checks
- readout freshness checks
- contamination checks
- temporal wait checks

## Scale Gate

Do not scale to 1,000 tasks until Phase 1 passes. The next step after Phase 1 is
six calibrated templates and 30 generated tasks, not a generic framework.

## Phase 2 Acceptance Checklist

Phase 2 turns the single proof task into a calibrated mini-benchmark.

Target:

```text
6 hand-calibrated templates x 5 seeds = 30 admitted tasks
```

The six templates should remain inside one OD600 wet-lab workflow family:

1. nominal run
2. low source volume requiring replanning
3. tip exhaustion or contaminated-tip risk
4. instrument busy or wait-required readout
5. stale OD600 readout requiring reread
6. partial dispense or read failure requiring recovery

Each template must define:

- lab failure mode
- source references
- parameter ranges
- initial-state constraints
- visible artifact recipe
- oracle strategy
- known-bad plan strategy
- verifier predicates
- difficulty target

Each generated task must write:

- generated task bundle
- hidden oracle plan
- hidden known-bad plans
- hidden verifier expectations
- `admission.json`

Admission must prove:

- oracle plan passes
- at least one known-bad plan fails
- initial state is physically possible
- visible artifacts are internally consistent
- hidden verifier state does not leak
- expected horizon matches the difficulty target
- verifier predicates are non-vacuous

Only after all 30 tasks pass admission should we scale toward the 1,000-task
paper benchmark.
