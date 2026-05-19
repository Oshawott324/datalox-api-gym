# Agentic RL Layer Map

This document records the product boundary for Datalox Agent Replay inside the
larger agentic RL stack.

The short version:

```text
Datalox is the tool-I/O VCR layer.
It records real agent-visible tool observations once, packages them into
verifiable replay bundles, and replays them deterministically later.
```

Primary replay loop:

```text
agent tool call -> tool_io_record.v1 -> replay_bundle.v1 -> deterministic replay -> optional derivatives
```

This can function as record-based mocking during replay, but Datalox is not a
mock-construction platform, sandbox runtime, environment builder, or reward
engine.

## The Four Layers

Frontier agentic RL systems usually combine at least four layers.

```text
Layer 1   sandbox/runtime foundation
Layer 1.5 tool-I/O record/replay
Layer 2   task environment construction
Layer 3   evaluation and reward rules
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

### Layer 1.5: Tool-I/O Record/Replay

This is Datalox's home layer.

Record mode:

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

Replay mode:

```text
tool name + arguments -> request_hash + sequence_index -> recorded observation
```

No live upstream call happens during replay.

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

### Layer 2: Task Environment Construction

This layer builds the world the agent acts inside.

Examples:

- turning GitHub issues into runnable Docker environments
- dependency installation and test setup agents
- browser task environments
- mobile hardware simulators
- stateful behavioral mocks
- synthetic task generation with Docker images and validators

Datalox does not own this layer.

If a team needs a stateful phone simulator that responds to unseen camera,
GPS, or movement actions, record/replay alone is not enough. They need a real
environment or a behavioral mock. Datalox can still record the tool I/O around
that environment, but it does not construct the environment.

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

Datalox should preserve verifier commands, outputs, source references, and
reward provenance when available, but it should not become the reward engine.
The replay bundle lets existing evaluators run or compare against stable
observations.

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

Datalox owns:

- exact tool-I/O capture
- deterministic request hashing
- sequence indexes for repeated identical calls
- MCP proxy `tools/list` catalog capture
- replay bundle packing and verification
- deterministic replay with no live fallback
- strict action/observation normalization over replay evidence
- optional derivative rows after replay evidence exists

Datalox does not own:

- sandbox orchestration
- container image construction
- dependency setup agents
- stateful environment simulation
- reward function design
- judge-agent implementation
- RL training algorithms
- hidden chain-of-thought capture

## Technical Plan

### Phase 1: Harden Tool-I/O VCR

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

> Datalox is the open-source tool-I/O VCR layer for agentic RL teams: record
> real tool observations once, package them into verifiable replay bundles, and
> replay them deterministically across eval, debugging, regression, and data
> pipelines.
