# Env Data Proof v0 Eval Command

## Corrected Training Boundary

`exports/eval.seed.jsonl` is a context-eval validation file: it preloads replay
observations in the prompt and checks whether the model can read evidence and
emit the target JSON.

`exports/eval.tool_env.seed.jsonl` is the primary environment-facing eval
contract: the model starts from the task prompt and must use domain tools.

`exports/sft.tool_messages.seed.jsonl` is the collaborator-facing SFT handoff:
standard `system`/`user`/`assistant`/`tool` messages with assistant tool
calls followed by tool observations.

`exports/sft.tool_evidence.seed.jsonl` keeps the same information in a
Datalox-rich evidence/audit shape.

## Context-Eval Baseline

```bash
# Serve the same open-weight base model that will later receive LoRA SFT.
# Example local endpoint, replace with the model team's normal inference stack.
vllm serve Qwen/Qwen3-1.7B \
  --host 127.0.0.1 \
  --port 8000
```

```bash
node handoff/env-data-proof-v0/tools/run-seed-baseline.mjs \
  --input handoff/env-data-proof-v0/exports/eval.seed.jsonl \
  --out handoff/env-data-proof-v0/exports/eval.baseline.jsonl \
  --mode openai-compatible \
  --model Qwen/Qwen3-1.7B \
  --base-url http://127.0.0.1:8000/v1 \
  --api-key token \
  --min-failures 5
```

The key rule is that this baseline must use the same trainable open-weight base
model that will be fine-tuned. A closed API model can be useful as a reference
inference run, but it is not the SFT baseline unless that exact model can be
fine-tuned by the post-training workflow.

## Tool-Env Baseline Target

The tool-env eval requires an agent harness that exposes the family tools and
logs tool calls. The input contract is:

```text
handoff/env-data-proof-v0/exports/eval.tool_env.seed.jsonl
  -> agent uses allowed domain tools
  -> verifier checks final answer and workspace/tool evidence
  -> baseline report by split/family
```

The current `run-seed-baseline.mjs` script does not execute tool-env rows; it
only runs the context-eval rows above.

Optional closed-model reference command:

```bash
node handoff/env-data-proof-v0/tools/run-seed-baseline.mjs \
  --input handoff/env-data-proof-v0/exports/eval.seed.jsonl \
  --out handoff/env-data-proof-v0/exports/eval.baseline.reference.jsonl \
  --mode openai-compatible \
  --model <reference-api-model> \
  --base-url <openai-compatible-base-url> \
  --api-key "$API_KEY" \
  --min-failures 0
```

Local verifier wiring command. This proves schemas, parsing, and verifier
wiring only; it is not model evidence:

```bash
node handoff/env-data-proof-v0/tools/run-seed-baseline.mjs \
  --input handoff/env-data-proof-v0/exports/eval.seed.jsonl \
  --out handoff/env-data-proof-v0/exports/eval.baseline.verifier.jsonl \
  --mode verifier-check \
  --model deterministic-weak-baseline \
  --min-failures 10
```
