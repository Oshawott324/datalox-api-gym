# Genera Intake

## Public Claims

Retisoft positions Genera as laboratory automation scheduling software rather than a public cloud API service. The strongest public claims for API Gym relevance are scheduler orchestration, runtime decisions, simulation/estimation, error recovery, instrument pooling, driver integration, and some external access surfaces:

- Retisoft's Genera scheduling page describes Genera as lab scheduling software with a drag-and-drop workflow editor and simulation features for resource management, and lists Gantt progress monitoring, deadlock prevention, runtime decision making, scripting, flexible error handling, parallel execution, instrument pooling, and process estimation as features ([Retisoft Genera automatic scheduling software](https://retisoft.com/genera-automatic-scheduling-software/)).
- The same page says process estimation can "simulate a full process run" for timing and throughput, and says flexible error handling can recover mid-run by retrying a step or continuing after resolution ([Retisoft Genera automatic scheduling software](https://retisoft.com/genera-automatic-scheduling-software/)).
- Retisoft's Hub Genera page repeats the core scheduler claims: decision nodes, look-ahead deadlock prevention, process estimation for throughput simulation, built-in scripting, flexible error handling, and parallel execution ([Retisoft Hub Genera](https://retisoft.com/hub/genera/)).
- Retisoft's main site says Genera 6 is a dynamic scheduler, supports real-time workflow decisions, hardware integration and automation control, custom runtime decision features, and control of lab hardware from any vendor through an open software architecture ([Retisoft home page](https://retisoft.com/)).
- Retisoft's instrument drivers page says Genera drivers connect devices to automation platforms, translate software commands into device-specific instructions, capture instrument data, monitor status/errors/performance, and support USB, TCP/IP, or serial connections ([Genera instrument drivers](https://retisoft.com/genera-instrument-drivers/)).
- Retisoft's free-trial page says a trial includes workflow scheduling, device integration, custom scripting tools, and a simulation mode for exploring/testing automation setup without live hardware ([Retisoft free trial](https://retisoft.com/request-your-free-trial/)).
- Retisoft's Genera Web App page says the web app communicates directly with Genera, exposes live system information, monitors current process progress, process completion, instrument status, running protocols, real-time updates, and error/notification alerts ([Genera Web App](https://retisoft.com/genera-web-app/)).
- Retisoft Hub says existing customers can access training videos, user manuals/documents, demo software, and a testing software license, but this appears account-gated rather than public source evidence ([Retisoft Hub](https://retisoft.com/hub/)).
- A public Retisoft/LinkedIn post claims a "Genera Scheduling's Remote API plugin" provides RESTful access for third-party applications to interact with scheduling, execution, and system state, trigger runs/workflows remotely, query status/execution data in real time, integrate with LIMS/ELN/MES/custom apps, and use standard HTTP methods, predictable endpoints, and structured data exchange. This is an API existence claim, not a documented contract ([LinkedIn public post result](https://www.linkedin.com/posts/arty-tyagi_bioprocessing-bioreactors-software-activity-7445574660978724865-o3Kj); linked video title: [Genera Remote API Plugin](https://www.youtube.com/watch?v=6rGXVluNnok)).
- Opentrons' partner page describes Retisoft as dynamic lab automation scheduling software and says Genera integrates with Opentrons robots for centralized scheduling, error handling, and multi-instrument coordination ([Opentrons Retisoft partner spotlight](https://opentrons.com/our-partners/retisoft)).

These are useful L0/L1 product signals. They establish domain fit for a scheduler/source-substrate investigation, but they do not define action contracts.

## API Evidence Found

Public L2+ API evidence was not found.

Found:

- Product pages that describe scheduling, workflow decisions, error handling, simulation/process estimation, driver integration, monitoring, and web-app communication with Genera ([Retisoft Genera automatic scheduling software](https://retisoft.com/genera-automatic-scheduling-software/), [Retisoft Hub Genera](https://retisoft.com/hub/genera/), [Genera Web App](https://retisoft.com/genera-web-app/), [Genera instrument drivers](https://retisoft.com/genera-instrument-drivers/)).
- Public claims that a Remote API plugin exists and is RESTful, with standard HTTP methods, predictable endpoints, structured data exchange, remote run/workflow triggering, and system-status/execution-data queries ([LinkedIn public post result](https://www.linkedin.com/posts/arty-tyagi_bioprocessing-bioreactors-software-activity-7445574660978724865-o3Kj), [Genera Remote API Plugin video](https://www.youtube.com/watch?v=6rGXVluNnok)).
- Public evidence that customer-gated Retisoft Hub may contain manuals, documents, demo software, and testing software licenses ([Retisoft Hub](https://retisoft.com/hub/)).
- Public support agreement language saying Retisoft may use logs, screenshots, Genera installation files, and drivers for debugging; this confirms logs and installation artifacts exist operationally, but not their schemas or export contract ([Retisoft RAPP Exhibit III](https://retisoft.com/rapp/exhibit-iii/)).

Not found:

- OpenAPI, Swagger, Postman collection, protobuf/gRPC/FDL, SDK source, typed request/response examples, endpoint reference, auth model, versioning policy, error-code catalog, event/log schema, export schema, simulator interface contract, or sandbox/test-mode API documentation.
- Public examples of actual Remote API requests or responses.
- Public examples of workflow/process definitions, validation responses, simulation responses, run event logs, result/artifact payloads, instrument status payloads, or execution-state payloads.

## Missing Shape

Genera cannot become an API Gym source pack from public evidence alone because the operation shape is missing:

- Provider/version identity: no public Remote API version, Genera version-to-API compatibility matrix, plugin version, or deprecation policy.
- Transport/auth: no base URL pattern, local/network binding model, authentication, authorization, token/session handling, TLS expectations, or role model.
- Operation catalog: no endpoint paths, HTTP methods tied to concrete resources, query/body parameters, idempotency semantics, or pagination/filtering rules.
- Workflow schema: no structured representation for workspaces, processes, activities, decision nodes, instruments, instrument pools/zones, scripts, dependencies, or scheduling constraints.
- Execution lifecycle: no public state machine for draft/validated/simulated/queued/running/paused/error/recovered/completed/canceled process runs.
- Simulation/process estimation: no request schema, response schema, timing/throughput output shape, validation failure shape, or deterministic replay knobs.
- Runtime monitoring: no response shape for process progress, Gantt data, running protocols, instrument status, system state, alerts, errors, or notifications.
- Error recovery: no structured error codes, recovery actions, retry/continue semantics, operator intervention model, or event-log representation.
- Results/artifacts: no export/result schema for run outputs, instrument files, data products, logs, audit trails, or artifact metadata.
- Driver layer: no driver SDK/API schema, command model, device-status schema, data acquisition payload shape, or simulation/stub-driver contract.

## Safe Probe Possibilities

Do not call live endpoints and do not create scheduler, workflow, hardware, or instrument runs.

Safe next probes, only with Retisoft/customer-provided approval and non-production setup:

- Request or use an offline/demo Genera installation with the Remote API plugin enabled and simulation mode only.
- Enumerate bundled local documentation, API reference files, OpenAPI/Swagger assets, Postman collections, sample scripts, SDK files, or example projects from the installation package without starting workflows.
- Inspect training/demo materials from Retisoft Hub for documented API examples, simulator examples, validation examples, and run-log/export examples.
- Run read-only API discovery only if Retisoft identifies explicit docs/discovery endpoints or provides a test-mode sandbox; do not brute-force endpoint paths.
- Capture recorded HTTP traffic from Retisoft's own Remote API demo or a customer-approved simulation-only workflow, with no live hardware attached and no production samples.
- Collect generated logs, validation outputs, simulation/process-estimation outputs, and run-event exports from a Retisoft-provided toy workflow that is designed for documentation capture.

## Outreach Ask

Ask Retisoft for source-pack-grade artifacts, not a live production integration:

- Remote API plugin documentation: provider/version, auth, endpoint catalog, request/response schemas, error codes, pagination/filtering, idempotency, and versioning.
- OpenAPI/Swagger/Postman/SDK/protobuf/gRPC/FDL or equivalent typed interface definitions if they exist.
- Simulator/test-mode documentation for Genera simulation mode and process estimation, including validation/simulation request and response examples.
- Workflow/process examples covering workspace, process, activity, decision node, instrument, instrument pool, script, schedule constraint, and dependency representations.
- Execution lifecycle examples covering create/validate/simulate/queue/start/status/pause/recover/cancel/complete if those operations are supported.
- Run event log examples, instrument/system status examples, alert/error examples, and recovery-action examples.
- Result/artifact response examples, including produced files, metadata, audit trail, and export/log locations.
- Sandbox/test-mode access or recorded captures from a simulation-only workflow with no live hardware.

## Datalox Boundary

API Gym should treat Retisoft Genera as a candidate source substrate for dry-run lab scheduler worlds, not as a live API connector.

Allowed here:

- Preserve public claims and sourced references for intake.
- Build a source pack only after L2+ evidence defines concrete operation shapes.
- Use Retisoft-provided docs, schemas, typed examples, sandbox/test-mode probes, simulator captures, or recorded traffic to model original-shaped API calls behind a dry-run gate.
- Later select grounded operations into a resettable world with filesystem/SQLite state, MCP action contracts, hidden verifier checks, and run exports.

Not allowed here:

- Invent endpoint paths, request bodies, response bodies, error codes, or workflow schemas from marketing copy.
- Call live Genera endpoints, trigger runs/workflows, or touch hardware.
- Build live API aggregation to Retisoft systems.
- Treat product claims about scheduling, simulation, or REST access as source-pack operations without concrete schema evidence.

## Decision

needs_docs_or_probe

Rationale: Genera is a strong domain fit for lab scheduler/API source substrate because public materials claim dynamic scheduling, simulation/process estimation, runtime decisions, error recovery, instrument pooling, driver integration, monitoring, and a RESTful Remote API plugin. However, the public evidence found is L0/L1 plus API-existence claims. No public L2+ contract was found for endpoint paths, schemas, typed examples, SDKs, logs, simulator responses, validation responses, run event logs, or result/artifact responses. A source pack should wait for Retisoft documentation, sandbox/test-mode access, or recorded simulation-only captures.

Concrete artifact ask: provide API/export/log docs, simulator interface docs, workflow/process examples, validation/simulation request and response examples, run event logs, result/artifact response examples, sandbox/test-mode access, or recorded Remote API captures from a simulation-only Genera workflow.
