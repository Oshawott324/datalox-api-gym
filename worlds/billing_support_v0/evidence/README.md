# Billing Support v0 Evidence

Phase 5 starts from observed provider behavior instances before changing fake
world behavior.

This directory contains:

- `observed_instances.jsonl`: provider behavior instances from official docs or
  live probes.
- `normalized_cases.jsonl`: small fake-world-relevant cases that cite observed
  instance ids.
- `probes/stripe_refund_instances.py`: a Stripe test-mode probe for refund
  behavior.
- `raw/`: raw JSONL output from live probes.

## Current Evidence State

No usable Stripe or Zendesk credentials were found during this pass. The checked
locations were:

- environment variables: `STRIPE_SECRET_KEY`, `STRIPE_API_KEY`,
  `ZENDESK_API_TOKEN`, `ZENDESK_EMAIL`, `ZENDESK_SUBDOMAIN`
- `/Users/yifanjin/datalox-agent-replay/docs/api_keys.md`

The rows in `observed_instances.jsonl` are therefore `source_type: docs`. They
are not live sandbox observations. They only use concrete examples and partial
shapes from official Stripe and Zendesk documentation.

## Run The Stripe Probe

Use a Stripe test secret key. The script refuses to run with a non-test key
unless `--unsafe-live-key` is passed explicitly.

```bash
STRIPE_SECRET_KEY=sk_test_... \
  python worlds/billing_support_v0/evidence/probes/stripe_refund_instances.py
```

The probe writes raw request/response/error rows under
`worlds/billing_support_v0/evidence/raw/`.

Targeted Stripe cases:

- full refund
- partial refund
- over-refund after a partial refund
- duplicate-like second payment refunded with reason `duplicate`
- invalid refund reason, if Stripe exposes it as a clean API error

## How Evidence Feeds Fake-World Design

Agents should be able to inspect this directory and see exactly why fake billing
and support behaviors exist. `normalized_cases.jsonl` is the bridge:

1. Read one normalized case.
2. Follow `observed_instance_ids` back to `observed_instances.jsonl`.
3. Implement or adjust fake-world behavior only when the provider instance
   supports it.
4. Keep verifiers tied to SQLite state changes, not prose summaries.

Do not promote docs prose into a rule unless it is represented as a concrete
observed/doc-derived instance and cited by a normalized case.
