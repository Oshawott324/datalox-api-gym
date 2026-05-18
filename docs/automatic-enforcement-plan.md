# Automatic Enforcement Plan

This document defines what "automatic enforcement" means for `datalox-agent-replay`, what counts as supported, and the minimum implementation plan for this repo.

The product-facing goal is approved Datalox session data plus derived trajectory data: capture agent debugging turns through Datalox MCP, assemble sessions, then package approved anonymized sessions directly or derive lean outcome-labeled rows for coding-agent training and evaluation.

## Target

For this repo, automatic enforcement means:

- on supported hosts, Datalox runs at loop boundaries without the model deciding to call MCP
- the repo stays the source of truth
- unsupported hosts degrade to guidance-only, and the docs say that plainly

Product boundary:

- `Datalox Session Data` = primary B2B source dataset product
- `AgentTurnV1` = simple per-turn capture primitive defined by [agent-turn-schema.md](./agent-turn-schema.md)
- `Datalox Trajectory Data` = compact derived B2B dataset/eval product
- `Datalox MCP` = product-facing instrumentation, session capture, and control surface
- `datalox-agent-replay` = portable protocol, CLI, durable local knowledge, and adoption assets
- `adapter` = host-specific enforcement
- `trajectory dataset` = derived export product defined by [trajectory-dataset-schema.md](./derivatives/trajectory/trajectory-dataset-schema.md)

## Non-Goals

This plan does not try to:

- make `AGENTS.md` itself into enforcement
- claim MCP availability means automatic use
- move durable knowledge into a hidden server-only runtime
- pretend unsupported hosts are automatic

## Current Boundary

Today the repo already has:

- Codex and Claude wrapper entrypoints
- a generic CLI wrapper
- a post-turn hook path
- MCP tools for resolve, record, capture, promote, and lint

But the automatic boundary is still partial:

- supported wrapper paths can be automatic
- MCP-only usage is still model-chosen
- repo instructions alone are guidance, not enforcement

## Current Mechanism

The current enforcement mechanism is not "MCP auto-calls itself". It is:

1. install-time host interception
2. shared pre-run loop assembly
3. wrapped child execution
4. shared post-run record or review
5. provenance-backed durable writes

### 1. Install-time host interception

Installation is the first enforcement point.

- Codex and Claude installs write local shim binaries in `src/core/installCore.ts`.
- The Codex shim wraps only `exec`, `e`, and `review`.
- The Claude shim wraps normal prompt runs and skips config or maintenance commands.

Concrete code:

- `src/core/installCore.ts`
  - `buildCodexShim()`
  - `buildClaudeShim()`

These shims do the important thing: they intercept the host command before the model runs and redirect into Datalox wrapper entrypoints instead of relying on the model to call MCP.

### 2. Shared pre-run loop assembly

Once the shim redirects into Datalox, the wrapper builds one shared loop envelope in `src/adapters/shared.ts`.

Current steps:

1. resolve repo path
2. auto-bootstrap the pack when safe
3. inspect the prompt for source routes such as `pdf`
4. if no source route wins, resolve loop guidance
5. render one wrapped prompt
6. export one wrapper env bundle

Concrete code:

- `src/adapters/shared.ts`
  - `buildLoopEnvelope()`
  - `buildWrapperEnv()`
  - `replacePromptPlaceholders()`

This is the real pre-run enforcement boundary today.

### 3. Wrapped child execution

Host-specific wrappers are thin. Their job is to make sure the child host actually receives the wrapped prompt.

- Claude:
  - replace the discovered prompt arg when possible
  - otherwise append the wrapped prompt
- Generic wrapper:
  - requires `__DATALOX_PROMPT__` when guidance is active
  - fails closed if injection cannot happen

Concrete code:

- `src/adapters/claude/run.ts`
- `src/adapters/generic/run.ts`

This is where enforcement stops being "guidance" and becomes "the child did or did not receive the Datalox envelope".

### 4. Shared post-run record or review

After the child exits, the wrapper goes back through shared post-run logic in `src/adapters/shared.ts`.

Current steps:

1. sanitize transcript and output
2. collect changed files
3. classify the run as `trace` or `candidate`
4. build one observed-turn payload
5. always record an event
6. optionally run second-pass review
7. optionally compile or promote the recorded event

Concrete code:

- `src/adapters/shared.ts`
  - `finalizeWrappedRun()`
  - `buildObservedTurnPayload()`
  - `recordObservedTurnPayload()`

This is the real post-run enforcement boundary today.

### 5. Hook as sidecar automation

The Claude hook path exists, but it is not the primary enforcement surface.

- `removed legacy hook script` reuses the shared payload builders
- it can auto-record from host hook payloads
- it is stronger than prompt guidance
- it is weaker than full wrapper ownership

The hook is sidecar automation, not universal enforcement.

### 6. Provenance-backed writes

Durable writes should only happen from wrapped or hook-produced provenance, not from arbitrary unwrapped edits.

Some of that path already exists through wrapped record and review flows, but the stricter provenance gate described later in this document is still part of the implementation plan, not fully finished architecture.

## What Is Already Real vs Planned

Already real:

- install-time Codex and Claude shims
- generic wrapper fail-closed prompt injection
- shared loop envelope assembly
- shared post-run record path
- optional second-pass review on supported wrapper paths
- hook reuse of shared observed-turn payload builders
- `src/adapters/capabilities.ts` as one host-support registry
- `datalox status --json`
- provenance-gated durable writes for `patch` and `promote`

Planned but not fully implemented:

- final cleanup so every wrapper uses one identical adapter contract name-for-name
- broader status and install reporting for more host/plugin surfaces beyond Codex, Claude, generic CLI, MCP-only, and repo instructions

## Support Matrix

Use one explicit support matrix in code and docs.

| Host surface | Enforcement level | Notes |
| --- | --- | --- |
| `codex` | `enforced` | shim intercepts `exec`, `e`, `review`; pre-run resolve/capture; post-run record; optional second-pass review |
| `claude` | `enforced` | shim intercepts normal prompt runs; optional hook for post-turn resume/promotion |
| generic CLI wrapper | `conditional` | enforced only when prompt injection is possible; otherwise fail or warn depending on mode |
| MCP-only host | `guidance_only` | tools are available, but the model still chooses whether to call them |
| repo instructions only | `guidance_only` | `AGENTS.md`, `CLAUDE.md`, `DATALOX.md` influence behavior but do not enforce it |

Do not call `guidance_only` paths automatic.

## Adapter Contract

Every `enforced` adapter should implement the same contract.

### Pre-run

1. Detect repo.
2. Ensure the pack is bootstrapped.
3. Detect source kinds: `pdf`, `web`, `trace`.
4. If source-grounded, capture first.
5. If routing matters, resolve loop guidance.
6. Build one wrapped prompt/evidence bundle.
7. Inject that bundle into the host command.

### Post-run

1. Sanitize transcript and child output.
2. Always record an event.
3. Optionally run second-pass review.
4. Preserve enough structured evidence for later `debugging_trajectory.v1` export.
5. Only persist note or skill changes through provenance-backed write paths.

This contract should live centrally, not be reimplemented ad hoc in each host adapter.

## Enforcement Rules

### Hard fail for enforced hosts

- wrapper is active but prompt or evidence injection did not happen
- source-grounded task required capture and capture failed
- event recording failed
- review mode was requested but reviewer is missing
- knowledge write attempted without provenance

### Soft warn

- unsupported host
- repo has only `AGENTS.md` or `DATALOX.md`
- MCP is present but host is not wrapped

This is the clean line:

- enforced adapters fail closed
- unsupported paths stay guidance-only

## Concrete Repo Design

### 1. Central host capability registry

Add:

- `src/adapters/capabilities.ts`

Define per host:

- host id
- enforcement level: `enforced | conditional | guidance_only`
- supports pre-run injection
- supports post-run hook
- supports second-pass review
- requires prompt placeholder

Acceptance:

- one importable source of truth for host support
- docs and CLI status use the same registry

### 2. Unified adapter pipeline

Main file:

- `src/adapters/shared.ts`

Central pipeline:

- `prepareWrappedRun()`
- `runChild()`
- `finalizeWrappedRun()`

Host adapters only provide:

- how prompt is injected
- how args are parsed
- whether review is available

Acceptance:

- Codex, Claude, and generic wrappers all route through the same pre/post contract
- host files stop duplicating loop assembly logic

### 3. Install remains the enforcement entrypoint

Main file:

- `src/core/installCore.ts`

Install should write a machine-readable status file:

- `.datalox/install.json`

It should include:

- installed adapters
- enforcement level by host
- hook status
- review default

Acceptance:

- agents and humans can inspect real enforcement state instead of guessing
- docs can say "automatic on supported hosts" based on actual install state

### 4. Provenance-gated durable writes

Main file:

- `src/core/packCore.ts`

`patchKnowledge()` and `promoteGap()` should require one of:

- `eventPath`
- `sessionId + hostKind`
- explicit admin override

Acceptance:

- direct unwrapped edits cannot silently mutate durable knowledge
- wrapper and hook paths can still write because they produce provenance

### 5. Keep the hook as a sidecar

Main file:

- `removed legacy hook script`

Hook responsibilities:

- reuse shared payload and provenance builders
- stay stronger than prompt guidance
- stay weaker than full wrapper ownership

Acceptance:

- hook path reuses shared observation and record logic
- hook is documented as sidecar automation, not universal enforcement

### 6. Explicit status surface

Add:

- `datalox status --json`

Show:

- host support
- current enforcement mode
- installed shims
- hook installed or not
- review default
- whether this repo is `guidance_only`, `conditional`, or `enforced`

Acceptance:

- no need to infer enforcement state from scattered files
- docs can point to one honest status command

## Docs Contract

All public docs should say:

- automatic on supported hosts
- not automatic everywhere
- MCP is available where installed
- enforcement only happens when the host adapter is active

Keep `AGENTS.md`, `CLAUDE.md`, and `DATALOX.md` as visible protocol surfaces, not as fake enforcement.

## Recommended Implementation Order

1. `src/adapters/capabilities.ts`
2. unify adapter contract in `src/adapters/shared.ts`
3. add `datalox status --json`
4. provenance-gate durable writes in `src/core/packCore.ts`
5. tighten the hook onto shared payload/provenance builders
6. update docs and install surfaces

## Suggested Acceptance Checks

- `codex exec` on an installed host always records an event without requiring MCP tool choice
- `claude --print` on an installed host does the same
- generic wrapper fails closed when active guidance cannot be injected
- MCP-only paths remain usable but are labeled `guidance_only`
- `datalox status --json` reports the same enforcement classification the docs describe
- note or skill writes fail without provenance

## Product Shape

The intended product shape for this repo is:

- portable pack first
- mandatory adapters where supported
- guidance only where not
