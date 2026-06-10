# UniteLabs Call Plan

## Scheduling

Book soon. A good slot is Wednesday morning in Europe, which is Wednesday
afternoon or evening in China.

Suggested message:

> Happy to do a 15-minute sanity check. I am looking at replay/eval
> infrastructure for AI-controlled lab workflows: when agents call lab APIs or
> instruments, can we capture enough tool I/O and state context to debug, audit,
> evaluate, and eventually turn verified traces into resettable practice
> environments without rerunning the physical workflow every time?
>
> Would Wed Jun 10 around 10:00-11:30 CEST work? That is 16:00-17:30 for me.
> Also happy to do Thu same window if easier.

## Call Goal

Do not try to prove the whole company.

The goal is to learn whether replay/eval is the right hook above UniteLabs'
programmable control layer, and whether the longer-term synthetic environment
layer is credible for their customer workflows.

Primary question:

> Once instruments and workflows are programmable, do automation-heavy labs need
> stronger observability, replay, validation, and eval for AI-controlled
> workflows?

Secondary question:

> Once real lab runs are captured and verified, would teams want resettable
> practice environments for dry-runs, regression tests, and agent training?

## Positioning

## UniteLabs Read

Use this as your mental model, not as a long speech:

- They are not just aggregating instruments.
- They position as a vendor-agnostic lab automation OS / programmable lab
  control plane.
- Public materials emphasize device connectors, Python SDK/API control,
  workflow execution, lab-as-code, data capture, and AI-ready/self-driving lab
  interfaces.
- Their public docs include mainstream automation surfaces such as Hamilton
  STAR/Vantage, Agilent Bravo, Agilent BioTek readers, Tecan Freedom EVO
  mentions, BMG LABTECH readers, Inheco, QInstruments, Azenta, and others.

So do not ask "are you only connectivity?"

Ask:

> Once workflows run through UniteLabs, how much of the agent/tool interaction
> is reconstructable later, and is it enough for debugging, audit, eval, and
> dry-run regression?

Short version:

> Datalox is replay and eval infrastructure for AI-controlled lab workflows.
> When an agent calls instruments or lab APIs, Datalox captures the tool I/O,
> observations, state context, and verifier evidence so teams can debug, audit,
> evaluate, and reuse the interaction without rerunning the physical workflow
> every time.

Strategic version:

> Replay is the capture layer. Eval is the scoring layer. Resettable synthetic
> environments are what you can build once enough real runs have been captured
> and verified.

Complementary framing:

- UniteLabs makes instruments and workflows programmable.
- Datalox makes agent behavior over those programmable surfaces replayable,
  verifiable, and reusable as evals or resettable practice environments.

Avoid saying:

- "We replace instrument connectors."
- "We replay physical chemistry perfectly."
- "This is a finished lab product."
- "We simulate chemistry or biology perfectly."

Say instead:

- "Replay captures tool/API I/O, observations, state fingerprints, and decision
  context."
- "Physical execution remains the source of truth."
- "The question is when to pay for real execution versus when to reuse evidence
  for debugging, audit, and eval."
- "Synthetic environment means workflow-level practice and validation, not a
  claim that we can recreate physical reality perfectly."

## 15-Minute Agenda

### 0:00-1:00 Opening

> I am looking at replay and eval infrastructure for AI-controlled lab
> workflows. When an agent calls instruments or lab APIs, can we capture enough
> tool I/O, observations, state context, and verifier evidence to debug, audit,
> evaluate, and eventually turn verified runs into resettable practice
> environments without rerunning the physical experiment every time?

Then:

> I am not trying to pitch a finished product. I mainly want to understand
> where this fits relative to the pain you see: connectivity, observability,
> failure recovery, validation, dry-runs, and AI-generated workflows.

### 1:00-3:30 Demo

Open:

```bash
open demos/unitelabs_chat/index.html
```

Use slides:

1. After programmable lab control, agents need verifiable practice.
2. UniteLabs is the programmable lab control plane.
3. Real execution is source of truth, but costly for every agent attempt.
4. Datalox ladder: capture, score, reuse.
5. Concrete artifact: structured tool I/O plus state-based verifier.
6. Discovery questions.

Cut slide 5 if the conversation is already moving. The demo is not the center
of the meeting.

Avoid showing repo internals in the main flow. If they ask whether anything is
implemented underneath, use this backup proof command:

```bash
api-gym verify --run demos/unitelabs_chat/evidence/billing_demo_run
```

### 3:30-13:00 Discovery

Ask these in priority order:

1. When a workflow runs through UniteLabs, how much tool/instrument interaction
   is reconstructable later?
2. When a workflow fails mid-run, what state is captured today?
3. What is still hard to reconstruct after a failed run?
4. Do customers ask for dry-runs or simulated execution before running physical
   instruments?
5. Are AI-generated workflows being executed today, or is that still
   future-facing?
6. What would make an AI-generated workflow safe enough to execute?
7. Would replayable traces be useful for debugging, compliance, customer
   support, or regression tests?
8. If you had a fake/resettable lab workflow environment, what would need to be
   faithful for it to be useful?
9. What language would customers use for this: replay, audit trail, digital
   twin, simulation, dry-run, validation, or eval?

### 13:00-15:00 Close

If it resonates:

> If this direction is relevant, the useful next step would be for me to model
> one representative non-proprietary lab workflow as a tiny resettable
> environment. Then we can see whether replay/eval plus synthetic dry-run adds
> value on top of programmable instrument control.

If they say connectivity is still the bottleneck:

> That is helpful. My hypothesis is replay/eval becomes painful right after
> connectivity works, especially once AI agents start generating or adapting
> workflows. It is useful to know if the market is not there yet.

## Objection Handling

### "We already have logs."

> That makes sense. I am trying to distinguish logs from replay/eval artifacts.
> Logs explain what happened. A replay/eval bundle should let an agent or
> evaluator inspect, score, compare, and reuse behavior later.

### "Physical workflows cannot really be replayed."

> Agreed. I would not claim physical reality can be replayed perfectly. The
> target is replaying tool/API I/O, observations, metadata, state fingerprints,
> and decision context, then using real runs as ground truth for evals and
> practice environments.

### "Simulation is hard in labs."

> Agreed. This does not require simulating chemistry perfectly. The first value
> is debugging and audit. The second value is workflow-level eval: did the agent
> call the right tools, respect constraints, interpret observations correctly,
> and stop before unsafe side effects?

### "Are you building a synthetic lab simulator?"

> Not in the sense of simulating the underlying science. The first environment
> layer is workflow-level: tool schemas, instrument responses, state ledgers,
> observations, constraints, and verifiers. Real runs stay the source of truth.
> The synthetic layer is for cheap practice, regression, and pre-execution
> validation.

### "We are focused on connectivity first."

> That is the right layer to own. My question is whether replay/eval becomes a
> complementary layer once connectivity and programmable control are in place.

## What To Listen For

Strong positive signals:

- They mention failed-run debugging.
- They mention audit/compliance.
- They mention AI-generated workflow validation.
- They mention dry-run, simulation, or digital twin gaps.
- They ask whether traces can become fake/resettable tasks.
- They say customers ask what happened after an instrument action fails.
- They have no good way to turn past workflows into regression tests.

Weak signals:

- All demand is still manual instrument connectivity.
- Customers do not run agentic or adaptive workflows.
- Logs are enough for current users.
- They see no near-term need for evals before real execution.
- They only want physical simulation fidelity and reject workflow-level dry-run.

## Best Follow-Up Ask

> Could you share one non-proprietary workflow shape that represents the kind of
> agentic lab automation you expect to matter? I can model it as a tiny
> resettable environment and use that to test whether this layer is useful.
