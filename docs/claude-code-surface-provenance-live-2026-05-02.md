# Claude Code Surface Provenance Live Proof

Date: 2026-05-02

## Problem

Claude Code can expose Datalox through four different surfaces:

- Claude shim wrapper
- Claude Stop hook
- Claude native skills
- Claude MCP tools

Those surfaces are not equivalent. Status must let an agent answer what is enforceable before the model acts, without inferring behavior from raw `installed`, `hookInstalled`, and `nativeSkillLinks` fields.

## Implemented Boundary

`datalox status --json` now keeps the existing raw `adapters.claude` fields and adds:

```text
adapters.claude.surfaces.wrapper
adapters.claude.surfaces.stopHook
adapters.claude.surfaces.nativeSkills
adapters.claude.surfaces.mcp
```

The active Claude wrapper is counted as pre-run enforced only when:

```text
currentSession.activeWrapper == "claude"
currentSession.wrapperEnforced == true
```

The Stop hook is always reported as post-turn sidecar automation, not pre-run enforcement.

## Native Status Check

Command:

```bash
node bin/datalox.js status --repo . --json
```

Observed Claude surface excerpt:

```json
{
  "installed": false,
  "automatic": false,
  "hookInstalled": true,
  "nativeSkillLinks": {
    "installed": true,
    "canonical": true
  },
  "surfaces": {
    "wrapper": {
      "installed": false,
      "automatic": false,
      "active": false,
      "preRunEnforced": false,
      "enforcementLevel": "guidance_only"
    },
    "stopHook": {
      "installed": true,
      "postTurnSidecar": true,
      "recordsAfterTurn": true,
      "preRunEnforced": false
    },
    "nativeSkills": {
      "installed": true,
      "canonical": true,
      "restartSensitive": true,
      "modelChosen": true,
      "preRunEnforced": false
    },
    "mcp": {
      "available": true,
      "guidanceOnly": true,
      "modelChosen": true,
      "preRunEnforced": false
    }
  }
}
```

## Wrapper Sentinel Check

Command:

```bash
DATALOX_ACTIVE_WRAPPER=claude \
DATALOX_HOST_KIND=claude \
DATALOX_ENFORCEMENT=wrapper \
DATALOX_SESSION_ID=proof-claude-session \
node bin/datalox.js status --repo . --json
```

Observed current-session excerpt:

```json
{
  "detectedHostKind": "claude",
  "activeWrapper": "claude",
  "wrapperEnforced": true,
  "enforcementLevel": "enforced",
  "sessionId": "proof-claude-session",
  "notes": [
    "Current process is inside the Datalox claude wrapper."
  ]
}
```

Observed Claude wrapper surface excerpt:

```json
{
  "active": true,
  "preRunEnforced": true,
  "enforcementLevel": "enforced"
}
```

The same status keeps:

```json
{
  "stopHook": {
    "preRunEnforced": false,
    "postTurnSidecar": true
  }
}
```

## Focused Proofs

Passed:

```bash
npm run build
npx vitest run tests/adoptionScripts.test.ts tests/wrapperSurfaces.test.ts tests/hookIntegration.test.ts
```

These prove:

- status reports Claude wrapper, hook, native skill, and MCP surfaces separately
- hook/native-skill availability does not imply pre-run wrapper enforcement
- `DATALOX_ACTIVE_WRAPPER=claude` with `DATALOX_ENFORCEMENT=wrapper` reports wrapper-enforced Claude
- `datalox claude` child processes receive wrapper sentinels
- Claude hook maintenance still runs without pretending to be pre-run enforcement
