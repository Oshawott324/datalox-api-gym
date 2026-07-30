# eLabFTW Reference-Conformance Review

Date: 2026-07-26
Status: historical selected three-call slice
Reviewers: training-system reviewer and scientific-workflow reviewer
Architecture:
`docs/reference-conformance-science-architecture.md`

> This document describes the earlier selected `POST -> PATCH -> GET` evidence
> slice. It is preserved for provenance and existing projection tests, but it
> is not the complete eLabFTW behavior case. The complete, generic-harvester
> artifact is reviewed in `docs/elabftw-complete-behavior-case.md`.

## What Exists

This historical provider slice has four separate artifacts:

```text
disposable eLabFTW 5.6.10 service
  -> sanitized connected reference capture
  -> bounded eLabFTW experiment projection
  -> generic differential conformance report
```

The executed reference sequence is exactly:

```text
POST /api/v2/experiments with {}
  -> PATCH the created experiment with title, body, and metadata
  -> GET the same experiment
```

Observed results:

- create returned `201`;
- patch returned `200`;
- get returned `200`;
- accessible experiment count changed from zero to one;
- title, body, and structured isolate metadata persisted;
- the stack was destroyed with its owned volumes after each run.

The real execution found one material contract detail: eLabFTW 5.6.10 accepted
the PATCH metadata on this surface as a JSON string. The bounded projection
uses that observed wire format and rejects an object-valued metadata field.

## Evidence Identity

Reference service:

```text
eLabFTW version:
  5.6.10

web image:
  elabftw/elabimg:5.6.10
  sha256:a4dd2264b6fa40bb250ca68d3845afa442bb15c29aed95cd444786084eb30e67

raw capture:
  sha256:ab08452c77328dc894fb2b081efa42eb7632f1ec6f66d539628d8ede41509cc6
```

Conformance:

```text
trace schema:
  datalox_reference_trace_v1

trace digest:
  sha256:7bf5abfbc60f69e81d8e11f280cb04eefc4350b3fbd061c5eabb82e2797814e5

target:
  elabftw_experiments_projection_v0
  elabftw_experiments_create_patch_get_v0

normalization profile:
  elabftw_experiment_id_location_v0

result:
  passed=true
  mismatches=[]
```

Generated experiment IDs and the create `Location` header are the only
normalized fields. Tests prove that an inconsistent ID in a later PATCH, GET,
or final observation still fails conformance.

## Code Boundary

Generic runtime code:

```text
datalox-gated-runtime/
  src/datalox_gated_runtime/reference/
```

This owns trace contracts, exact JSON comparison, target/profile protocols,
stable mismatches, trace hashing, and reports. It has no eLabFTW or science
knowledge.

Reusable eLabFTW-specific code:

```text
datalox-api-gym/
  api_gym/provider_components/elabftw/
  scripts/providers/elabftw/
  source_packs/apis/elabftw/2026-07-26/
```

This owns the fixture, real capture, provider observations, explicit ID
normalization, and bounded projection.

World-specific AMR code does not exist yet. Isolate-to-artifact-to-Galaxy joins,
scientific obligations, task families, and mutants belong in the future
`science_amr_analysis_v0` world.

## What This Proves

- A consequential provider write sequence can be executed against a disposable
  real service without adding live writes to the agent runtime.
- The retained evidence records connected request, response, and state changes,
  rather than unrelated endpoint examples.
- A resettable projection can be checked against that evidence with exact,
  type-sensitive comparison.
- A passing report is bound to the exact raw capture, converted trace, target
  version, and normalization profile.
- Provider evidence refresh and projected rollout execution can remain
  separate processes.

## What This Does Not Prove

The current provider component does not support or claim:

- attachments or file uploads;
- tags, links, permissions, teams, templates, deletion, search, or pagination;
- multiple experiments or repeated operations in one reset;
- authentication fidelity;
- concurrent updates, latency, rate limits, or injected faults;
- an HTTP/MCP agent-facing server;
- production eLabFTW behavior beyond the executed local version;
- a complete research or wet-lab workflow.

The checked-in directory is not yet a complete canonical source pack. It
contains raw connected evidence and a conformance report. Operation catalogs,
response cases, known gaps, and source-pack validation should be added only
after selecting the next reference sequences.

## Measured Cost

On the current machine:

```text
clean real-service provision + bootstrap + create/patch/get + teardown:
  approximately 23 seconds

1,000 fresh projection conformance runs over the three-call trace:
  0.289 seconds total
  3,460 runs/second
  0.289 ms/run
```

The second number measures only provider projection conformance. It is not
full-world agent rollout throughput and not final verifier latency.

## Reproduce

Real reference sequence:

```bash
ELABFTW_REFERENCE_TEST=1 \
PYTHONPATH=/path/to/datalox-gated-runtime/src:/path/to/datalox-api-gym \
python -m pytest -q tests/integration/test_elabftw_reference_fixture.py
```

Projection and differential conformance:

```bash
PYTHONPATH=/path/to/datalox-gated-runtime/src:/path/to/datalox-api-gym \
python -m pytest -q \
  tests/test_elabftw_projection.py \
  tests/integration/test_elabftw_projection_conformance.py

PYTHONPATH=/path/to/datalox-gated-runtime/src:/path/to/datalox-api-gym \
python scripts/providers/elabftw/check_projection_conformance.py
```

## Questions For Zheng

Please judge this artifact as input to a training pipeline, not as a complete
benchmark:

1. Is the trace plus per-path mismatch format sufficient for downstream reward
   construction without embedding reward weights in the environment?
2. Are target, profile, capture, and trace identities sufficient to prevent
   silent reward drift when provider evidence is refreshed?
3. Should conformance reports remain an admission-time artifact, or should a
   sampled subset run during rollout collection?
4. Which additional outcome fields are needed for filtering, diagnosis, or
   credit assignment?
5. Is it acceptable for expensive reference services to run during evidence
   refresh and CI while training rollouts use only admitted projections?

## Questions For A Scientific Reviewer

The current sequence is infrastructure grounding, not yet a scientifically deep
task. Review should begin after the MinIO and Galaxy reference sequences are
connected into one AMR analysis workflow:

1. Are isolate identity, artifact freshness, checksum, output completeness, and
   provenance the correct workflow obligations?
2. Are wrong-isolate, stale-artifact, wrong-attachment, partial-output, and
   early-finalization failures realistic?
3. Which AMR result-interpretation decisions require domain thresholds or
   additional controls?
4. What minimum evidence should be attached to an eLabFTW experiment before an
   analysis result is considered complete?

## Next Engineering Gate

Do not expand eLabFTW breadth immediately. Add the next two reference
components needed by the first real workflow:

1. MinIO object version, checksum, and stale-artifact selection;
2. one exact local Galaxy AMR invocation through terminal output and
   provenance.

Then execute the complete eLabFTW -> MinIO -> Galaxy -> eLabFTW reference
workflow twice. Build the agent-facing resettable world only after that
semantic fingerprint is stable and the two reviewer groups accept the evidence
surface.
