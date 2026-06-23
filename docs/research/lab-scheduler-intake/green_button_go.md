# Green Button Go Intake

## Public Claims

Biosero positions [Green Button Go Scheduler](https://biosero.com/products/green-button-go-scheduler/) as automated laboratory scheduling software for designing, scheduling, monitoring, and executing integrated workcell workflows. The public Scheduler page claims broad installed-base credibility, a drag-and-drop workflow builder, a large device-driver library, and integration with existing lab software. The most relevant source-pack claim is that Scheduler is "Built to connect" and "Easily integrates with lab software via RESTful API and database hooks."

The official [Green Button Go Scheduler brochure](https://biosero-assets.sfo3.digitaloceanspaces.com/pages/products/green-button-go-scheduler/30000-Green-Button-Go-Scheduler-Brochure.pdf) repeats the workcell-scheduler positioning and adds two useful dry-run/source-pack signals: "Software API available for external function calls" and "API connectivity through Data Services Lite." The brochure also says users can build and test workflows in Simulation Mode before working on live equipment.

Biosero's [Green Button Go Galaxy product update](https://biosero.com/product-updates/gbg-galaxy-a-unified-future-for-lab-automation-software/) says Green Button Go Scheduler will include a Green Button Go Orchestrator component called Data Services Lite in the installer, making Scheduler "API-capable out of the box" through a "secure, extensible API layer." It frames Data Services Lite as a gateway for connecting Scheduler to LIMS, ELN, and other digital systems, with an upgrade path to the full Orchestrator suite.

Biosero's [Green Button Go Data Services 1.1 product update](https://biosero.com/product-updates/stay-on-top-of-lab-activity-with-gbg-data-services-feature/) says Data Services added webhooks with more than 40 event triggers, including instrument errors, sensor measurements, canceled jobs, and changes in instrument status. The same page says information from lab events passes through Data Services APIs and is stored in databases for other systems and audit use.

The [Green Button Go Orchestrator page](https://biosero.com/products/green-button-go-orchestrator/) is adjacent context rather than Scheduler-only API shape. It says Orchestrator is built on GBG Scheduler, coordinates multi-workcell workflows, integrates LIMS/ELN/analysis tools, and includes Data Services as a central hub for communication and data orchestration.

Biosero's general blog post [What is an application programming interface?](https://biosero.com/blog/what-is-an-application-programming-interface/) is not a Green Button Go API contract, but it is useful as vendor philosophy: Biosero says useful APIs should be documented, reliable, error-aware, and should accurately represent instrument behavior.

## API Evidence Found

Public evidence supports the existence of integration surfaces, but not enough concrete shape for source-pack operation records.

- REST/API/database-hook evidence: the Scheduler product page explicitly mentions RESTful API and database hooks, but does not publish endpoint paths, authentication, versioning, database tables/views/procedures, request bodies, response bodies, errors, or examples.
- Data Services Lite evidence: the Scheduler brochure and Galaxy product update say Scheduler has API connectivity through Data Services Lite, but they do not expose a contract for Data Services Lite operations.
- Webhook/event evidence: the Data Services 1.1 update says webhooks can be registered for lab events and mentions more than 40 event triggers. It gives event categories, but no webhook registration endpoint, payload schema, signing/auth model, retry behavior, event envelope, or sample payload.
- Simulation evidence: the Scheduler brochure says workflows can be built and tested in Simulation Mode before live equipment. It does not expose a simulator API, validation endpoint, workflow export format, simulated run response, or run-event log schema.
- Workflow surface evidence: public pages describe scheduling, execution, real-time monitoring, error handling, dynamic workflow changes, scripts, drivers, and extensions. These claims identify likely operation families, but do not define original-shaped operations.

No public OpenAPI/Swagger, protobuf/gRPC schema, SDK reference, typed examples, plugin API contract, database hook contract, workflow/process export schema, validation/simulation response schema, run event log schema, or result/artifact response schema was found in public Biosero pages reviewed for this intake.

## Missing Shape

The public material does not answer the source-pack questions needed to build dry-run operations faithful to Green Button Go:

- Capability discovery: no operation for listing installed Scheduler/Data Services capabilities, versions, drivers, instruments, extensions, workcells, or supported event types.
- Auth/session model: no public details for API authentication, local-vs-cloud base URL, tenant/workcell scoping, tokens, API keys, user roles, service accounts, or permissions.
- Workflow/protocol read: no schema for reading projects, methods, workflows, processes, steps, instruments, labware, resources, variables, scheduling constraints, scripts, or error handlers.
- Workflow/protocol create or modify: no request/response examples for creating or editing protocols, adding steps, setting instrument processes, changing workflows during a run, or validating edits.
- Validation/simulation: no documented API shape for Simulation Mode, static timing studies, dry-run validation, simulated errors, scheduling conflicts, or feasibility checks.
- Run control boundary: no safe dry-run contract for creating a job, queuing a run, starting/stopping/pausing a simulated run, or querying status without touching live hardware.
- Events and logs: no event envelope, webhook registration contract, event type catalog, run log schema, instrument status schema, error schema, retry semantics, or audit-log export shape.
- Results/artifacts: no schema for outputs such as measurements, files, plate maps, sample history, consumable usage, generated reports, or links to external LIMS/ELN records.
- Database hooks: no database contract for hook type, read/write direction, connection model, table/view/procedure names, transactions, idempotency, or audit behavior.
- Versioning: no public mapping from Scheduler/Galaxy/Data Services Lite versions to API compatibility or schema version identifiers.

## Safe Probe Possibilities

Do not call live endpoints, create scheduler jobs, start hardware, or mutate production workflow state.

Safe probes require explicit customer/vendor approval and should be limited to non-hardware, non-production surfaces:

- Read-only documentation capture from Biosero Portal or customer-provided docs: OpenAPI/Swagger, SDK docs, database hook contract, Data Services Lite docs, webhook docs, plugin docs, or export format docs.
- Local/offline Scheduler project export inspection, if Biosero or a customer can provide sample files with no confidential science and no hardware credentials.
- Simulation Mode probe in an isolated test installation with no connected instruments and no production workcells, limited to capability discovery, workflow validation, simulated run status, and exported run/event logs.
- Webhook capture from a sandbox/test Data Services installation using synthetic events only, with payloads recorded and redacted before source-pack ingestion.
- Database hook inspection against a disposable test database seeded with synthetic workflows/samples, with read-only access preferred unless an explicit write contract is being tested.
- Recorded captures from Biosero or an approved user showing request/response pairs, webhook payloads, validation responses, simulated run logs, and result/artifact objects.

## Outreach Ask

Ask Biosero or an approved Green Button Go customer for the minimum artifact set needed to build a source-backed dry-run source pack:

- REST/OpenAPI/Swagger docs for Green Button Go Scheduler, Data Services Lite, and/or Data Services, including auth, base URLs, versioning, error codes, and examples.
- Database hook contract for Green Button Go Scheduler, including hook direction, tables/views/procedures, payload columns, transactions, idempotency, and audit behavior.
- Workflow/process export format for Scheduler projects/methods/workflows/processes, with one sanitized example.
- Protocol/workflow create and modify examples, including validation failures and successful responses.
- Validation/simulation responses from Simulation Mode or an equivalent non-hardware test mode.
- Run event logs and webhook payload examples for synthetic events such as workflow queued, workflow started, instrument status change, sensor measurement, canceled job, instrument error, pause/resume, workflow completed, and artifact/result produced.
- Result/artifact response examples for files, measurements, sample/labware state, plate maps, reports, and links to LIMS/ELN records.
- Sandbox/test-mode access or recorded captures that prove behavior without live hardware or production state.

## Datalox Boundary

For API Gym, Green Button Go should stay at intake/reference level until L2+ evidence is available. Public Biosero pages are useful source references for market fit and operation-family selection, but they are not enough to create original-shaped API operation records.

API Gym can model a Green Button Go-like dry-run world only after the source substrate includes concrete API/database/export/capture evidence. Without that, any endpoint path, request/response body, event payload, or database schema would be invented. That would violate the product boundary: API Gym builds source-backed dry-run worlds and source packs, not live API aggregation or speculative scheduler emulation.

If Green Button Go evidence is obtained, the first safe source-pack operations should prioritize read/discovery and dry-run validation before execution:

1. capability/list or version/driver/workcell discovery
2. workflow/protocol/template read or export parse
3. workflow/protocol create or modify in a sandbox or file-backed export
4. validation/simulation response
5. run/event log read or webhook payload capture
6. result/artifact read

Do not add live provider execution, hardware control, or production workflow mutation unless there is an explicit live-gate policy and user approval.

## Decision

`needs_docs_or_probe`

Green Button Go has credible public claims for RESTful API/database hooks, Data Services Lite API connectivity, webhooks, event triggers, and Simulation Mode. The missing piece is concrete API/database/export shape. The next artifact ask is: REST docs/database hook contract, workflow/process export, protocol create/modify examples, validation/simulation responses, run event logs, result/artifact responses, sandbox/test-mode access, or recorded captures.
