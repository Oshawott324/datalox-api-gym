import process from "node:process";

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

import { recordAgentTurn } from "../core/agentTurnStore.js";
import { agentTurnV1Schema } from "../core/agentTurnSchema.js";
import { packReplayBundle, verifyReplayBundle } from "../core/replayBundle.js";
import { recordToolIo, replayToolIoObservation } from "../core/toolIoStore.js";
import { toolIoObservationV1Schema } from "../core/toolIoSchema.js";

const exportGateSchema = z
  .object({
    allowed: z.boolean(),
    redaction: z.enum(["none_needed", "applied", "blocked"]),
    approval_id: z.string().optional(),
  })
  .strict();

const toolIoExportGateSchema = z
  .object({
    allowed: z.boolean(),
    redaction: z.enum(["none_needed", "applied", "blocked"]),
  })
  .strict();

const sourceSchema = z
  .object({
    host: z.string().optional(),
    mcp_server: z.string().optional(),
    command: z.string().optional(),
  })
  .strict();

const taskSchema = z
  .object({
    prompt: z.string().optional(),
    domains: z.array(z.string()).optional(),
    workflows: z.array(z.string()).optional(),
  })
  .strict();

const JsonResultSchema = {
  result: z.unknown(),
};

function mcpJsonResult(result: unknown) {
  return {
    content: [{ type: "text" as const, text: JSON.stringify({ result }, null, 2) }],
    structuredContent: { result },
  };
}

export function buildReplayMcpServer(): McpServer {
  const server = new McpServer({
    name: "datalox-agent-replay",
    version: "0.1.0",
  });

  server.registerTool(
    "record_tool_io",
    {
      description: "Record one agent-visible tool request and observation as tool_io_record.v1.",
      inputSchema: {
        repo_path: z.string().describe("Absolute or relative path to the host repo."),
        session_id: z.string().optional().describe("Optional source session id."),
        turn_id: z.string().optional().describe("Optional source turn id."),
        call_id: z.string().min(1).describe("Stable id for this tool call within the source turn."),
        tool_name: z.string().min(1).describe("Agent-visible tool name."),
        arguments: z.unknown().describe("Exact agent-visible tool arguments."),
        observation: toolIoObservationV1Schema.describe("Exact agent-visible tool observation."),
        source: sourceSchema.optional().describe("Optional source host metadata visible to Datalox."),
        export: toolIoExportGateSchema.optional().describe("Explicit export gate for this record."),
      },
      outputSchema: JsonResultSchema,
    },
    async (input) => mcpJsonResult(await recordToolIo({
      repoPath: input.repo_path,
      sessionId: input.session_id,
      turnId: input.turn_id,
      callId: input.call_id,
      toolName: input.tool_name,
      arguments: input.arguments,
      observation: input.observation,
      source: input.source,
      export: input.export,
    })),
  );

  server.registerTool(
    "record_agent_turn",
    {
      description: "Record one completed turn review event as agent_turn.v1.",
      inputSchema: {
        repo_path: z.string().describe("Absolute or relative path to the host repo."),
        agent_turn: agentTurnV1Schema.describe("One agent_turn.v1 object."),
      },
      outputSchema: JsonResultSchema,
    },
    async (input) => mcpJsonResult(await recordAgentTurn({
      repoPath: input.repo_path,
      agentTurn: input.agent_turn,
    })),
  );

  server.registerTool(
    "pack_replay_bundle",
    {
      description: "Pack source tool I/O records and turn events into a replay_bundle.v1 directory.",
      inputSchema: {
        repo_path: z.string().describe("Absolute or relative path to the host repo."),
        bundle_id: z.string().min(1).describe("Replay bundle id and directory name."),
        title: z.string().optional().describe("Optional replay bundle title."),
        task: taskSchema.optional().describe("Optional task metadata."),
        export: exportGateSchema.optional().describe("Explicit export gate for the bundle."),
      },
      outputSchema: JsonResultSchema,
    },
    async (input) => mcpJsonResult(await packReplayBundle({
      repoPath: input.repo_path,
      bundleId: input.bundle_id,
      title: input.title,
      task: input.task,
      export: input.export,
    })),
  );

  server.registerTool(
    "verify_replay_bundle",
    {
      description: "Verify a replay_bundle.v1 directory from sealed bundle files and checksums.",
      inputSchema: {
        repo_path: z.string().describe("Absolute or relative path to the host repo."),
        bundle: z.string().min(1).describe("Relative or absolute path to the replay bundle directory."),
      },
      outputSchema: JsonResultSchema,
    },
    async (input) => mcpJsonResult(await verifyReplayBundle({
      repoPath: input.repo_path,
      bundlePath: input.bundle,
    })),
  );

  server.registerTool(
    "replay_tool_io",
    {
      description: "Replay one stored tool observation by exact request hash and sequence index.",
      inputSchema: {
        repo_path: z.string().describe("Absolute or relative path to the host repo."),
        tool_name: z.string().min(1).describe("Agent-visible tool name."),
        arguments: z.unknown().describe("Exact agent-visible tool arguments."),
        sequence_index: z.number().int().nonnegative().describe("Replay sequence index for repeated identical requests."),
      },
      outputSchema: JsonResultSchema,
    },
    async (input) => mcpJsonResult({
      observation: await replayToolIoObservation({
        repoPath: input.repo_path,
        toolName: input.tool_name,
        arguments: input.arguments,
        sequenceIndex: input.sequence_index,
      }),
    }),
  );

  return server;
}

export async function runReplayMcpServer(): Promise<void> {
  const server = buildReplayMcpServer();
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

async function main(): Promise<void> {
  await runReplayMcpServer();
}

main().catch((error: unknown) => {
  const message = error instanceof Error ? error.stack ?? error.message : String(error);
  process.stderr.write(`${message}\n`);
  process.exit(1);
});
