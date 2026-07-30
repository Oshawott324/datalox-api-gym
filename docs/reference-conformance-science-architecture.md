# Reference-Conformant Science Worlds

Date: 2026-07-26
Status: architecture boundary with execution status through `c748840`
Audience: API Gym engineering, training-team reviewers, and scientific reviewers

## Execution Status At 2026-07-30

The authoritative completion record is the
[2026-07-30 science grounding execution report](reports/2026-07-30-science-grounding-execution-report.md).
This status supersedes earlier planning or inventory statements where they
conflict; the architecture principles below remain unchanged.

- eLabFTW 5.6.10 behavior capture and Cromwell 92 success, failure, and abort
  captures are complete for their exact admitted programs.
- `science_elabftw_cromwell_v0` is the admitted first six-family
  eLabFTW-Cromwell world: twelve episodes, exact-code negatives, and
  runtime-hidden response digest evidence. Codex passed 4/6 and Claude Sonnet
  passed 5/6 at the frozen `20dd88a` API Gym and `9fc984a` runtime commits.
  These are integration baselines, not a statistically meaningful
  leaderboard.
- The Galaxy public pack records 19 provider-observed GET operations, 43
  contract-shaped candidates, and no provider-observed writes. The later
  pinned local run completed history creation, FASTA upload,
  `queued -> running -> ok`, dataset/provenance reads, exact 44-byte readback,
  and purge; the bounded projection conformance report passed.
- Galaxy AMR composition is blocked. All five exact StarAMR workflow tool
  versions returned HTTP 404, so workflow import and invocation were not
  attempted, no StarAMR or AMR analysis ran, and no Galaxy science world was
  composed.
- No private provider was promoted because no actual private tenant, sandbox,
  credential, or partner capture exists.

## Goal

Build long-horizon science environments in which agents operate across several
real service contracts, while making a precise distinction between:

1. behavior executed against a disposable reference service;
2. behavior reproduced by a fast resettable projection;
3. benchmark-authored cross-service workflow rules.

The first target is an AMR analysis and evidence-handoff workflow:

```text
eLabFTW experiment and isolate records
  -> versioned sequence artifacts in MinIO
  -> pinned Galaxy AMR workflow
  -> Galaxy output and provenance
  -> result attached to the matching eLabFTW experiment
```

This is deliberately named `science_amr_analysis_reference_v0`. It does not
claim to execute sample preparation, sequencing, or a complete wet-lab
campaign.

## First-Principles Rule

A provider operation enters the benchmark only through one of these evidence
lanes:

| Lane | Evidence | Permitted claim |
| --- | --- | --- |
| Reference-executed | Disposable local service, official simulator, or authorized sandbox | The tested sequence and selected observations matched the named provider version |
| Captured-replay | Sanitized request/response and state observations supplied by an authorized source | The projection replays the captured cases |
| Contract-shaped | Official schema or documentation without executable behavior | Request/response shape only |
| Benchmark-defined | No provider behavior claim | Cross-service task rules authored by the benchmark |

If a consequential operation has none of the first three forms of evidence, it
is excluded. It is not filled in from intuition.

## Three Ownership Levels

### 1. Generic runtime infrastructure

Repository: `datalox-gated-runtime`

```text
src/datalox_gated_runtime/reference/
  contracts.py
  comparison.py
  runner.py
  serialization.py
```

This layer owns only provider-neutral mechanics:

- a sanitized, durable reference-sequence contract;
- ordered execution against a `SequenceTarget`;
- explicit observations before and after calls;
- exact, type-sensitive JSON comparison;
- provider-supplied normalization hooks;
- deterministic mismatch codes and JSON-pointer locations;
- a machine-readable conformance report.

It does not know what an experiment, sample, Galaxy history, or scientific
result means. It does not call an LLM. It does not define reward.

The reference runner is offline infrastructure. It must not weaken the normal
runtime's GET-only live-capture boundary or make agent-facing world handlers
write to external services.

Generic service-fixture lifecycle code should be extracted only after two
providers demonstrate the same start, health, reset, and teardown contract.
Until then, provider-specific fixture control remains beside each provider.
This avoids turning eLabFTW deployment assumptions into a false universal
framework.

### 2. Reusable provider components

Repository: `datalox-api-gym`

```text
api_gym/provider_components/
  elabftw/
    reference_target.py
    observations.py
    normalization.py
    projection.py
    transition_atoms.py
  galaxy/
  minio/

scripts/providers/
  elabftw/
  galaxy/
  minio/

source_packs/apis/
  elabftw/<capture-version>/
  galaxy/<capture-version>/
  minio/<capture-version>/
```

Each provider component owns:

- provider-native operation and response shapes;
- disposable fixture setup specific to that service;
- safe seeding and observation queries;
- explicit normalization of generated IDs and timestamps;
- sanitized connected-sequence evidence;
- bounded projected transitions;
- reusable provider-level verifier facts;
- known gaps and forbidden claims.

Provider components are not generic CRUD engines. An eLabFTW experiment
revision remains eLabFTW-specific behavior.

### 3. Workflow-specific world

Repository: `datalox-api-gym`

```text
worlds/science_amr_analysis_v0/
  README.md
  task.json
  source_refs.json
  grounding_matrix.json
  family_contracts/
  tests/trajectories/
  world/
    manifest.json
    v1/
      implementation.py
      joins.py
      facts.py
      verifier.py
      episodes.jsonl
      roles.json
      tools.json
      verifier.json
      sources.json
```

The world owns only:

- the AMR task statement;
- joins among isolate IDs, barcodes, artifact versions, checksums, Galaxy
  histories, and eLabFTW experiments;
- asynchronous artifact and workflow state;
- scientific obligations for the selected AMR workflow;
- task-family parameters and mutants;
- final cross-service verification.

The provider implementation included in a self-contained world bundle must be
generated from the canonical provider component and hash-checked. Do not keep
two handwritten copies.

## Reference Before Projection

The implementation order is:

```text
real disposable service
  -> connected reference sequence
  -> sanitized durable trace
  -> bounded provider projection
  -> differential conformance report
  -> composed resettable world
  -> agent rollouts
```

The service performs its own business logic during the reference run. The
projection is built only for the operations and state observations exercised
by admitted reference sequences. This prevents a mock from silently becoming
the source of truth.

Conformance is separate from world admission:

- conformance asks whether a provider projection matches its reference;
- admission asks whether a resettable world and its verifier accept the oracle
  and reject required negative trajectories.

## First Vertical Slice

Seed:

- two eLabFTW isolate records;
- a current and a stale sequence artifact in MinIO;
- a manifest linking isolate IDs, barcodes, artifact versions, and checksums;
- one pinned Galaxy AMR workflow and immutable input fixtures.

Agent task:

1. inspect the experiment and isolate records;
2. select the current artifact for the requested isolate;
3. validate identity and checksum;
4. create a Galaxy history and invoke the pinned workflow;
5. wait for a terminal workflow state;
6. inspect output provenance and completeness;
7. attach the correct result to the matching eLabFTW experiment;
8. finalize the experiment only after the required evidence is present.

Initial required negatives:

- wrong isolate or barcode;
- stale artifact version;
- checksum mismatch;
- wrong eLabFTW experiment attachment;
- finalization before Galaxy reaches a terminal state;
- partial Galaxy output treated as complete;
- duplicate invocation after a successful result already exists.

## Acceptance Gates

### Generic runtime gate

- trace and report schemas round-trip without loss;
- secrets and sensitive headers are rejected;
- comparison is exact and type-sensitive;
- generated fields vary only through explicit provider normalization;
- target execution failures are represented with stable codes;
- existing runtime and live-capture safety tests remain green.

### Provider gate

- the service is pinned by version and immutable image digest;
- it binds only to loopback and carries a disposable deployment marker;
- start, health, seed, capture, reset, and destroy are reproducible;
- at least one connected create-update-read sequence executes twice;
- request, response, pre-state, and post-state observations are sanitized;
- the bounded projection passes the same sequence;
- known gaps state what was not tested.

### World gate

- at least two independent stateful services participate;
- reset reproduces the initial semantic fingerprint;
- the oracle passes;
- empty and required negative trajectories fail with exact expected codes;
- at least one valid alternative recovery passes;
- verifier output is a boolean plus deterministic obligation outcomes,
  diagnostics, and evidence references;
- no scalar reward, weights, or credit assignment are embedded;
- verifier and finalization latency are profiled;
- hidden state and verifier contracts are not agent-visible.

## Review Boundary

Zheng should judge the artifact from the training-system perspective:

- Is the observation and outcome evidence sufficient to construct rewards
  outside the environment?
- Are failure codes and obligation outcomes useful for filtering, diagnosis,
  and credit assignment?
- Is reset throughput adequate for rollout scale?
- Which evidence fields would be expensive or unusable in a training pipeline?
- Does the reference/projection split create unacceptable reward drift?

A scientific reviewer should judge a different surface:

- Does the task correspond to a real analysis and evidence-handoff workflow?
- Are identity, freshness, completeness, and provenance obligations correct?
- Are the negative trajectories plausible failures?
- Which scientific decisions require expert thresholds rather than generic
  workflow invariants?

Neither reviewer should be asked to decide internal repository boundaries.

## Current Work Order

Completed:

1. Implemented the generic offline reference-conformance core used by the
   pinned runtime.
2. Executed and captured the scoped eLabFTW behavior and Cromwell success,
   failure, and abort programs against pinned disposable services.
3. Built and admitted the bounded six-family eLabFTW-Cromwell world.
4. Captured the public Galaxy GET surface and a pinned local
   history/upload/readback/purge lifecycle.
5. Made the bounded Galaxy projection pass conformance for the selected
   captured trace.

Blocked and next:

1. Install and immutably pin all five exact StarAMR workflow tool versions in
   a disposable Galaxy fixture; require all five tool lookups to pass before
   workflow import.
2. Import and invoke the exact pinned AMR workflow, capture terminal outputs,
   completeness, provenance, native failures, teardown, repeatability, and
   reset. Do not compose a world before this provider-executed gate passes.
3. Execute and conform the pinned MinIO current/stale artifact lifecycle if the
   original three-service AMR slice remains the target.
4. Compose and admit the AMR world only after the Galaxy tool-stack and
   reference-workflow gates pass, then obtain training-system and scientific
   review.
5. Keep private providers outside promoted worlds until actual authorized
   access produces sanitizable execution evidence.

Opentrons is not part of this first slice. Its public read surface is grounded,
but its non-GET protocol, analysis, run, and command lifecycle has not yet been
executed against the official local environment. It can enter a later world
after that independent grounding gate passes.
