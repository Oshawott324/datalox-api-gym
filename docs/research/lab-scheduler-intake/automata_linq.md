# Automata LINQ Intake

## Public Claims

Automata presents LINQ as a fully integrated, AI-ready lab automation platform for workflow design, scheduling, orchestration, execution, analytics, and lab connectivity. Automata's public homepage says software-defined LINQ supports process orchestration, parallel workflow execution, real-time analytics, and MCP-enabled connectivity to AI models: [Automata homepage](https://www.automata.tech/).

Automata's developer page makes stronger developer-facing claims: LINQ has a Python SDK and API for workflow lifecycle control, simulation on a digital workcell, dynamic workflow creation, run control, error handling, orchestration, webhooks, queues, and management APIs. It also claims integrations with external APIs, LIMS, ELNs, databases, AI models, GitHub, and cloud providers: [LINQ SDK & API developer experience](https://www.automata.tech/linq/developer-experience).

Automata's company-news page repeats the MCP claim in an AI-native lab framing: LINQ Canvas and Run Manager are described as driving process orchestration, parallel execution, workflow parameters, batch scaling, runtime optimization, analytics, simulations, and MCP-enabled AI integration: [AI-Native Labs: Why Legacy Lab Automation Must Evolve](https://www.automata.tech/company-news/legacy-labs-evolve-with-ai).

Automata's BIO-IT World 2026 event page describes LINQ as infrastructure for intelligent labs with hybrid scheduling, cloud orchestration, open architecture, simulation, advanced scheduling, ML, LLMs, and MCP: [AI Lab Automation & Orchestration | BIO-IT World 2026 Boston](https://www.automata.tech/events/bio-it-2026).

Third-party coverage aligns with the scheduler/orchestration positioning but is still claim-level evidence. Lab Manager describes LINQ as having dynamic replanning scheduling that plans and validates workflows upfront, responds to execution events, detects errors, recovers workflows, records event data, and transfers event data to the cloud interface: [Beyond Orchestration: The Evolving Role of Schedulers in Lab Automation](https://www.labmanager.com/beyond-orchestration-the-evolving-role-of-schedulers-in-lab-automation-32844). Beckman Coulter says LINQ includes modular robotics, unified scheduling software, an agile workflow design environment, and a cloud-native orchestration engine for multistep experimental processes: [Beckman Coulter partnership announcement](https://www.beckman.com/news/partners-with-automata-to-accelerate-ai-ready-laboratory-automation). Molecular Devices says LINQ unifies instruments, robotics, and software and integrates imaging/detection systems into research workflows: [Molecular Devices partnership announcement](https://www.moleculardevices.com/newsroom/news/molecular-devices-partnership-with-automata-linq-platform).

## API Evidence Found

L2 evidence exists for a shape-grounded SDK/API source pack. It does not yet
provide OpenAPI/MCP schemas, concrete provider response bodies, or live/sandbox
captures.

Automata publishes public Sphinx documentation for the LINQ SDK. The docs state that the SDK works with the Automata LINQ platform for creating and managing workflows and for planning and executing on hardware. They also state that the Python SDK is built on top of a RESTful LINQ API: [Automata LINQ SDK docs](https://docs.automata.tech/).

The public package exists on PyPI as `automata-linq-sdk`, with release `1.18.0` published on June 3, 2026, Python `>=3.11`, Apache-2.0 license metadata, and downloadable source/wheel artifacts: [automata-linq-sdk on PyPI](https://pypi.org/project/automata-linq-sdk/). Static inspection of the pinned public wheel found request routes, accepted status handling, domain routing, generated models, and structured error envelopes in `linq/client.py`, `linq/schema/workflow_api.py`, `linq/schema/backend_api.py`, and `linq/schema/auth_api.py`. No live Automata endpoints were called.

The docs expose a LINQ API client reference with typed method names and return types. Publicly documented operations include `get_api_version`, `get_organizations`, `create_workflow`, `get_workflows`, `update_workflow`, `delete_workflow`, `validate_workflow`, `plan_workflow`, `get_plan_status`, `get_plan_result`, `get_supported_scheduler_versions`, `get_workflow`, `get_sdk_workflow`, `get_all_drivers`, `get_workcells`, `deploy_workflow`, `get_status`, `get_latest_error`, `respond_to_error`, `start_workflow`, `pause_workflow`, `resume_workflow`, `stop_workflow`, `reset_workflow`, `publish_workflow`, machine-credential methods, script-info methods, and `get_workflow_puml`: [LINQ API Client](https://docs.automata.tech/client).

The planning docs provide sourceable scheduling semantics. Planning converts a validated workflow into a concrete execution plan; planning can vary by optimization objectives, search behavior, computation limits, and soft timing preferences; hard constraints are always satisfied; successful planning is documented as guaranteeing deadlock-free execution by resolving resource conflicts before deployment. Workflow-level inputs include tasks, dependencies, time constraints, and timing targets: [Planning and Validation](https://docs.automata.tech/planning-validation).

The same planning docs provide schema-level examples for `PlannerOptions`, `OptimisationStage`, `StoppingConditions`, objective values, and carry-forward rules. This is useful L2 material for a dry-run scheduler model because it names objectives such as `makespan`, `deadtime`, `timing_targets`, `consistency`, and `slack`, and it documents planning options such as computation limits, load balancing, transport concurrency, feasibility strategy, and multi-stage optimization: [Planning and Validation](https://docs.automata.tech/planning-validation).

The workflow execution docs provide an execution lifecycle and CLI-shaped operation examples: publish a workflow, optionally bundle a plan, list workcells, deploy a workflow to a workcell, start, pause, resume, stop, reset, retrieve status, retrieve latest error, and respond to an error. They also document a simulation flag behavior for instruments configured with `"simulate": true`: simulated instruments avoid hardware-driver initialization during deployment and do not generate hardware connectivity errors: [Workflow Execution](https://docs.automata.tech/workflow-execution).

The access-log docs document programmatic log export through the SDK/CLI, including workcell ID, from-date, output directory, ZIP output, partial logs for running workflows, timestamps, statuses, and instrument interactions: [Access Logs in the SDK](https://docs.automata.tech/access-logs).

The example workflow docs provide typed Python examples for `Workflow`, `Labware`, `LabwareType`, `ActionTask`, `Inputs`, `LabwareSource`, `StoredLabware`, `LabwareOutput`, `LabwareLocation`, scheduler version selection, task dependencies, static arguments, labware movement, and time estimates: [Example Workflows](https://docs.automata.tech/wf-creation-tutorial).

## Missing Shape

No public OpenAPI document, Postman collection, JSON Schema bundle, protobuf/gRPC/FDL contract, or MCP schema was found in the public pages reviewed.

The SDK client implementation exposes selected REST route paths and methods, but the public docs do not expose a canonical endpoint catalog, OpenAPI examples, full request bodies, concrete response bodies, authentication header contract beyond the SDK behavior, webhook payloads, queue semantics, run-event schemas, artifact/result schemas, or idempotency behavior.

The SDK client reference gives method signatures and broad return types. Static wheel inspection supplied enough route/model shape for `source_packs/apis/automata_linq/2026-06-22`, but not enough concrete provider bodies for runtime-world readiness.

The public MCP claims are L0/L1 marketing/product claims only. I found no public Automata MCP server docs, MCP endpoint URL, transport mode, authentication model, tool list, resource list, prompt list, JSON Schemas for tool inputs/outputs, example `tools/list` response, example `tools/call` response, or MCP error/event contract.

The scheduler semantics are strong enough for candidate dry-run design notes and shape-grounded source records. They are not enough for a runtime world that claims concrete provider behavior across validation, planning, run control, replanning, event logs, artifacts, and results.

The public docs mention simulation and simulated instruments, but I found no public sandbox/test-mode account path, no fixture workspace, no non-hardware test credentials, and no recorded captures showing validate/plan/publish/deploy/start responses.

## Safe Probe Possibilities

Safe now, without calling live endpoints or touching hardware:

- Refresh the pinned `automata-linq-sdk` source distribution or wheel from PyPI and statically inspect exported Pydantic models, typed dictionaries, enums, client method implementations, URL construction, error classes, and serializers.
- Run local-only examples only if they do not authenticate, call cloud APIs, or initialize hardware drivers. Any code execution should be isolated and network-disabled unless the code is known to be pure object construction/serialization.
- Capture public docs pages into source notes for stable citations and extract operation names, typed classes, enums, and CLI command shapes.

Safe only with explicit Automata-provided sandbox/test-mode access and approval:

- Call validation/planning endpoints against a sandbox workspace using simulated instruments only.
- Probe `validate_workflow`, `plan_workflow`, `get_plan_status`, `get_plan_result`, and `get_workflow_puml` with a minimal fixture workflow and record full request/response captures.
- Probe non-mutating discovery methods such as API version, supported scheduler versions, drivers, scripts info, and workcell listing in a sandbox tenant.
- Export run logs from a sandbox/simulated run to capture event-log ZIP structure and partial-log behavior.

Not safe for this intake:

- Creating, publishing, deploying, starting, pausing, stopping, resetting, or otherwise controlling real workcell/hardware runs.
- Inferring REST endpoint paths from SDK method names unless confirmed by source code or official docs.
- Treating public MCP marketing claims as MCP tool/resource schema evidence.

## Outreach Ask

Ask Automata for source-pack evidence at the contract level, not another sales overview:

- Public or partner OpenAPI/JSON Schema/Postman documentation for LINQ Cloud.
- Python SDK model/schema docs for workflow creation, validation, planning, execution control, error response, webhooks, logs, artifacts, and results.
- MCP server documentation if MCP is available: endpoint/transport, auth, `tools/list`, `resources/list`, tool input schemas, output schemas, and example errors.
- Minimal workflow/run examples with full validate, plan, plan-status, plan-result, publish/deploy/start status, simulation response, and event-log captures.
- Sandbox/test-mode tenant access that cannot control physical hardware.
- Recorded request/response captures for simulated workflows if sandbox access is not available.

## Datalox Boundary

API Gym should not build a live Automata LINQ connector or API aggregator from this intake. The product boundary is source-backed dry-run worlds and source packs.

The public evidence supports a shape-grounded SDK/API source pack for workflow validation, planning, optimization objectives, hard constraints, soft timing targets, simulated-instrument semantics, workcell status, latest-error inspection, error-response boundaries, run histories, and run-log export URL shape. It does not support a live connector, a public MCP source pack, or concrete runtime-world behavior without sandbox probes or recorded captures.

The checked-in near-term use is `source_packs/apis/automata_linq/2026-06-22`. A runtime world or MCP-shaped pack should wait for official schema docs, sandbox probes, or recorded captures.

## Decision

source_pack_now

Public LINQ docs plus static inspection of `automata-linq-sdk==1.18.0` provide enough L2 evidence for a structurally valid, shape-grounded source pack. The pack is not concrete-sampled and not runtime-world-ready.

Concrete artifact ask: provide API/MCP schema docs, tool/resource schema examples, workflow/run examples, validation/simulation response examples, run event log examples, artifact/result response examples, sandbox/test-mode access, or recorded captures.
