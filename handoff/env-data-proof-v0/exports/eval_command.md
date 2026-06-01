# Env Data Proof v0 Eval Command

Primary model-team baseline command:

```bash
node handoff/env-data-proof-v0/tools/run-seed-baseline.mjs \
  --input handoff/env-data-proof-v0/exports/eval.seed.jsonl \
  --out handoff/env-data-proof-v0/exports/eval.baseline.jsonl \
  --mode openai-compatible \
  --model Qwen/Qwen2.5-1.5B-Instruct \
  --base-url http://127.0.0.1:8000/v1 \
  --api-key token \
  --min-failures 10
```

Local verifier plumbing smoke command, used only when no cheap model endpoint is
available:

```bash
node handoff/env-data-proof-v0/tools/run-seed-baseline.mjs \
  --input handoff/env-data-proof-v0/exports/eval.seed.jsonl \
  --out handoff/env-data-proof-v0/exports/eval.baseline.smoke.jsonl \
  --mode verifier-smoke \
  --model deterministic-weak-baseline \
  --min-failures 10
```
