import { existsSync } from "node:fs";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { canonicalJson } from "../src/core/canonicalJson.js";
import {
  buildToolIoRequestHash,
  parseToolIoRecordV1,
  ToolIoRecordValidationError,
} from "../src/core/toolIoSchema.js";
import {
  recordToolIo,
  replayToolIoObservation,
  TOOL_IO_RECORDS_RELATIVE_DIR,
  ToolIoReplayMissError,
} from "../src/core/toolIoStore.js";

const legacyWikiDir = ["agent", "wiki"].join("-");

describe("tool_io_record.v1 store", () => {
  const tempDirs: string[] = [];

  afterEach(async () => {
    await Promise.all(tempDirs.splice(0).map((dir) => rm(dir, { recursive: true, force: true })));
  });

  async function makeTempRepo(): Promise<string> {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-tool-io-"));
    tempDirs.push(tempDir);
    return tempDir;
  }

  it("hashes the same JSON object identically regardless of key order", () => {
    const first = buildToolIoRequestHash("search_policy", {
      query: "Beijing taxi reimbursement",
      filters: { region: "CN", active: true },
      top_k: 5,
    });
    const second = buildToolIoRequestHash("search_policy", {
      top_k: 5,
      filters: { active: true, region: "CN" },
      query: "Beijing taxi reimbursement",
    });

    expect(first).toBe(second);
    expect(canonicalJson({ b: 2, a: { d: 4, c: 3 } })).toBe('{"a":{"c":3,"d":4},"b":2}');
  });

  it("rejects non-JSON values instead of silently normalizing them", () => {
    expect(() => canonicalJson({ value: undefined })).toThrow("undefined is not valid JSON");
    expect(() => canonicalJson({ value: Number.NaN })).toThrow("number must be finite");
  });

  it("records identical requests with stable sequence indexes", async () => {
    const repoPath = await makeTempRepo();
    const first = await recordToolIo({
      repoPath,
      callId: "call-1",
      toolName: "search_policy",
      arguments: { query: "Beijing business-trip taxi reimbursement limit", top_k: 5 },
      observation: {
        status: "ok",
        content: ["doc1 ...", "doc2 ..."],
      },
      now: new Date("2026-05-16T00:00:00.000Z"),
    });
    const second = await recordToolIo({
      repoPath,
      callId: "call-2",
      toolName: "search_policy",
      arguments: { top_k: 5, query: "Beijing business-trip taxi reimbursement limit" },
      observation: {
        status: "ok",
        content: ["doc1 ...", "doc2 ..."],
      },
      now: new Date("2026-05-16T00:01:00.000Z"),
    });

    expect(first.record.request_hash).toBe(second.record.request_hash);
    expect(first.record.sequence_index).toBe(0);
    expect(second.record.sequence_index).toBe(1);
    expect(first.recordPath).toContain(`${TOOL_IO_RECORDS_RELATIVE_DIR}/`);
    expect(existsSync(path.join(repoPath, first.recordPath))).toBe(true);
    expect(existsSync(path.join(repoPath, legacyWikiDir))).toBe(false);
  });

  it("replays the exact stored agent-visible observation by request hash and sequence index", async () => {
    const repoPath = await makeTempRepo();
    const observation = {
      status: "ok" as const,
      content: {
        stdout: "done\n",
        exit_code: 0,
        nested: { rows: [{ id: "a", score: 1 }] },
      },
    };
    const recorded = await recordToolIo({
      repoPath,
      callId: "shell-1",
      toolName: "exec_command",
      arguments: { command: "npm test", cwd: "/repo" },
      observation,
      source: { host: "codex", command: "npm test" },
      export: { allowed: true, redaction: "none_needed" },
      now: new Date("2026-05-16T00:02:00.000Z"),
    });
    const stored = JSON.parse(await readFile(path.join(repoPath, recorded.recordPath), "utf8"));

    expect(stored.observation).toEqual(observation);
    await expect(replayToolIoObservation({
      repoPath,
      toolName: "exec_command",
      arguments: { cwd: "/repo", command: "npm test" },
      sequenceIndex: 0,
    })).resolves.toEqual(observation);
  });

  it("fails missing replay lookups deterministically without fuzzy matching", async () => {
    const repoPath = await makeTempRepo();
    await recordToolIo({
      repoPath,
      callId: "call-1",
      toolName: "search_policy",
      arguments: { query: "taxi reimbursement", top_k: 5 },
      observation: { status: "ok", content: ["policy"] },
    });

    await expect(replayToolIoObservation({
      repoPath,
      toolName: "search_policy",
      arguments: { query: "taxi reimbursement ", top_k: 5 },
      sequenceIndex: 0,
    })).rejects.toBeInstanceOf(ToolIoReplayMissError);

    await expect(replayToolIoObservation({
      repoPath,
      toolName: "search_policy",
      arguments: { query: "taxi reimbursement", top_k: 5 },
      sequenceIndex: 1,
    })).rejects.toBeInstanceOf(ToolIoReplayMissError);
  });

  it("validates that stored records carry the canonical request hash", () => {
    expect(() => parseToolIoRecordV1({
      schema_version: "tool_io_record.v1",
      id: "bad-hash",
      call_id: "call-1",
      tool_name: "search_policy",
      arguments: { query: "taxi reimbursement", top_k: 5 },
      request_hash: "0".repeat(64),
      sequence_index: 0,
      observation: { status: "ok", content: ["policy"] },
      created_at: "2026-05-16T00:00:00.000Z",
      export: { allowed: false, redaction: "blocked" },
    })).toThrow(ToolIoRecordValidationError);
  });
});
