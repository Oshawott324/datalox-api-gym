# Contract-Compiled Tiered Verification

Date: 2026-07-10
Status: discussion proposal

## Summary

LabLongRun currently has credible verifier checks for a small strict-admission
slice, but its verifier implementation grows largely by adding scenario-specific
Python. That approach can improve individual tasks while making the benchmark
slower and increasingly expensive to extend.

This proposal tests a different scaling unit:

```text
task family contract
  -> typed verification IR
  -> streaming predicates and final-state queries
  -> failure codes and diagnostic signals
```

The hypothesis is not that laboratory verification becomes domain-free. The
hypothesis is that a bounded catalog of well-tested predicate primitives can
amortize the verifier work across task families. Domain expertise remains in
mapping world state into canonical facts, selecting the required checks, and
justifying genuinely new primitives.

This should be treated as a falsifiable systems experiment. If each new family
still requires mostly new primitives or custom Python, the abstraction is not
working.

## Why Test This Now

The current `pylabrobot_star_v0` verifier has:

```text
91 scenario verifier functions
864 terminal or temporal check call sites
858 statically named checks
386 distinct static check names
```

About 55% of the static check call sites repeat an existing exact check name.
Semantic duplication is higher: checks such as `zero_before_tare`,
`close_before_seal`, `lock_before_spin`, and `pump_before_transfer` are all
instances of the same temporal-precedence operation.

This is evidence that a reusable layer may exist. It is not evidence that the
layer will preserve scientific validity. That must be demonstrated with
held-out families and mutation tests.

## Proposed Boundary

The verifier should have four explicit layers:

```text
provider/world events and state
  -> domain fact adapter
  -> typed verification contract
  -> streaming and final-state backends
  -> verdict, failure codes, and diagnostic vector
```

### Domain fact adapter

The adapter converts world-specific records into canonical facts such as:

```text
event type and logical time
actor, instrument, resource, source, and target
resource quantity before and after an action
sample lineage and contamination labels
observation version and provenance source
instrument state transitions
numeric measurements and units
```

This is expected to have lower reuse than the compiler. A centrifuge and a plate
reader expose different facts even when both later use the same ordering or
freshness primitive.

### Typed verification contract

A task-family contract may select and parameterize known primitives. It may
compose them through a small typed grammar of selectors, quantifiers, temporal
operators, state-diff aggregates, and numeric relations.

It must not execute arbitrary Python or embed unrestricted expressions. At the
same time, the grammar should not be so rigid that every new ordering or numeric
combination requires a new named primitive. The stable boundary is a small set
of typed operators over canonical facts.

### Verification backends

One contract may produce three outcomes at each tier:

```text
full verdict
necessary-condition or early-warning signal
not decidable at this tier
```

Tier 0 is a streaming fold over events. It should update bounded state per event
and avoid rescanning the complete trajectory after every action.

Tier 1 checks final or checkpoint state, state diffs, and evidence references.
It may decide requirements that cannot be decided faithfully in-stream.

Tier 2 is sparse calibration by an expensive model, human, or domain reviewer.
It audits blind spots and helps validate new primitives; it is not part of every
rollout.

## Candidate Primitive Catalog

The initial catalog should be extracted from a real family rather than designed
as a general language in advance. Likely primitive classes include:

| Primitive class | Example requirement |
| --- | --- |
| Existence and cardinality | At least one valid readout exists |
| Entity coverage | Every dilution well is present in the submitted readout |
| Temporal precedence | Dilution completes before measurement |
| Sequence or phase ordering | Close, execute, then reopen an instrument |
| Freshness | Evidence was observed after the latest relevant mutation |
| Provenance | Submitted evidence derives from the current sample lineage |
| Forbidden event | No live action or unsafe bypass occurred |
| Resource availability | Enough tips or reagent existed before action |
| Resource identity or uniqueness | A fresh tip was used for each dilution step |
| Conservation or bounded state diff | Final well volumes match allowed changes |
| State transition or interlock | Instrument was locked before operation |
| Numeric range or tolerance | Temperature or measurement is within tolerance |
| Numeric trend or ratio | Serial-dilution measurements follow the expected curve |
| Bounded retry and recovery | Retry follows a transient fault and then stops |
| Decision consistency | Final decision is supported by submitted evidence |
| Collateral-change exclusion | Unrelated resources were not mutated |

A request for a new primitive must include its semantics, required canonical
facts, tier behavior, failure code, complexity, and validation cases. A family
must not silently add a custom verifier escape hatch.

## Mutants Define Validity

A primitive is not reusable merely because another contract can reference it.
It needs validation at two boundaries.

### Primitive-level validation

Each primitive includes:

```text
minimal passing case
minimal target mutant that it must catch
near-miss case that it must accept
stable failure code
Tier 0 and Tier 1 agreement rules where both can decide
```

### Family-level binding validation

Each family also needs mutants proving that the contract selected the correct
events, resources, state fields, and evidence. This catches a valid generic
primitive wired to the wrong domain facts.

For every admitted family:

```text
oracle must pass
empty trajectory must fail
applicable known-bad mutants must fail
applicable stale/provenance mutants must fail
applicable resource/fault mutants must fail
exact expected failure-code sets must match
near-miss trajectories must not be rejected
```

Primitive tests prove implementation correctness. Family tests prove semantic
binding correctness. Both are required before reuse counts as validated.

## Reuse Metrics

A single reuse percentage is too ambiguous. The experiment should report three
metrics.

### Primitive-type reuse

```text
R_type(F | P) =
  prior primitive types used by family F
  / all primitive types required by family F
```

This measures whether the catalog generalizes. It is the primary reuse metric.

### Validated contract-clause reuse

```text
R_clause(F | P) =
  clauses expressed with prior primitives and passing family-level mutants
  / all required clauses in family F
```

This measures how much of the actual contract is reused. Repetition across many
wells or time points can make this number higher than `R_type`, so both numbers
must be shown.

### Authoring-effort reduction

```text
R_effort(F) =
  1 - contract-and-binding authoring time / scenario-verifier baseline time
```

This includes domain adapter work, contract authoring, mutants, debugging, and
review. Compiler implementation time should be reported separately as a fixed
investment.

The report should also show cumulative catalog size and new primitives per
family. The defensible scaling claim is sublinear catalog growth, not a catalog
that literally stops growing.

## Reuse Forecast

The following ranges are hypotheses to test, not promised results:

| Held-out family | Predicted `R_type` |
| --- | ---: |
| Another liquid-handling or QC family | 70-85% |
| Plate-reader kinetics after OD600 dilution | 60-75% |
| A different instrument workflow | 40-60% |
| A cross-provider campaign or API workflow | 25-50% |
| Marginal family after 6-8 representative lab families | 65-80% |

For OD600 dilution followed by plate-reader kinetics, the point estimate is
approximately 68%. Ordering, coverage, freshness, provenance, numeric trend,
and decision consistency should transfer. Sampling-interval tolerance,
incubation stability, and replicate or slope interpretation would probably be
new.

Clause-weighted reuse may reach 75-85% because the same primitives repeat over
many wells and time points. That number should not be reported alone.

High reuse is not automatically good. A shallow catalog of `exists`, `count`,
and `after` could score well while missing biological and safety failures. Reuse
must therefore be reported together with mutant catch rate, near-miss
specificity, critical-failure coverage, verifier latency, and expert review of
the required obligations.

## Falsification Experiment

### Step 0: Profile the current verifier

Measure the present verifier before changing its architecture:

```text
time per action and per final verification
number of complete event-history scans
number of state loads or copies
latency by trajectory length
p50 and p95 across strict-admission cases
```

This establishes whether repeated scans are the actual bottleneck and provides
a before/after baseline.

### Step 1: Extract one deep family

Use `pylabrobot_lab_v0::serial_dilution_qc` as the source family. Express its
current requirements as approximately 8-12 typed primitives without weakening
its admitted mutants or exact failure-code behavior.

### Step 2: Compile both tiers

Compile the family contract into:

```text
incremental Tier 0 state for temporal, freshness, resource, and provenance facts
Tier 1 final-state and state-diff checks for volume, curve, and decision validity
the same stable failure-code vocabulary used by strict admission
```

### Step 3: Test generated variants

Generate 20-50 controlled dilution variants over stock OD, chain length, target
wells, and applicable mutants. Every variant must preserve oracle acceptance,
mutant rejection, near-miss acceptance, and exact failure-code sets.

This tests contract parameterization, but it does not establish cross-family
reuse.

### Step 4: Freeze and test held-out families

Freeze the catalog after the dilution family. Then use two held-out probes:

1. An adjacent measurement family, such as plate-reader kinetics or a
   shaker-reader QC workflow.
2. A dissimilar cross-instrument family, such as centrifuge-scale QC.

For each probe, record reused primitives, new primitives, adapter work, contract
work, mutant coverage, and latency. Do not redesign the first-family catalog
after seeing the held-out family without recording that revision as a new
catalog version.

### Step 5: Evaluate the result

Evidence in favor of the approach would include:

```text
adjacent-family R_type at or above 60%
cross-instrument R_type at or above 40%
all admitted target mutants caught with exact failure codes
near-miss cases accepted
no verifier latency regression, with streaming work bounded per event
fewer new primitives and less authoring effort on later families
```

Evidence against the approach would include:

```text
adjacent-family R_type below 50%
most families requiring custom code or family-named primitives
high reuse achieved only by dropping scientifically important checks
domain adapters dominating authoring effort without declining
mutation catch rate or specificity falling after compilation
catalog growth remaining roughly linear with family count
```

## Reward Use

The compiled checks should initially emit a diagnostic vector rather than an
unvalidated dense reward:

```text
terminal success
milestone completion
freshness and provenance status
resource and safety violations
recovery behavior
collateral state changes
efficiency counters
```

These signals can support debugging, trajectory filtering, curriculum design,
and failure analysis. A signal should become a shaped training reward only
after adversarial validation shows that optimizing it does not create an easier
but incorrect policy. The trusted terminal verifier remains the reward anchor.

## What Would Be Paper-Worthy

Moving checks into a schema is engineering cleanup by itself. The stronger
research claim requires measured evidence that contract compilation:

```text
reduces marginal verifier-authoring cost
transfers to held-out task families
preserves or improves mutation-based validity
reduces verifier latency through incremental evaluation
produces useful diagnostics without weakening the terminal reward
```

The contribution would then be a verified environment-compilation method for
long-horizon agents, demonstrated in lab automation. It should not be framed as
"state-based verification is new" or "all scientific verification is generic."

## Decision

The immediate decision is whether this falsification experiment is worth doing
before expanding the task inventory further.

The proposal is attractive if the goal is a method paper or scalable training
infrastructure. It is less necessary if the near-term goal is only a fixed
benchmark artifact, where the existing strict-admission plan may be sufficient
and cheaper.

The recommended checkpoint is intentionally small: profile the existing
verifier, compile the OD600 family, then test one adjacent and one dissimilar
held-out family. That is enough to decide whether the reuse hypothesis has real
support before committing to a general framework.
