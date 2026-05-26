import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { exportSftFromRun } from "../src/core/exports/exportSftFromRun.js";
import { parseSftFrameV1 } from "../src/core/exports/sftFrameSchema.js";

const tempDirs: string[] = [];

afterEach(async () => {
  await Promise.all(tempDirs.splice(0).map((dir) => rm(dir, { recursive: true, force: true })));
});

describe("exportSftFromRun", () => {
  it("exports one SFT frame from a successful replay-backed run", async () => {
    const runDir = await makeTempDir("datalox-sft-export-run-");
    const outPath = path.join(runDir, "exports", "sft.jsonl");
    const run = successfulRun();
    await writeFile(path.join(runDir, "run.json"), JSON.stringify(run, null, 2), "utf8");

    const result = await exportSftFromRun({
      runDir,
      outPath,
    });

    expect(result.frameCount).toBe(1);
    const lines = (await readFile(outPath, "utf8")).trim().split("\n");
    expect(lines).toHaveLength(1);
    const frame = parseSftFrameV1(JSON.parse(lines[0]) as unknown);
    expect(frame.source_run_id).toBe("run_success_001");
    expect(frame.input_messages.map((message) => message.role)).toEqual(["system", "user", "assistant", "tool"]);
    expect(frame.target_message).toMatchObject({
      role: "assistant",
      content: "The policy allows reimbursement with approval.",
    });
    expect(frame.evidence_refs.tool_record_refs).toEqual(["toolio-abc"]);
    expect(frame.quality).toBe("success");
  });

  it("blocks SFT export when replay misses are present", async () => {
    const runDir = await makeTempDir("datalox-sft-export-miss-");
    const outPath = path.join(runDir, "sft.jsonl");
    const run = successfulRun();
    (run.steps[0] as Record<string, unknown>).replay_miss = {
      code: "replay_miss",
      message: "No recorded observation for tool call.",
      request_hash: "sha256:abc",
      sequence_index: 0,
      tool_name: "policy_lookup",
      active_fixture_refs: ["support-basic@2026-05.0"],
      available_tool_names: ["policy_lookup"],
      liveFallback: false,
    };
    await writeFile(path.join(runDir, "run.json"), JSON.stringify(run, null, 2), "utf8");

    await expect(exportSftFromRun({ runDir, outPath })).rejects.toThrow(/replay misses/u);
  });
});

async function makeTempDir(prefix: string): Promise<string> {
  const dir = await mkdtemp(path.join(tmpdir(), prefix));
  tempDirs.push(dir);
  await mkdir(dir, { recursive: true });
  return dir;
}

function successfulRun() {
  return {
    schema_version: "datalox_run.v1",
    id: "run_success_001",
    created_at: "2026-05-23T00:00:00.000Z",
    task_ref: "task:support-policy",
    fixture_refs: ["support-basic@2026-05.0"],
    fixture_set_ref: "support-set@2026-05.0",
    model: {
      provider: "openai_compatible",
      model: "local-qwen-test",
      base_url: "http://127.0.0.1:8000/v1",
      sampling: {
        temperature: 0.2,
      },
    },
    messages: [
      {
        role: "system",
        content: "Use tools.",
      },
      {
        role: "user",
        content: "Can I reimburse this?",
      },
      {
        role: "assistant",
        content: null,
        tool_calls: [
          {
            id: "call_1",
            type: "function",
            function: {
              name: "policy_lookup",
              arguments: "{\"query\":\"approval\"}",
            },
          },
        ],
      },
      {
        role: "tool",
        tool_call_id: "call_1",
        name: "policy_lookup",
        content: "{\"status\":\"ok\",\"content\":[\"approval required\"]}",
      },
      {
        role: "assistant",
        content: "The policy allows reimbursement with approval.",
      },
    ],
    steps: [
      {
        index: 0,
        assistant_message: {
          role: "assistant",
          content: null,
          tool_calls: [
            {
              id: "call_1",
              type: "function",
              function: {
                name: "policy_lookup",
                arguments: "{\"query\":\"approval\"}",
              },
            },
          ],
        },
        tool_call: {
          id: "call_1",
          name: "policy_lookup",
          arguments: {
            query: "approval",
          },
        },
        observation: {
          status: "ok",
          content: ["approval required"],
        },
        tool_record_ref: "toolio-abc",
      },
      {
        index: 1,
        assistant_message: {
          role: "assistant",
          content: "The policy allows reimbursement with approval.",
        },
      },
    ],
    final_answer: "The policy allows reimbursement with approval.",
    stop_reason: "final_answer",
    export: {
      allowed: true,
      redaction: "none_needed",
    },
  };
}
