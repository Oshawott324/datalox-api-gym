# Retrieval Live Drift - 2026-04-22

This note records grounded live drift found after the retrieval cleanup pass.

It is intentionally narrow: only behaviors reproduced through the built CLI and wrapper paths are recorded here.

## Drift

Unscoped task queries still admit weak cross-workflow candidates from `primary_term_overlap` alone.

This means retrieval is still broader than the contract in [retrieval-fix-plan.md](./retrieval-fix-plan.md), which says candidate admission should be structural and that repo hints should only break ties after admission.

## Reproducer

### CLI resolve

```bash
node dist/src/cli/main.js resolve \
  --repo . \
  --task "use async chunk parsing for long-lived agent runtime SSE in the Tauri host" \
  --json | jq '{selectionBasis, workflow, matchedSkillId: (.matches[0].skill.id // null), candidateSkills: [.matches[] | {skillId: .skill.id, workflow: .skill.workflow, whyMatched: .loopGuidance.whyMatched}]}'
```

### Wrapper prompt

```bash
node dist/src/cli/main.js wrap prompt \
  --repo . \
  --task "use async chunk parsing for long-lived agent runtime SSE in the Tauri host" \
  --prompt "Check candidate drift."
```

## Actual Behavior

The resolve path currently returns:

- `repo-engineering.maintain-datalox-agent-replay`
- `repo-engineering.use-datalox-through-host-cli`
- `web-capture.capture-web-knowledge`

The second and third candidates are admitted with only:

- `primary_term_overlap`

The wrapper output shows the same leakage in the visible candidate list.

## Expected Behavior

For this query:

- the system should either return no candidate, or at most a very small set of structurally plausible candidates
- `web-capture.capture-web-knowledge` should not appear from weak lexical overlap alone
- a candidate should not be admitted only because a few broad terms overlap in free text
- repo hints should not be enough to pull in `maintain-datalox-agent-replay` unless the query already cleared a stronger admission rule

## Recommended Next Fix

Tighten unscoped admission in `removed legacy pack script`:

1. Treat `primary_term_overlap` as supporting evidence, not a sufficient admission reason.
2. For queries without an explicit workflow, require at least one strong field phrase match in:
   - skill id
   - name
   - display name
   - trigger
   - description
3. Keep repo hints as tie-breakers only after a skill has already cleared that stronger admission rule.
4. Do not admit cross-workflow candidates on unscoped queries unless they have a strong field phrase match.

## Non-Drift Checks Run

These did not reproduce drift during the same live pass:

- no `candidateSkills[].score` leakage
- no `matchedSkillScore` leakage
- `repo_context` no longer auto-admits by repo hints alone
- PDF source routing still selects `source_kind_pdf`
