# Adaptyv Qualification Plan

This is a qualification plan, not a build plan. Do not start
`adaptyv_foundry_dryrun_v0` until the qualification gates below are answered.

## Why Adaptyv Matters

Adaptyv is more aligned with API Gym than a generic wet-lab visual simulator.
The relevant environment is not:

```text
agent controls pipette -> simulated deck state
```

It is:

```text
agent designs protein campaign
  -> Foundry API dry-run projection
  -> verifier checks cost, quote, lifecycle, result interpretation, provenance
```

This sits directly on API Gym's native strengths:

- source-grounded API projection
- dry-run gate before live action
- mutable campaign state
- tool traces
- hidden verifier
- temporal/provenance/resource checks
- run export evidence

Even if real Adaptyv experiments are relatively cheap, the feedback loop can
still be expensive because a bad campaign decision may burn a multi-week cycle.

## Gate Before Build

The build is gated by one qualification question:

> When customers let agents or scripts interact with the Foundry API, do those
> agents ever waste real submissions, quotes, budget, or multi-week cycles
> because they made a bad planning, tool-use, or result-interpretation decision?

If the answer is clearly yes, build a thin `adaptyv_foundry_dryrun_v0` proof.

If the answer is no, ask why:

- real runs are cheap enough that dry-run rehearsal is not needed
- scoped tokens and quote checks already solve the problem
- agent usage is still too early
- customers do not yet trust agents to submit real campaigns
- Adaptyv already plans to ship its own sandbox/dry-run layer

Only the first two weaken the wedge. The latter three may still imply a future
partner path.

## Who To Qualify

Start with Adaptyv because they see aggregate customer behavior and can become a
partner/data source.

But do not treat Adaptyv's second-hand account as final demand validation. The
binding signal is at least one actual customer or competition participant who
would use or pay for a dry-run/eval layer before spending real Foundry cycles.

Qualification ladder:

1. Adaptyv technical/product person:
   - Does the failure mode exist?
   - Is it common enough to matter?
   - Would a dry-run/eval layer help their adoption funnel?
2. One Adaptyv customer or agent-builder:
   - Did they personally waste submissions, money, or time?
   - Would they run agent rollouts in a dry-run projection first?
   - What verifier failure would have saved them?
3. Adaptyv partnership check:
   - Would they prefer this as a partner layer, platform feature, or not at all?

## Real Risk

Adaptyv is the most likely party to build this themselves. It is their API, and
a dry-run or sandbox mode is a natural platform feature.

Therefore, the positioning should not be:

```text
Datalox mocks Adaptyv's API.
```

It should be:

```text
Datalox helps make the Foundry API agent-ready:
  dry-run rollouts
  verifier-backed campaign checks
  cross-customer eval/training data
  replayable traces
  grounded result-interpretation tests
```

The partner path is stronger than a third-party API-mock path.

## Moat Hypothesis

The API projection is not the moat. Adaptyv can implement a shallow Foundry API
sandbox faster than we can.

The moat must be verifier depth and grounded result interpretation:

- duplicate paid submissions
- quote expiration
- budget cap violations
- wrong target selection
- low-diversity or invalid sequence batch
- partial results treated as final
- stale or low-quality results used for decision
- result ids not cited in final campaign decision
- campaign stopped before required evidence arrived
- agent fails to distinguish design hypothesis from measured evidence

The strongest v0 is not a broad API mock. It is a small environment where the
agent can look correct by transcript but the verifier catches a costly campaign
mistake.

## Data Check

Before using private data or asking for partnership data, check public data:

- Adaptyv public protein-design competitions
- public competition leaderboards/results
- example targets and result schemas in docs
- public campaign examples from blog/docs

If public competition data can ground result-interpretation checks, use it for
v0. Private Adaptyv/customer data should be a later partner path, not a Phase 0
dependency.

## Thin v0 If Qualified

Only build this slice first:

```text
campaign planning
  + budget/quote discipline
  + result-interpretation correctness
```

Do not build full Foundry lifecycle in v0.

Minimal task:

- Agent receives target objective, budget cap, allowed result schema, and a set
  of candidate sequences.
- Agent uses dry-run Foundry tools to select target, create campaign, request
  quote, submit or reject within budget, monitor status, read result records,
  and make a final design decision.
- Hidden verifier checks whether the agent:
  - chose the correct target
  - avoided duplicate paid submissions
  - stayed within budget
  - did not confirm an expired or over-budget quote
  - did not treat partial results as final
  - cited actual result ids in its final decision
  - made a decision supported by measured results rather than prior guesses

Stop at this proof before adding every Foundry API endpoint.

## Build/No-Build Decision

Build `adaptyv_foundry_dryrun_v0` only if at least one of these is true:

- Adaptyv says agent-caused wasted cycles are a real adoption problem and wants
  a partner/design-prototype.
- One customer says they would run agent rollouts through a dry-run/eval layer
  before spending real Foundry cycles.
- Public competition data is sufficient to build a credible result-verifier
  proof, and outreach suggests the pain is plausible.

Do not build if:

- real feedback is cheap/fast enough that dry-run rehearsal is irrelevant
- Adaptyv already has an adequate sandbox and does not want an external layer
- no actual agent-builder can name a costly failure mode

## Outreach Prompt

Use a narrow question, not a broad partnership pitch:

```text
We're exploring dry-run/eval layers for agents that interact with costly live
scientific APIs. For Adaptyv specifically, the question is simple:

When customers let agents or scripts interact with the Foundry API, is burning
real submissions/quotes/3-week cycles to discover a bad planning or tool-use
decision a real pain, or does the current cost/feedback model make dry-run
rehearsal unnecessary?

If it is real, we'd like to understand one concrete failure mode well enough to
build a tiny verifier-backed dry-run proof. If it is not real, that is equally
useful for us to know.
```
