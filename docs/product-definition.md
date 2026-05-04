# Product Definition

This is the canonical definition of what this repo is building.

If other docs drift, this document wins. For the exported dataset row shape,
[trajectory-dataset-schema.md](./trajectory-dataset-schema.md) wins.

## One-Sentence Definition

Datalox Trajectory Data is a B2B dataset and eval product that uses Datalox MCP to turn agent debugging work into lean, outcome-labeled training rows.

## Product Focus

The repo should optimize for the B2B trajectory data and eval product.

The repo product pipeline is:

```text
agent run -> structured event -> verified trajectory row -> curated dataset/eval corpus
```

Do not preserve legacy note/skill promotion as a second product loop in this repo. Existing skills and notes are legacy or internal agent-guidance surfaces until they are migrated or isolated behind the trajectory pipeline.

## Business Goal

The commercial goal is to sell high-signal debugging trajectory datasets and eval corpora to AI companies.

The operating model is:

1. Users run an agent with Datalox MCP instrumentation enabled.
2. Datalox MCP records structured events from debugging work.
3. A small export gate and outcome label are applied.
4. Valid episodes become `debugging_trajectory.v1` rows.
5. Curated rows are packaged as datasets or eval corpora for coding-agent companies.

The desktop or host agent is the source of agent runs. The B2B trajectory dataset is the product this repo should describe and implement first.

## Why This Exists

AI companies need more than final answers or raw chat logs. For coding agents and debugging agents, the valuable unit is:

```text
problem -> context -> trajectory -> final fix -> verification -> outcome
```

That unit is useful for:

- coding-agent evals
- debugging-agent regression suites
- post-training data
- tool-use analysis
- failure-mode analysis

Datalox exists to capture that unit with enough structure and evidence that it can be useful to a B2B buyer without forcing agents to fill an audit-heavy schema during normal work.

## What We Are Building

This repo builds one product pipeline with supporting infrastructure:

1. **Datalox MCP**
   Agent instrumentation, event capture, host adapters, outcome labeling, verification status, and export control.
2. **Datalox Trajectory Data**
   The B2B dataset/eval product: lean, outcome-labeled `debugging_trajectory.v1` records and curated corpora.

Legacy repo-local skill and note surfaces may remain while the pack is being migrated, but they are not the product architecture for this repo.

The commercial export structure is:

- one lean trajectory row per meaningful debugging episode
- schema defined in [trajectory-dataset-schema.md](./trajectory-dataset-schema.md)
- records include the problem, context, agent trajectory, final fix, outcome label, verification state, and a small export gate

The agent capture structure is:

- agents or host adapters produce structured events
- events preserve enough context, action, evidence, and verification material for export
- valid events become trajectory rows after the row is labeled and export-blocking issues are handled

The first-class capture surface is Datalox MCP:

- `record_trajectory` records one explicit `debugging_trajectory.v1` row as `payload.trajectoryRow`
- `export_trajectories` exports sellable row candidates from recorded events into JSONL
- `record_turn_result` may carry an explicit trajectory row candidate, but it must not infer one from prose fields

## Data Capture Rule

Datalox should capture data only when it can preserve trust.

Every exportable trajectory record must include:

- explicit schema version
- task prompt or problem statement
- minimal context needed to understand the fix
- concise agent-visible trajectory steps
- final fix summary
- outcome label
- verification status
- small export gate

Raw chat logs are not the product. A record is useful only after it has been structured, verified, and labeled.

## Source Rules

The event capture and dataset export should stay direct:

- `trace` inputs record what happened during an agent run
- `web` and `pdf` inputs provide source evidence
- verified debugging episodes can become trajectory dataset rows

An exported trajectory can link:

- source event paths
- changed files or patches
- matched internal guidance ids when available
- verification artifacts

## Product Boundary

- `Datalox Trajectory Data` = primary B2B dataset/eval product.
- `Datalox MCP` = instrumentation, capture, labeling, verification status, and export-control surface.
- `Datalox Desktop` or a desktop agent = a capture client, not a separate product loop for this repo.
- `datalox-trajectory-mcp` = repo-local implementation package, protocol, CLI, event capture, export, and remaining legacy guidance assets.
- `adapter` = host-specific enforcement and automation.

MCP availability alone is not enforcement. Enforced host wrappers still matter because they inject guidance before the child run and can record after it.

## How Knowledge And Data Should Emerge

Datalox should not be a raw log dump and should not be generic vector memory.

The export progression is primary:

```text
agent run -> structured event -> verified trajectory row -> curated dataset/eval corpus
```

Legacy note/skill promotion should be treated as internal behavior in this repo. New product work should route through structured events and trajectory rows.

The system should prefer:

- provenance-aware capture
- explicit export blocking when data cannot be sold
- outcome-labeled rows
- exportable structured rows
- simple agent-readable capture outputs
- low-human-setup operation

## What We Are Not Building

We are not building:

- a generic chat memory blob
- a raw desktop surveillance stream
- a hidden server-only memory layer that agents cannot inspect
- a human-first wiki with agent support added later
- a consumer data marketplace sold directly to end users
- an unlabeled collection of traces with no outcome or export gate
- a parallel local skill/note product loop inside this trajectory export repo

## Stable Product Sentence

Use this sentence when describing the project:

> Datalox Trajectory Data provides lean, outcome-labeled debugging trajectories for coding-agent training and evaluation, captured through Datalox MCP.

## Repo Rule

When repo docs talk about Datalox, they should stay consistent with this definition:

- B2B trajectory data/evals are the primary product focus
- Datalox MCP is the instrumentation, capture, labeling, verification, and export-control layer
- `datalox-trajectory-mcp` is the repo-local implementation package
- legacy note/skill promotion is not a product loop for this repo
- raw traces are not the product
- exported dataset rows must follow [trajectory-dataset-schema.md](./trajectory-dataset-schema.md)
- agent-first operation and setup
