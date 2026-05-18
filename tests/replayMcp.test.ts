import { existsSync } from "node:fs";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { afterEach, describe, expect, it } from "vitest";

const repoRoot = process.cwd();
const builtMcpPath = path.join(repoRoot, "dist", "src", "mcp", "replayServer.js");
const legacyWikiDir = ["agent", "wiki"].join("-");

function extractStructuredResult(result: unknown): unknown {
  const resolved = (typeof result === "object" && result !== null && "toolResult" in result)
    ? (result as { toolResult: unknown }).toolResult
    : result;

  if (
    resolved
    && typeof resolved === "object"
    && "structuredContent" in resolved
    && (resolved as { structuredContent?: unknown }).structuredContent
    && typeof (resolved as { structuredContent?: unknown }).structuredContent === "object"
  ) {
    return (resolved as { structuredContent: { result: unknown } }).structuredContent.result;
  }

  const content = (resolved as { content?: Array<{ type: string; text?: string }> }).content;
  const text = content?.find((item) => item.type === "text")?.text;
  if (!text) {
    throw new Error("No structured MCP result found");
  }
  const parsed = JSON.parse(text) as { result?: unknown };
  return parsed.result;
}

function makeAgentTurn(toolIoRecord: {
  id: string;
  request_hash: string;
  sequence_index: number;
}) {
  return {
    schema_version: "agent_turn.v1",
    id: "turn-1",
    session_id: "session-1",
    turn_index: 0,
    created_at: "2026-05-16T00:00:00.000Z",
    user_prompt: "Find the reimbursement policy.",
    assistant_summary: "Recorded and replayed a policy search tool call.",
    tool_calls: [
      {
        tool: "search_policy",
        call_id: "call-1",
        tool_io_ref: {
          record_id: toolIoRecord.id,
          request_hash: toolIoRecord.request_hash,
          sequence_index: toolIoRecord.sequence_index,
        },
        args_summary: "taxi reimbursement",
        output_summary: "Two policy documents.",
      },
    ],
    verification: {
      status: "passed",
      evidence: "Replay returned the stored policy observation.",
    },
    export: {
      allowed: true,
      redaction: "none_needed",
    },
  };
}

describe("install-facing replay MCP server", () => {
  const tempDirs: string[] = [];

  afterEach(async () => {
    await Promise.all(tempDirs.splice(0).map((dir) => rm(dir, { recursive: true, force: true })));
  });

  async function makeTempRepo(): Promise<string> {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-replay-mcp-"));
    tempDirs.push(tempDir);
    return tempDir;
  }

  it("lists replay tools only and records, replays, packs, and verifies replay data", async () => {
    const tempDir = await makeTempRepo();
    const transport = new StdioClientTransport({
      command: process.execPath,
      args: [builtMcpPath],
      cwd: repoRoot,
      stderr: "pipe",
    });
    const client = new Client({ name: "replay-mcp-test-client", version: "1.0.0" }, { capabilities: {} });

    try {
      await client.connect(transport);
      const tools = await client.listTools();
      const toolNames = tools.tools.map((tool) => tool.name);
      expect(toolNames).toEqual([
        "record_tool_io",
        "record_agent_turn",
        "pack_replay_bundle",
        "verify_replay_bundle",
        "replay_tool_io",
      ]);
      expect(toolNames.some((name) => name.includes("trajectory"))).toBe(false);
      expect(toolNames.some((name) => name.includes("grade"))).toBe(false);
      expect(toolNames.some((name) => name.includes("repair"))).toBe(false);
      expect(toolNames.some((name) => name.includes("export"))).toBe(false);

      const recordToolResult = extractStructuredResult(await client.callTool({
        name: "record_tool_io",
        arguments: {
          repo_path: tempDir,
          session_id: "session-1",
          turn_id: "turn-1",
          call_id: "call-1",
          tool_name: "search_policy",
          arguments: {
            query: "Beijing business-trip taxi reimbursement limit",
            top_k: 5,
          },
          observation: {
            status: "ok",
            content: ["doc1 ...", "doc2 ..."],
          },
          export: {
            allowed: true,
            redaction: "none_needed",
          },
        },
      })) as { recordPath: string; record: { id: string; request_hash: string; sequence_index: number } };

      expect(recordToolResult.recordPath).toContain(".datalox/tool-io/records/");
      expect(recordToolResult.record.sequence_index).toBe(0);

      const replayResult = extractStructuredResult(await client.callTool({
        name: "replay_tool_io",
        arguments: {
          repo_path: tempDir,
          tool_name: "search_policy",
          arguments: {
            top_k: 5,
            query: "Beijing business-trip taxi reimbursement limit",
          },
          sequence_index: 0,
        },
      })) as { observation: unknown };
      expect(replayResult.observation).toEqual({
        status: "ok",
        content: ["doc1 ...", "doc2 ..."],
      });

      const recordTurnResult = extractStructuredResult(await client.callTool({
        name: "record_agent_turn",
        arguments: {
          repo_path: tempDir,
          agent_turn: makeAgentTurn(recordToolResult.record),
        },
      })) as { eventPath: string; turnId: string };

      expect(recordTurnResult.turnId).toBe("turn-1");
      expect(recordTurnResult.eventPath).toContain(".datalox/events/agent-turns/");

      const packResult = extractStructuredResult(await client.callTool({
        name: "pack_replay_bundle",
        arguments: {
          repo_path: tempDir,
          bundle_id: "mcp-replay-bundle",
          export: {
            allowed: true,
            redaction: "none_needed",
          },
        },
      })) as { bundlePath: string; manifest: { id: string; replay: { tool_record_count: number; turn_count: number } } };

      expect(packResult.bundlePath).toBe(".datalox/replay-bundles/mcp-replay-bundle");
      expect(packResult.manifest).toMatchObject({
        id: "mcp-replay-bundle",
        replay: {
          tool_record_count: 1,
          turn_count: 1,
        },
      });

      await rm(path.join(tempDir, ".datalox", "tool-io"), { recursive: true, force: true });
      await rm(path.join(tempDir, ".datalox", "events", "agent-turns"), { recursive: true, force: true });

      const verifyResult = extractStructuredResult(await client.callTool({
        name: "verify_replay_bundle",
        arguments: {
          repo_path: tempDir,
          bundle: packResult.bundlePath,
        },
      })) as { verified: boolean; checkedFiles: number };

      expect(verifyResult).toMatchObject({
        verified: true,
        checkedFiles: 3,
      });
      expect(existsSync(path.join(tempDir, legacyWikiDir))).toBe(false);
    } finally {
      await client.close();
    }
  });
});
