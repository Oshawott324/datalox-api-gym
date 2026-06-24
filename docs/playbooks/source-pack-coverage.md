# Source Pack Coverage

This is the operational tracker for the Section 3.1 source-pack-first backlog.
It freezes the definition of done for source-pack coverage so prose plans,
structural validation, sampled provider evidence, and runtime world readiness
are not conflated.

## Section 3.1 Definition Of Done

Section 3.1 coverage is done only when every claimed provider/lane entry points
to checked-in evidence under:

```text
source_packs/apis/<provider>/<version>
```

A lane is not complete from prose alone. A provider/version directory must
exist, validate with:

```bash
api-gym source-pack validate source_packs/apis/<provider>/<version>
```

and include operation records plus response-case evidence for the operations
used to justify the lane. Empty directories, wishlist provider names, world
README text, sales notes, or benchmark-plan prose do not count as source-pack
coverage.

Use these four statuses precisely:

- structurally valid source pack: `source_pack.json` lists existing non-empty
  record files, records have stable ids and source refs, live execution is not
  allowed, every operation has at least one response case, and
  `api-gym source-pack validate` passes.
- concrete-sampled pack: a structurally valid pack whose important success,
  error, permission, conflict, or validation cases include concrete `body` or
  `body_excerpt` values from cited official docs, explicit contracts, safe
  test-mode probes, or recorded observations. `body_shape` alone is not a
  concrete sample.
- runtime-world-ready selected records: a world can cite only the selected
  operation, schema, response-case, error, and candidate records it needs in
  `worlds/<world_id>/source_refs.json`; those records must cover the runtime
  read/list path, mutation or transition path, important failure path, and any
  declared synthetic dynamics boundary. The whole provider pack does not need
  to be world-ready, but the selected records do.
- live/test-mode probe evidence: optional evidence rows from approved safe
  probes or recorded provider test-mode observations. Probe evidence must be
  stored as source substrate, cite the provider/version and command or capture
  context, and must not enable live provider execution in the dry-run world
  without a separate live-gate policy and explicit approval.

Shape-only response cases are useful source grounding, but they are not strong
sample evidence. They should stay clearly labeled until official examples,
OpenAPI examples, safe test-mode probes, or recorded observations provide
concrete bodies.

## Provider/Lane Acceptance Checklist

The not-yet-complete lanes below are accepted only when each selected provider
has a real provider/version directory, validates cleanly, and has operation and
response-case evidence. Do not mark a lane complete until the table includes
the providers, versions, operation counts, response-case counts, concrete-case
counts, error-case counts, and world-selection status.

Appointment/service lane:

- Provider packs exist for the selected appointment/service providers, such as
  calendar, booking, dispatch, or vertical service systems.
- Operations cover availability lookup, customer or job lookup, reservation or
  appointment creation, reschedule or cancellation, and conflict handling when
  those behaviors are part of the claimed lane.
- Response cases include success and unavailable-slot, conflict, validation, or
  permission cases for the operations selected into a world.
- Critical booking or reschedule mutations have concrete sampled bodies or an
  explicit synthetic-dynamics note cited from selected source records.

Workflow SaaS lane:

- Provider packs exist for the selected workflow SaaS providers, such as chat,
  issue tracking, documents, tables, email, or automation systems.
- Operations cover read/list context, create/update action, state transition or
  assignment, and permission or rate/validation failure cases.
- Response cases include concrete success or error evidence for selected
  mutations that agents will dry-run.
- Cross-system workflow claims are grounded by selected source refs, not by a
  generic integration story.

Finance approval lane:

- Provider packs exist for the selected finance or procurement providers.
- Operations cover request or bill lookup, approval or rejection transition,
  attachment/comment/audit context when relevant, and permission/policy failure
  cases.
- Response cases include success and policy, permission, validation, duplicate,
  or conflict cases for selected approval mutations.
- No lane claim implies real payment movement, card issuance, procurement
  execution, or live provider calls unless a separate approved live-gate policy
  exists.

Lab/physical-action lane:

- Provider packs or approved contract-sample packs exist for the selected lab,
  instrument, scheduler, protocol, or physical-action systems.
- Operations or action records cover inspect/read state, prepare or validate
  protocol, perform dry-run transition, record readout/result, and reject
  unsafe or invalid physical actions.
- Response cases or state cases include deck/labware/protocol inspection,
  transfer or action success, invalid volume or unsafe-action failure, and
  missing-control or readiness failure where relevant.
- No source-pack or world claim implies live hardware execution. Physical
  execution requires an explicit live-gate policy, approval, and evidence kept
  separate from dry-run source-pack coverage.

## Current Support/Billing/CRM Coverage

Checked on 2026-06-16 with:

```bash
for p in source_packs/apis/*/2026-06-12; do
  api-gym source-pack validate "$p"
done
```

All checked-in support, billing, and CRM packs validate.

| Provider | Lane | Ops | Response cases | Concrete cases | Shape cases | Error cases | World status | Quality status |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| Stripe | billing | 2 | 3 | 2 | 0 | 1 | selected by `billing_support_v0` | focused concrete samples |
| Chargebee | billing | 5 | 8 | 0 | 5 | 3 | candidate; not runtime-gated | shape-grounded only |
| PayPal | billing | 4 | 6 | 3 | 1 | 2 | candidate | concrete plus shape |
| Square | billing | 3 | 6 | 3 | 0 | 3 | candidate | concrete samples |
| Zendesk | support | 4 | 5 | 2 | 2 | 1 | selected by `billing_support_v0` | concrete plus shape |
| Intercom | support | 4 | 5 | 0 | 4 | 1 | candidate | shape-grounded |
| Freshdesk | support | 4 | 6 | 4 | 0 | 2 | candidate | concrete support-ticket samples |
| Help Scout | support | 5 | 8 | 0 | 5 | 3 | candidate | shape-grounded |
| HubSpot | CRM | 4 | 6 | 4 | 0 | 2 | selected by `billing_support_v0` | concrete selected samples |
| Salesforce | CRM | 4 | 5 | 0 | 4 | 1 | candidate | shape-grounded |
| Pipedrive | CRM | 4 | 6 | 2 | 2 | 2 | candidate | concrete plus shape |
| Zoho CRM | CRM | 4 | 7 | 0 | 4 | 3 | candidate | shape-grounded |

## Appointment/Service Coverage

Checked on 2026-06-16 with:

```bash
for p in google_calendar microsoft_graph_calendar calendly servicetitan; do
  api-gym source-pack validate "source_packs/apis/$p/2026-06-16"
done
```

All checked-in appointment/service packs validate structurally. They are
candidate source packs only; none are runtime-world-ready yet because the
selected critical booking or event mutations are mostly shape-grounded and have
not been selected into a world contract.

| Provider | Lane | Ops | Response cases | Concrete cases | Shape cases | Error cases | World status | Quality status |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| Google Calendar | calendar appointments | 4 | 5 | 0 | 3 | 1 | candidate | shape-grounded; no concrete event mutation fixture |
| Microsoft Graph Calendar | calendar appointments | 4 | 5 | 0 | 3 | 1 | candidate | shape-grounded; recurrence-boundary error documented |
| Calendly | scheduling/booking | 5 | 6 | 0 | 5 | 1 | candidate | shape-grounded; direct invitee booking boundary documented |
| ServiceTitan | service booking/dispatch candidate | 4 | 5 | 1 | 3 | 1 | candidate | one concrete callback excerpt; direct dispatch APIs remain boundary-gated |

Appointment/service caveats:

- Google Calendar and Microsoft Graph Calendar cover event list plus
  create/update/delete or cancel event lifecycle operations, but the response
  cases are shape-grounded from official docs rather than concrete sampled
  event bodies.
- Calendly covers current-user and event-type lookup, available-time lookup,
  single-use scheduling-link creation, and the public create-event-invitee
  booking endpoint. Response bodies are still shape-grounded.
- ServiceTitan covers the official Leads Integration Platform token,
  account-pairing, booking request, and appointment-scheduled callback
  contract. Direct job/customer/dispatch API reference details were not
  captured from the developer portal in this task, so those remain explicit
  runtime gate boundaries.

## Workflow SaaS Coverage

Checked on 2026-06-16 with:

```bash
for p in slack gmail linear jira github notion; do
  api-gym source-pack validate "source_packs/apis/$p/2026-06-16"
done
```

All checked-in workflow SaaS packs validate structurally. They are candidate
source packs only; none are runtime-world-ready yet because most responses are
shape-grounded from official API references and have not been selected into a
world contract with concrete tenant/workspace fixtures or declared synthetic
dynamics.

| Provider | Lane | Ops | Response cases | Concrete cases | Shape cases | Error cases | World status | Quality status |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| Slack | chat workflow | 4 | 5 | 1 | 3 | 1 | candidate | one official success excerpt; remaining cases shape-grounded |
| Gmail | email workflow | 4 | 5 | 0 | 4 | 1 | candidate | shape-grounded Gmail message and label lifecycle |
| Linear | issue tracking | 4 | 5 | 0 | 4 | 1 | candidate | shape-grounded GraphQL query/mutation cases; schema selection still required |
| Jira | issue tracking | 4 | 5 | 0 | 3 | 1 | candidate | shape-grounded issue/comment/transition cases; tenant transition IDs still required |
| GitHub | repo issue workflow | 4 | 5 | 0 | 4 | 1 | candidate | shape-grounded issue/comment cases; issue-vs-PR distinction noted |
| Notion | docs/table workflow | 5 | 6 | 0 | 5 | 1 | candidate | current data-source API used; shape-grounded page/block cases |

Workflow SaaS caveats:

- Slack covers conversation history, posting, updating, and reactions. The
  `chat.update` success excerpt is official; workspace-specific message
  fixtures are still needed before runtime sampling.
- Gmail covers message list/get, send, and label modification. Response cases
  are shape-grounded from official Gmail Message resources and documented
  error handling.
- Linear covers team/issue/status context plus issue create/update and
  comment-create candidates. The pack cites Linear's public GraphQL docs and
  schema browser, but runtime selection must pin exact schema fields.
- Jira covers issue get/create, add comment, and transition. Transition IDs and
  permission behavior are tenant-specific and must be captured or modeled by a
  declared synthetic-dynamics boundary before world readiness.
- GitHub covers repository issue list/create/update and issue or PR comments.
  The pack preserves GitHub's documented secondary-rate and issues-disabled
  boundaries.
- Notion uses the current data-source query API, not the deprecated database
  query endpoint, and covers search, query, page create/update, and block
  append operations.

## Finance Approval Coverage

Checked on 2026-06-16 with:

```bash
for p in quickbooks xero bill_com ramp brex; do
  api-gym source-pack validate "source_packs/apis/$p/2026-06-16"
done
```

All checked-in finance approval packs validate structurally. They are candidate
source packs only; none are runtime-world-ready yet because most responses are
shape-grounded and none have been selected into a world contract with concrete
tenant fixtures or declared synthetic dynamics.

No real payment movement, card issuance, procurement execution, reimbursement
execution, vendor creation, bill creation, or live provider call is authorized
by these source packs.

| Provider | Lane | Ops | Response cases | Concrete cases | Shape cases | Response error cases | World status | Quality status |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| QuickBooks | accounting AP approval candidate | 5 | 6 | 0 | 5 | 1 | candidate | shape-grounded; payment movement boundary documented |
| Xero | accounting AP approval candidate | 5 | 6 | 0 | 5 | 1 | candidate | shape-grounded; payable invoice/payment boundary documented |
| BILL | AP bills/approvals/payments candidate | 5 | 6 | 3 | 1 | 1 | candidate | concrete official bill, approval-list, and payment excerpts; approval action is no-body; live payment boundary documented |
| Ramp | spend/AP/card/reimbursement candidate | 6 | 7 | 0 | 7 | 0 | candidate | shape-grounded; observed rate-limit and policy-decline records document error boundaries |
| Brex | expenses/vendors/transfers/cards/transactions candidate | 6 | 7 | 0 | 6 | 1 | candidate | shape-grounded; transfer and role/scope boundaries documented |

Finance approval caveats:

- QuickBooks covers vendor lookup, bill create/read/update, and BillPayment
  response shape. BillPayment rows are a dry-run boundary only and do not
  authorize vendor payment movement.
- Xero covers contact lookup, purchase-bill context through invoices, invoice
  create/read/update, and payment response shape. Payment rows are a dry-run
  boundary only.
- BILL covers vendor lookup, bill creation, pending approval lookup,
  approve/deny action, and payment response shape. Concrete excerpts come from
  official BILL docs, but live payment remains disallowed.
- Ramp covers bills, virtual-card task creation, cards, transactions, and
  mileage reimbursement. Card issuance, bill payment, and reimbursement
  execution remain boundary-gated. Ramp error boundaries are documented in
  `observed_errors.jsonl`, not as response error cases.
- Brex covers expenses, vendors, transfer creation, cards, and card
  transactions. Transfer creation records the official endpoint shape and
  permission/policy boundaries only; no live transfer is authorized.

## Lab/Physical-Action Coverage

Checked on 2026-06-22 with:

```bash
for p in unitelabs opentrons emerald_cloud_lab; do
  api-gym source-pack validate "source_packs/apis/$p/2026-06-16"
done
api-gym source-pack validate source_packs/apis/pylabrobot/2026-06-18
api-gym source-pack validate source_packs/apis/benchling/2026-06-22
api-gym source-pack validate source_packs/apis/sila2_reference/2026-06-22
api-gym source-pack validate source_packs/apis/automata_linq/2026-06-22
```

All checked-in lab/physical-action and lab-scheduler public-lane packs validate
structurally. They are dry-run/source-substrate packs only. No source pack
authorizes live workflow execution, robot control, instrument control,
experiment submission, device actuation, sample shipment, scheduler run
creation, or physical-action execution.

| Provider | Lane | Ops | Response cases | Concrete cases | Shape cases | Response error cases | Observed/boundary errors | World status | Quality status |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| UniteLabs | lab workflow run/log/artifact grounding | 4 | 5 | 0 | 4 | 1 | 2 | candidate; `unitelabs_plate_qc_v0` still cites world-local grounding | shape-grounded from public docs and repo grounding; no checked-in OpenAPI sample |
| Opentrons | protocol analysis and run inspection candidate | 4 | 6 | 1 | 4 | 1 | 2 | candidate; not runtime-world-ready | one concrete docs-derived upload excerpt plus shape-grounded analysis/run inspection rows; hardware execution boundary documented |
| Emerald Cloud Lab | documentation/API-index discovery candidate | 4 | 5 | 0 | 4 | 1 | 2 | candidate; not runtime-world-ready | boundary-gated; public docs are insufficient for lab-operation runtime modeling |
| PyLabRobot | dry-run liquid-handling action semantics candidate | 6 | 9 | 6 | 0 | 3 | 5 | candidate; not runtime-world-ready | concrete Chatterbox/OT-2 simulator excerpts plus tracker error boundaries; no live hardware |
| Benchling | automation handoff-side API candidate | 8 | 14 | 0 | 8 | 6 | 3 | candidate; not runtime-world-ready | source-packable from public API/SDK docs; explicitly boundary-gates Cellario execution |
| SiLA 2 Reference | standard/reference feature API candidate | 6 | 7 | 0 | 6 | 1 | 3 | candidate; not vendor scheduler-ready | reference gRPC/FDL semantics for discovery, feature definitions, properties, commands, status, and validation boundaries |
| Automata LINQ | lab orchestration SDK/API candidate | 15 | 18 | 0 | 15 | 3 | 5 | selected by `automata_linq_workflow_planning_v0` with declared synthetic dry-run dynamics | shape-grounded from public docs plus pinned SDK static wire/model inspection; no live tenant, run, workcell, or hardware execution |

Lab/physical-action caveats:

- UniteLabs covers source-contract sampling plus read-only run status, run log,
  and run artifact shapes. `unitelabs_plate_qc_v0` still cites
  `worlds/unitelabs_plate_qc_v0/API_GROUNDING.md`, not this source pack, until
  a real UniteLabs OpenAPI contract sample is checked in and selected through
  `worlds/unitelabs_plate_qc_v0/source_refs.json`. This does not expose
  verifier state or mutable session state.
- Opentrons covers protocol upload, protocol analysis creation, protocol
  analysis reads, and run-command inspection as source substrate. It now has
  one concrete docs-derived upload response excerpt for required equipment and
  metadata. Robot run start, command execution, maintenance movement, module
  commands, pipetting, lights, homing, and other hardware-control surfaces are
  explicitly outside this dry-run pack.
- Emerald Cloud Lab covers the public documentation center categories and the
  Constellation API documentation index as a boundary-gated candidate. It does
  not model experiment submission, lab scheduling, instrument operation, sample
  logistics, or result generation because public endpoint contracts and
  concrete response examples were not captured in this task.
- PyLabRobot covers software-only `LiquidHandlerChatterboxBackend`, tracker
  enablement, tip pickup, aspirate, dispense, and offline
  `OpentronsOT2Simulator` setup. It is stronger than Emerald Cloud Lab for
  dry-run action semantics because official PyLabRobot docs provide concrete
  Chatterbox/OT-2 simulator output and documented tracker failures, but it is
  still not runtime-world-ready until a world selects a deck/resource state
  schema, dynamics rules, and verifier invariants.
- Benchling covers the ELN/LIMS-side handoff substrate: plates, workflow
  tasks, workflow outputs, blobs, automation input generation, automation
  output processing, and events. It does not cover Cellario endpoint shape,
  scheduler run creation, workcell execution, robot motion, or instrument
  control.
- SiLA 2 Reference covers generic standard semantics only: discovery,
  implemented features, feature definitions, properties, commands, observable
  command status, typed data, and validation errors. Vendor-specific features,
  instruments, and scheduler processes still need their own FDL/protobuf/docs
  or safe captures before source-pack promotion.
- Automata LINQ covers source-grounded SDK/API routes for workflow creation,
  workflow listing and retrieval, validation, planning, plan polling/result
  retrieval, scheduler versions, drivers, workcells, device status, run
  histories, and log-export URL shape. The pack is grounded by public Automata
  docs plus static inspection of `automata-linq-sdk==1.18.0`; it does not
  contain live captures or concrete tenant bodies. The selected records are now
  used by `automata_linq_workflow_planning_v0`, which declares modest
  synthetic dry-run dynamics and boundary-gates publish, deploy,
  start/pause/resume/stop/reset, error response, hub restart, credential
  management, and any hardware/workcell execution.
- The lab packs are structurally valid but only PyLabRobot has concrete
  dry-run action excerpts. Do not claim high-fidelity lab/physical-action
  coverage until selected records have concrete official examples, approved
  recorded evidence, or a declared synthetic-dynamics boundary that passes the
  runtime-world acceptance gate.

## Lab Scheduler Commercial Intake

Sprint 1 commercial scheduler intake is complete at dossier level. Cellario,
Green Button Go, and Genera remain `needs_docs_or_probe`; do not create
operation records from public marketing claims alone. Automata LINQ has been
promoted from intake to a shape-grounded source pack through public SDK static
inspection, not through marketing claims.

| Provider | Dossier | Public evidence level | Decision | Promotion trigger |
| --- | --- | --- | --- | --- |
| HighRes Cellario | `docs/research/lab-scheduler-intake/cellario.md` | L0/L1 with a private Swagger/API-docs pointer | `needs_docs_or_probe` | OpenAPI/Swagger, SDK/protobuf/plugin docs, sandbox validate/simulate probe, or approved captures |
| Biosero Green Button Go | `docs/research/lab-scheduler-intake/green_button_go.md` | L0/L1 REST/API/database-hook and simulation-mode claims | `needs_docs_or_probe` | REST/database hook docs, workflow export schema, simulation responses, event logs, or approved captures |
| Retisoft Genera | `docs/research/lab-scheduler-intake/genera.md` | L0/L1 scheduler/simulation/error-recovery claims plus Remote API existence signal | `needs_docs_or_probe` | Remote API docs, simulator/export/log schemas, sandbox simulation, or approved captures |
| Automata LINQ | `docs/research/lab-scheduler-intake/automata_linq.md` plus `source_packs/apis/automata_linq/2026-06-22` | L2 pinned SDK route/model inspection plus public docs; no concrete sampled bodies | selected into dry-run world v0 with explicit synthetic dynamics | Sandbox validation/planning captures, concrete run/log examples, OpenAPI/MCP schemas, or recorded logs for high-fidelity promotion |

## What Is Sampled Well Today

The current hero world is `billing_support_v0`. Its source refs select Stripe,
Zendesk, and HubSpot records.

Strongest selected samples:

- Stripe `response_case:createRefund:success`
- Stripe `response_case:payInvoice:success`
- Stripe `response_case:createRefund:invalid_request_error`
- Zendesk `response_case:listTicketComments:success`
- Zendesk `response_case:listTicketAudits:success`
- Zendesk `response_case:updateTicket:comment_limit_reached`
- HubSpot `response_case:searchCrmObject:success`
- HubSpot `response_case:createContact:success`
- HubSpot `response_case:updateTicket:success`
- Freshdesk `response_case:viewTicket:success`
- Freshdesk `response_case:listTicketConversations:success`
- Freshdesk `response_case:updateTicket:success`
- Freshdesk `response_case:replyTicket:success`

Still weak:

- HubSpot `response_case:readContactTicketAssociations:success` is concrete for
  the official v3 batch-read association response envelope, but HubSpot
  publishes the body with Companies/Deals IDs while documenting
  Contacts/Tickets as the same endpoint pattern. Treat it as an association
  response-envelope sample, not a contact-ticket-specific fixture.
- Zendesk ticket show/update success cases are shape-grounded only.
- Most non-selected candidate packs have no concrete response bodies.
- Chargebee remains out of runtime-world gating because refund and
  collect-payment success cases are still shape-only.
- No checked-in source pack currently includes `raw/` captures or
  `probes.jsonl`.

## Next Sampling Work

Do this before creating new worlds:

1. Add contact-ticket-specific HubSpot association evidence if official docs,
   safe test-mode probes, or recorded observations become available.
2. Add concrete support-ticket samples for another support provider:
   Intercom or Help Scout.
3. Add concrete billing samples for Chargebee refund and collect-payment
   operations before considering Chargebee for runtime-world gating.
4. Keep shape-only cases, but treat them as schema grounding rather than
   sampled response fixtures.
5. Only build `appointment_service_ops_v0` after its first provider packs have
   the same coverage table and at least one concrete sample per critical
   mutation.

## Acceptance Gate For A Runtime World

A source pack can inform a runtime world when the selected operations have:

- at least one read/list operation
- at least one mutation or workflow transition operation
- a success response case for every selected operation
- at least one documented error, permission, conflict, or validation case
- concrete `body` or `body_excerpt` samples for critical mutations, or an
  explicit note that the world uses declared synthetic dynamics rather than
  sampled provider fixtures
- stable record ids cited from `worlds/<world_id>/source_refs.json`

This gate is intentionally stricter than structural validation. Structural
validation proves records are well-formed. The runtime-world gate proves the
selected records are good enough to justify dry-run behavior.
