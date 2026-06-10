# UniteLabs Chat Demo

This page is a short presentation script for a UniteLabs sanity-check call.
The demo should take 2-3 minutes; the value is in the questions.

The demo is intentionally not a UniteLabs integration. It frames Datalox as a
layer above programmable lab control:

- tool/API calls with structured arguments and results
- stateful side effects
- hidden verifier state
- replay/eval evidence
- resettable synthetic environment seed

## Opening

> I am looking at replay and eval infrastructure for AI-controlled lab
> workflows. When an agent calls instruments or lab APIs, can we capture enough
> tool I/O, observations, state context, and verifier evidence to debug, audit,
> evaluate, and eventually turn verified runs into resettable practice
> environments without rerunning the physical experiment every time?

The important boundary:

- UniteLabs makes instruments and workflows programmable.
- Datalox records and verifies agent behavior over programmable surfaces.
- Replay/eval is the hook; resettable synthetic environments are the
  compounding layer.

## Demo Flow

1. UniteLabs is the programmable lab control plane.
2. Real execution is source of truth, but too costly for every agent attempt.
3. Datalox captures tool I/O, scores behavior, and reuses verified traces.
4. The artifact is structured tool I/O plus state-based verification.
5. Move to discovery.

## Hook And Destination

Replay is the easiest front door because it is concrete: the lab can inspect
what the agent asked instruments to do and what observations came back.

Eval is the next layer: the same record becomes scoreable once a verifier checks
final state and workflow invariants.

The strategic destination is a resettable environment: verified traces and
domain rules become cheap practice worlds for dry-runs, regression tests, and
agent training before spending real instrument time.

## Lab-Shaped Replay Artifact

This is the target shape for lab workflows:

```json
{"turn":1,"tool":"labware.get_deck_state","arguments":{"deck_id":"deck_alpha"},"result":{"ok":true,"data":{"loaded_labware":["source_plate","assay_plate"]}}}
{"turn":2,"tool":"liquid_handler.aspirate","arguments":{"source":"source_plate:A1","volume_ul":50},"result":{"ok":true,"data":{"observed_volume_ul":50}}}
{"turn":3,"tool":"liquid_handler.dispense","arguments":{"target":"assay_plate:B1","volume_ul":50},"result":{"ok":true,"data":{"target_volume_ul":50}}}
{"turn":4,"tool":"plate_reader.read_absorbance","arguments":{"plate":"assay_plate","wavelength_nm":600,"wells":["B1"]},"result":{"ok":true,"data":{"values":{"B1":0.82}}}}
```

This is not a transcript. It is structured evidence: exact calls, observations,
state transitions, and side effects.

The local demo files are:

- `demos/unitelabs_chat/lab_tool_io.jsonl`
- `demos/unitelabs_chat/lab_replay_bundle.json`
- `demos/unitelabs_chat/index.html`

## Verifier

A useful replay/eval artifact needs verifier output, not just logs.

```json
{
  "schema_version": "datalox.verifier_result.v0",
  "workflow_id": "demo_plate_qc_001",
  "verifier": "plate_qc_transfer_and_readout",
  "ok": true,
  "checks": [
    {"name": "source_not_overdrawn", "ok": true},
    {"name": "target_volume_recorded", "ok": true},
    {"name": "readout_recorded_after_dispense", "ok": true},
    {"name": "agent_decision_matches_observation", "ok": true}
  ]
}
```

For a real lab workflow, verifier checks could come from instrument state,
labware metadata, run logs, volume ledgers, readout ledgers, and
domain-specific invariants.

## From Trace To Environment

| Artifact | What it enables |
| --- | --- |
| Replay bundle | Debug exact tool calls, observations, state fingerprints, and decision context after a run fails. |
| Eval case | Score whether an agent respected constraints, interpreted observations, and reached a valid final state. |
| Regression test | Compare new agents, prompts, policies, or tool schemas against the same verified workflow. |
| Resettable environment | Let agents practice workflow-level decisions before spending real instrument time. |

The useful next prototype is one representative non-proprietary lab workflow,
not a broad synthetic lab. Good candidates are plate setup, reader QC, sample
tracking, or instrument warmup.

## Discovery Questions

- Is the bottleneck still connectivity, or are replay and validation already
  painful?
- When workflows fail mid-run, what state is captured today?
- What is still hard to reconstruct after a failed run?
- What would make an AI-generated workflow safe enough to execute?
- Would dry-runs or resettable eval worlds be useful before physical runs?
- Which lab workflow shape would be best for a tiny non-proprietary prototype?
- Would customers call this replay, audit trail, digital twin, simulation,
  dry-run, validation, or eval?

## Close

> If this direction is relevant, the useful next step would be for me to model
> one representative non-proprietary lab workflow as a tiny resettable
> environment. Then we can see whether replay/eval plus synthetic dry-run adds
> value on top of programmable instrument control.
