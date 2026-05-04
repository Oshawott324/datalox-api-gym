---
type: note
title: Use Datalox Through Host CLI
workflow: repo_engineering
status: active
related:
  - agent-wiki/notes/maintain-datalox-pack.md
sources:
  - agent-wiki/sources/portable-pack-design-notes.md
usage:
  read_count: 16
  last_read_at: 2026-05-03T14:41:40.680Z
  apply_count: 0
  last_applied_at: 
  evidence_count: 0
updated: 2026-04-13T09:00:00.000Z
review_after: 2026-07-13
---
# Use Datalox Through Host CLI

## When to Use

Use this page when an agent host cannot prove an enforced Datalox pre-run wrapper path, even if it has MCP, native skill, or hook surfaces.

## Signal

The host can run a CLI command or expose MCP tools, native skills, or post-turn hooks, but the active session cannot prove it will receive Datalox guidance before the model acts.

## Interpretation

MCP availability is not enforcement. The enforceable path should stay a thin wrapper that injects resolved loop guidance into the host command. Claude Code also has separate surfaces: the Claude shim wrapper can enforce pre-run guidance injection, the Stop hook is post-turn sidecar automation, native skills are model-chosen and restart-sensitive, and MCP is guidance-only unless Claude calls the tools.

## Recommended Action

If MCP is available in the active session, call `resolve_loop` before acting and `record_turn_result` after meaningful grounded outcomes. Prefer `datalox codex` for enforceable Codex `exec` flows and `datalox claude` for enforceable Claude prompt runs. Otherwise use `datalox wrap command` with `__DATALOX_PROMPT__` or the `DATALOX_PROMPT` environment variable.

## Examples

- A Codex thread that has the MCP server installed but is not automatically calling it
- A native Codex chat with MCP tools but no `DATALOX_ACTIVE_WRAPPER=codex` sentinel
- A Claude Code session with Stop-hook and native skill links installed but no `DATALOX_ACTIVE_WRAPPER=claude` sentinel
- A generic CLI agent that accepts a prompt argument but exposes no hook surface

## Evidence

- agent-wiki/sources/portable-pack-design-notes.md

## Related

- agent-wiki/notes/maintain-datalox-pack.md
