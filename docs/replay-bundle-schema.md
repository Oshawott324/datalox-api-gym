# Replay Bundle Schema

This document is the canonical schema contract for approved Datalox replay
bundles. If other docs describe the source product differently, this document
wins for `replay_bundle.v1`.

## Purpose

A replay bundle is the source product artifact for Datalox Agent Replay.

It seals the agent turn summaries and exact tool I/O records needed to inspect,
audit, and replay an agent episode. Trajectory and eval rows are optional
derivatives from a replay bundle, not the canonical capture product.

Canonical path:

```text
.datalox/replay-bundles/
```

Canonical pipeline:

```text
agent run -> tool I/O records -> replay bundle -> approval/export -> optional derivatives
```

## Bundle Layout

```text
.datalox/replay-bundles/<bundle-id>/
  manifest.json
  tool-io/
    <record-id>.json
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
  };
  replay: {
    tool_record_count: number;
    turn_count: number;
    deterministic: boolean;
  };
  runtime?: {
    model_version?: string;
    sampling?: {
      temperature?: number;
      top_p?: number;
      seed?: number;
    };
    system_prompt_hash?: string;
  };
  env?: {
    tool_versions?: Record<string, string>;
    corpus_snapshot_hash?: string;
    snapshot_at?: string;
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

## Runtime And Env Rule

`runtime` and `env` are optional reproducibility metadata. When present, they
let a downstream consumer recompute rewards or compare model behavior against
the same recorded environment three months later without guessing.

- `runtime.model_version` should pin the model used during recording so a
  replay against a new model is an explicit comparison, not a silent drift.
- `runtime.sampling` should include any sampling parameters needed to
  reproduce decoded outputs at the agent layer when the agent is not
  deterministic.
- `runtime.system_prompt_hash` should reference the system prompt by
  content hash, not store it inline, so prompt changes are detectable
  without leaking prompt text into every bundle.
- `env.tool_versions` should pin the versions of agent-visible tools used
  during recording. Replay does not require live tools, but mismatched tool
  versions across recordings invalidate cross-bundle reward comparisons.
- `env.corpus_snapshot_hash` should reference any indexed or retrievable
  corpus the agent read against. Drift in the underlying corpus is the
  single most common reason rewards stop reproducing.
- `env.snapshot_at` is the wall-clock snapshot timestamp for the corpus or
  external state.

Missing `runtime` or `env` does not block bundle verification. Their absence
means the bundle is replayable but not pinned for cross-time reward
comparison.

## Checksum Rule

Every file in the bundle except `checksums.json` must have a SHA-256 checksum
entry.

Verification must fail when:

- a listed file is missing
- a listed file has a different checksum
- an unlisted file appears in the bundle
- `manifest.json` points outside the bundle directory

## Replay Rule

Replay uses bundled `tool_io_record.v1` records.

The replay lookup key is:

```text
request_hash + sequence_index
```

Replay mode must not start upstream tools, call live providers, or silently
fall back to live execution when a record is missing.

## Approval Rule

Unapproved replay bundles are private source artifacts. They are not sellable
data.

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
