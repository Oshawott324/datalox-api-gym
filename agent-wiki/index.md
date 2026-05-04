# Agent Wiki Index

- Project: Datalox Flow Cytometry Demo
- Generated: 2026-05-04T02:01:57.388Z
- Skills: 4
- Wiki pages: 10

## Skills

### Review Ambiguous Viability Gate

- Id: flow-cytometry.review-ambiguous-viability-gate
- Workflow: flow_cytometry
- Trigger: Use when live/dead separation is ambiguous during viability gate review.
- Status: approved
- Maturity: stable
- Source: host
- Notes:
  - agent-wiki/notes/dead-tail-exception.md
  - agent-wiki/notes/qc-escalation-policy.md
  - agent-wiki/notes/viability-gate-review.md

### Maintain Datalox Pack

- Id: repo-engineering.maintain-datalox-pack
- Workflow: repo_engineering
- Trigger: Use when changing the Datalox pack or agent guidance in this repo.
- Status: approved
- Maturity: stable
- Source: host
- Updated: 2026-04-12T10:31:16.869Z
- Author: yifanjin
- Notes:
  - agent-wiki/notes/maintain-datalox-pack.md
  - agent-wiki/notes/repo-engineering-multi-agent-bootstrap-surfaces.md

### Use Datalox Through Host CLI

- Id: repo-engineering.use-datalox-through-host-cli
- Workflow: repo_engineering
- Trigger: Use when the host agent cannot auto-call Datalox through MCP or hooks and needs a CLI wrapper path.
- Status: approved
- Maturity: stable
- Source: host
- Author: yifanjin
- Notes:
  - agent-wiki/notes/use-datalox-through-host-cli.md

### Capture Web Knowledge

- Id: web-capture.capture-web-knowledge
- Workflow: web_capture
- Trigger: Use when analyzing a website's layout, tokens, and components into reusable repo knowledge.
- Status: approved
- Maturity: stable
- Source: host
- Updated: 2026-04-13T00:00:00.000Z
- Author: yifanjin
- Notes:
  - agent-wiki/notes/capture-web-knowledge.md

## Wiki Pages

### Note Pages

#### A diffusion-based framework for designing molecules in flexible protein pockets

- Path: agent-wiki/notes/pdf/diffusion-framework-designing-molecules-flexible-protein-pockets.md
- Type: note
- Source: host
- Workflow: pdf_capture
- Status: active
- Updated: 2026-04-18T12:46:33.792Z
- Linked Skills: none
- Action: Read agent-wiki/notes/pdf/diffusion-framework-designing-molecules-flexible-protein-pockets.md for the overview, then inspect agent-wiki/not…
- Related:
  - Add follow-up notes or skills here when the PDF changes runtime behavior.
- Sources:
  - https://pmc.ncbi.nlm.nih.gov/articles/PMC13060587/
- Summary: The reusable value is concentrated in normalized page evidence grouped by sections such as Methods, with agent-side extraction deciding whi…

#### Nucleotide-resolution mapping of regulatory elements via allelic readout of tiled base editing

- Path: agent-wiki/notes/pdf/nucleotide-resolution-regulatory-elements-tiled-base-editing.md
- Type: note
- Source: host
- Workflow: pdf_capture
- Status: active
- Updated: 2026-04-18T12:46:33.791Z
- Linked Skills: none
- Action: Read agent-wiki/notes/pdf/nucleotide-resolution-regulatory-elements-tiled-base-editing.md for the overview, then inspect agent-wiki/notes/p…
- Related:
  - Add follow-up notes or skills here when the PDF changes runtime behavior.
- Sources:
  - https://pmc.ncbi.nlm.nih.gov/articles/PMC13065808/
- Summary: The reusable value is concentrated in normalized page evidence grouped by sections such as Abstract, with agent-side extraction deciding wh…

#### IL-7/IL-15/IL-21 cytokine-fusion scaffold generates highly functional CAR T cells enriched in long-lived T memory stem cells

- Path: agent-wiki/notes/pdf/il7-il15-il21-cytokine-fusion-scaffold-car-t-memory-stem-cells.md
- Type: note
- Source: host
- Workflow: pdf_capture
- Status: active
- Updated: 2026-04-18T12:46:22.634Z
- Linked Skills: none
- Action: Read agent-wiki/notes/pdf/il7-il15-il21-cytokine-fusion-scaffold-car-t-memory-stem-cells.md for the overview, then inspect agent-wiki/notes…
- Related:
  - Add follow-up notes or skills here when the PDF changes runtime behavior.
- Sources:
  - https://pmc.ncbi.nlm.nih.gov/articles/PMC12985740/
- Summary: The reusable value is concentrated in normalized page evidence grouped by sections such as Abstract, with agent-side extraction deciding wh…

#### Capture web knowledge

- Path: agent-wiki/notes/capture-web-knowledge.md
- Type: note
- Source: host
- Workflow: web_capture
- Status: active
- Updated: 2026-04-14T00:00:00.000Z
- Linked Skills:
  - web-capture.capture-web-knowledge
- Action: - Use `design-doc` for an agent-facing brief. - Use `design-tokens` for normalized JSON tokens. - Use `css-variables` for a reusable `.vars…
- Related:
  - skills/capture-web-knowledge/SKILL.md
- Summary: Web capture should write one reusable note first, then emit only the artifact the downstream task actually needs.

#### Use Datalox Through Host CLI

- Path: agent-wiki/notes/use-datalox-through-host-cli.md
- Type: note
- Source: host
- Workflow: repo_engineering
- Status: active
- Updated: 2026-04-13T09:00:00.000Z
- Review After: 2026-07-13
- Linked Skills:
  - repo-engineering.use-datalox-through-host-cli
- Action: If MCP is available in the active session, call `resolve_loop` before acting and `record_turn_result` after meaningful grounded outcomes. P…
- Related:
  - agent-wiki/notes/maintain-datalox-pack.md
- Sources:
  - agent-wiki/sources/portable-pack-design-notes.md
- Summary: If MCP is available in the active session, call `resolve_loop` before acting and `record_turn_result` after meaningful grounded outcomes. P…

#### Dead tail exception

- Path: agent-wiki/notes/dead-tail-exception.md
- Type: note
- Source: host
- Workflow: flow_cytometry
- Status: active
- Updated: 2026-04-12T15:10:00.000Z
- Review After: 2026-07-12
- Author: yifanjin
- Linked Skills:
  - flow-cytometry.review-ambiguous-viability-gate
- Action: Review the exception path first and avoid widening the gate until the artifact explanation is checked.
- Related:
  - agent-wiki/comparisons/manual-threshold-shift-vs-exception-review.md
  - agent-wiki/concepts/ambiguous-viability-gate-review.md
  - agent-wiki/notes/viability-gate-review.md
- Sources:
  - agent-wiki/sources/flow-cytometry-demo-notes.md
- Summary: Review the exception path first and avoid widening the gate until the artifact explanation is checked.

#### Maintain Datalox Pack

- Path: agent-wiki/notes/maintain-datalox-pack.md
- Type: note
- Source: host
- Workflow: repo_engineering
- Status: active
- Updated: 2026-04-12T15:10:00.000Z
- Review After: 2026-07-12
- Author: yifanjin
- Linked Skills:
  - repo-engineering.maintain-datalox-pack
- Action: Keep the loop as: detect skill each turn, read linked notes, and write generated skills back into `skills/`.
- Related:
  - agent-wiki/concepts/loop-bridge.md
  - agent-wiki/notes/repo-engineering-multi-agent-bootstrap-surfaces.md
  - agent-wiki/questions/when-should-a-new-skill-be-created.md
- Sources:
  - agent-wiki/sources/portable-pack-design-notes.md
- Summary: Keep the loop as: detect skill each turn, read linked notes, and write generated skills back into `skills/`.

#### QC escalation policy

- Path: agent-wiki/notes/qc-escalation-policy.md
- Type: note
- Source: host
- Workflow: flow_cytometry
- Status: active
- Updated: 2026-04-12T15:10:00.000Z
- Review After: 2026-07-12
- Author: yifanjin
- Linked Skills:
  - flow-cytometry.review-ambiguous-viability-gate
- Action: Escalate before applying the change.
- Related:
  - agent-wiki/concepts/ambiguous-viability-gate-review.md
  - agent-wiki/notes/viability-gate-review.md
  - agent-wiki/questions/when-should-qc-escalate-after-viability-review.md
- Sources:
  - agent-wiki/sources/flow-cytometry-demo-notes.md
- Summary: Escalate before applying the change.

#### Review ambiguous viability gate

- Path: agent-wiki/notes/viability-gate-review.md
- Type: note
- Source: host
- Workflow: flow_cytometry
- Status: active
- Updated: 2026-04-12T15:10:00.000Z
- Review After: 2026-07-12
- Author: yifanjin
- Linked Skills:
  - flow-cytometry.review-ambiguous-viability-gate
- Action: Check the exception and escalation pattern docs before widening the gate, then explain the proposed gate decision in terms of the observed…
- Related:
  - agent-wiki/concepts/ambiguous-viability-gate-review.md
  - agent-wiki/notes/dead-tail-exception.md
  - agent-wiki/notes/qc-escalation-policy.md
  - agent-wiki/questions/when-should-qc-escalate-after-viability-review.md
- Sources:
  - agent-wiki/sources/flow-cytometry-demo-notes.md
- Summary: Check the exception and escalation pattern docs before widening the gate, then explain the proposed gate decision in terms of the observed…

#### Multi-agent bootstrap surfaces

- Path: agent-wiki/notes/repo-engineering-multi-agent-bootstrap-surfaces.md
- Type: note
- Source: host
- Workflow: repo_engineering
- Status: active
- Updated: 2026-04-12T10:31:16.852Z
- Review After: 2026-07-12
- Author: yifanjin
- Linked Skills:
  - repo-engineering.maintain-datalox-pack
- Action: Add WIKI, GEMINI, Copilot, Cursor, Windsurf, and GitHub bootstrap surfaces and keep them aligned with DATALOX.md.
- Related:
  - agent-wiki/comparisons/repo-protocol-vs-loop-bridge.md
  - agent-wiki/concepts/loop-bridge.md
  - agent-wiki/notes/maintain-datalox-pack.md
- Sources:
  - agent-wiki/sources/portable-pack-design-notes.md
- Summary: Add WIKI, GEMINI, Copilot, Cursor, Windsurf, and GitHub bootstrap surfaces and keep them aligned with DATALOX.md.
