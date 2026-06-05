# World API Contract

This is the proposed stable interface behind Datalox environments.

MCP is the first adapter because the collaborator already uses MCP. The
canonical interface is the lifecycle below.

## Lifecycle

```text
reset(task_id, run_dir, seed=None)
  -> session_id
  -> initial observation
  -> environment tool specs
  -> task-relevant tool names in the prompt/observation

tools(session_id)
  -> environment tool catalog

step(session_id, tool_call)
  -> observation
  -> reward
  -> terminated
  -> truncated
  -> info

finalize(session_id, answer)
  -> passed
  -> reward
  -> terminated
  -> verifier checks

export(session_id, format)
  -> SFT / eval / trajectory export derived from the run
```

## Why This Exists

MCP answers how an agent calls tools. It does not define the full training or
eval episode lifecycle. This API defines the lifecycle once, then exposes it
through adapters.

```text
Datalox World API
  -> MCP adapter
  -> Python adapter
  -> CLI adapter
  -> later HTTP adapter
```

## Current Implementation

The preview implementation wraps `appendix/runnable-world/`.

```text
world-api/datalox_world/drivers/runnable_world.py
  wraps the existing runnable-world tools and verifier

world-api/datalox_world/adapters/mcp_stdio.py
  exposes environment tools plus datalox_submit_answer
  relies on the system prompt to scope task-relevant tools

world-api/datalox_world/drivers/sandbox_command.py
  thin command-driver boundary for Docker/E2B/Modal/custom sandboxes
```

## Sandbox Boundary

Sandbox-backed worlds should implement the same lifecycle. Datalox should not
own the sandbox platform in this repo.

```text
Sandbox backend owns:
  container / VM / hosted runtime
  task setup
  tool execution
  file and state mutations
  verifier execution

Datalox World API owns:
  reset/step/finalize/export contract
  tool specs exposed to the agent
  trajectory shape
  adapters
```

## Review Question

Please judge this contract, not the Python code style:

```text
Can your current MCP harness use this adapter today, and would this lifecycle be
enough for SFT/eval/RL extraction after we scale to 80/20/20?
```
