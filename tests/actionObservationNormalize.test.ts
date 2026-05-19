import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import {
  actionObservationFromRawTrace,
  actionObservationFromToolIoRecord,
  RawActionObservationTraceValidationError,
} from "../src/core/actionObservationNormalize.js";
import {
  ActionObservationValidationError,
  parseActionObservationV1,
} from "../src/core/actionObservationSchema.js";
import { buildToolIoRequestHash } from "../src/core/toolIoSchema.js";
import { recordToolIo } from "../src/core/toolIoStore.js";

describe("action_observation.v1 normalization", () => {
  const tempDirs: string[] = [];

  afterEach(async () => {
    await Promise.all(tempDirs.splice(0).map((dir) => rm(dir, { recursive: true, force: true })));
  });

  async function makeTempRepo(): Promise<string> {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-action-observation-"));
    tempDirs.push(tempDir);
    return tempDir;
  }

  it("strictly rejects unknown top-level fields", () => {
    expect(() => parseActionObservationV1({
      schema_version: "action_observation.v1",
      action: {
        type: "tool_call",
        name: "search_policy",
        arguments: { query: "policy" },
        request_hash: buildToolIoRequestHash("search_policy", { query: "policy" }),
        sequence_index: 0,
      },
      observation: {
        status: "ok",
        content: ["policy"],
      },
      provenance: {
        source_kind: "raw_trace",
        call_id: "call-1",
      },
      reward: 1,
    })).toThrow(ActionObservationValidationError);
  });

  it("normalizes tool_io_record.v1 into a stable action/observation view", async () => {
    const repoPath = await makeTempRepo();
    const recorded = await recordToolIo({
      repoPath,
      sessionId: "session-1",
      turnId: "turn-1",
      callId: "call-1",
      toolName: "exec_command",
      arguments: { command: "npm test", cwd: "/repo" },
      observation: { status: "ok", content: { stdout: "passed", exit_code: 0 } },
      source: { host: "codex", command: "npm test" },
      now: new Date("2026-05-18T00:00:00.000Z"),
    });

    const normalized = actionObservationFromToolIoRecord(recorded.record, {
      sourcePath: recorded.recordPath,
    });

    expect(normalized).toEqual({
      schema_version: "action_observation.v1",
      action: {
        type: "tool_call",
        name: "exec_command",
        arguments: { command: "npm test", cwd: "/repo" },
        request_hash: recorded.record.request_hash,
        sequence_index: 0,
      },
      observation: { status: "ok", content: { stdout: "passed", exit_code: 0 } },
      provenance: {
        source_kind: "wrapper",
        source_path: recorded.recordPath,
        host: "codex",
        session_id: "session-1",
        turn_id: "turn-1",
        call_id: "call-1",
      },
    });
  });

  it("normalizes MCP tool I/O records as MCP source actions", async () => {
    const repoPath = await makeTempRepo();
    const recorded = await recordToolIo({
      repoPath,
      callId: "mcp-call-1",
      toolName: "policy_search",
      arguments: { query: "travel reimbursement" },
      observation: { status: "ok", content: { result: ["policy-a"] } },
      source: { mcp_server: "policy-mcp", command: "node policy-server.js" },
      now: new Date("2026-05-18T00:00:00.000Z"),
    });

    const normalized = actionObservationFromToolIoRecord(recorded.record);

    expect(normalized.provenance.source_kind).toBe("mcp");
    expect(normalized.provenance.host).toBeUndefined();
    expect(normalized.action.name).toBe("policy_search");
    expect(normalized.action.arguments).toEqual({ query: "travel reimbursement" });
    expect(normalized.observation).toEqual({ status: "ok", content: { result: ["policy-a"] } });
  });

  it("normalizes raw traces with the same request hash as recordToolIo", async () => {
    const repoPath = await makeTempRepo();
    const args = {
      top_k: 5,
      filters: { active: true, region: "CN" },
      query: "Beijing reimbursement policy",
    };
    const recorded = await recordToolIo({
      repoPath,
      callId: "recorded-call",
      toolName: "search_policy",
      arguments: {
        query: "Beijing reimbursement policy",
        filters: { region: "CN", active: true },
        top_k: 5,
      },
      observation: { status: "ok", content: ["policy"] },
    });

    const normalized = actionObservationFromRawTrace({
      source_kind: "raw_trace",
      host: "custom-agent",
      session_id: "session-raw",
      turn_id: "turn-raw",
      call_id: "raw-call",
      tool_name: "search_policy",
      tool_version: "2026-05-18",
      arguments: args,
      argument_schema_ref: "schema://search_policy/input/v1",
      observation: { status: "ok", content: ["policy"] },
      observation_schema_ref: "schema://search_policy/output/v1",
    });

    expect(normalized.action.request_hash).toBe(recorded.record.request_hash);
    expect(normalized.action.sequence_index).toBe(0);
    expect(normalized.action.version).toBe("2026-05-18");
    expect(normalized.action.argument_schema_ref).toBe("schema://search_policy/input/v1");
    expect(normalized.observation.observation_schema_ref).toBe("schema://search_policy/output/v1");
    expect(normalized.provenance).toEqual({
      source_kind: "raw_trace",
      host: "custom-agent",
      session_id: "session-raw",
      turn_id: "turn-raw",
      call_id: "raw-call",
    });
  });

  it("preserves repeated identical action replay order through sequence indexes", async () => {
    const repoPath = await makeTempRepo();
    const first = await recordToolIo({
      repoPath,
      callId: "first",
      toolName: "search_policy",
      arguments: { query: "policy", top_k: 3 },
      observation: { status: "ok", content: ["a"] },
    });
    const second = await recordToolIo({
      repoPath,
      callId: "second",
      toolName: "search_policy",
      arguments: { top_k: 3, query: "policy" },
      observation: { status: "ok", content: ["b"] },
    });

    const firstNormalized = actionObservationFromToolIoRecord(first.record);
    const secondNormalized = actionObservationFromToolIoRecord(second.record);

    expect(firstNormalized.action.request_hash).toBe(secondNormalized.action.request_hash);
    expect(firstNormalized.action.sequence_index).toBe(0);
    expect(secondNormalized.action.sequence_index).toBe(1);
  });

  it("fails invalid raw traces deterministically with a clear error path", () => {
    expect(() => actionObservationFromRawTrace({
      source_kind: "raw_trace",
      call_id: "call-1",
      tool_name: "search_policy",
      arguments: { query: "policy" },
      observation: { status: "missing" },
    })).toThrow(RawActionObservationTraceValidationError);

    try {
      actionObservationFromRawTrace({
        source_kind: "raw_trace",
        call_id: "call-1",
        tool_name: "search_policy",
        arguments: { query: "policy" },
        observation: { status: "missing" },
      });
    } catch (error) {
      expect(error).toBeInstanceOf(RawActionObservationTraceValidationError);
      expect(String(error)).toContain("observation.status");
      return;
    }
    throw new Error("expected invalid raw trace to throw");
  });

  it("rejects missing raw trace arguments before canonicalization", () => {
    expect(() => actionObservationFromRawTrace({
      source_kind: "raw_trace",
      call_id: "call-missing-args",
      tool_name: "search_policy",
      observation: { status: "ok", content: ["policy"] },
    })).toThrow(RawActionObservationTraceValidationError);

    try {
      actionObservationFromRawTrace({
        source_kind: "raw_trace",
        call_id: "call-missing-args",
        tool_name: "search_policy",
        observation: { status: "ok", content: ["policy"] },
      });
    } catch (error) {
      expect(error).toBeInstanceOf(RawActionObservationTraceValidationError);
      expect(String(error)).toContain("arguments");
      expect(String(error)).toContain("required");
      return;
    }
    throw new Error("expected raw trace without arguments to throw");
  });

  it("does not infer observations, aliases, tool versions, or schema refs from prose", () => {
    expect(() => actionObservationFromRawTrace({
      source_kind: "raw_trace",
      call_id: "call-1",
      tool_name: "shell",
      arguments: { command: "npm test" },
      stdout: "npm test passed",
    })).toThrow(RawActionObservationTraceValidationError);

    const normalized = actionObservationFromRawTrace({
      source_kind: "raw_trace",
      call_id: "call-2",
      tool_name: "shell",
      arguments: { command: "npm test" },
      observation: { status: "ok", content: { stdout: "npm test passed" } },
    });

    expect(normalized.action.name).toBe("shell");
    expect(normalized.action.version).toBeUndefined();
    expect(normalized.action.argument_schema_ref).toBeUndefined();
    expect(normalized.observation.observation_schema_ref).toBeUndefined();
  });
});
