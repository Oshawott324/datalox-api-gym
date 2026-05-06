---
name: use-datalox-through-host-cli
description: Use when an agent host has no enforced Datalox wrapper path, or when MCP/native skill/hook surfaces are available but still model-chosen. Prefer `datalox codex` for Codex exec flows, `datalox claude` for Claude prompt runs, and `datalox wrap` for other CLI hosts.
metadata:
  datalox:
    id: repo-engineering.use-datalox-through-host-cli
    workflow: repo_engineering
    trigger: Use when the host agent cannot auto-call Datalox through MCP or hooks and needs a CLI wrapper path.
    note_paths:
      - agent-wiki/notes/use-datalox-through-host-cli.md
    tags:
      - repo_engineering
      - host_adapter
      - cli_wrapper
      - codex
    status: approved
    author: yifanjin
---

# Use Datalox Through Host CLI

Use this skill when the host agent cannot receive Datalox guidance through an enforced pre-run wrapper, but still needs loop guidance on every run.

## When to Use

- The host has no MCP support
- The host has no automatic pre-turn or post-turn hook API
- The host has MCP tools, but the active session is not inside an enforced Datalox wrapper
- Claude Code has native skills, MCP, or Stop-hook automation, but no active Claude wrapper sentinel
- The agent is launched from a CLI and accepts a prompt argument or environment variables
- You need a deterministic fallback that still injects Datalox guidance

## When Not to Use

- The active session is already inside an enforced Datalox wrapper such as `datalox codex` or `datalox claude`
- The task only needs post-turn recording and the host hook already calls `bin/datalox-auto-promote.js`
- The task is not agent-loop work and does not need pack guidance

## Workflow

1. If MCP tools are available in the active session, call `resolve_loop` before acting.
2. For buyer-facing trajectory dataset capture after coding/debugging work, build a `debugging_trajectory.v1` row and call MCP tool `record_trajectory` when it is available.
3. If MCP is not available, write the row JSON and run `datalox record-trajectory --repo <repo> --trajectory-row <row.json> --json`.
4. In every trajectory row, `context.relevant_files[].before` and `after` must be exact minimal code snippets from the changed source, not prose, pointers, or "see file" summaries. Put explanation in `context.notes`, `trajectory.content`, or `final.explanation`.
5. If `record_trajectory` or `record-trajectory` returns `qualityDowngraded: true`, repair the row before treating it as `curation.quality: "use"` or exporting it as training-grade data.
6. Use `record_turn_result` or `datalox record` only for legacy/internal guidance maintenance when no explicit trajectory row/session event is being captured.
7. Treat native Codex chat with MCP as guidance-only unless a Datalox wrapper sentinel is present.
8. Treat Claude Code native skills and MCP as model-chosen guidance unless `currentSession.activeWrapper` is `"claude"` and `currentSession.wrapperEnforced` is `true`.
9. Treat the Claude Stop hook as post-turn sidecar automation only; it can record, compile, and maintain after Claude responds, but it cannot force pre-turn `resolve_loop`.
10. For enforceable Codex `exec`, use `datalox codex --repo <repo> --task "<task>" --prompt "<prompt>"`.
11. For enforceable Claude prompt runs, use `datalox claude --repo <repo> --task "<task>" --prompt "<prompt>" -- --print "<prompt>"` or the installed Claude shim when status proves it is automatic.
12. For other CLI hosts, use `datalox wrap command --repo <repo> --task "<task>" --prompt "<prompt>" -- <host-command> __DATALOX_PROMPT__`.
13. If the host cannot accept prompt placeholders, use `datalox wrap prompt` and pass the returned prompt to the host manually.
14. When the host has no automatic post-turn hook or wrapper and the work is only repeated internal guidance maintenance, use `datalox record` or `datalox promote` explicitly after repeated corrections.

## Checks Before Editing

- Keep the wrapper thin. It should resolve guidance and pass it into the host, not reimplement pack logic.
- Preserve the host repo as the write target for generated skills and wiki pages.
- Prefer placeholders and environment variables over shell-specific quoting tricks.
- Keep Codex-specific behavior inside the Codex wrapper and everything else in the generic wrapper.
- Do not describe MCP availability as enforcement. MCP-only sessions still depend on the agent choosing to call the tools.
- Do not describe Claude Stop-hook or native-skill availability as pre-run enforcement.
- Keep Datalox additive to Claude native skills; do not shadow or replace Claude's own skill behavior.
- Do not use `record_turn_result` or `datalox record` for product trajectory data. Use `record_trajectory` or `datalox record-trajectory`.
- Do not let trajectory rows rely on repository paths alone. Inline exact before/after code snippets so the exported row stands alone.

## Expected Output

- State which surface is being used: MCP, hook, native skill, `datalox codex`, `datalox claude`, or `datalox wrap`.
- State how the wrapped prompt is injected into the host.
- State whether the active session is wrapper-enforced or guidance-only.
- State whether trajectory capture used MCP `record_trajectory`, CLI `record-trajectory`, or legacy internal `record` / `promote`.
- State whether the trajectory quality gate downgraded the row and what must be repaired before export.

## Notes

- agent-wiki/notes/use-datalox-through-host-cli.md
