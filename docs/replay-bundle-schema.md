# Replay Bundle Schema

This document is the canonical schema contract for Datalox replay bundles. If
other docs describe replay bundles differently, this document
wins for `replay_bundle.v1`.

## Purpose

A replay bundle is the portable replay artifact for Datalox Agent Replay.

It seals the agent turn summaries and exact tool I/O records needed to inspect,
audit, and replay an agent episode. Trajectory and eval rows are optional
derivatives from a replay bundle, not the canonical capture layer.

Canonical path:

```text
.datalox/replay-bundles/
```

Canonical pipeline:

```text
agent tool call -> tool_io_record.v1 -> replay_bundle.v1 -> deterministic replay -> optional derivatives
```

## Bundle Layout

```text
.datalox/replay-bundles/<bundle-id>/
  manifest.json
  tool-io/
    <record-id>.json
  mcp-tool-catalogs/
    <catalog-id>.json
  agent-turns/
    <turn-id>.json
  checksums.json
```

## Manifest Shape

```ts
type ReplayBundleV1 = {
  schema_version: "replay_bundle.v1";
  id: string;
  created_at: string;
  title?: string;
  task?: {
    prompt?: string;
    domains?: string[];
    workflows?: string[];
  };
  source: {
    repo_path?: string;
    session_ids: string[];
    turn_event_paths: string[];
    tool_io_record_paths: string[];
    mcp_tool_catalog_paths?: string[];
  };
  replay: {
    tool_record_count: number;
    turn_count: number;
    deterministic: boolean;
  };
  checksums_path: "checksums.json";
  export: {
    allowed: boolean;
    redaction: "none_needed" | "applied" | "blocked";
    approval_id?: string;
  };
  derivatives?: Array<{
    kind: "debugging_trajectory.v1" | "agent_task_trajectory.v1" | "eval_input.v1";
    path: string;
  }>;
};
```

## Runtime And Env Metadata

Runtime, environment, reward, validator, and database snapshot metadata are
future replay-bundle extensions. They are intentionally not fields in the
current strict `replay_bundle.v1` schema. Until code accepts those fields, store
that information in bundled tool I/O records, agent turns, or external
provenance artifacts referenced by approved derivatives.

## MCP Tool Catalog Metadata

When the MCP VCR proxy records through an upstream MCP server, it should persist
the agent-visible `tools/list` catalog as `mcp_tool_catalog.v1` under:

```text
.datalox/mcp-tool-catalogs/
```

Bundled catalog artifacts live under `mcp-tool-catalogs/*.json` and are listed
in `source.mcp_tool_catalog_paths`. They preserve upstream tool names,
descriptions, `inputSchema`, `outputSchema`, annotations, `_meta`, and other
MCP tool-list fields that are visible to the agent. Replay mode may use this
catalog to answer `tools/list` without starting the upstream server.

Existing bundles without `source.mcp_tool_catalog_paths` remain valid. Replay
implementations may expose a strict passthrough object schema for those legacy
bundles, but new proxy-recorded bundles should include the catalog.

## Checksum Rule

Every file in the bundle except `checksums.json` must have a SHA-256 checksum
entry.

Verification must fail when:

- a listed file is missing
- a listed file has a different checksum
- an unlisted file appears in the bundle
- `manifest.json` points outside the bundle directory
- a bundled `mcp_tool_catalog.v1` artifact is invalid

## Replay Rule

Replay uses bundled `tool_io_record.v1` records.

The replay lookup key is:

```text
request_hash + sequence_index
```

Replay mode must not start upstream tools, call live providers, or silently
fall back to live execution when a record is missing.

## Approval Rule

Unapproved replay bundles are private source artifacts. They are not export
artifacts.

An approved replay bundle can be exported when:

- all tool I/O records have explicit export status
- redaction status is explicit
- checksums verify
- the bundle contains enough turn context to understand the task episode
- approval or review state allows sharing

## Derivative Rule

Trajectory and eval rows are optional derivatives.

Derivative rows should reference the replay bundle id and must not become the
source of truth. If the bundle fails verification, derivative export is blocked
until the replay bundle is repaired or regenerated.
