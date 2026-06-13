# Datalox API Gym

Datalox API Gym packages source-backed dry-run worlds for testing, evaluating,
training, and auditing tool-using agents before they touch real systems.

An API Gym world is a resettable, stateful action system:

```text
World = source substrate
      + mutable episode state
      + actions
      + dynamics
      + observations
      + verifier
      + evidence
```

The product object is not a connector catalog and not just a fake API. It is a
world package that an agent runtime can attach to, dry-run inside, verify, and
export as audit/eval/training evidence.

```text
source substrate
  -> world package
  -> world session
  -> MCP/action interface
  -> agent rollout
  -> verifier outcome
  -> run_export evidence
```

API Gym owns world/session/runtime behavior. `datalox-rollout-collector` owns
dataset packaging downstream from exported evidence.

API source packs are first-class source substrate. Validate a pack before using
it to design or update a world:

```bash
api-gym source-pack validate source_packs/apis/<provider>/<version>
```

Source packs include response cases for dry-run gating. An agent can call an
original-shaped API surface, while Datalox returns a grounded sampled response
case instead of calling the live provider.

## Current Worlds

`billing_support_v0`

- deterministic business workflow world
- SQLite episode state
- billing, support, CRM, and email tools
- hidden verifier checks final business state

`unitelabs_plate_qc_v0`

- deterministic dry-run lab workflow world
- SQLite episode state
- labware, liquid transfer, plate readout, workflow note, and protocol decision
  tools
- hidden verifier checks dry-run workflow invariants
- API semantics should be grounded from an explicit UniteLabs OpenAPI contract

## Quickstart

Install the package and run the tests:

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
```

Create one world session:

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

The session manifest is the integration contract for external agent
environments. It contains the task package, recommended MCP config,
`expected_tools`, a tool preflight command, finalization command, and artifact
paths.

Before rollout:

```bash
api-gym session check-tools --run runs/unitelabs-demo
```

The host must also compare its own agent-visible tool registry against
`expected_tools`. The Datalox check proves the API Gym MCP server has the right
catalog; the host check proves the agent can actually see those tools.

After the agent stops:

```bash
api-gym session finalize --run runs/unitelabs-demo --json
```

Finalize runs the verifier, writes `run_export.json`, writes
`session_finalization.json`, and exits nonzero if the verifier fails.

## Integration Contract

Agent hosts should treat API Gym as a world provider:

```ts
type DataloxWorldSessionAdapter = {
  createSession(input: {
    world: string;
    scenario: string;
    seed: number;
    out: string;
  }): Promise<SessionManifest>;

  attachTools(manifest: SessionManifest): Promise<void>;
  assertToolsVisible(expectedTools: string[]): Promise<void>;
  runAgent(taskPackagePath: string): Promise<unknown>;
  finalizeSession(runDir: string): Promise<SessionFinalization>;
};
```

MCP is the action channel. The session manifest is the lifecycle contract.

## Evidence Output

`run_export.json` is upstream evidence for collectors. It contains:

- world and scenario metadata
- task package
- captured tool trace
- verifier result
- artifact paths

The agent must not receive hidden verifier state or direct access to mutable
state files such as `state.sqlite`.

## Manual Debug Commands

The lower-level commands are still useful when debugging a world:

```bash
api-gym sample --world billing_support_v0 --scenario duplicate_payment_refund --seed 1 --out runs/demo
api-gym task --run runs/demo --out runs/demo/agent_task.json
api-gym mcp --run runs/demo
api-gym verify --run runs/demo
api-gym export --run runs/demo --out runs/demo/run_export.json
```

Billing-only HTTP/oracle/model-eval surfaces remain available:

```bash
api-gym serve --run runs/demo --port 8080
api-gym resolve --run runs/demo --policy oracle
api-gym run --run runs/demo --model qwen --base-url http://localhost:8000/v1 --api-key EMPTY
api-gym eval --world billing_support_v0 --scenarios duplicate_payment_refund,failed_invoice_retryable,refund_not_allowed_policy --seeds 1,2,3 --model qwen --base-url http://localhost:8000/v1 --api-key EMPTY --out runs/billing-eval.jsonl
api-gym report --input runs/billing-eval.jsonl
```

## Project Boundary

Read [docs/product-definition.md](docs/product-definition.md) for the canonical
boundary.

API Gym owns:

- API source packs and source references
- world specs
- world sessions
- state backends
- action contracts
- dynamics backends
- observation contracts
- hidden verifier execution
- tool traces
- run exports

API Gym does not own:

- dataset manifests
- train/dev/test split assignment
- dataset quality labels
- dataset validation reports
- model training recipes

## Layout

```text
api_gym/                 Python package and world runtime surfaces
source_packs/apis/       Raw and normalized API source substrate
worlds/                  World specs, grounding notes, evidence, and policies
website/                 VitePress documentation
tests/                   Runtime and contract tests
```

See [source_packs/apis/README.md](source_packs/apis/README.md) for the source
pack boundary and schema guidance.

For contributor workflow, see
[docs/playbooks/api-gym-builder-playbook.md](docs/playbooks/api-gym-builder-playbook.md).
