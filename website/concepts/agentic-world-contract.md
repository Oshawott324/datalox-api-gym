# Agentic World Contract

A Datalox world is a stateful action system for agents.

```text
World = source substrate
      + mutable episode state
      + actions
      + dynamics
      + observations
      + verifier
      + evidence
```

The word "world" is broader than "simulator" and broader than "fake API."
Simulator logic is only one possible dynamics backend.

## World Shell

The world shell is the stable contract an agent runtime integrates with:

- session lifecycle
- state path
- action contract
- observation contract
- reset policy
- verifier contract
- evidence export

The current lifecycle surface is:

```bash
api-gym session create --world <world> --scenario <scenario> --seed <seed> --out <run-dir> --json
api-gym session check-tools --run <run-dir>
api-gym session finalize --run <run-dir> --json
```

`session_manifest.json` is the handoff object for agent hosts. It contains the
task package, MCP config, expected tools, preflight command, finalization
command, and artifact paths.

## Dynamics Backend

The dynamics backend decides what changes after an action. Different worlds can
use different backends:

- deterministic business logic
- dry-run lab workflow logic
- replayed provider observations
- live-gated provider calls
- simulator or oracle output

The backend can change without changing the agent-host lifecycle contract.

## MCP Is Only The Action Channel

MCP lets the agent inspect and mutate world state through tools. It is not the
whole environment contract.

External hosts also need to create sessions, attach tools, prove the tools are
agent-visible, run the agent, finalize the session, and consume the verifier
plus exported evidence.

## Verifier State Is Hidden

Agents should see task instructions and tool observations. They should not see
hidden verifier state or direct state files such as `state.sqlite`.

The verifier checks final world state and workflow invariants, not whether the
agent wrote a plausible final answer.

## Evidence For Collectors

API Gym produces upstream evidence. Dataset packaging happens in
`datalox-rollout-collector`.

```text
API Gym:
  world_ref + task_ref + tool trace + verifier outcome + run_export

Rollout Collector:
  world_ref + rollout_ref + outcome_ref + label_ref -> dataset package
```
