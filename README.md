# Datalox API Gym

Resettable, verifiable environments for tool-using agents: the high-stakes tool
use you cannot safely rehearse on real systems, such as lab instruments, billing
and financial ops, and anything costly or irreversible to run for real.

A "world" is a resettable stateful system the agent acts on through MCP tools,
with a hidden state-based verifier that grades the final world state and
workflow invariants, not the transcript. The agent passes because the world
ended up correct, not because it wrote a plausible answer.

```text
World = source substrate
      + mutable episode state
      + actions (MCP tools)
      + dynamics
      + observations
      + hidden verifier
      + exported evidence
```

## Try It In 60 Seconds

```bash
pip install -e '.[dev]'
python -m pytest -q
api-gym session create \
  --world unitelabs_plate_qc_v0 \
  --scenario plate_transfer_qc --seed 1 \
  --out runs/demo --json
api-gym session finalize --run runs/demo --json
```

## What's Real Today

- Two complete worlds: a dry-run lab plate-QC world and a billing/support-ops
  world with HTTP serving, an oracle resolver, and an OpenAI-compatible eval
  runner.
- A dry-run API gate over 31 source-grounded providers, 134 operations, and 179
  sourced response cases. An agent can call an original-shaped API and get a
  sourced response back instead of hitting the live service.
- A session lifecycle that plugs into an agent host, with run exports that
  produce SFT/eval rows, plus a seed post-training packet across three lab/bio
  task families.

## What's Early

- The lab world's API semantics are not yet grounded in a real vendor contract.
- Two worlds and a seed dataset: early, with no model-lift claims.
- Verifiers check workflow invariants and tool evidence, not scientific
  correctness.

## Closest Neighbors

tau-bench, WebArena, SWE-bench, and AppWorld. API Gym's bet is high-stakes,
costly-to-run domains those do not cover, with state-based verification and
source-grounded APIs.

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

  attachAdapters(manifest: SessionManifest): Promise<void>;
  assertToolsVisible(expectedTools: string[]): Promise<void>;
  runAgent(taskPackagePath: string): Promise<unknown>;
  finalizeSession(runDir: string): Promise<SessionFinalization>;
};
```

MCP is one action channel. For provider-shaped environments, the session
manifest may also include an `http` surface. Use
`api-gym serve --run <run_dir>` when the agent or SDK needs original-shaped
HTTP calls. MCP remains available for hosts that prefer tool calls; both
adapters must share the same world state and verifier. The session manifest is
the lifecycle contract.

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
