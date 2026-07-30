# eLabFTW Complete Behavior Case

Date: 2026-07-30  
Status: captured, compiled, and projection-conformant  
Provider boundary: disposable loopback eLabFTW 5.6.10; production equivalence
is not claimed

## Purpose

This is the first complete provider behavior program captured by the generic
runtime harvester. It supersedes the older selected three-call sequence as the
admitted eLabFTW behavior case without deleting or rewriting that historical
evidence.

The retained program is:

```text
authenticated GET /api/v2/info identity preflight
POST /api/v2/experiments
GET /api/v2/experiments
GET /api/v2/experiments/{id}
PATCH /api/v2/experiments/{id}
repeat the exact PATCH
PATCH an unknown update target
GET /api/v2/experiments/{id}
```

All eight provider calls were dispatched by
`BehaviorHarvester` V2. Provider-specific setup was limited to provisioning,
bootstrapping, inspecting, and destroying the disposable Docker fixture.

## Exact Observations

| Step | Role | Status | Response bytes | Observation |
| --- | --- | ---: | ---: | --- |
| create | supporting | 201 | 0 | exact zero-length body, `text/html`, `Location` present |
| collection read | supporting | 200 | 893 | integer experiment ID bound from `/0/id` |
| item read | before | 200 | 1,831 | title was `Untitled` |
| PATCH | success | 200 | 3,196 | title, body, and metadata persisted |
| exact repeat PATCH | duplicate | 200 | 3,665 | two additional changelog entries appeared |
| unknown update target | native failure | 400 | 64 | `Invalid update target.` |
| final item read | resulting state | 200 | 3,665 | title changed from before and equaled success |

The duplicate role is intentionally `expected_outcome=observe`. The 200 does
not establish idempotency because the second request changed the changelog.

## Artifact Identity

```text
engine:
  behavior_harvest_http11
  version 2
  sha256:efbdea5510aead688bf128d3c2091db4650998d3e96a57bec2415018bcf81844

capture:
  sha256:f83ba0c58a078c332064e16f629084b8dcd7e341ef3d2861e2ff974790e6eca6

connector:
  sha256:99e021f67e8cf642d8085268291dff1e76528ab56ed21c75345c5e95995eb4ee

recipe:
  sha256:cfb40b56272ec5f86aebd95e7ef9988fd06436f5b7dbd8264c1ace4f645fd3d7

fixture inspection:
  sha256:2e4efce0c9ff395b1c57ef863bf6300902bc0ac1d91b2161cad98933009f4759
```

The fixture receipt is generated from Docker inspection of the running web and
database images. It records stable image content identity, the disposable
marker, and the reviewed `http://127.0.0.1:3148` origin. It excludes container
IDs, project names, credentials, and mutable runtime state.

## Exactness And Normalization

Complete safe JSON response bodies are retained in `capture.json`; they are not
reduced to selected fields.

The only compile-time normalization is the generated experiment ID, and it is
pointer-specific. The integer is declared at:

```text
list_experiments /0/id
before_experiment /id
patch_experiment /id
duplicate_patch /id
resulting_experiment /id
```

Equal integers at unrelated locations, including `team: 1` and `state: 1`,
remain literal. Generated timestamps, `elabid`, changelog entries, and other
safe fields remain exact observed values. The provider target is
capture-backed exact program replay/normalization, not an independent
implementation of arbitrary eLabFTW business logic and not a claim that these
fields can be generated for arbitrary workflows.

## Authentication And Cleanup

The API key is generated per fixture and supplied only as secret bytes to the
runtime's `opaque_authorization_header` strategy. It is absent from the
connector, recipe, capture, partial journal, metadata, documentation, and
command line. The live test also checks absence of raw, Base64, and SHA-256
forms.

The fixture accepts only the fixed loopback origin. Every capture owns a unique
Compose project, verifies the disposable marker and pinned images, and runs
`down --volumes` in `finally`.

`reset_equivalence_claimed` is `false`. Fresh provisioning and teardown were
executed, but this case does not retain a two-run functional reset-equivalence
study.

## Files

```text
source_packs/apis/elabftw/2026-07-30/behavior_cases/
  experiments_patch_complete_v1/
    connector.json
    recipe.json
    fixture_receipt.json
    capture.json
    case_metadata.json
    README.md
```

Provider-specific construction and projection code lives in
`api_gym/provider_components/elabftw/complete_behavior.py`. Fixture lifecycle
and capture entry points live under `scripts/providers/elabftw/`.

## Unclaimed Behavior

This case does not claim production equivalence, arbitrary experiment CRUD,
pagination, attachments, permissions, teams, templates, concurrent edits,
rate limits, latency, or physical/scientific correctness. It proves one exact
local provider program and a fail-closed projection boundary.

## Verification

```bash
PYTHONPATH=/path/to/datalox-gated-runtime/src:. \
python -m pytest -q tests/test_elabftw_complete_behavior.py

ELABFTW_COMPLETE_BEHAVIOR_LIVE=1 \
PYTHONPATH=/path/to/datalox-gated-runtime/src:. \
python -m pytest -q tests/integration/test_elabftw_complete_behavior_live.py
```
