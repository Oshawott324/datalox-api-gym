# vLLM And verl Quickstart

This path is for teams that already have a model server or trainer and want
Datalox to provide the replay world plus grounded export data.

```text
OpenAI-compatible model endpoint
  -> datalox run
  -> replay fixture world
  -> datalox_run.v1
  -> datalox export sft
  -> sft_frame.v1 JSONL
```

## Run A Replay Fixture With vLLM

Start a vLLM server with the OpenAI-compatible API:

```bash
vllm serve Qwen/Qwen2.5-7B-Instruct --api-key token
```

Then run one task against a declared replay world:

```bash
datalox run \
  --fixture-set support-triage-basic@2026-05.0 \
  --base-url http://127.0.0.1:8000/v1 \
  --model Qwen/Qwen2.5-7B-Instruct \
  --api-key token \
  --prompt "Resolve this support triage task." \
  --out runs/support-triage-qwen \
  --json
```

For local bundle development, use a bundle path instead of a registry fixture:

```bash
datalox run \
  --bundle .datalox/replay-bundles/ref-mcp-repeated-call \
  --base-url http://127.0.0.1:8000/v1 \
  --model local-model \
  --api-key token \
  --prompt "Look up the policy and answer." \
  --out runs/repeated-call-smoke \
  --json
```

The run writes:

```text
runs/<run>/run.json
runs/<run>/transcript.jsonl
```

`run.json` is a `datalox_run.v1` artifact. It includes the model-visible
messages, replayed tool observations, tool record refs, replay misses if any,
final answer, fixture refs, and export gate.

Replay misses stop the run. The runner does not silently call live upstream
tools during replay.

## Export SFT Frames

Successful runs can be exported to SFT JSONL:

```bash
datalox export sft \
  --run runs/support-triage-qwen \
  --out exports/support-triage-qwen.sft.jsonl \
  --json
```

The output row is `sft_frame.v1`:

```text
exact model-visible input messages
  -> final assistant target message
  -> replay evidence refs
```

Runs with replay misses or blocked export state are rejected.

## How This Fits verl

Datalox does not replace verl. The intended first integration is:

```text
Datalox fixture set -> datalox run -> datalox export sft -> verl SFT dataset
```

Later adapters can expose the same fixture world as a reset/step environment and
reward function, but the first useful path is SFT and completion export from
verified replay evidence.
