# Quickstart

Install the package in editable mode and run the tests:

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
```

## Create A World Session

The session lifecycle is the canonical integration path for agent hosts:

```bash
api-gym session create \
  --world unitelabs_plate_qc_v0 \
  --scenario plate_transfer_qc \
  --seed 1 \
  --out runs/unitelabs-demo \
  --json
```

This writes:

```text
runs/unitelabs-demo/
  run.json
  state.sqlite
  task.json
  agent_task.json
  session_manifest.json
```

`session_manifest.json` contains:

- task instructions
- recommended MCP config
- expected tools
- preflight command
- verifier command
- finalization command
- artifact paths

## Preflight Tools

Check that the Datalox MCP server exposes the expected tools:

```bash
api-gym session check-tools --run runs/unitelabs-demo
```

The agent host must also prove its own agent-visible tool registry contains
every entry in `expected_tools`. The Datalox check proves the MCP server
catalog. The host check proves the agent can actually use those tools.

## Run The Agent

Configure the host from `session_manifest.json`.

The host should load the task package, attach the MCP server, run the agent, and
prevent the agent from reading `state.sqlite` or hidden verifier state directly.

For generic command-line hosts, use:

```bash
api-gym run-host --run runs/unitelabs-demo -- <agent-host-command>
```

## Finalize

After the agent stops, finalize the session:

```bash
api-gym session finalize --run runs/unitelabs-demo --json
```

Finalize runs the verifier, writes `run_export.json`, writes
`session_finalization.json`, and exits nonzero if the verifier fails.

## Debugging Worlds Directly

Lower-level commands are useful while developing a world:

```bash
api-gym sample --world billing_support_v0 --scenario duplicate_payment_refund --seed 1 --out runs/demo
api-gym task --run runs/demo --out runs/demo/agent_task.json
api-gym mcp --run runs/demo
api-gym verify --run runs/demo
api-gym export --run runs/demo --out runs/demo/run_export.json
```

Billing-only HTTP, oracle, and model-eval commands remain available for the
current billing world:

```bash
api-gym serve --run runs/demo --port 8080
api-gym resolve --run runs/demo --policy oracle
api-gym run --run runs/demo --model qwen --base-url http://localhost:8000/v1 --api-key EMPTY
api-gym eval --world billing_support_v0 --scenarios duplicate_payment_refund,failed_invoice_retryable,refund_not_allowed_policy --seeds 1,2,3 --model qwen --base-url http://localhost:8000/v1 --api-key EMPTY --out runs/billing-eval.jsonl
api-gym report --input runs/billing-eval.jsonl
```
