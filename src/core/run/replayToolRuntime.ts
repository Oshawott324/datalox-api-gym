import {
  mcpToolCatalogToListToolsResult,
  strictPassthroughToolCatalogTool,
} from "../mcpToolCatalogStore.js";
import type { McpToolCatalogToolV1 } from "../mcpToolCatalogSchema.js";
import {
  readReplayBundleMcpToolCatalogs,
  readReplayBundleToolIoRecords,
  verifyReplayBundle,
} from "../replayBundle.js";
import {
  buildToolIoRequestHash,
  type ToolIoObservationV1,
  type ToolIoRecordV1,
} from "../toolIoSchema.js";
import { resolveFixtureRuntime } from "../fixtures/resolveFixtureRuntime.js";
import { resolveFixtureSetRuntime } from "../fixtures/resolveFixtureSetRuntime.js";
import { validateNoToolNameCollisions } from "../fixtures/validateToolCollisions.js";

export interface ReplayMiss {
  code: "replay_miss";
  message: string;
  request_hash: string;
  sequence_index: number;
  tool_name: string;
  active_fixture_refs: string[];
  available_tool_names: string[];
  liveFallback: false;
}

export interface ReplayToolCallResult {
  observation: ToolIoObservationV1;
  record?: ToolIoRecordV1;
  replayMiss?: ReplayMiss;
}

export interface ReplayToolRuntime {
  activeFixtureRefs: string[];
  bundlePaths: string[];
  listTools(): Promise<McpToolCatalogToolV1[]>;
  callTool(input: {
    name: string;
    arguments: Record<string, unknown>;
  }): Promise<ReplayToolCallResult>;
}

export interface CreateReplayToolRuntimeInput {
  repoPath?: string;
  cacheRoot?: string;
  fixtureRef?: string;
  fixtureRefs?: string[];
  fixtureSetRef?: string;
  bundlePaths?: string[];
  activeFixtureRefs?: string[];
}

export async function createReplayToolRuntime(
  input: CreateReplayToolRuntimeInput,
): Promise<ReplayToolRuntime> {
  const resolved = await resolveRuntimeBundles(input);
  const records = (await Promise.all(resolved.bundlePaths.map((bundlePath) => (
    readReplayBundleToolIoRecords({ repoPath: input.repoPath, bundlePath })
  )))).flat();
  const catalogs = (await Promise.all(resolved.bundlePaths.map((bundlePath) => (
    readReplayBundleMcpToolCatalogs({ repoPath: input.repoPath, bundlePath })
  )))).flat();
  const tools = catalogs.length > 0
    ? catalogs.flatMap((catalog) => mcpToolCatalogToListToolsResult(catalog).tools.map((tool) => ({
      name: tool.name,
      ...(tool.title !== undefined ? { title: tool.title } : {}),
      ...(tool.description !== undefined ? { description: tool.description } : {}),
      input_schema: tool.inputSchema as Record<string, unknown>,
      ...(tool.outputSchema !== undefined ? { output_schema: tool.outputSchema as Record<string, unknown> } : {}),
      ...(tool.annotations !== undefined ? { annotations: tool.annotations as Record<string, unknown> } : {}),
      ...(tool.execution !== undefined ? { execution: tool.execution as Record<string, unknown> } : {}),
      ...(tool.icons !== undefined ? { icons: tool.icons as Record<string, unknown>[] } : {}),
      ...(tool._meta !== undefined ? { _meta: tool._meta as Record<string, unknown> } : {}),
    })))
    : Array.from(new Set(records.map((record) => record.tool_name)))
      .sort()
      .map(strictPassthroughToolCatalogTool);

  const toolsByName = indexTools(tools);
  const recordsByReplayKey = indexRecords(records);
  const replayCounters = new Map<string, number>();
  const availableToolNames = Array.from(toolsByName.keys()).sort();

  return {
    activeFixtureRefs: resolved.activeFixtureRefs,
    bundlePaths: resolved.bundlePaths,
    async listTools() {
      return tools;
    },
    async callTool(call) {
      if (!toolsByName.has(call.name)) {
        return {
          observation: {
            status: "error",
            error_code: "unknown_tool",
            error_message: `Tool ${call.name} not found in replay catalog.`,
          },
        };
      }
      const requestHash = buildToolIoRequestHash(call.name, call.arguments);
      const sequenceIndex = nextReplaySequenceIndex(replayCounters, requestHash);
      const record = recordsByReplayKey.get(`${requestHash}:${sequenceIndex}`);
      if (!record) {
        const miss: ReplayMiss = {
          code: "replay_miss",
          message: `Replay miss for request_hash=${requestHash} sequence_index=${sequenceIndex}.`,
          request_hash: requestHash,
          sequence_index: sequenceIndex,
          tool_name: call.name,
          active_fixture_refs: resolved.activeFixtureRefs,
          available_tool_names: availableToolNames,
          liveFallback: false,
        };
        return {
          observation: {
            status: "error",
            error_code: "replay_miss",
            error_message: miss.message,
            content: miss,
          },
          replayMiss: miss,
        };
      }
      return {
        observation: record.observation,
        record,
      };
    },
  };
}

async function resolveRuntimeBundles(input: CreateReplayToolRuntimeInput): Promise<{
  bundlePaths: string[];
  activeFixtureRefs: string[];
}> {
  if (input.bundlePaths && input.bundlePaths.length > 0) {
    for (const bundlePath of input.bundlePaths) {
      await verifyReplayBundle({ repoPath: input.repoPath, bundlePath });
    }
    return {
      bundlePaths: input.bundlePaths,
      activeFixtureRefs: input.activeFixtureRefs ?? [],
    };
  }

  if (input.fixtureSetRef) {
    const runtime = await resolveFixtureSetRuntime({
      ref: input.fixtureSetRef,
      cacheRoot: input.cacheRoot,
    });
    return {
      bundlePaths: runtime.bundlePaths,
      activeFixtureRefs: runtime.activeFixtureRefs,
    };
  }

  const fixtureRefs = [
    ...(input.fixtureRef ? [input.fixtureRef] : []),
    ...(input.fixtureRefs ?? []),
  ];
  if (fixtureRefs.length === 0) {
    throw new Error("Replay tool runtime requires bundlePaths, fixtureRef, fixtureRefs, or fixtureSetRef.");
  }
  const runtimes = [];
  for (const ref of fixtureRefs) {
    runtimes.push(await resolveFixtureRuntime({
      ref,
      cacheRoot: input.cacheRoot,
    }));
  }
  await validateNoToolNameCollisions(runtimes);
  return {
    bundlePaths: runtimes.map((runtime) => runtime.bundlePath),
    activeFixtureRefs: runtimes.map((runtime) => runtime.ref),
  };
}

function indexTools(tools: McpToolCatalogToolV1[]): Map<string, McpToolCatalogToolV1> {
  const indexed = new Map<string, McpToolCatalogToolV1>();
  for (const tool of tools) {
    if (indexed.has(tool.name)) {
      throw new Error(`Duplicate replay tool name across catalogs: ${tool.name}`);
    }
    indexed.set(tool.name, tool);
  }
  return indexed;
}

function indexRecords(records: ToolIoRecordV1[]): Map<string, ToolIoRecordV1> {
  const indexed = new Map<string, ToolIoRecordV1>();
  for (const record of records) {
    const key = `${record.request_hash}:${record.sequence_index}`;
    if (indexed.has(key)) {
      throw new Error(`Duplicate replay key in runtime records: ${key}`);
    }
    indexed.set(key, record);
  }
  return indexed;
}

function nextReplaySequenceIndex(replayCounters: Map<string, number>, requestHash: string): number {
  const next = replayCounters.get(requestHash) ?? 0;
  replayCounters.set(requestHash, next + 1);
  return next;
}
