import process from "node:process";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import { z } from "zod";

import {
  type DataloxReplayProxyConfigV1,
  readDataloxReplayProxyConfigFile,
} from "../core/mcpProxyConfig.js";
import {
  readReplayBundleToolIoRecords,
  resolveReplayBundlePath,
} from "../core/replayBundle.js";
import {
  buildToolIoRequestHash,
  type ToolIoObservationV1,
  type ToolIoRecordV1,
} from "../core/toolIoSchema.js";
import { recordToolIo, ToolIoReplayMissError } from "../core/toolIoStore.js";

type ReplayProxyMode = "record" | "replay";

interface ReplayProxyServerInput {
  mode: ReplayProxyMode;
  repoPath?: string;
  config?: DataloxReplayProxyConfigV1;
  bundlePath?: string;
}

const passthroughInputSchema = z.object({}).passthrough();

export async function buildReplayProxyServer(input: ReplayProxyServerInput): Promise<McpServer> {
  switch (input.mode) {
    case "record":
      if (!input.config) {
        throw new Error("Record mode requires a replay proxy config.");
      }
      return buildRecordProxyServer({ ...input, config: input.config });
    case "replay":
      if (!input.bundlePath) {
        throw new Error("Replay mode requires a replay bundle path.");
      }
      return buildReplayOnlyProxyServer({ ...input, bundlePath: input.bundlePath });
  }
}

export async function runReplayProxyServer(input: ReplayProxyServerInput): Promise<void> {
  const server = await buildReplayProxyServer(input);
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

async function buildRecordProxyServer(input: ReplayProxyServerInput & {
  config: DataloxReplayProxyConfigV1;
}): Promise<McpServer> {
  const upstream = await connectUpstream(input.config);
  const upstreamTools = await upstream.client.listTools();
  const server = new McpServer({
    name: "datalox-agent-replay-proxy",
    version: "0.1.0",
  });
  let callCounter = 0;

  for (const tool of upstreamTools.tools) {
    server.registerTool(
      tool.name,
      {
        description: tool.description ?? `Datalox record-mode proxy for upstream tool ${tool.name}.`,
        inputSchema: passthroughInputSchema,
      },
      async (toolInput) => {
        const toolArguments = normalizeToolArguments(toolInput);
        const callId = `proxy-call-${callCounter}`;
        callCounter += 1;
        try {
          const upstreamResult = await upstream.client.callTool({
            name: tool.name,
            arguments: toolArguments,
          }) as CallToolResult;
          await recordToolIo({
            repoPath: input.repoPath,
            callId,
            toolName: tool.name,
            arguments: toolArguments,
            observation: {
              status: "ok",
              content: upstreamResult,
            },
            source: {
              mcp_server: "upstream",
              command: [input.config.upstream.command, ...input.config.upstream.args].join(" "),
            },
          });
          return upstreamResult;
        } catch (error) {
          await recordToolIo({
            repoPath: input.repoPath,
            callId,
            toolName: tool.name,
            arguments: toolArguments,
            observation: {
              status: "error",
              error_code: "upstream_tool_error",
              error_message: formatError(error),
            },
            source: {
              mcp_server: "upstream",
              command: [input.config.upstream.command, ...input.config.upstream.args].join(" "),
            },
          });
          return mcpErrorResult("upstream_tool_error", formatError(error));
        }
      },
    );
  }

  return server;
}

async function buildReplayOnlyProxyServer(input: ReplayProxyServerInput & {
  bundlePath: string;
}): Promise<McpServer> {
  const bundlePath = resolveReplayBundlePath(input.repoPath, input.bundlePath);
  const records = await readReplayBundleToolIoRecords({ bundlePath });
  const recordsByReplayKey = indexBundleToolIoRecords(records);
  const toolNames = Array.from(new Set(records.map((record) => record.tool_name))).sort();
  const replayCounters = new Map<string, number>();

  const server = new McpServer({
    name: "datalox-agent-replay-proxy",
    version: "0.1.0",
  });

  for (const toolName of toolNames) {
    server.registerTool(
      toolName,
      {
        description: `Datalox replay-mode proxy for recorded tool ${toolName}.`,
        inputSchema: passthroughInputSchema,
      },
      async (toolInput) => {
        const toolArguments = normalizeToolArguments(toolInput);
        const requestHash = buildToolIoRequestHash(toolName, toolArguments);
        const sequenceIndex = nextReplaySequenceIndex(replayCounters, requestHash);
        const record = recordsByReplayKey.get(`${requestHash}:${sequenceIndex}`);
        if (!record) {
          return mcpErrorResult(
            "replay_miss",
            new ToolIoReplayMissError(requestHash, sequenceIndex).message,
            { request_hash: requestHash, sequence_index: sequenceIndex },
          );
        }
        return observationToMcpResult(record.observation);
      },
    );
  }

  return server;
}

async function connectUpstream(config: DataloxReplayProxyConfigV1): Promise<{ client: Client }> {
  const transport = new StdioClientTransport({
    command: config.upstream.command,
    args: config.upstream.args,
    stderr: "pipe",
  });
  const client = new Client(
    { name: "datalox-agent-replay-upstream-client", version: "1.0.0" },
    { capabilities: {} },
  );
  await client.connect(transport);
  return { client };
}

function normalizeToolArguments(input: unknown): Record<string, unknown> {
  return input && typeof input === "object" && !Array.isArray(input)
    ? (input as Record<string, unknown>)
    : {};
}

function indexBundleToolIoRecords(records: ToolIoRecordV1[]): Map<string, ToolIoRecordV1> {
  const indexed = new Map<string, ToolIoRecordV1>();
  for (const record of records) {
    const replayKey = `${record.request_hash}:${record.sequence_index}`;
    if (indexed.has(replayKey)) {
      throw new Error(`Duplicate replay key in bundle: ${replayKey}`);
    }
    indexed.set(replayKey, record);
  }
  return indexed;
}

function nextReplaySequenceIndex(replayCounters: Map<string, number>, requestHash: string): number {
  const next = replayCounters.get(requestHash) ?? 0;
  replayCounters.set(requestHash, next + 1);
  return next;
}

function observationToMcpResult(observation: ToolIoObservationV1): CallToolResult {
  if (observation.status === "ok") {
    if (isMcpToolResult(observation.content)) {
      return observation.content;
    }
    return {
      content: [{ type: "text", text: JSON.stringify(observation.content ?? null) }],
      structuredContent: { observation: observation.content ?? null },
    };
  }
  return mcpErrorResult(
    observation.error_code ?? "recorded_tool_error",
    observation.error_message ?? "Recorded tool call failed.",
  );
}

function isMcpToolResult(value: unknown): value is CallToolResult {
  return Boolean(
    value
    && typeof value === "object"
    && Array.isArray((value as { content?: unknown }).content),
  );
}

function mcpErrorResult(
  code: string,
  message: string,
  detail?: Record<string, unknown>,
): CallToolResult {
  const error = { code, message, ...(detail ?? {}) };
  return {
    isError: true,
    content: [{ type: "text", text: JSON.stringify({ error }, null, 2) }],
    structuredContent: { error },
  };
}

function formatError(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

async function main(): Promise<void> {
  const args = process.argv.slice(2);
  const mode = getFlag(args, "--mode") as ReplayProxyMode | undefined;
  const repoPath = getFlag(args, "--repo");
  const configPath = getFlag(args, "--config");
  const bundlePath = getFlag(args, "--bundle");
  if (mode !== "record" && mode !== "replay") {
    throw new Error("replayProxyServer requires --mode record or --mode replay.");
  }
  const config = mode === "record"
    ? await readDataloxReplayProxyConfigFile({
      repoPath,
      configPath: configPath ?? "datalox.replay.json",
    })
    : undefined;
  await runReplayProxyServer({
    mode,
    repoPath,
    config,
    bundlePath,
  });
}

function getFlag(args: string[], flag: string): string | undefined {
  const index = args.indexOf(flag);
  if (index === -1) {
    return undefined;
  }
  const value = args[index + 1];
  return value && !value.startsWith("--") ? value : undefined;
}

const currentFilePath = fileURLToPath(import.meta.url);

if (process.argv[1] && path.resolve(process.argv[1]) === currentFilePath) {
  main().catch((error: unknown) => {
    const message = error instanceof Error ? error.stack ?? error.message : String(error);
    process.stderr.write(`${message}\n`);
    process.exit(1);
  });
}
