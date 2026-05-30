# Datalox Pitch Deck Outline

Status: working outline.
Updated: 2026-05-20.

This is a pitch outline, not a rendered deck. It should stay honest about what
is shipped, what is planned, and which layer Datalox owns.

Canonical product sentence:

> Datalox turns traditional workflows into agent-native environments, then
> packages exact tool-I/O evidence into verifiable replay bundles and
> training/eval exports.

## Slide 1: Title

Headline:

Datalox: agent-native workflow environments with replay evidence.

Body:

- MCP-compatible domain tools and structured workflow state
- Exact tool I/O captured once as `tool_io_record.v1`
- Portable replay artifacts packaged as `replay_bundle.v1`
- Training/eval exports derived from verified evidence
- Open source: `github.com/Oshawott324/datalox-agent-replay`

Speaker note:

Say this plainly: "Datalox makes messy workflows usable by agents, records what
the agent saw at the tool boundary, and lets teams replay that evidence later
without calling the live upstream tool."

## Slide 2: Problem

Headline:

Agent logs are not replayable training evidence.

Body:

- Agent teams depend on live tools, APIs, search systems, databases, browsers,
  and sandboxes.
- Those observations drift, expire, or become expensive to reproduce.
- Chat logs collapse too much: tool names, arguments, observations, errors,
  and repeated calls often become prose.
- Teams rebuild local VCRs and tool mocks per project, but the artifacts do not
  compose across frameworks or teams.

Speaker note:

Do not frame this as "reward changes require replay" in all cases. Simple
rescoring can happen from already-captured data. Replay matters when the
team needs exact tool observations, deterministic eval/debug loops, or
record-based mocks for tool/API calls.

## Slide 3: Why Now

Headline:

The agentic RL stack is forming, but the replay layer is still missing.

Body:

- MCP made tool calling more standard.
- Open agentic RL stacks are moving quickly: verl, OpenRLHF, SkyRL, and similar
  systems.
- Frontier labs build internal sandbox, logging, and replay infrastructure.
- Mid-tier labs and agent startups need the reusable slice without building the
  whole frontier stack.
- Record/replay is most reusable at the tool-I/O boundary.

Speaker note:

The timing argument is standardization. Tool calling has a protocol. Replay
evidence does not yet have a widely adopted open artifact.

## Slide 4: Layer Boundary

Headline:

Datalox owns Layer 1.5, not the whole agentic RL stack.

Body:

```text
Layer 1   sandbox/runtime foundation
Layer 1.5 tool-I/O record/replay        <- Datalox
Layer 2   task environment construction
Layer 3   evaluation and reward rules
```

- Datalox records and replays agent-visible tool observations.
- Datalox can act as record-based mocking for tool/API calls.
- Datalox does not build stateful environments, sandboxes, reward engines, or
  judge agents.

Speaker note:

This slide prevents overclaiming. Datalox sits between the runtime and the
training/eval layer as portable evidence.

## Slide 5: Product

Headline:

Capture exact tool I/O. Seal it. Replay it deterministically.

Body:

```text
agent tool call -> tool_io_record.v1 -> replay_bundle.v1 -> deterministic replay -> optional derivatives
```

Core artifacts:

- `tool_io_record.v1`: exact request, exact observation, deterministic
  `request_hash + sequence_index`
- `mcp_tool_catalog.v1`: captured MCP `tools/list` metadata
- `agent_turn.v1`: optional turn review context
- `replay_bundle.v1`: manifest, tool I/O records, catalog artifacts, turn
  events, checksums, export state
- optional derivatives: compact trajectory/eval rows after replay evidence
  exists

Speaker note:

The replay bundle is the portable source artifact. Derivative rows are useful
but downstream.

## Slide 6: What Is Built

Headline:

The core VCR path is working.

Body:

- MCP server tools:
  - `record_tool_io`
  - `replay_tool_io`
  - `record_agent_turn`
  - `pack_replay_bundle`
  - `verify_replay_bundle`
- MCP VCR proxy:
  - record mode stores tool calls and MCP tool catalogs
  - replay mode serves verified bundle observations without upstream fallback
- Wrapper defaults:
  - replay-first post-run mode
  - trajectory export stays derivative-only
- Regression gates:
  - canonical docs tests
  - wrapper tests
  - MCP proxy tests
  - repo identity tests

Speaker note:

The demo should be a 60-second loop: record a tool call, pack a bundle, verify
it, stop upstream, replay the same call.

## Slide 7: Reference Proof

Headline:

Three verified reference bundles make the format concrete.

Body:

- `ref-mcp-success`: successful tool call with bundled tool catalog
- `ref-mcp-repeated-call`: same request hash, ordered sequence indexes
- `ref-mcp-error-observation`: structured error observation replayed exactly
- Each bundle verifies locally.
- Each bundle replays with upstream disabled.
- Each bundle has a short public README.

Speaker note:

Do not pitch a large dataset yet. Pitch proof artifacts first. These bundles
make the format real.

## Slide 8: Customer Discovery

Headline:

Early signal: teams need reproducible scenarios, not bigger chat logs.

Body:

- Current signal is early and should be stated as early.
- The recurring pain is not "store every conversation." It is:
  - tool/API observations are hard to reproduce
  - state/action boundaries get blurry
  - reward or eval analysis cannot tie cleanly back to the exact action
  - mocks are rebuilt per project instead of reused as replay evidence
- Discovery question:
  - "Do you need a stateful simulator for unseen actions, or reproducible
    replay for scenarios you already observed?"

Speaker note:

If the answer is "stateful simulator," Datalox is complementary. If the answer
is "replay observed scenarios," Datalox is directly in the pain.

## Slide 9: Competition

Headline:

The adjacent layers are crowded. The open replay artifact is not.

Body:

| Layer | Examples | Relationship |
| --- | --- | --- |
| Sandbox/runtime | e2b, Daytona, Modal, Docker, Firecracker | Datalox records tool I/O around them |
| Environment construction | RepoLaunch-style systems, benchmark harnesses | Complementary |
| Observability/evals | LangSmith, Braintrust, Helicone, Arize | Adjacent; not sealed replay bundles |
| RL frameworks | verl, OpenRLHF, SkyRL | Downstream consumers |
| Agent-native workflow environments | traditional scientific/enterprise apps reconstructed as tools and state | Datalox product wedge |
| Tool-I/O replay | no dominant open standard | Datalox evidence layer |

Speaker note:

The wedge is agent-native reconstruction of high-value workflows. Replay
evidence is the trust/data layer underneath it. The product should not become a
generic sandbox company or reward company.

## Slide 10: Business Model

Headline:

Open format first. Managed agent-native workflow infrastructure later.

Body:

- Open source:
  - schemas
  - MCP server
  - VCR proxy
  - CLI
  - reference bundles
- Hosted later:
  - managed domain workflow environments
  - managed bundle registry
  - verification and replay service
  - redaction/export workflows
  - team permissions and audit history
- Enterprise later:
  - VPC/on-prem deployment for private agent traces

Speaker note:

Do not promise hosted sandboxes as the default business. The paid wedge is
managed agent-native workflow environments plus replay evidence and governance.

## Slide 11: Roadmap

Headline:

90 days: reference bundles, design partners, one framework/runtime adapter.

Body:

- Next 2 weeks:
  - polish 3 verified reference bundles
  - replay them on a fresh clone
  - use them in discovery calls
- Next 90 days:
  - 10 public reference bundles
  - 2 design partners producing private bundles
  - one adapter beyond the MCP proxy or wrapper path
- 6 months:
  - one RL/eval framework integration or benchmark reference
  - hosted bundle registry prototype
- 12 months:
  - 3-5 active design partners
  - repeatable managed replay workflow

Speaker note:

The milestone is not "more docs." It is public, verified replay artifacts plus
teams using the format.

## Slide 12: Ask

Headline:

Raise enough to make replay bundles the default artifact for agentic RL teams.

Body:

- Use of funds:
  - engineering on adapters, verification, redaction, and hosted registry
  - design partner support
  - reference bundle production and launch
  - legal/security review for private trace handling
- Next-round proof:
  - public bundle corpus
  - design partners
  - external integration
  - hosted workflow in private beta

Speaker note:

Pick the actual amount only after investor conversations. The core ask should
be concrete: turn the open replay artifact into the adopted standard.

## Claims To Avoid

- Datalox builds sandboxes.
- Datalox constructs stateful behavioral mocks.
- Datalox computes rewards or replaces judge agents.
- Datalox captures hidden chain of thought.
- Datalox turns every chat log into training data.
- Datalox has paying customers before that is true.
- Datalox solves unseen environment behavior through replay.

## Demo Script

Use this as the live or recorded demo:

1. Start a safe upstream MCP fixture.
2. Start Datalox proxy in record mode.
3. Call one tool through the proxy.
4. Show the new `tool_io_record.v1`.
5. Pack a replay bundle.
6. Verify the bundle.
7. Stop the upstream fixture.
8. Start Datalox proxy in replay mode using the bundle.
9. Call the same tool request.
10. Show the recorded observation returned without upstream fallback.

The demo should make the product sentence obvious without explaining the whole
agentic RL stack.
