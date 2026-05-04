import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

import { buildLoopPulse } from "./loopPulse.js";
import {
  buildSharedMcpInputSchema,
  parseSharedMcpInput,
  type SharedCommandSpec,
} from "../surface/sharedCommands.js";

const JsonValueSchema = z.record(z.string(), z.unknown()).or(z.array(z.unknown()));
const JsonResultSchema = {
  result: JsonValueSchema,
  loop_pulse: z.record(z.string(), z.unknown()),
};

export interface SharedMcpServerOptions {
  name: string;
  version: string;
  commands: readonly SharedCommandSpec[];
  unavailableLoopPulseTools?: readonly string[];
  fallbackLoopPulseTool?: string | null;
}

function maybeRepoPath(command: string, input: Record<string, unknown>): string | undefined {
  if (typeof input.repo_path === "string") {
    return input.repo_path;
  }
  if (command === "adopt_pack" && typeof input.host_repo_path === "string") {
    return input.host_repo_path;
  }
  return undefined;
}

export function buildSharedMcpServer(options: SharedMcpServerOptions): McpServer {
  const server = new McpServer({
    name: options.name,
    version: options.version,
  });

  for (const command of options.commands) {
    server.registerTool(
      command.mcpTool,
      {
        description: command.description,
        inputSchema: buildSharedMcpInputSchema(command),
        outputSchema: JsonResultSchema,
      },
      async (input) => {
        const rawInput = input as Record<string, unknown>;
        const normalizedInput = parseSharedMcpInput(command, rawInput);
        const result = await command.run(normalizedInput);
        const loopPulse = await buildLoopPulse({
          command: command.mcpTool,
          repoPath: maybeRepoPath(command.mcpTool, rawInput),
          result,
          options: {
            unavailableTools: options.unavailableLoopPulseTools,
            fallbackRecommendedTool: options.fallbackLoopPulseTool,
          },
        });

        return {
          content: [{ type: "text", text: JSON.stringify({ result, loop_pulse: loopPulse }, null, 2) }],
          structuredContent: {
            result,
            loop_pulse: loopPulse,
          },
        };
      },
    );
  }

  return server;
}

export async function runSharedMcpServer(options: SharedMcpServerOptions): Promise<void> {
  const server = buildSharedMcpServer(options);
  const transport = new StdioServerTransport();
  await server.connect(transport);
}
