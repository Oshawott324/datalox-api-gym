# UniteLabs Demo Slide Scripts

Use this with `demos/unitelabs_chat/index.html`.

Target length: 2-3 minutes. The demo is only a conversation starter; the call
should mainly be questions.

Open the deck:

```bash
open demos/unitelabs_chat/index.html
```

## Slide 1: After Programmable Lab Control

Say:

> My read is that UniteLabs is making the lab programmable: connectors, SDK/API
> access, workflow execution, and AI-ready interfaces.
>
> The layer I am exploring starts after that. Once agents can call lab tools,
> how do teams capture what happened, score whether it was correct, and reuse
> verified traces for dry-runs before touching instruments again?
>
> So the short version is: replay/eval is the front door, and resettable
> environments are the longer-term layer.

Transition:

> I want to make sure I am not misreading where UniteLabs sits.

## Slide 2: My Read On UniteLabs

Say:

> I do not see UniteLabs as just a connector aggregator. From the public docs,
> it looks more like a programmable lab control plane.
>
> You connect instruments, expose SDK and API surfaces, run workflows, capture
> data, and make those interfaces usable by people and AI systems.
>
> That means Datalox should not compete with the control layer. It should sit
> one layer above: replay, eval, audit, and dry-run environments for agents that
> are using those programmable surfaces.

Transition:

> The reason that upper layer matters is that real execution is costly.

## Slide 3: Why Another Layer

Say:

> Physical execution is still the source of truth. I am not trying to replace
> it.
>
> But it is not a good place for every agent attempt. Instrument time,
> consumables, scheduling, latency, and irreversible side effects make repeated
> trial-and-error expensive.
>
> The question is when an agent should pay for reality, and when verified
> evidence can support debugging, audit, eval, or dry-run practice.

Transition:

> That leads to the Datalox ladder.

## Slide 4: Datalox Ladder

Say:

> The first layer is capture: exact tool/API I/O, observations, state
> fingerprints, and side effects.
>
> The second layer is score: verifiers check final state and workflow
> invariants, so the trace is not just a passive log.
>
> The third layer is reuse: verified traces become regression tests and
> resettable workflow-level environments.
>
> I want to be precise here: this is not claiming to perfectly simulate biology
> or chemistry. It is workflow-level simulation: tools, observations, state
> ledgers, constraints, and verifiers.

Transition:

> The artifact itself is simple.

## Slide 5: Concrete Artifact

Say:

> This is the shape of the artifact. On the left, the agent calls a lab tool and
> gets structured observations back. On the right, a verifier checks state and
> invariants.
>
> The important distinction from ordinary logs is that the result is scoreable
> and reusable. You can ask whether the agent called the right tool, with the
> right parameters, in the right order, and whether its later decision matched
> the observation.
>
> The agent should not pass because it writes a nice final answer. It should
> pass because the environment state is correct.

Transition:

> That is the concept. I would rather spend the rest of the time learning from
> you.

## Slide 6: Discovery Questions

Say:

> The questions I care about are these.
>
> Once workflows run through UniteLabs, how much of the agent/tool interaction
> is reconstructable later?
>
> Is that evidence enough for debugging and audit, or would customers need a
> more explicit replay/eval artifact?
>
> Do users ask for dry-runs, digital twins, or simulated execution before
> running physical instruments?
>
> If I modeled one tiny non-proprietary lab workflow as a resettable
> environment, what would need to be faithful for it to be useful?

Close:

> If this direction is relevant, the useful next step would be for me to model
> one representative workflow shape as a tiny resettable environment. Then we
> can test whether replay/eval plus dry-run adds value on top of programmable
> instrument control.

## 90-Second Cut

If the call is tight, use only this:

> My read is that UniteLabs makes labs programmable: connectors, SDK/API
> control, workflows, and AI-ready interfaces.
>
> Datalox would sit one layer above that. When an agent uses those programmable
> surfaces, Datalox captures exact tool I/O and observations, scores the run
> with verifiers, and eventually turns verified traces into resettable dry-run
> environments.
>
> I am not claiming to simulate chemistry. The first synthetic layer is
> workflow-level: tool semantics, state ledgers, constraints, observations, and
> verifier checks.
>
> What I want to learn is whether this is already painful for your customers:
> replaying failures, auditing AI-controlled workflows, validating generated
> workflows, or dry-running before physical execution.

Then go directly to questions.

## One-Sentence Answers

If they ask "What is Datalox?":

> A replay/eval layer that turns agent tool/API interactions into verifiable
> artifacts and, over time, resettable practice environments.

If they ask "Are you building a simulator?":

> Not a physics or chemistry simulator. The first layer is workflow-level:
> tools, observations, state ledgers, constraints, and verifiers.

If they ask "Why not just use logs?":

> Logs explain what happened; Datalox artifacts are meant to be replayed,
> scored, compared, and reused for eval or dry-run.

If they ask "What would you need from us?":

> One representative non-proprietary workflow shape and feedback on which state
> and verifier checks would make it realistic enough to be useful.
