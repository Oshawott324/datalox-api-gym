# UniteLabs Plate QC v0

`unitelabs_plate_qc_v0` is a deterministic dry-run API Gym world for a plate
transfer QC workflow.

See [API_GROUNDING.md](API_GROUNDING.md) before changing the dry-run tool
semantics. V0 should be grounded from an explicit UniteLabs OpenAPI contract
sample, not guessed from demo scripts or live workflow execution.

The `plate_transfer_qc` scenario starts with:

- `source_plate:A1` containing `120 uL`
- `assay_plate:B1` containing `0 uL`
- `tip_rack_1:A1` available
- deck mode `dry_run` with loaded labware `source_plate`, `assay_plate`, and `tip_rack_1`
- an OD600 control band for `assay_plate:B1` of `0.75..0.9`

After a valid `50 uL` aspirate from `source_plate:A1` and dispense into
`assay_plate:B1`, `read_absorbance` at `600 nm` returns `0.82` for `B1`.
The verifier expects the final submitted protocol decision to cite that readout
and choose `continue`.

## World Contract

Source substrate:

- explicit UniteLabs OpenAPI contract sample
- UniteLabs technical docs for workflow, run, log, and artifact surfaces
- no live workflow execution in V0

Episode state:

- `state.sqlite` per sampled run
- deck layout
- labware inventory
- well volume ledger
- absorbance readout ledger
- workflow notes
- submitted protocol decision

Actions:

- inspect deck state
- inspect labware state
- aspirate
- dispense
- read absorbance
- add workflow note
- submit final protocol decision

Dynamics:

- deterministic dry-run lab workflow logic
- no live hardware, workflow run, or device endpoint call

Observations:

- structured MCP tool responses
- structured errors for invalid dry-run actions
- readout ids used as evidence in the final protocol decision

Verifier:

- reads final SQLite state
- checks source volume, target volume, readout ordering, submitted target,
  decision, readout evidence, and dry-run safety constraints

Evidence:

- `run.json`
- `task.json`
- `agent_task.json`
- `agent_tool_calls.jsonl`
- `session_manifest.json`
- `session_finalization.json`
- `run_export.json`

## Session Handoff

Agent runtimes should integrate through the session manifest, not by calling
individual setup commands by hand.

Create one local session:

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

The session manifest is the integration contract. It contains:

- `task` and `task_instructions` for the agent
- `mcp` config for the tool server
- `expected_tools` for preflight validation
- `commands.check_tools` to verify the Datalox MCP tool catalog
- `commands.finalize` to verify and export evidence after the agent run
- `artifacts` paths for the run root, task package, tool trace, export, and finalization result

Before running an agent, the host must prove the agent-visible tool layer
contains every tool in `expected_tools`. For direct MCP hosts, use the `mcp`
config from the manifest. For non-MCP hosts, write an adapter that converts the
listed MCP tools into the host's native tool registry, then compare the host's
visible tool list against `expected_tools`.

The expected tools are:

```text
add_workflow_note
aspirate
dispense
get_deck_state
get_labware_state
read_absorbance
submit_protocol
```

After the agent stops, finalize the session:

```bash
api-gym session finalize --run runs/unitelabs-demo --json
```

Finalize runs the verifier, writes `runs/unitelabs-demo/run_export.json`, writes
`runs/unitelabs-demo/session_finalization.json`, and exits nonzero if the
verifier fails.

## Host Adapter Contract

An external agent environment should implement this lifecycle:

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

The host must fail before rollout if any expected tool is missing. The agent
should not receive `state.sqlite`, hidden verifier events, or direct file
access to the run state.

## Manual Smoke Path

This direct flow is useful for debugging the world itself:

```bash
api-gym session create \
  --world unitelabs_plate_qc_v0 \
  --scenario plate_transfer_qc \
  --seed 1 \
  --out runs/unitelabs-demo \
  --json

api-gym session check-tools --run runs/unitelabs-demo

# Configure the agent host from runs/unitelabs-demo/session_manifest.json.
# The host runs the agent through the MCP tools.

api-gym session finalize --run runs/unitelabs-demo --json
```

## Collector Boundary

`run_export.json` is upstream evidence. Dataset rows, labels, splits,
manifests, and validation reports belong in `datalox-rollout-collector`, not in
this world.
