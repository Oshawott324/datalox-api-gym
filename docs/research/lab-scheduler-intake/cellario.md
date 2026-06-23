# Cellario Intake

## Public Claims

HighRes positions Cellario OS as lab orchestration software for coordinating instruments, workflows, data, software applications, manual tasks, and automation systems across a lab. The public [HighRes Lab Orchestration page](https://www.highres.com/lab-orchestration) says Cellario OS lets labs create, plan, execute, and analyze scientific work digitally and physically, with centralized visibility into workflows, orders, instruments, and system status. The same page says Cellario OS exposes flexible APIs for integration with LIMS, ELNs, analytics platforms, and AI tools, and describes Cellario Scheduler as the engine for developing, simulating, and executing protocols on automation systems.

The Q1 2026 HighRes update is the clearest public scheduler/API signal found. In [Innovation Update Q1 2026](https://www.highres.com/highres-blog/innovation-update-q1-2026), HighRes says Cellario Scheduler introduced RESTful API endpoints for programmatic protocol creation, modification, and optimization through automated agents and intelligent systems. The same section says the APIs are type-safe and cover complex multi-threaded workflows, polymorphic step types, parameters, resources, and timing constraints. Later in the same Q1 2026 update, HighRes says Cellario OS added a new API endpoint for the Lab Overview that returns a hierarchical lab representation from campus down to individual resources, with status and aggregate counts, through a single GET request.

HighRes also describes Cellario OS as an API-first integration layer. In [Cellario OS as an Integration Layer](https://www.highres.com/highres-blog/cellario-os-as-an-integration-layer), HighRes says Cellario OS can run headless, that UI capabilities can be accessed programmatically through the API, and that digital applications can communicate with one unified interface while Cellario OS handles device communication, scheduling, workflow orchestration, and data capture. That post also says Cellario OS provides comprehensive Swagger-documented APIs and shows a public page reference to the [Developer Site](https://developer.highresbio.com/), but the developer site content was not publicly readable without authentication in this research pass.

Integration claims are also public. [Cloud-based Management with Lab Automation](https://www.highres.com/highres-blog/cloud-based-management-with-lab-automation) says Cellario has coupled API layers, a RESTful API usable for integration with other software platforms, and publisher/subscriber event APIs used by TetraScience to receive data events. [How HighRes + Benchling Automate the Lab-to-Insight Pipeline](https://www.highres.com/highres-blog/how-highres-benchling-automate-the-lab-to-insight-pipeline) says Benchling hands structured experiment parameters to Cellario OS via API, including sample information, plate barcodes, and layout, after which Cellario schedules and runs the assay and returns results.

## API Evidence Found

Public evidence found is L0/L1 plus a strong pointer to private L2 material:

- L0/L1: public product and blog pages claim Cellario OS and Cellario Scheduler APIs exist, including RESTful endpoints, type-safe protocol designer APIs, event APIs, and a Lab Overview GET endpoint.
- L1: public pages identify likely operation families: protocol create/modify/optimize, lab hierarchy/resource status read, device operation discovery, operation start/status/events, device error clearing, output-file download, driver reset, run scheduling/execution, data event publication, and result return.
- L1: public integration pages identify likely domain objects: protocols, orders, requests, labware/microplates, plate barcodes, plate layouts, resources, devices, operations, events, output files, runs, and result data.
- L2 pointer, not acquired: HighRes says Cellario OS has Swagger-documented APIs on the [Cellario OS as an Integration Layer](https://www.highres.com/highres-blog/cellario-os-as-an-integration-layer) page, and the public footer links to [developer.highresbio.com](https://developer.highresbio.com/). A docs fetch of the developer homepage returned an Archbee-hosted page whose metadata marked the docs space private with JWT protection, so no public Swagger/OpenAPI paths, schemas, examples, or response bodies were available.

No public OpenAPI/Swagger document, endpoint path catalog, SDK schema, protobuf/gRPC/FDL file, typed request example, typed response example, error schema, sandbox transcript, or recorded capture was found during this pass. Do not create a Cellario source pack from the public pages alone.

## Missing Shape

The public material does not provide enough shape for `source_packs/apis/highres_cellario/<version>` because it omits:

- exact base URLs, authentication model, scopes, tenant/workcell identifiers, and versioning policy
- operation IDs and endpoint paths for protocol creation, modification, optimization, validation, simulation, order creation, run creation, run status, event log retrieval, artifact/result retrieval, lab overview, device operation discovery, device operation start/status/events, device error clearing, output-file download, and driver reset
- request bodies for protocol design, including how Cellario represents multi-threaded workflows, polymorphic step types, resources, timing constraints, parameters, plate barcodes, plate layouts, samples, and workcell targets
- response bodies for successful protocol creation/modification/optimization, validation/simulation output, lab hierarchy/resource status, run status, run event logs, output-file metadata, result/artifact records, and result return to upstream ELN/LIMS systems
- stable error codes for invalid protocols, unsafe live execution, missing resources, unavailable devices, conflicting schedules, stale revisions, insufficient permissions, missing artifacts, failed device operations, and recoverable/nonrecoverable device faults
- dry-run, simulation, sandbox, or test-mode boundaries that prove requests can be validated without creating real scheduler or hardware runs
- event-stream shape for publisher/subscriber APIs and the relationship between Cellario event IDs, runs/orders, resources, files, and scientific results
- any recorded body examples that could become grounded response cases for an API Gym gate

## Safe Probe Possibilities

Do not call live Cellario endpoints and do not create scheduler, device, protocol, order, run, or hardware activity without a separate explicit live-gate policy and user approval.

Safe next probes, if HighRes or a customer provides access and the user approves:

- Fetch official OpenAPI/Swagger JSON/YAML, protobuf, SDK schema, or plugin docs from the authenticated HighRes developer site.
- Inspect SDK packages or generated clients locally if HighRes provides them as files, without connecting to a tenant.
- Use a sandbox/test-mode tenant only for read/list operations such as capability discovery, API version, lab hierarchy/resource status, protocol template read, and schema discovery.
- Use a sandbox/test-mode validation or simulation endpoint only if HighRes confirms it does not enqueue a real order, start a scheduler run, reserve resources, or touch hardware.
- Capture approved recorded request/response pairs from HighRes/customer demos where secrets, tenant IDs, sample IDs, and proprietary protocol details have been redacted.

Candidate safe operations to prioritize after documentation or sandbox access:

1. API/version/capability discovery
2. Lab hierarchy/resource status read
3. Protocol/template read
4. Protocol create or modify in validation-only mode
5. Protocol validate/simulate/optimize without live execution
6. Run/order status read from a sandbox fixture
7. Run/order event log read from a sandbox fixture
8. Artifact/result metadata read from a sandbox fixture
9. Permission, validation, conflict, missing-resource, unavailable-device, and unsafe-live-execution error cases

## Outreach Ask

Ask HighRes for the minimum evidence needed to build a source-backed dry-run Cellario API Gym source pack without live execution:

- OpenAPI/Swagger JSON/YAML for Cellario OS and Cellario Scheduler APIs, including the Q1 2026 protocol designer APIs and the Lab Overview GET endpoint
- SDK, generated client, protobuf/gRPC/FDL, plugin docs, or typed examples if the public API is not fully represented by OpenAPI
- one protocol create request example that includes realistic step/resource/timing/labware shape, with all proprietary identifiers redacted
- one protocol validation or simulation response that proves no real scheduler/hardware run is created
- one run/order status response and one run/order event log response from a sandbox or recorded demo
- one artifact/result response showing how Cellario returns output files, metadata, or result context to upstream systems
- stable error response examples for invalid protocol, missing resource/device unavailable, conflict/stale revision, permission/scope failure, artifact not found, and unsafe live execution
- sandbox/test-mode access limited to read/list/validate/simulate operations, or approved recorded captures if sandbox access is not possible

Concrete artifact ask: provide OpenAPI/Swagger/protobuf/SDK/plugin docs, a protocol create request example, a validation/simulation response, a run event log, an artifact/result response, sandbox/test-mode access, or recorded captures.

## Datalox Boundary

Cellario is a good candidate domain for API Gym because lab scheduling and orchestration are costly, stateful, and risky to exercise against real systems. The current public evidence is not enough to create original-shaped operations or response cases.

For API Gym:

- Treat the public HighRes pages as intake evidence only.
- Do not build a live API aggregator or Cellario connector.
- Do not invent Cellario endpoint paths, request bodies, response bodies, auth scopes, or error codes.
- Do not model live scheduler/hardware execution from marketing claims.
- Do not create `source_packs/apis/highres_cellario/<version>` until L2+ evidence is available.
- Once L2+ evidence is obtained, build source substrate first: docs index, operation catalog, schemas, examples, response cases, observed errors, probes/captures, and world-candidate notes.
- Only promote to a world after selected source-pack records cover read/list context, protocol creation or validation/simulation, run/event/artifact inspection, failure cases, dry-run/live boundaries, and verifier-relevant evidence.

## Decision

`needs_docs_or_probe`

Rationale: public Cellario pages show strong L0/L1 evidence that RESTful, type-safe, Swagger-documented APIs exist for protocol design, lab overview/resource status, integrations, events, and result flow. However, the public material available in this pass does not expose API paths, request/response schemas, typed examples, error shapes, safe sandbox behavior, or recorded captures. Source-pack operations require L2+ evidence, so Cellario should remain an intake dossier until HighRes docs, sandbox/test-mode probes, or approved captures are available.
