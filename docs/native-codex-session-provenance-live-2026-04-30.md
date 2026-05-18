# Native Codex Session Provenance Live Proof

Date: 2026-04-30

## Problem

`datalox status --json` could report Codex as enforced because the shim was installed, while the active Codex chat was not actually running inside the `datalox codex` wrapper.

That made it too easy to confuse:

- installed/enforceable Codex adapter
- active session wrapper enforcement
- MCP-only guidance where the agent still chooses whether to call tools

## Implemented Boundary

Status now reports `currentSession` separately from installed adapters.

Current-session fields:

- `detectedHostKind`
- `activeWrapper`
- `wrapperEnforced`
- `enforcementLevel`
- `sessionId`
- `codexThreadId`
- `notes`

Wrappers now set child-process sentinels:

- `DATALOX_ACTIVE_WRAPPER`
- `DATALOX_HOST_KIND`
- `DATALOX_ENFORCEMENT=wrapper`

## Native Codex Status Check

Command:

```bash
node bin/datalox.js status --json
```

Observed current-session result:

```json
{
  "detectedHostKind": "codex",
  "activeWrapper": null,
  "wrapperEnforced": false,
  "enforcementLevel": "guidance_only",
  "notes": [
    "Native Codex session detected without a Datalox wrapper sentinel; MCP use depends on explicit tool calls."
  ]
}
```

## Wrapper Sentinel Status Check

Command:

```bash
DATALOX_ACTIVE_WRAPPER=codex \
DATALOX_HOST_KIND=codex \
DATALOX_ENFORCEMENT=wrapper \
DATALOX_SESSION_ID=proof-session \
node bin/datalox.js status --json
```

Observed current-session result:

```json
{
  "detectedHostKind": "codex",
  "activeWrapper": "codex",
  "wrapperEnforced": true,
  "enforcementLevel": "enforced",
  "sessionId": "proof-session",
  "notes": [
    "Current process is inside the Datalox codex wrapper."
  ]
}
```

## Focused Proofs

Passed:

- `npm run build`
- `npx vitest run tests/adoptionScripts.test.ts tests/wrapperSurfaces.test.ts -t "reports enforced host adapters as automatic in status output|Codex wrapper"`

These prove:

- installed Codex adapter remains reported as enforceable
- native Codex active session is guidance-only without sentinels
- wrapper-enforced sessions are visible through `currentSession`
- `datalox codex` child processes receive wrapper sentinels
