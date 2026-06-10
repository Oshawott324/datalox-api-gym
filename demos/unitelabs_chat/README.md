# UniteLabs Chat Demo

This folder contains a presentation-ready concept demo for a 15-minute
UniteLabs sanity-check call. Keep the demo to 2-3 minutes and save most of the
time for questions.

The demo goal is narrow:

> Show how Datalox can record agent tool/API I/O, observations, state context,
> and verifier results so AI-controlled workflows can be debugged, audited,
> evaluated, and reused without rerunning the physical workflow every time.

The strategic point:

> Replay/eval is the hook. Once traces are verified, they become the basis for
> resettable synthetic environments where agents can practice and regress-test
> before spending real instrument time.

## What To Open

Open this file in a browser:

```bash
open demos/unitelabs_chat/index.html
```

The page is a small browser deck. Use the on-screen controls or left/right arrow
keys.

## Talk Track

Use this in the first minute:

> I am looking at replay and eval infrastructure for AI-controlled lab
> workflows. When an agent calls instruments or lab APIs, can we capture enough
> tool I/O, observations, state context, and verifier evidence to debug, audit,
> evaluate, and later turn the interaction into reusable practice environments
> without rerunning the physical experiment every time?

Then show the deck:

1. UniteLabs is the programmable lab control plane.
2. Real execution is source of truth, but too costly for every agent attempt.
3. Datalox captures tool I/O, scores state, and reuses verified traces.
4. The artifact is structured tool I/O plus state-based verification.
5. The rest of the call is discovery.

## Files

- `index.html`: browser deck for the call.
- `slide_scripts.md`: presenter script for each slide.
- `call_plan.md`: call agenda, positioning, objection handling, and close.
- `lab_tool_io.jsonl`: fake lab trace showing the desired replay artifact shape.
- `lab_replay_bundle.json`: compact manifest for the same fake lab workflow.
- `evidence/billing_demo_run/`: real API Gym evidence run generated from the
  current repo.

## Optional Backup Demo

If you want to prove the existing primitive live, run:

```bash
api-gym verify --run demos/unitelabs_chat/evidence/billing_demo_run
```

That verifier reads final SQLite state, not transcript text.

To regenerate the evidence run:

```bash
rm -rf demos/unitelabs_chat/evidence/billing_demo_run
api-gym sample \
  --world billing_support_v0 \
  --scenario duplicate_payment_refund \
  --seed 7 \
  --out demos/unitelabs_chat/evidence/billing_demo_run
api-gym resolve --run demos/unitelabs_chat/evidence/billing_demo_run --policy oracle \
  > demos/unitelabs_chat/evidence/billing_demo_run/oracle_resolution.json
api-gym verify --run demos/unitelabs_chat/evidence/billing_demo_run \
  > demos/unitelabs_chat/evidence/billing_demo_run/verifier_result.json
api-gym task --run demos/unitelabs_chat/evidence/billing_demo_run \
  --out demos/unitelabs_chat/evidence/billing_demo_run/agent_task.json \
  > demos/unitelabs_chat/evidence/billing_demo_run/task_package_stdout.json
```

## Discovery Questions

- Is the current bottleneck still connectivity, or do teams already feel pain
  around observability, replay, validation, and failed-run debugging?
- When an AI-generated workflow fails mid-run, what state is captured today?
- Would replayable tool traces help support, audit, compliance, or regression
  testing?
- Do customers ask for dry-run or simulated execution before physical
  instruments are used?
- What parts of a lab workflow need to be faithful for a resettable eval world
  to be useful?
- Would they describe this need as replay/eval, dry-run, digital twin,
  simulation, or environment?
