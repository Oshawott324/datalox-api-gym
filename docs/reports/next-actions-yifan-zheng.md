# Next Actions For Yifan And Zheng

Current state:

- Track A: Adaptyv is the highest-priority qualification lead.
- Track B: LabLongRun-Wet Phase 2 now has six calibration templates, seeded
  fault schedules, admission checks, oracle pass checks, and exact known-bad
  failure checks.
- Track C: the next serious build should be `lab_campaign_ops_v0`, a
  multi-provider lab operations world. Opentrons is one source pack, not the
  benchmark identity.

The next step is not to ask Zheng to invent biology tasks or make an
Opentrons-only simulator. Zheng should harden the machinery and source-pack
schema. Yifan should own provider choice, task semantics, qualification, and
domain-task selection.

The deeper technical direction is a projection contract with documented
stochasticity, not arbitrary simulator noise. See:

```text
docs/reports/lablongrun-projection-stochastic-plan.md
```

Current next-build doc:

```text
docs/reports/lab-campaign-ops-v0-next-build.md
```

## Yifan: This Week

1. Qualify Adaptyv before building a Foundry world.
   - Ask whether agents/scripts waste real submissions, quotes, budget, or
     multi-week cycles because of planning/tool-use/result-interpretation
     mistakes.
   - Ask for one concrete failure mode.
   - Ask whether one customer or competition participant can validate the pain.

2. Decide the first `lab_campaign_ops_v0` source packs.
   - Recommended v0 source packs:
     - `opentrons_http_v1`
     - `benchling_assay_v1`
     - `tetrascience_context_v1`
   - Do not start with six providers. Add Labstep/Labguru/SciNote only after
     the first cross-provider tasks admit.

3. Draft two cross-provider task specs, not code.
   - Start with:
     - `od600_qc_handoff_nominal`
     - `stale_instrument_data_handoff`
   - Each spec must define:
     - visible evidence
     - valid behavior
     - known-bad behavior
     - expected verifier/tool failure
     - provider/source basis

4. Decide source status for each source pack and task family.
   - `source_grounded`
   - `domain_reviewed`
   - `speculative_calibration_only`

5. Use Ann Arbor researcher network only for targeted review if a task family
   is likely to become part of a public dataset. Do not use them for generic
   brainstorming.

## Zheng: This Week

Zheng should not invent biological scenarios or provider semantics. Zheng should
make the generator/source-pack/admission machinery reject shallow tasks.

Tasks:

1. Define a source-pack schema for provider-shaped tools.
   - source refs
   - endpoint/tool ids
   - request/response fixtures
   - dry-run semantics
   - allowed errors
   - live-execution boundary
2. Create skeleton source packs:
   - `opentrons_http_v1`
   - `benchling_assay_v1`
   - `tetrascience_context_v1`
3. Define `lab_campaign_ops_v0` task schema.
   - `tool_families`
   - cross-provider entity ids
   - visible artifacts
   - hidden state
   - verifier expectations
   - expected failure codes
4. Extend admission from single-world checks to cross-provider checks:
   - declared source packs exist
   - every tool maps to a source pack
   - oracle passes through public tools
   - known-bad plan fails for the named reason
   - no hidden leakage
   - no live execution attempt
   - sample/entity/plate/result ids are consistent
5. Keep the existing `greenfield_lablongrun` Phase 2 prototype as the
   calibration kernel. Do not expand it into a larger wet-lab-only benchmark
   until `lab_campaign_ops_v0` is tested.

The old admission rule was:

```text
some known-bad plan fails
```

The required admission rule is:

```text
the named failure-mode plan fails for the named reason
```

And for `lab_campaign_ops_v0`, also:

```text
the named failure-mode plan fails across the intended provider boundary
```

## Task Spec Format

Use this before asking Zheng or a coding agent to encode a task:

```text
task_family_id:
failure_mode:
source_packs:
source_status:
source_refs:

visible evidence:
valid behavior:
known-bad behavior:
expected verifier/tool failure:
cross-provider invariant:
why this matters:
```

Example:

```text
task_family_id: stale_instrument_data_handoff
failure_mode: stale_instrument_data_uploaded_to_current_assay
source_packs: benchling_assay_v1, tetrascience_context_v1
source_status: source_grounded for API shapes; speculative_calibration_only for
  synthetic task state
source_refs: provider docs/examples for assay/result/context payload shapes

visible evidence:
  ELN assay request references sample/entity ids and expected run id.
  Instrument context includes one stale readout and one current-run readout.

valid behavior:
  inspect assay request, reject stale readout, use current-run readout, upload
  result to the correct assay/entity with provenance.

known-bad behavior:
  upload the stale readout to the current assay.

expected verifier/tool failure:
  submission_cites_current_instrument_record

why this matters:
  tests whether the agent preserves cross-system data freshness and scientific
  record provenance.
```

## Decision In One Week

- If Adaptyv qualifies, it becomes a high-value source pack/world candidate,
  but do not block `lab_campaign_ops_v0` on it.
- If Adaptyv does not qualify, continue with the public-source provider stack:
  Opentrons + Benchling + TetraScience.
- If public source-pack grounding is too weak for Benchling or TetraScience,
  reduce v0 to Opentrons + one better-grounded record/data provider, but keep
  the benchmark identity multi-provider.
- Keep LabLongRun-Wet at calibration-kernel scale unless we deliberately choose
  a wet-lab-only paper.
