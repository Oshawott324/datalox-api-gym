# Grounded Multi-Workflow Science Agent Plan

Date: 2026-07-25
Status: execution proposal

Concrete file-level work packets, commands, admission gates, and the first
ten-day sequence are in
[`science-workflow-portfolio-implementation.md`](science-workflow-portfolio-implementation.md).

## Decision

Build a portfolio of executable scientific workflows, not one oversized
laboratory demo and not a collection of unrelated API calls.

The initial benchmark target is four workflows:

1. microbial AMR sequencing;
2. RNA-seq experiment and rerun;
3. long-running microbial growth kinetics;
4. LC-MS metabolomics batch QC.

They cover distinct scientific work:

```text
sample preparation and identity
  + asynchronous computational analysis
  + elapsed biological time
  + instrument-result handling
  + cross-system provenance
  + recovery after changing or partial evidence
```

The public benchmark must not depend on receiving private access from
Benchling, TetraScience, or an instrument vendor. It should first use systems
we can run or probe faithfully:

- a locally deployed eLabFTW ELN;
- the official Opentrons development simulator and protocol simulator;
- Galaxy public captures plus the admitted local shadow world;
- a Seqera trial/community workspace if an authorized probe succeeds;
- current public UniProt, Ensembl, ChEMBL, PubChem, and RCSB PDB captures;
- pinned public scientific datasets and protocols.

Benchling, TetraScience, Agilent, HighRes, and similar providers are
provider-specific upgrade paths. Their documented shapes may support
development, but paper claims about their behavior require sandbox captures or
provider review.

No workflow includes ordering, procurement, billing, payment, refund, or other
commercial operations.

## What The Benchmark Is Testing

The central question is not whether an agent can call a pipette API or produce
a plausible report. It is:

> Can an agent complete a changing scientific workflow across several real
> software and instrument boundaries while preserving identity, provenance,
> freshness, resource constraints, and scientific validity?

The portfolio should support four research questions.

1. How reliably do frontier agents complete multi-system scientific workflows
   under partial failure, asynchronous execution, and stale evidence?
2. Which failures arise from scientific reasoning, tool discovery, provider
   semantics, or cross-system state reconciliation?
3. Do science-native scaffolds improve final-state validity over controlled
   general agent harnesses?
4. Can typed verifier primitives transfer across scientifically different
   workflows without weakening mutation coverage or increasing latency
   linearly?

## Release Gate

A workflow is admitted to the headline benchmark only when all consequential
boundaries meet these requirements.

| Boundary | Minimum evidence |
| --- | --- |
| Provider operation shape | Official example, OpenAPI, SDK contract, or stronger |
| Consequential transition | Authorized local/test execution, source-executed implementation, or partner capture |
| Scientific procedure | Published protocol, public workflow, or expert-reviewed SOP |
| Scientific observations | Pinned public dataset, executable analysis output, or partner capture |
| Fault behavior | Documented/observed behavior or an explicitly benchmark-defined deterministic schedule |
| Final decision | Deterministic state checks plus scientifically reviewed acceptance criteria |

Use the existing grounding vocabulary:

- `G0`: documentation only;
- `G1`: official example or deterministic schema instance;
- `G2`: authorized sandbox, test-mode, or seeded self-hosted probe;
- `G3`: public or production-like traffic capture;
- `G4`: provider-reviewed or provider-supplied evidence.

G0/G1 components may appear in a development world, but they cannot support
claims about real permissions, side effects, timing, recovery, or error
behavior. Every workflow publishes an operation-by-operation grounding matrix.

Fault probabilities must not be invented. Until frequency data exists, use
seeded deterministic fault schedules and claim only that the benchmark tests
the response to the fault, not that the frequency resembles production.

## Current Grounded Inventory

### Reusable now

`galaxy_usegalaxy_public_v0` in `datalox-gated-runtime`

- 62 provider-shaped operations across discovery, tools, histories, datasets,
  collections, jobs, workflows, and invocations;
- 24 deterministic run-private writes;
- G3 public GET captures and G2 stateful local execution;
- one exact admitted AMR Gene Detection workflow;
- asynchronous execution, failures, cancellation, collections, and
  provenance.

`probed_opentrons_local_v0` in `datalox-gated-runtime`

- 138 OpenAPI operations cataloged;
- 66 GETs executed against the official local `robot-server` simulator;
- 30 successful reads plus captured 4xx/5xx semantics;
- real response bodies for robot, protocol, run, module, instrument, motor,
  deck, and health surfaces.

The important gap is that 65 non-GET operations were cataloged but not
executed. Protocol upload, analysis creation, run creation, run actions, and
commands must be probed locally before a composite workflow treats those HTTP
transitions as G2.

Public scientific data providers in `datalox-gated-runtime`

- `uniprot_public_v0`;
- `ensembl_public_v0`;
- `chembl_public_v0`;
- `pubchem_public_v0`;
- the probed/captured RCSB PDB component.

These provide useful read-side evidence. They do not create a long-horizon
workflow by themselves.

Worlds and artifacts in API Gym

- `pylabrobot_lab_v0` and `pylabrobot_star_v0`;
- `synergy_h1_yeast_growth_v0`;
- `unitelabs_plate_qc_v0`;
- flow-cytometry, molecule-biology, and protein task artifacts under
  `handoff/env-data-proof-v0`.

The Synergy H1 world already has logical time and a 20-hour kinetic structure,
but its temperature ramp and absorbance values are calibration assumptions.
It is useful infrastructure, not yet grounded biological evidence.

### Development-only today

The current Benchling source pack is G0/G1 and mostly shape-derived. It has not
observed a Benchling tenant's read, write, asynchronous task, permission, or
failure behavior.

TetraScience has unusually concrete public documentation for file pointers,
IDS validation, command creation, command history, and instrument-facing
Command Service behavior. We still lack an authorized Tetra tenant or partner
capture, so these contracts remain G0/G1.

The current Adaptyv material is an API-shape and product-direction source, not
an observed Foundry lifecycle. It should not be forced into the initial
portfolio.

## New Provider Components To Acquire

### 1. eLabFTW local provider pack

Purpose: provide a real, resettable ELN and experiment-record boundary without
waiting for a commercial tenant.

Grounding path:

```text
official eLabFTW OpenAPI
  -> pinned Docker image and MySQL state
  -> seeded local instance
  -> G2 read/write/error captures
  -> construction-ready API Gym provider pack
```

Initial operation families:

- experiments and experiment revisions;
- resources/items;
- containers and storage units;
- uploads and artifact attachment;
- tags, links, metadata, and timestamps;
- soft deletion and restoration where supported;
- role and permission failures needed by the selected workflows.

Do not model the complete eLabFTW product. Declare and review the workflow
scope against the official OpenAPI.

### 2. Opentrons non-GET lifecycle

Purpose: turn the existing broad read probe into a faithful dry-run execution
boundary.

Probe only the official local simulator:

- protocol upload and delete;
- protocol analysis create/read;
- run create/read/delete;
- run action transitions;
- run command list/read;
- module and instrument state associated with simulated protocols;
- invalid labware, deck, parameter, state-transition, and missing-ID errors.

No real hardware connection or live motion belongs in the benchmark build.

### 3. Seqera workflow-execution pack

Purpose: provide a commercial, API-driven computational workflow provider
distinct from Galaxy.

Grounding path:

```text
official OpenAPI and documented launch JSON
  -> authorized community/trial workspace
  -> run one pinned nf-core test pipeline
  -> capture launch, progress, task, log, cancel, failure, and resume behavior
  -> G2 construction-ready pack
```

Initial operation families:

- pipelines and revisions;
- datasets or sample sheets;
- launch configuration;
- workflow launch and status;
- task progress and logs;
- cancellation;
- resume using the original work directory and revision;
- permission and invalid-parameter errors.

If an authorized Seqera probe is not available, the RNA-seq workflow remains a
development candidate and does not enter the headline benchmark.

### 4. Exact second Galaxy workflow

Purpose: reuse the admitted Galaxy provider core without pretending its current
AMR-specific workflow model supports arbitrary workflows.

Add one exact Workflow4Metabolomics or Galaxy Training Network workflow with:

- pinned workflow definition and tool versions;
- pinned input artifacts;
- local state transitions and output provenance;
- public instance availability check;
- admitted positive and negative trajectories.

## Workflow Portfolio

| World | Scientific mode | Required services | Current state | Headline gate |
| --- | --- | --- | --- | --- |
| `science_amr_campaign_v0` | NGS and AMR analysis | eLabFTW, Opentrons, Galaxy | Galaxy ready; other two need G2 writes | First |
| `science_rnaseq_campaign_v0` | expression analysis and rerun | eLabFTW, Opentrons, Seqera, Ensembl | Ensembl ready; Seqera/eLabFTW/Opentrons writes pending | Second |
| `science_growth_kinetics_v0` | elapsed biological time and adaptive QC | eLabFTW, Opentrons Flex reader simulation or one selected reader backend, public OD600 traces | logical-time world exists; biological trace and topology upgrade pending | Third |
| `science_metabolomics_qc_v0` | LC-MS batch QC and reprocessing | eLabFTW, exact Galaxy W4M workflow, PubChem/ChEMBL | public inputs and databases ready; exact Galaxy world pending | Fourth |

Every task must cross at least two independently stateful services. Public data
lookups count as supporting tools, not as the second stateful service.

### Workflow 1: AMR sequencing campaign

Scientific objective:

Process a bacterial isolate batch for research-use AMR analysis, preserve
sample identity through library-preparation dry run and analysis, recover
failed or incomplete work, and record current findings against the correct
samples.

Natural boundaries:

```text
eLabFTW experiment, samples, plate map, and protocol revision
  -> Opentrons protocol analysis and dry-run state
  -> sequencing-result arrival as pinned FASTQ/contig artifacts
  -> Galaxy AMR workflow and asynchronous jobs
  -> eLabFTW result artifact and repeat/accept research decision
```

The sequencing instrument is initially an artifact-arrival boundary, not a
fictional instrument API. A TetraScience or vendor connector may replace it
only after G2/G4 evidence.

Initial task families:

1. nominal multi-isolate batch;
2. plate or barcode identity mismatch;
3. invalid deck, labware, module, or protocol analysis;
4. missing, truncated, duplicated, or checksum-mismatched sequence artifact;
5. Galaxy failed job, partial collection, or cancelled invocation;
6. result from an earlier analysis used after rerun;
7. AMR result associated with the wrong isolate;
8. decision submitted before QC and current provenance are complete.

Scientific sources:

- the Galaxy Training Network AMR Gene Detection workflow;
- its pinned MRSA input artifacts;
- an Opentrons NGS application protocol selected and version-pinned before
  task generation.

This is a research workflow. It must not make clinical susceptibility or
treatment recommendations.

### Workflow 2: RNA-seq experiment and rerun

Scientific objective:

Prepare and analyze a small perturbation-study batch, validate sample-sheet and
reference compatibility, inspect pipeline QC, selectively recover failed
samples, and record a versioned analysis decision.

Natural boundaries:

```text
eLabFTW experiment design and sample manifest
  -> Opentrons NGS protocol analysis/dry run
  -> Seqera launch of pinned nf-core/rnaseq test workflow
  -> Ensembl reference and identifier checks
  -> eLabFTW analysis artifact, exclusions, and rerun record
```

Initial task families:

1. nominal paired-end batch;
2. sample-sheet identity or pairing mismatch;
3. wrong genome assembly or annotation release;
4. incompatible strandedness or pipeline parameter;
5. partial cohort caused by one failed sample;
6. cancel/resume using the wrong work directory or revision;
7. MultiQC or pipeline output from a superseded run;
8. final interpretation that silently ignores excluded or failed samples.

The benchmark verifies operational and evidence correctness. Open-ended
biological interpretation should be a separately calibrated rubric and must
not replace deterministic pipeline and provenance checks.

### Workflow 3: long-running growth kinetics

Scientific objective:

Prepare a controlled 96-well microbial growth experiment, establish the
required environment, collect OD600 measurements over many hours of logical
time, recover missed or failed measurements, and make a decision from the
complete current series.

Natural boundaries:

```text
eLabFTW plate map, strains, controls, and protocol revision
  -> one selected physical topology
  -> asynchronous kinetic measurement jobs over logical time
  -> pinned public OD600 trace observations
  -> eLabFTW QC decision and deviations
```

Select one topology:

1. Opentrons Flex with the documented Absorbance Plate Reader module; or
2. PyLabRobot with the Agilent BioTek Synergy H1 backend.

Do not combine them into a fictional workcell. The recommended public v0 is the
Opentrons Flex reader path if the official protocol simulator can execute the
complete module workflow. Keep the existing Synergy H1 world as a separate
backend until device or partner evidence exists.

Use pinned public OD600 traces instead of handwritten growth curves. Candidate
datasets must contain well or replicate identity, exact time, OD600, and
protocol conditions. The selected dataset and protocol are reviewed together;
data from one instrument must not be represented as observed output from
another instrument.

Initial task families:

1. nominal controlled growth series;
2. wrong plate or barcode at a measurement;
3. missing blank, control, or replicate;
4. temperature set but not stabilized before exposure;
5. insufficient incubation or shaking exposure;
6. reader busy or missed cadence window with valid reschedule;
7. partial read treated as a complete plate;
8. stale series after plate mutation or protocol revision;
9. overlapping exclusive reader jobs;
10. decision from an incomplete or non-current series.

This workflow is the main test of true horizon: early choices must affect
observations and recovery options many logical hours later.

### Workflow 4: LC-MS metabolomics batch QC

Scientific objective:

Receive a metabolomics batch, preserve sample and injection metadata, process
the batch through a pinned LC-MS QC workflow, correct justified analytical
effects, recover incomplete processing, and record a traceable QC decision.

Natural boundaries:

```text
eLabFTW sample manifest, batch, blanks, pools, and injection order
  -> pinned LC-MS table or mzML artifact arrival
  -> exact Galaxy Workflow4Metabolomics processing workflow
  -> PubChem/ChEMBL lookup for bounded annotation support
  -> eLabFTW QC outputs, exclusions, and reprocessing record
```

The initial workflow begins after instrument export. It does not claim to
control an LC-MS instrument. TetraScience Command Service or vendor behavior
may be added only after authorized captures.

Initial task families:

1. nominal two-batch QC;
2. missing blank or pooled QC samples;
3. incorrect injection order or batch mapping;
4. incomplete or duplicated raw/input artifacts;
5. inappropriate drift correction given available pools;
6. output generated from the wrong workflow/tool revision;
7. feature annotation attached to the wrong data version;
8. final QC decision made before all required metrics exist.

The Galaxy Training Network LC-MS material provides a concrete starting
dataset with biological samples, pooled QC samples, blanks, batches, injection
order, quality metrics, and drift correction. The exact released workflow must
be pinned and admitted rather than generalized from prose.

## Partner-Gated Extensions

### Protein engineering result loop

Potential services:

- eLabFTW or Benchling;
- UniProt, RCSB PDB, ChEMBL, and PubChem;
- Adaptyv or another foundry with an observed submission/result lifecycle.

Do not build the paid or physical foundry lifecycle from API prose. Promote
this workflow only after a provider or user supplies an authorized test trace
covering submission, status, partial result, failure, version, and result
lineage.

### Instrument-to-data-platform overlay

Potential services:

- TetraScience;
- Benchling Connect;
- Agilent, Thermo Fisher, Waters, HighRes, Biosero, or another instrument and
  orchestration provider.

The bounded request is not "send us your API." Ask for one redacted workflow:

```text
input manifest
  -> accepted command or file arrival
  -> status history
  -> raw artifact metadata and checksum
  -> processed artifact/version
  -> one success, one retryable failure, and one permanent failure
```

This overlay can replace benchmark-local artifact arrival in one released
workflow without changing its scientific contract.

## Shared Composition Contract

Do not normalize provider APIs into one universal science API. Preserve
provider-shaped requests and responses.

Each world defines only the joins it needs:

```text
sample mapping:
  native record id <-> barcode <-> plate/well

artifact lineage:
  file id + checksum + source sample version + created-at

execution lineage:
  protocol/workflow revision + input refs + run id + status

decision evidence:
  decision id + cited observations + current lineage versions
```

The agent must discover tools from a fixed benchmark registry. The task prompt
states the scientific objective, constraints, and available evidence, but does
not enumerate the correct tools or sequence.

## Verification Plan

Compose verification from provider capsules and workflow contracts:

```text
provider-shaped events and state
  -> workflow-specific fact adapters
  -> typed verification contract
  -> streaming predicates and final-state queries
  -> verdict, failure codes, and diagnostic vector
```

Shared primitive candidates:

- entity identity and mapping;
- artifact checksum and version;
- temporal precedence;
- freshness after mutation or rerun;
- provenance to current sample and workflow revision;
- asynchronous job lifecycle;
- partial-result completeness;
- resource exclusivity;
- controls and replicate coverage;
- bounded retry and recovery;
- interval exposure and cadence coverage;
- decision consistency;
- collateral-change exclusion.

Each workflow still owns scientific adapters and obligations. A generic
primitive is not allowed to erase scientific distinctions.

Every family must admit:

- an oracle trajectory;
- an empty trajectory rejection;
- a wrong-entity mutant;
- a stale/provenance mutant where applicable;
- a resource, timing, or fault mutant where applicable;
- a partial-result mutant;
- an idempotency or duplicate-action mutant where applicable;
- a scientifically valid near-miss;
- exact expected failure codes.

Measure primitive-type reuse, validated clause reuse, authoring effort, mutant
catch rate, near-miss specificity, and verifier latency. Do not report reuse
alone.

## Scaling To 1,000 Episodes

The task family, not an individual hard-coded episode, is the authoring unit.

Target:

```text
4 workflows
  x 6-10 reviewed families
  x 25-50 generated configurations
  = 600-2,000 admissible episodes
```

Generate variation from scientifically meaningful dimensions:

- sample count and plate layout;
- sample/barcode mapping;
- controls and replicates;
- protocol or workflow revision;
- reference database release;
- job timing and deterministic fault schedule;
- resource and queue state;
- artifact completeness and version;
- allowed recovery window;
- decision threshold defined by the pinned protocol.

LLMs may propose task language or candidate mutations, but they do not define
ground truth. The family contract generates state and obligations, and strict
admission determines whether an instance enters the benchmark.

Use the Ann Arbor researcher network for high-leverage review:

- review the four workflow contracts;
- review the family-level scientific obligations;
- inspect 5-10 stratified instances per workflow;
- adjudicate ambiguous near-miss cases.

Do not ask researchers to hand-author or individually review 1,000 tasks.

Dataset manifests and train/dev/test splits belong in
`datalox-rollout-collector`, not API Gym. Splits should hold out family
configurations, workflow revisions, and mutation combinations rather than
randomly splitting near-duplicate episodes.

## Agent Evaluation

### Controlled track

Run Claude Code, Codex, and one additional agent host with:

- identical world version and provider registry;
- identical task prompt and visible artifacts;
- identical CPU, memory, network, and logical-time policy;
- fixed maximum turns, tool calls, and cost;
- at least five repeats per task;
- no hidden state or verifier access;
- one final submission, with no verifier-guided repair.

For a 30-task pilot across four workflows:

```text
30 tasks x 3 systems x 5 repeats = 450 rollouts
```

For the first serious release:

```text
100-200 held-out tasks x 3 systems x 5 repeats
= 1,500-3,000 evaluation rollouts
```

### Native-scaffold track

Run Claude Science separately with its native skills, connectors, reviewer,
and session behavior. If Codex or another product is evaluated with a
different native scaffold, report it in the same system-study track.

Do not put native-scaffold scores on the controlled model leaderboard unless
the visible tools, runtime, and budgets are equivalent.

### Recorded outcomes

- terminal success;
- diagnostic verifier vector;
- tool discovery and selected providers;
- invalid or denied actions;
- stale/provenance failures;
- partial-result handling;
- recovery behavior;
- turns, tool calls, latency, and cost;
- infrastructure failure rate;
- result variance across repeats.

Do not collect or publish private chain-of-thought.

## Why Providers Should Care

The provider deliverable is not a generic benchmark score. Each provider gets a
private compatibility report across every workflow that uses its service:

- operations agents discover or fail to discover;
- fields, identifiers, and errors that cause repair loops;
- invalid or dangerous transitions attempted;
- stale and cross-system identity failures;
- timeout, partial-result, resume, and cancellation behavior;
- differences across Claude, Codex, and native science scaffolds;
- regression when the provider API or agent version changes.

This creates a concrete reason for participation:

- eLabFTW/Deltablot: evidence about agents operating an ELN and preserving
  experiment records across several scientific modalities;
- Opentrons: evidence about protocol analysis, module use, run state, and
  recovery across NGS and plate-reader workflows;
- Seqera: evidence about agent-driven launch, monitoring, failure diagnosis,
  cancellation, and resume of bioinformatics pipelines;
- Galaxy: reproducible agent behavior over histories, datasets, collections,
  workflows, and provenance;
- Benchling: an upgrade path from a public ELN baseline to a
  provider-certified integration report;
- TetraScience and instrument vendors: a bounded way to test whether agents
  preserve command and artifact lineage without exposing production systems.

Attribution is private by default. A provider approves any public use of its
name, captures, or provider-specific findings.

## Why Frontier Model Labs Should Care

The benchmark must expose a capability gap that static science benchmarks do
not:

```text
scientifically plausible final answer
  != correct execution
  != current evidence
  != correct sample
  != valid final workflow state
```

Multiple workflows are necessary to show that failures are not one protocol's
quirks. The release should report which failures transfer across AMR, RNA-seq,
growth kinetics, and metabolomics, and whether the same verifier primitives
capture them.

The strongest paper claim is:

> Frontier agents can perform substantial scientific work, but cross-system
> identity, freshness, provenance, asynchronous recovery, and elapsed-time
> reasoning remain distinct reliability bottlenecks that static
> response-based evaluations miss.

## Repository Boundaries

`datalox-gated-runtime`

- authorized live/local probes;
- capture, sanitization, replay, and promotion;
- generic gates and call-path adapters;
- generic session and audit/export plumbing.

`datalox-api-gym`

- canonical provider/API packs;
- workflow world specs;
- state and dynamics specific to each world;
- task-family contracts;
- domain fact adapters;
- verifier and reward atoms;
- executable world composition.

`datalox-rollout-collector`

- benchmark dataset manifests;
- public/private and train/dev/test splits;
- rollout packaging and quality reports;
- leaderboard input artifacts.

Do not add another generic session runtime or capture mechanism to API Gym.

## Execution Sequence

### Phase 0: lock evidence and topology, 3-5 days

1. Create the four workflow grounding matrices.
2. Select one exact protocol, workflow, and public dataset per world.
3. Choose one instrument topology per workflow.
4. Mark every consequential transition G0-G4.
5. Reject any workflow that depends on an undocumented transition.

Exit:

- four reviewed world contracts;
- no ambiguous provider claims;
- explicit missing-capture list.

### Phase 1: acquire the shared executable substrate, 1-2 weeks

1. Probe eLabFTW locally and build its construction-ready pack.
2. Execute the Opentrons non-GET protocol/analysis/run lifecycle locally.
3. Probe Seqera with one pinned nf-core test workflow.
4. Pin the second exact Galaxy workflow and input artifacts.

Exit:

- G2 eLabFTW;
- G2 Opentrons dry-run writes;
- G2 Seqera or a documented stop decision;
- admitted second Galaxy workflow.

### Phase 2: build two workflows first, 2 weeks

1. Build `science_amr_campaign_v0`.
2. Build `science_growth_kinetics_v0`.
3. Add six deep families and 30 admitted tasks per workflow.
4. Profile verifier latency and primitive reuse.

These two are deliberately different: one emphasizes cross-system
asynchronous provenance; the other emphasizes biological time and cadence.

Exit:

- 60 admitted tasks;
- all oracle/mutant/near-miss gates pass;
- no G0/G1 consequential transitions in headline paths.

### Phase 3: held-out workflow transfer, 2-3 weeks

1. Freeze the initial verifier primitive catalog.
2. Build `science_rnaseq_campaign_v0`.
3. Build `science_metabolomics_qc_v0`.
4. Record which primitives transfer and which are genuinely new.

Exit:

- four executable workflows;
- 120-task pilot;
- measured verifier reuse and latency, not estimated reuse.

### Phase 4: agent study and provider reports, 2 weeks

1. Run the controlled 450-rollout pilot.
2. Run the native-scaffold subset.
3. Audit infrastructure failures separately.
4. Have domain reviewers inspect stratified successes, failures, and
   near-misses.
5. Produce one cross-workflow report and one private report per provider.

Exit:

- at least two stable, non-obvious cross-workflow findings;
- reproducible agent comparisons;
- concrete partner asks based on observed gaps.

### Phase 5: scale and publish

1. Expand validated families to at least 1,000 admitted episodes.
2. Create contamination-resistant held-out sets in the rollout collector.
3. Publish the executable code, public task subset, benchmark card, provider
   grounding matrix, and technical report.
4. Keep provider-specific captures private unless approved.

## Stop Rules

Stop or downgrade a workflow when:

- a consequential provider transition remains G0/G1;
- the selected services do not form a workflow scientists recognize;
- verifier correctness depends on a hidden handwritten answer rather than
  state and evidence;
- valid alternative scientific plans are rejected;
- the public artifact license cannot support redistribution;
- the workflow adds no failure mode beyond an existing world;
- infrastructure failures cannot be distinguished from model failures;
- the provider-specific layer cannot be refreshed when its API changes.

Do not substitute more task count for a failed grounding gate.

## Primary Sources

- OpenAI LifeSciBench:
  https://openai.com/index/introducing-life-sci-bench/
- Anthropic agent-evaluation guidance:
  https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
- Anthropic agents in biology:
  https://www.anthropic.com/research/agents-in-biology
- Opentrons HTTP API:
  https://docs.opentrons.com/http/api_reference.html
- Opentrons Flex NGS workstation:
  https://insights.opentrons.com/hubfs/Products/Workstations/Flex%20Workstations/Flex%20NGS%20Workstation%20Brochure%20-%20Rev%202024_V3.pdf
- Opentrons Flex Absorbance Plate Reader:
  https://docs.opentrons.com/python-api/modules/absorbance-plate-reader/
- Galaxy AMR workflow:
  https://training.galaxyproject.org/training-material/topics/genome-annotation/tutorials/amr-gene-detection/workflows/main-workflow.html
- Galaxy LC-MS data processing:
  https://training.galaxyproject.org/topics/metabolomics/tutorials/lcms-dataprocessing/tutorial.html
- Workflow4Metabolomics:
  https://workflow4metabolomics.org/
- Seqera automation API:
  https://docs.seqera.io/platform-enterprise/getting-started/quickstart-demo/automation
- Seqera workflow launch:
  https://docs.seqera.io/platform-api/create-workflow-launch
- eLabFTW API:
  https://doc.elabftw.net/api/v2/
- eLabFTW local deployment:
  https://doc.elabftw.net/docs/install/prerequisites/
- Benchling Connect API workflow:
  https://docs.benchling.com/docs/use-apis-to-process-outputfile-with-lab-automation
- TetraScience Command Service:
  https://developers.tetrascience.com/docs/command-service
- TetraScience Context API:
  https://developers.tetrascience.com/docs/context-api
- PyLabRobot Synergy H1:
  https://docs.pylabrobot.org/stable/user_guide/02_analytical/plate-reading/synergyh1.html
- Agilent BioTek Synergy H1 technical details:
  https://www.agilent.com/cs/library/specifications/public/Synergy-H1-technical-details-5994-3583EN-agilent.pdf
- Public OD600 example with time, replicate, and measurement cadence:
  https://datadryad.org/dataset/doi:10.5061/dryad.stqjq2chf
