# Bootstrap Payload Shape - Live Validation - 2026-04-23

This note records the grounded result of tightening the default bootstrap payload
for fresh repos.

## Problem

Fresh repos were receiving the whole seed corpus through:

- `adoptPack()`
- `autoBootstrapIfSafe()`

That meant unrelated knowledge landed in generic repos by default, including:

- `skills/github`
- `skills/ordercli`
- `skills/review-ambiguous-viability-gate`
- `skills/capture-web-knowledge`
- `removed-wiki-store/notes/pdf/*`
- `removed-wiki-store/notes/web/*`

The problem was not MCP itself. The problem was bootstrap/adoption payload shape.

## Change

In [src/core/packCore.ts](/Users/yifanjin/datalox-agent-replay/src/core/packCore.ts):

- removed whole-tree default adoption of:
  - `skills/`
  - `removed-wiki-store/notes/`
- replaced it with a small core bootstrap bundle:
- `skills/maintain-datalox-agent-replay`
- `skills/use-datalox-through-host-cli`
- `removed-wiki-store/notes/maintain-datalox-agent-replay.md`
- `removed-wiki-store/notes/use-datalox-through-host-cli.md`
  - `removed-wiki-store/notes/repo-engineering-multi-agent-bootstrap-surfaces.md`

This keeps:

- core runtime/instruction surfaces
- core repo-engineering pack knowledge

And drops unrelated example/domain seed knowledge from fresh repos by default.

## Test Compatibility

Some wrapper tests were previously relying on the flow-cytometry skill being copied
into every adopted repo.

That was changed in:

- [tests/wrapperSurfaces.test.ts](/Users/yifanjin/datalox-agent-replay/tests/wrapperSurfaces.test.ts)

The flow-cytometry fixture is now created locally inside the test instead of being
part of the product bootstrap bundle.

## Focused Verification

Used:

- `npm run build`
- `npx vitest run tests/adoptionScripts.test.ts`
- `npx vitest run tests/bridgeSurfaces.test.ts tests/wrapperSurfaces.test.ts`

Results:

- `tests/adoptionScripts.test.ts`: `6/6`
- `tests/bridgeSurfaces.test.ts`: `22/22`
- `tests/wrapperSurfaces.test.ts`: `26/26`

## Live Proof 1: Fresh Explicit Adopt

Fresh repo:

- `/tmp/datalox-bootstrap-live-adopt-wDwBok`

Observed adopted skills:

- `skills/maintain-datalox-agent-replay/SKILL.md`
- `skills/use-datalox-through-host-cli/SKILL.md`

Observed adopted notes:

- `removed-wiki-store/notes/maintain-datalox-agent-replay.md`
- `removed-wiki-store/notes/use-datalox-through-host-cli.md`
- `removed-wiki-store/notes/repo-engineering-multi-agent-bootstrap-surfaces.md`

Not present:

- `skills/github`
- `skills/ordercli`
- `skills/review-ambiguous-viability-gate`
- `skills/capture-web-knowledge`
- `removed-wiki-store/notes/pdf/`
- `removed-wiki-store/notes/web/`

## Live Proof 2: Fresh Auto-Bootstrap + Real Codex Loop

Fresh repo:

- `/tmp/datalox-bootstrap-live-loop-AOWrkK`

Used real `datalox codex` with `gpt-5.4-mini`.

Run 1:

- action: `create_note_from_gap`
- decision: `create_operational_note`
- note:
  - `removed-wiki-store/notes/agent-adoption-stabilize-manual-pack-adoption-in-non-technical-repos.md`

Run 2:

- action: `create_skill_from_gap`
- decision: `create_new_skill`
- same note reused
- skill created:
  - `skills/stabilize-manual-pack-adoption-in-non-technical-repos/SKILL.md`

Final repo skills:

- `maintain-datalox-agent-replay`
- `use-datalox-through-host-cli`
- `stabilize-manual-pack-adoption-in-non-technical-repos`

Final repo notes:

- `agent-adoption-stabilize-manual-pack-adoption-in-non-technical-repos.md`
- `maintain-datalox-agent-replay.md`
- `use-datalox-through-host-cli.md`
- `repo-engineering-multi-agent-bootstrap-surfaces.md`

No unrelated seed skills or note corpora were present.

## Pass Criteria Result

Passed:

1. fresh `adopt` repos no longer get unrelated skills like `github`, `ordercli`, or `review-ambiguous-viability-gate`
2. fresh `auto-bootstrap` repos no longer get unrelated `pdf/` and `web/` note corpora by default
3. enforced wrapper behavior still works
4. first-note bootstrap still works
5. the live skill-generation proof still passes on a fresh repo

## Remaining Open Item

Still open:

- whether optional example/domain bundles should get an explicit separate install path

That is now a product choice, not a blocker for the default bootstrap payload.
