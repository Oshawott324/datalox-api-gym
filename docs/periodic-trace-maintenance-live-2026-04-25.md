# Periodic Trace Maintenance Live Proof

This note records the grounded proof for the `Periodic Trace Maintenance And Skill Synthesis` loop.

## Repo

- Fresh adopted repo: `/tmp/datalox-maintain-proof-AWcSb6`

## Goal

Prove the maintenance loop works end to end with the intended boundary:

- first pass: `trace -> note`
- second pass: `note -> skill`
- wrapper-generated `unknown` traces may still compact into notes, but they do not create a new skill on their own

## Live Sequence

1. Create a fresh repo and adopt the pack.
2. Run a fresh cheap agent twice with real `codex exec`:
   - model: `gpt-5.4-mini`
   - prompt: `In one sentence, state the committed Datalox bootstrap read order for future agents in this repo.`
3. Let the enforced Codex wrapper record its own `unknown` trace events.
4. Explicitly record the same two agent outputs as `agent_adoption` trace events.
5. Run:
   - `node dist/src/cli/main.js maintain --repo /tmp/datalox-maintain-proof-AWcSb6 --max-events 50 --min-skill-occurrences 2 --json`
6. Run the same `maintain` command again.

## First Pass Result

- `scannedEvents: 4`
- `candidateCount: 2`
- candidates:
  - `agent_adoption`
  - `unknown`
- note actions:
  - `create_note` for `agent_adoption`
  - `create_note` for `unknown`
- coverage:
  - all 4 input trace events were explicitly marked with:
    - `coveredByNotePath`
    - `coveredAt`
    - `maintenanceStatus: "covered"`
- skill actions:
  - none

This passes the required first boundary:

- repeated traces compact into notes
- traces are explicitly marked covered
- no skill is created in the same maintenance pass that creates the note

## Second Pass Result

- `scannedEvents: 0`
- `skippedCoveredEvents: 4`
- skill actions:
  - `create_skill`
    - `notePath: removed-wiki-store/notes/agent-adoption-state-the-committed-datalox-bootstrap-read-order-for-future-agent.md`
    - `skillId: agent_adoption.read-the-committed-datalox-bootstrap-surfaces-before-acting`
    - `skillPath: skills/read-the-committed-datalox-bootstrap-surfaces-before-acting/SKILL.md`
    - `reason: note_backed_skill_synthesis`
  - `keep_note_only`
    - `notePath: removed-wiki-store/notes/unknown-in-one-sentence-state-the-committed-datalox-bootstrap-read-order-for-fut.md`
    - `reason: workflow_unknown_for_skill_synthesis`

This passes the required second boundary:

- a new skill is synthesized only from note-backed evidence
- the workflow-scoped note creates the skill
- the wrapper-generated `unknown` note stays note-only

## File Checks

Inspected note:

- `removed-wiki-store/notes/unknown-in-one-sentence-state-the-committed-datalox-bootstrap-read-order-for-fut.md`

Result:

- no `# Wrapped Prompt`
- no `# Datalox Loop Guidance`

Inspected skill:

- `skills/read-the-committed-datalox-bootstrap-surfaces-before-acting/SKILL.md`

Result:

- workflow is `agent_adoption`
- id is `agent_adoption.read-the-committed-datalox-bootstrap-surfaces-before-acting`
- no wrapper-protocol text leaked into the skill body or trigger

## Verification

- `npm run build`
- `npx vitest run tests/agentScripts.test.ts tests/bridgeSurfaces.test.ts tests/wrapperSurfaces.test.ts`
- result: `63/63` passing

## Conclusion

The maintenance loop now passes the intended model:

- recent traces in `removed-wiki-store/events/` are compacted periodically
- coverage is durable and explicit
- the first durable compaction boundary is `trace -> note`
- new skills are synthesized only from note-backed evidence
- workflow-scoped note-backed evidence can create a reusable skill
- low-quality or unscoped `unknown` note-backed evidence stays note-only
