# Fixture Worlds And Fixture Sets

Fixture worlds are pinned replay runtimes for agent tool I/O. A fixture install
only materializes verified data into a local cache. Replay activation is a
separate command.

Primary rule:

```text
install caches
replay activates
```

Datalox does not invent behavior for calls outside a fixture. Unseen calls
return deterministic replay misses.

## Fixture Repository

The curated fixture repository is expected beside this repo during local
development:

```text
../datalox-replay-fixtures
```

That repo owns fixture data, fixture-set data, expected behavior docs, eval
prompts, and fixture validation/packing scripts. This repo owns the engine that
installs, verifies, and serves those fixtures.

Current known fixture packs:

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

Current known fixture sets:

```text
appworld-calendar-basic@2026-06.0
bio-agent-basic@2026-06.0
coding-review-ci-basic@2026-06.0
support-triage-basic@2026-06.0
```

## Install One Fixture

Install directly from a local fixture directory:

```bash
datalox fixtures install ../datalox-replay-fixtures/fixtures/github-pr-review-basic
```

Install from the fixture repo catalog:

```bash
datalox fixtures install github-pr-review-basic@2026-05.0 \
  --catalog ../datalox-replay-fixtures/catalog.json
```

List installed fixture worlds:

```bash
datalox fixtures list
```

## Install A Fixture Set

Fixture sets are catalog-backed because they resolve multiple member fixtures.

```bash
datalox fixture-sets install support-triage-basic@2026-06.0 \
  --catalog ../datalox-replay-fixtures/catalog.json
```

## Replay

Replay one installed fixture:

```bash
datalox replay --fixture github-pr-review-basic@2026-05.0
```

Replay one installed fixture set:

```bash
datalox replay --fixture-set support-triage-basic@2026-06.0
```

Replay multiple installed fixtures:

```bash
datalox replay --fixtures \
  github-pr-review-basic@2026-05.0 \
  slack-support-thread-basic@2026-05.0 \
  search-policy-corpus-basic@2026-05.0
```

## Run With An OpenAI-Compatible Model

`datalox run` is the immediate path for vLLM, verl data generation, Groq, or
OpenAI-compatible hosted models. It auto-installs the fixture set, converts the
replayed MCP tool catalog into OpenAI function tools, and writes one
`datalox_fixture_run.v1` JSONL row per eval prompt.

```bash
export OPENAI_BASE_URL=http://localhost:8000/v1
export OPENAI_API_KEY=EMPTY

datalox run \
  --fixture-set support-triage-basic@2026-06.0 \
  --catalog ../datalox-replay-fixtures/catalog.json \
  --model Qwen/Qwen2.5-7B-Instruct \
  --split train \
  --max-tasks 1 \
  --out exports/fixture-runs/support-triage-basic.train.jsonl \
  --json
```

For hosted OpenAI-compatible APIs, change only `OPENAI_BASE_URL`,
`OPENAI_API_KEY`, and `--model`. The runner does not execute verifier specs or
reference rewards. It records the model-visible episode and replay misses so
verl or another trainer/eval harness can consume the JSONL and compute rewards
outside this repo.

## Spec Metadata

Fixture packs and fixture sets may reference metadata-only specs:

```json
{
  "specs": {
    "taskSpecs": [{ "path": "tasks/github-pr-review-risk.json" }],
    "verifierSpecs": [{ "path": "verifiers/github-pr-review-risk.json" }],
    "scaffoldSpecs": [{ "path": "scaffolds/codex-review.json" }]
  }
}
```

The engine validates those files during install and preserves the resolved spec
refs in replay startup output. These specs are declarations only. Installing or
replaying a fixture must not execute verifier commands, start runtime adapters,
or infer hidden reward logic from the spec.

## Pass Criteria

- Fixture manifests validate against the existing `datalox-replay-fixtures`
  manifest shape.
- Optional task, verifier, and scaffold specs validate when referenced by a
  fixture or fixture set.
- Spec refs are preserved through cache install and replay startup output.
- Every installed fixture verifies its replay bundle before it can be served.
- Install does not start replay.
- Replay verifies bundles again before serving observations.
- Fixture-set replay rejects tool-name collisions unless namespacing is added
  explicitly in a later version.
- Replay misses include request hash, sequence index, tool name, active fixture
  refs, available tool names, and `liveFallback: false`.
- `datalox run` returns replay misses to the model as tool results and never
  calls live upstream tools for missing records.
- `datalox run` writes `datalox_fixture_run.v1` JSONL with task metadata,
  model-visible messages, replayed tool observations, SFT/preference flags, and
  unlabeled quality.

Primary replay loop:

```text
agent tool call -> tool_io_record.v1 -> replay_bundle.v1 -> deterministic replay -> optional derivatives
```
