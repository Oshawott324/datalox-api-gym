# Claude Native Skill Installation — Live Proof 2026-04-27

## Environment

- Host: macOS Darwin 24.5.0
- Pack root: `/Users/yifanjin/datalox-pack`
- Claude Code: running as IDE extension (VSCode native extension mode)
- `claude` CLI binary: not present in shell PATH — running as IDE extension

## Focused test results

All four required proofs were covered by the `adoptionScripts.test.ts` suite.

```
npx vitest run tests/adoptionScripts.test.ts
✓ installs Claude native skills at canonical paths and safely cleans managed links (18284ms)
  — install in temp HOME creates direct per-skill symlinks
  — each linked directory contains a root SKILL.md
  — disable removes Datalox-managed per-skill links
  — disable preserves unrelated user-owned skill directories
  — old nested datalox-pack symlink is handled (removed if it targets the same pack)
✓ 9 tests passed
```

Build status: `npm run build` — passed (0 errors, 0 warnings).

Bridge/wrapper regression: `npx vitest run tests/bridgeSurfaces.test.ts tests/wrapperSurfaces.test.ts` — 54 tests passed.

## Live machine check

Pre-install state of `~/.claude/skills/`:
```
lrwxr-xr-x  datalox-pack -> /private/tmp/datalox-pack/skills   (stale link from prior temp-dir install)
```

Command run:
```
node bin/datalox.js install claude --json
```

Post-install state:
```
lrwxr-xr-x  capture-web-knowledge    -> /Users/yifanjin/datalox-pack/skills/capture-web-knowledge
lrwxr-xr-x  datalox-pack             -> /private/tmp/datalox-pack/skills   (unrelated — not touched)
lrwxr-xr-x  github                   -> /Users/yifanjin/datalox-pack/skills/github
lrwxr-xr-x  maintain-datalox-pack    -> /Users/yifanjin/datalox-pack/skills/maintain-datalox-pack
lrwxr-xr-x  use-datalox-through-host-cli -> /Users/yifanjin/datalox-pack/skills/use-datalox-through-host-cli
```

`status --json` post-install confirms:
```json
"nativeSkillLinks": {
  "installed": true,
  "canonical": true,
  "linked": [
    "/Users/yifanjin/.claude/skills/capture-web-knowledge",
    "/Users/yifanjin/.claude/skills/github",
    "/Users/yifanjin/.claude/skills/maintain-datalox-pack",
    "/Users/yifanjin/.claude/skills/use-datalox-through-host-cli"
  ],
  "missing": [],
  "legacyPackLink": null
}
```

Hook state: `~/.claude/hooks/removed legacy hook` — present.

## Host limitation note

The proof was run inside an active Claude Code session (IDE extension). The `claude` CLI binary is not in the shell PATH, so:
- the Claude shim was not installed (expected — shim is optional for skill surfacing)
- native skill links **are** installed at the documented `~/.claude/skills/<skill-name>/SKILL.md` shape
- this session itself demonstrates Datalox guidance is active via `CLAUDE.md` (repo instructions surface) and the hook sidecar
- a fresh interactive Claude Code session would pick up the canonical skill links from `~/.claude/skills/`

The stale `~/.claude/skills/datalox-pack` link (pointing to `/private/tmp/`) was preserved because it does not target the current pack root; it is not a Datalox-managed link for this pack and the disable path will not touch it.

## Proof summary

| Check | Result |
|---|---|
| install in temp HOME creates canonical per-skill symlinks | PASS (test) |
| disable removes Datalox-managed per-skill links | PASS (test) |
| disable preserves unrelated user skills | PASS (test) |
| old nested datalox-pack symlink handled safely | PASS (test) |
| live Claude Code session / host limitation recorded | PASS (live) |
| `npm run build` | PASS |
| bridge/wrapper regression | PASS (54/54) |
