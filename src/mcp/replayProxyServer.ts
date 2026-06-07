import process from "node:process";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  type CallToolResult,
  type ListToolsResult,
} from "@modelcontextprotocol/sdk/types.js";

import {
  type DataloxReplayProxyConfigV1,
  readDataloxReplayProxyConfigFile,
} from "../core/mcpProxyConfig.js";
import {
  readReplayBundleMcpToolCatalogs,
  readReplayBundleToolIoRecords,
  resolveReplayBundlePath,
  verifyReplayBundle,
} from "../core/replayBundle.js";
import {
  mcpToolCatalogToListToolsResult,
  recordMcpToolCatalog,
  strictPassthroughToolCatalogTool,
} from "../core/mcpToolCatalogStore.js";
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
  bundlePaths?: string[];
  activeFixtureRefs?: string[];
}

export async function buildReplayProxyServer(input: ReplayProxyServerInput): Promise<McpServer> {
  switch (input.mode) {
    case "record":
      if (!input.config) {
        throw new Error("Record mode requires a replay proxy config.");
      }
      return buildRecordProxyServer({ ...input, config: input.config });
    case "replay":
      if (!input.bundlePath && (!input.bundlePaths || input.bundlePaths.length === 0)) {
        throw new Error("Replay mode requires a replay bundle path.");
      }
      return buildReplayOnlyProxyServer(input);
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
  await recordMcpToolCatalog({
    repoPath: input.repoPath,
    upstream: {
      command: input.config.upstream.command,
      args: input.config.upstream.args,
      ...(input.config.upstream.cwd !== undefined ? { cwd: input.config.upstream.cwd } : {}),
    },
    listToolsResult: upstreamTools,
    export: input.config.record?.export,
  });

  const server = new McpServer({
    name: "datalox-api-gym-proxy",
    version: "0.1.0",
  });
  server.server.registerCapabilities({
    tools: {
      listChanged: false,
    },
  });

  let callCounter = 0;
  const upstreamToolNames = new Set(upstreamTools.tools.map((tool) => tool.name));
  const upstreamToolsByName = new Map(upstreamTools.tools.map((tool) => [tool.name, tool]));

  server.server.setRequestHandler(ListToolsRequestSchema, () => upstreamTools);
  server.server.setRequestHandler(CallToolRequestSchema, async (request) => {
    const toolName = request.params.name;
    if (!upstreamToolNames.has(toolName)) {
      return mcpErrorResult("unknown_tool", `Tool ${toolName} not found in upstream catalog.`);
    }
    const toolHasOutputSchema = upstreamToolsByName.get(toolName)?.outputSchema !== undefined;

    const toolArguments = normalizeToolArguments(request.params.arguments);
    const callId = `proxy-call-${callCounter}`;
    callCounter += 1;
    let upstreamResult: CallToolResult;
    try {
      upstreamResult = await upstream.client.callTool({
        name: toolName,
        arguments: toolArguments,
      }) as CallToolResult;
    } catch (error) {
      const upstreamErrorMessage = formatError(error);
      try {
        await recordProxyToolIo({
          repoPath: input.repoPath,
          config: input.config,
          callId,
          toolName,
          arguments: toolArguments,
          observation: {
            status: "error",
            error_code: "upstream_tool_error",
            error_message: upstreamErrorMessage,
          },
        });
      } catch (recordError) {
        return proxyRecordErrorResult(recordError, { includeStructuredContent: !toolHasOutputSchema });
      }
      return mcpErrorResult(
        "upstream_tool_error",
        upstreamErrorMessage,
        undefined,
        { includeStructuredContent: !toolHasOutputSchema },
      );
    }

    try {
      await recordProxyToolIo({
        repoPath: input.repoPath,
        config: input.config,
        callId,
        toolName,
        arguments: toolArguments,
        observation: {
          status: "ok",
          content: upstreamResult,
        },
      });
    } catch (recordError) {
      return proxyRecordErrorResult(recordError, { includeStructuredContent: !toolHasOutputSchema });
    }
    return upstreamResult;
  });

  return server;
}

async function buildReplayOnlyProxyServer(input: ReplayProxyServerInput): Promise<McpServer> {
  const requestedBundlePaths = input.bundlePaths ?? (input.bundlePath ? [input.bundlePath] : []);
  const bundlePaths = requestedBundlePaths.map((bundlePath) => resolveReplayBundlePath(input.repoPath, bundlePath));
  for (const bundlePath of bundlePaths) {
    await verifyReplayBundle({ bundlePath });
  }
  const records = (await Promise.all(bundlePaths.map((bundlePath) => (
    readReplayBundleToolIoRecords({ bundlePath })
  )))).flat();
  const catalogs = (await Promise.all(bundlePaths.map((bundlePath) => (
    readReplayBundleMcpToolCatalogs({ bundlePath })
  )))).flat();
  const recordsByReplayKey = indexBundleToolIoRecords(records);
  const listToolsResult = buildReplayListToolsResult(catalogs, records);
  const toolNames = new Set(listToolsResult.tools.map((tool) => tool.name));
  const toolsByName = new Map(listToolsResult.tools.map((tool) => [tool.name, tool]));
  const replayCounters = new Map<string, number>();

  const server = new McpServer({
    name: "datalox-api-gym-proxy",
    version: "0.1.0",
  });
  server.server.registerCapabilities({
    tools: {
      listChanged: false,
    },
  });

  server.server.setRequestHandler(ListToolsRequestSchema, () => listToolsResult);
  server.server.setRequestHandler(CallToolRequestSchema, async (request) => {
    const toolName = request.params.name;
    if (!toolNames.has(toolName)) {
      return mcpErrorResult("unknown_tool", `Tool ${toolName} not found in replay catalog.`);
    }
    const toolHasOutputSchema = toolsByName.get(toolName)?.outputSchema !== undefined;

    const toolArguments = normalizeToolArguments(request.params.arguments);
    const requestHash = buildToolIoRequestHash(toolName, toolArguments);
    const sequenceIndex = nextReplaySequenceIndex(replayCounters, requestHash);
    const record = recordsByReplayKey.get(`${requestHash}:${sequenceIndex}`);
    if (!record) {
      return mcpErrorResult(
        "replay_miss",
        new ToolIoReplayMissError(requestHash, sequenceIndex).message,
        {
          request_hash: requestHash,
          sequence_index: sequenceIndex,
          tool_name: toolName,
          active_fixture_refs: input.activeFixtureRefs ?? [],
          available_tool_names: Array.from(toolNames).sort(),
          liveFallback: false,
        },
        { includeStructuredContent: !toolHasOutputSchema },
      );
    }
    return observationToMcpResult(record.observation, {
      includeStructuredErrorContent: !toolHasOutputSchema,
    });
  });

  return server;
}

async function connectUpstream(config: DataloxReplayProxyConfigV1): Promise<{ client: Client }> {
  const transport = new StdioClientTransport({
    command: config.upstream.command,
    args: config.upstream.args,
    cwd: config.upstream.cwd,
    env: {
      ...stringProcessEnv(),
      ...(config.upstream.env ?? {}),
    },
    stderr: "pipe",
  });
  const client = new Client(
    { name: "datalox-api-gym-upstream-client", version: "1.0.0" },
    { capabilities: {} },
  );
  await client.connect(transport);
  return { client };
}

async function recordProxyToolIo(input: {
  repoPath?: string;
  config: DataloxReplayProxyConfigV1;
  callId: string;
  toolName: string;
  arguments: Record<string, unknown>;
  observation: ToolIoObservationV1;
}): Promise<void> {
  await recordToolIo({
    repoPath: input.repoPath,
    sessionId: input.config.record?.session_id,
    turnId: input.config.record?.turn_id,
    callId: input.callId,
    toolName: input.toolName,
    arguments: input.arguments,
    observation: input.observation,
    source: {
      mcp_server: "upstream",
      command: [input.config.upstream.command, ...input.config.upstream.args].join(" "),
    },
    export: input.config.record?.export,
  });
}

function stringProcessEnv(): Record<string, string> {
  return Object.fromEntries(
    Object.entries(process.env).filter((entry): entry is [string, string] => (
      typeof entry[1] === "string"
    )),
  );
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

function buildReplayListToolsResult(
  catalogs: Awaited<ReturnType<typeof readReplayBundleMcpToolCatalogs>>,
  records: ToolIoRecordV1[],
): ListToolsResult {
  if (catalogs.length > 0) {
    const toolsByName = new Map<string, ListToolsResult["tools"][number]>();
    for (const catalog of catalogs) {
      const listToolsResult = mcpToolCatalogToListToolsResult(catalog);
      for (const tool of listToolsResult.tools) {
        if (toolsByName.has(tool.name)) {
          throw new Error(`Duplicate replay tool name across bundled catalogs: ${tool.name}`);
        }
        toolsByName.set(tool.name, tool);
      }
    }
    return {
      tools: Array.from(toolsByName.values()),
    };
  }
  return {
    tools: Array.from(new Set(records.map((record) => record.tool_name)))
      .sort()
      .map(strictPassthroughToolCatalogTool)
      .map((tool) => ({
        name: tool.name,
        description: tool.description,
        inputSchema: tool.input_schema as ListToolsResult["tools"][number]["inputSchema"],
      })),
  };
}

function observationToMcpResult(
  observation: ToolIoObservationV1,
  options?: { includeStructuredErrorContent?: boolean },
): CallToolResult {
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
    undefined,
    { includeStructuredContent: options?.includeStructuredErrorContent ?? true },
  );
}

function proxyRecordErrorResult(
  error: unknown,
  options?: { includeStructuredContent?: boolean },
): CallToolResult {
  return mcpErrorResult(
    "datalox_record_error",
    `Datalox record write failed: ${formatError(error)}`,
    undefined,
    options,
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
  options?: { includeStructuredContent?: boolean },
): CallToolResult {
  const error = { code, message, ...(detail ?? {}) };
  return {
    isError: true,
    content: [{ type: "text", text: JSON.stringify({ error }, null, 2) }],
    ...(options?.includeStructuredContent ?? true ? { structuredContent: { error } } : {}),
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
