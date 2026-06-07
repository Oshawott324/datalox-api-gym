# API Worlds And World Sets

API worlds are resettable, verifiable practice environments for agent tool use.
Some API worlds are replay-backed: installation materializes verified replay
evidence into a local cache, and activation serves that evidence through the
same tool contract an agent sees at run time.

Primary rule:

```text
install caches
replay activates
```

Datalox does not invent behavior for calls outside an API world. Unseen calls
return deterministic replay misses so the agent can reason about the finite
world boundary.

## API World Repository

The curated API world repository is expected beside this repo during local
development:

```text
../datalox-api-gym-worlds
```

That repo owns published API world data, world-set data, expected behavior docs,
eval prompts, and validation/packing scripts. This repo owns the runtime that
installs, verifies, serves, and exports those worlds.

Current known replay-backed API worlds:

```text
appworld-calendar-basic@2026-06.0
flowcyto-gating-basic@2026-06.0
github-ci-failure-basic@2026-05.0
github-pr-review-basic@2026-05.0
literature-protocol-search@2026-06.0
molecule-sequence-annotation@2026-06.0
protein-viewer-snapshot@2026-06.0
search-policy-corpus-basic@2026-05.0
slack-support-thread-basic@2026-05.0
stripe-billing-edge-cases@2026-05.0
```

Current known API world sets:

```text
appworld-calendar-basic@2026-06.0
bio-agent-basic@2026-06.0
coding-review-ci-basic@2026-06.0
support-triage-basic@2026-06.0
```

## Install One API World

Install directly from a local world directory:

```bash
datalox fixtures install ../datalox-api-gym-worlds/fixtures/github-pr-review-basic
```

Install from the API world catalog:

```bash
datalox fixtures install github-pr-review-basic@2026-05.0 \
  --catalog ../datalox-api-gym-worlds/catalog.json
```

List installed API worlds:

```bash
datalox fixtures list
```

## Install An API World Set

World sets are catalog-backed because they resolve multiple member worlds.

```bash
datalox fixture-sets install support-triage-basic@2026-06.0 \
  --catalog ../datalox-api-gym-worlds/catalog.json
```

## Replay-Backed Activation

Activate one installed replay-backed API world:

```bash
datalox replay --fixture github-pr-review-basic@2026-05.0
```

Activate one installed API world set:

```bash
datalox replay --fixture-set support-triage-basic@2026-06.0
```

Activate multiple installed API worlds:

```bash
datalox replay --fixtures \
  github-pr-review-basic@2026-05.0 \
  slack-support-thread-basic@2026-05.0 \
  search-policy-corpus-basic@2026-05.0
```

## Run One Prompt With An OpenAI-Compatible Model

`datalox run` is the immediate path for putting one model/agent inside one
declared API world. It writes a `datalox_run.v1` transcript directory that can
later be exported to SFT or other training/eval adapters.

```bash
export OPENAI_BASE_URL=http://localhost:8000/v1
export OPENAI_API_KEY=EMPTY

datalox run \
  --fixture-set support-triage-basic@2026-06.0 \
  --base-url "$OPENAI_BASE_URL" \
  --model Qwen/Qwen2.5-7B-Instruct \
  --api-key "$OPENAI_API_KEY" \
  --prompt "Find replayed policy evidence for delayed invoice webhooks." \
  --out runs/support-triage-basic.train-001 \
  --json
```

For hosted OpenAI-compatible APIs, change only `OPENAI_BASE_URL`,
`OPENAI_API_KEY`, and `--model`.

## Eval Fixture-Set Splits

`datalox eval` is the batch path for world-set tasks and splits. It
auto-installs the world set, converts the replayed MCP tool catalog into
OpenAI function tools, and writes one `datalox_fixture_run.v1` JSONL row per
eval prompt.

```bash
datalox eval \
  --fixture-set support-triage-basic@2026-06.0 \
  --catalog ../datalox-api-gym-worlds/catalog.json \
  --model Qwen/Qwen2.5-7B-Instruct \
  --base-url "$OPENAI_BASE_URL" \
  --api-key "$OPENAI_API_KEY" \
  --split train \
  --max-tasks 1 \
  --out exports/fixture-runs/support-triage-basic.train.jsonl \
  --json
```

The eval runner does not execute verifier specs or reference rewards. It records
the model-visible episode and replay misses so
verl or another trainer/eval harness can consume the JSONL and compute rewards
outside this repo.

## Spec Metadata

Replay-backed API worlds and world sets may reference metadata-only specs:

```json
{
  "specs": {
    "taskSpecs": [{ "path": "tasks/github-pr-review-risk.json" }],
    "verifierSpecs": [{ "path": "verifiers/github-pr-review-risk.json" }],
    "scaffoldSpecs": [{ "path": "scaffolds/codex-review.json" }]
  }
}
```

The runtime validates those files during install and preserves the resolved spec
refs in startup output. These specs are declarations only. Installing or
activating a replay-backed API world must not execute verifier commands, start
runtime adapters, or infer hidden reward logic from the spec.

## Pass Criteria

- World manifests validate against the existing `datalox-api-gym-worlds`
  manifest shape.
- Optional task, verifier, and scaffold specs validate when referenced by a
  world or world set.
- Spec refs are preserved through cache install and replay startup output.
- Every installed replay-backed world verifies its replay bundle before it can be
  served.
- Install does not start replay.
- Replay verifies bundles again before serving observations.
- World-set replay rejects tool-name collisions unless namespacing is added
  explicitly in a later version.
- Replay misses include request hash, sequence index, tool name, active fixture
  refs, available tool names, and `liveFallback: false`.
- `datalox eval` returns replay misses to the model as tool results and never
  calls live upstream tools for missing records.
- `datalox eval` writes `datalox_fixture_run.v1` JSONL with task metadata,
  model-visible messages, replayed tool observations, SFT/preference flags, and
  unlabeled quality.

Replay evidence loop:

```text
agent tool call -> tool_io_record.v1 -> replay_bundle.v1 -> deterministic replay -> optional derivatives
```
