# Agentic RL Layer Map

This document records the product boundary for Datalox Agent Replay inside the
larger agentic RL stack.

The short version:

```text
Datalox Agent Replay provides versioned API/MCP snapshot environments.
Teams consume fixture packs and fixture sets. Recording real agent-visible tool
observations is one authoring path for creating private snapshots.
```

Primary consumption loop:

```text
versioned API/MCP snapshot -> fixture set -> replay runtime -> agent run -> training/eval exports
```

Snapshot authoring loop:

```text
live MCP/API/domain env -> agent rollout -> tool_io_record.v1 -> replay_bundle.v1 -> fixture pack/version
```

This can function as record-based mocking during replay, but this repo is not a
mock-construction platform, sandbox runtime, generic environment builder, or
reward engine.

Portfolio nuance:

```text
Datalox Agent Replay repo = versioned API/MCP snapshots, fixture worlds, replay bundles
Datalox domain MCP repos  = live constrained scientific environments when shipped separately
```

Domain MCP environments can own file-backed scientific workspaces, domain tool
schemas, compact UIs, deterministic domain algorithms, and agent-first tool
contracts. Agent Replay snapshots and replays their tool I/O; it does not
become their domain runtime.

Current proof target:

```text
agent-native-science-seed@2026-06.0
  FlowCyto + Molecule Biology + scientific-data QC
  -> replay bundles / fixture set
  -> datalox run
  -> sft_frame.v1
```

This is the first test of the combined claim: Datalox ships or composes
versioned scientific agent environments plus the replay/data layer needed to
turn real rollouts into SFT, preference, eval, and later RL data.

## Environment Levels

Use these terms to avoid drifting between "environment" and "data recorder":

```text
Level 1: versioned snapshot environment
  versioned API/MCP snapshot + fixture set + verified replay bundles
  deterministic over observed scenarios
  unseen actions return replay_miss
  useful for SFT, preference data, eval, and regression

Level 2: runtime-backed environment
  live MCP/API/CLI/runtime starts from a declared state
  valid new actions advance the runtime
  every rollout emits replay evidence

Level 3: generative reset/step environment
  samples many task instances by seed/difficulty
  owns hidden state, observation renderer, terminal logic, and verifier hooks
  useful for scalable online RL after the data/export path is stable
```

## Layer Map

Frontier agentic RL systems usually combine several layers.

```text
Layer 1    sandbox/runtime foundation
Layer 2a   constrained domain MCP environments
Layer 2b   generic task environment construction
Layer 1.5  versioned snapshot environment + tool-I/O record/replay
Layer 3    evaluation and reward rules
```

### Layer 1: Sandbox And Runtime

This layer runs the agent's actual actions.

Examples:

- Docker containers
- Firecracker microVMs
- full virtual machines
- browser sessions
- terminal and filesystem sandboxes
- preemption recovery for long-running jobs
- fast image loading and container startup

Datalox does not own this layer.

The agent should still execute real code, real tests, real browser actions, or
real sandbox commands through whatever runtime the team already uses: local
Docker, e2b, Daytona, Modal, a custom sandbox cluster, or a frontier-lab
internal platform.

### Layer 1.5: Versioned Snapshot Environment And Tool-I/O Record/Replay

This is Datalox Agent Replay's home layer.

Most users should consume this layer as an installed fixture pack or fixture
set. They do not need to record anything unless they are authoring a new private
snapshot.

Snapshot authoring mode:

```text
agent tool call -> real upstream tool/API/runtime -> exact observation
```

Datalox stores:

```text
tool name
exact agent-visible arguments
request_hash = sha256(canonical_json({ tool_name, arguments }))
sequence_index
exact agent-visible observation
source/provenance metadata
export/redaction gate
```

Consumption/replay mode:

```text
fixture set -> tool name + arguments -> request_hash + sequence_index -> recorded observation
```

No live upstream call happens during replay.

A fixture set is the snapshot environment boundary. It declares which
fixture packs, task specs, verifier specs, scaffold specs, tool catalogs, and
reset behavior make up the task world. It is finite: if the agent takes a valid
but previously unrecorded path, replay must miss clearly instead of inventing a
new state transition.

This is record-based mocking in the narrow technical sense: the replayed result
stands in for a live tool or API response. But the mock is not hand-written and
not guessed. It is a real observation captured from an earlier run.

Good fit:

- MCP tools
- external APIs
- search/retrieval tools
- hosted service calls
- command results that are already captured at the tool boundary
- repeated eval/debug/regression runs over observed scenarios

Known limit:

- if the agent takes a new path that was never recorded, replay must miss
  clearly instead of inventing behavior

### Layer 2a: Constrained Domain MCP Environments

This layer gives an agent a domain-specific world to act inside without trying
to be a generic Docker or benchmark runtime.

Examples in the broader Datalox portfolio:

- flow cytometry workspaces: FCS metadata and previews, gates, plots, revisions
- molecular biology workspaces: FASTA, GenBank, sequence features, plasmid maps
- protein visualization workflows: PyMOL actions, viewer state, snapshots

These environments may be Datalox-owned when they live in sibling domain repos.
The common shape is:

```text
domain files -> file-backed workspace -> MCP tools -> structured observations -> optional UI
```

Agent Replay should capture their agent-visible tool calls, observations,
workspace revisions, validation outputs, and replay bundles. The domain repo
should own the scientific runtime, UI, parsers, and algorithms.

The first concrete Layer 2a pack should be the FlowCyto family inside
`agent-native-science-seed@2026-06.0`, not the whole seed by itself. It is not
just a trajectory format: the live domain environment must expose stateful
workspace mutations, structured tool errors, deterministic validators, and
replayable observations.

### Layer 2b: Generic Task Environment Construction

This layer builds the world the agent acts inside.

Examples:

- turning GitHub issues into runnable Docker environments
- dependency installation and test setup agents
- browser task environments
- mobile hardware simulators
- stateful behavioral mocks
- synthetic task generation with Docker images and validators

Datalox Agent Replay does not own this layer.

If a team needs a stateful phone simulator that responds to unseen camera,
GPS, or movement actions, record/replay alone is not enough. They need a real
environment or a behavioral mock. Datalox can still record the tool I/O around
that environment, but Agent Replay does not construct the generic environment.

### Layer 3: Evaluation And Reward Rules

This layer decides whether the agent succeeded.

Examples:

- F2P/P2P tests for software engineering tasks
- JUnit or language-specific test output
- Playwright browser checks
- judge agents for visual/UI tasks
- synthetic task self-verification
- reward functions and process supervision

Datalox does not own this layer.

Datalox Agent Replay should preserve verifier commands, outputs, source
references, and reward provenance when available, but it should not become the
reward engine. The replay bundle lets existing evaluators run or compare
against stable observations.

## Mocking Vocabulary

Use this distinction carefully.

```text
record-based mocking:
  real call once, save request/response, replay exact response later

behavioral mocking:
  hand-coded or generated fake system that responds to many possible inputs
```

Datalox implements the first kind for agent-visible tool I/O.

It does not implement the second kind. When a buyer says "mock," ask which kind
they mean.

Useful discovery question:

> Is your pain constructing a stateful environment that handles new unseen
> actions, or reproducing and versioning scenarios you already observed?

If the answer is reproducing observed scenarios, Datalox is directly relevant.
If the answer is handling unseen stateful behavior, the buyer needs environment
construction or behavioral simulation; Datalox can be complementary but is not
the full solution.

## Product Boundary

Datalox Agent Replay owns:

- exact tool-I/O capture
- deterministic request hashing
- sequence indexes for repeated identical calls
- MCP proxy `tools/list` catalog capture
- replay bundle packing and verification
- versioned API/MCP snapshot environments and fixture-set activation
- deterministic replay with no live fallback
- strict action/observation normalization over replay evidence
- optional derivative rows after replay evidence exists

Sibling Datalox domain MCP repos may own:

- constrained scientific workspace state
- domain-specific MCP tools
- compact domain review UIs
- deterministic domain parsers, validators, and algorithms
- domain-level action contracts that produce replayable tool I/O

Datalox Agent Replay does not own:

- sandbox orchestration
- container image construction
- dependency setup agents
- generic stateful environment simulation
- reward function design
- judge-agent implementation
- RL training algorithms
- hidden chain-of-thought capture

## Technical Plan

### Phase 1: Harden Snapshot Replay Primitive

Goal:

- make record/replay faithful enough that an MCP client can point at Datalox
  instead of an upstream MCP server without changing task behavior

Work:

- preserve upstream MCP `tools/list` schemas as `mcp_tool_catalog.v1`
- record every `tools/call` as `tool_io_record.v1`
- keep `request_hash + sequence_index` as the only replay key
- verify replay bundles before serving replay traffic
- return structured replay misses with hash and sequence index
- never call live upstream in replay mode

Done means:

- proxy record mode returns the exact upstream observation after recording
- proxy replay mode returns byte-equivalent recorded observations
- repeated identical calls replay in order
- missing calls fail deterministically

### Phase 2: Canonicalize Action/Observation Views

Goal:

- make raw traces and stored tool I/O comparable without creating a second
  replay store

Work:

- keep `tool_io_record.v1` as the stored primitive
- use `action_observation.v1` as a strict normalized view
- require explicit `arguments` on every action; use `null` when truly empty
- reject unknown fields and non-canonical JSON values
- preserve tool names exactly; no aliases or fuzzy matching
- include source kind: `mcp`, `wrapper`, or `raw_trace`

Done means:

- a tool I/O record and a raw trace with the same tool name and arguments
  produce the same request hash
- invalid raw traces fail with clear error paths
- no stdout/prose inference creates replay evidence

### Phase 3: Reference Replay Bundles

Goal:

- produce public, high-quality replay bundles that make the format concrete

Work:

- choose reproducible tasks with safe publishing rights
- capture tool I/O through the MCP proxy or wrapper path
- pack bundles with checksums
- include task README, verifier command, and expected outcome
- redact secrets and proprietary data
- publish bundles through GitHub releases or a dataset registry

Hard gate:

- every published bundle must verify locally
- every replayed observation must come from a bundled `tool_io_record.v1`
- no bundle should require live upstream tools to inspect its recorded
  observations

### Phase 4: Runtime And Verifier Provenance

Goal:

- preserve enough context for downstream eval/reward systems without making
  Datalox a sandbox or reward engine

Future replay-bundle extensions may include references to:

- model/runtime version
- sampling configuration
- system prompt hash
- tool version and corpus snapshot
- sandbox image digest
- verifier command and version
- reward source and reward version

Rule:

- store this as provenance and references only until strict schemas accept the
  fields
- do not add loose metadata bags that cannot be validated

### Phase 5: Adapters To Existing Runtimes

Goal:

- let teams keep their runtime while adopting Datalox as the record/replay
  layer

Likely adapters:

- MCP proxy adapter
- wrapper adapter for CLI agents
- OpenHands-style coding-agent adapter
- browser-agent adapter that records browser tool calls and Playwright results
- sandbox-runtime adapter that records command tool I/O without owning the
  sandbox itself

Rule:

- adapters produce `tool_io_record.v1` and optional `agent_turn.v1`
- adapters must not create replay evidence from prose summaries
- adapters may reference external artifacts, but replay bundles remain the
  portable evidence package

## Positioning Sentence

Use this when the product story drifts:

> Datalox turns traditional workflows into agent-native environments, then
> packages replay evidence into training/eval data. This repo powers the
> snapshot/replay evidence engine; recording is only the authoring path for
> private snapshots.
