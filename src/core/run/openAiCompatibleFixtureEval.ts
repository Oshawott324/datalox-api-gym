import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

import type { ListToolsResult } from "@modelcontextprotocol/sdk/types.js";

import {
  installFixtureSet,
  type InstallFixtureSetResult,
} from "../fixtures/installFixtureSet.js";
import {
  resolveFixtureSetRuntime,
  type FixtureSetRuntime,
} from "../fixtures/resolveFixtureSetRuntime.js";
import {
  parseTaskSpec,
  type TaskSpec,
} from "../fixtures/fixtureSpecSchema.js";
import {
  mcpToolCatalogToListToolsResult,
  strictPassthroughToolCatalogTool,
} from "../mcpToolCatalogStore.js";
import {
  readReplayBundleMcpToolCatalogs,
  readReplayBundleToolIoRecords,
} from "../replayBundle.js";
import {
  buildToolIoRequestHash,
  type ToolIoObservationV1,
  type ToolIoRecordV1,
} from "../toolIoSchema.js";

type FixtureRunSplit = "train" | "dev" | "test";
type FixtureRunTaskStatus = "completed" | "completed_with_replay_miss" | "max_turns_exceeded";
type JsonObject = Record<string, unknown>;

export interface OpenAiToolCall {
  id: string;
  type: "function";
  function: {
    name: string;
    arguments: string;
  };
}

export type OpenAiChatMessage =
  | {
    role: "system" | "user";
    content: string;
  }
  | {
    role: "assistant";
    content?: string | null;
    tool_calls?: OpenAiToolCall[];
  }
  | {
    role: "tool";
    tool_call_id: string;
    content: string;
  };

export interface OpenAiFunctionTool {
  type: "function";
  function: {
    name: string;
    description?: string;
    parameters: JsonObject;
  };
}

export interface OpenAiChatCompletionRequest {
  model: string;
  messages: OpenAiChatMessage[];
  tools: OpenAiFunctionTool[];
  tool_choice: "auto";
  temperature: number;
}

export interface OpenAiChatCompletionResponse {
  id?: string;
  choices: Array<{
    index?: number;
    finish_reason?: string | null;
    message: {
      role: "assistant";
      content?: string | null;
      tool_calls?: OpenAiToolCall[];
    };
  }>;
}

export type OpenAiChatCompletionClient = (
  request: OpenAiChatCompletionRequest,
) => Promise<OpenAiChatCompletionResponse>;

export interface EvalFixtureSetOpenAiCompatibleInput {
  fixtureSetRef: string;
  catalogPath: string;
  cacheRoot?: string;
  outputPath?: string;
  split?: FixtureRunSplit;
  maxTasks?: number;
  maxTurns?: number;
  model: string;
  baseUrl: string;
  apiKey: string;
  now?: Date;
  chatCompletionClient?: OpenAiChatCompletionClient;
}

export interface FixtureRunReplayMiss {
  toolName: string;
  requestHash: string;
  sequenceIndex: number;
  liveFallback: false;
}

export interface FixtureSetEvalTaskResult {
  evalPromptId: string;
  taskSpecId?: string;
  status: FixtureRunTaskStatus;
  finalAnswer: string;
  replayMisses: FixtureRunReplayMiss[];
  toolCallCount: number;
}

export interface EvalFixtureSetOpenAiCompatibleResult {
  fixtureSetRef: string;
  cacheRoot?: string;
  outputPath: string;
  liveFallback: false;
  installed: InstallFixtureSetResult;
  runtime: {
    activeFixtureRefs: string[];
    bundlePaths: string[];
    toolCount: number;
  };
  tasks: FixtureSetEvalTaskResult[];
}

interface EvalPrompt {
  id: string;
  taskSpecId?: string;
  title?: string;
  objective?: string;
  prompt: string;
  allowedFixtures?: string[];
  expectedOutcome?: {
    mustMention?: string[];
    mustNotDo?: string[];
  };
  replay?: {
    expectedMisses?: unknown[];
    allowedMisses?: unknown[];
  };
}

interface TaskSplits {
  schema_version: "datalox_task_splits.v1";
  fixtureSetRef: string;
  splits: Record<FixtureRunSplit, string[]>;
}

interface ReplayWorld {
  tools: OpenAiFunctionTool[];
  toolNames: Set<string>;
  recordsByReplayKey: Map<string, ToolIoRecordV1>;
  replayCounters: Map<string, number>;
}

interface ToolCallRunResult {
  message: OpenAiChatMessage;
  miss?: FixtureRunReplayMiss;
  toolName: string;
  arguments: unknown;
  observation?: ToolIoObservationV1;
}

export async function evalFixtureSetOpenAiCompatible(
  input: EvalFixtureSetOpenAiCompatibleInput,
): Promise<EvalFixtureSetOpenAiCompatibleResult> {
  const installed = await installFixtureSet({
    ref: input.fixtureSetRef,
    catalogPath: input.catalogPath,
    cacheRoot: input.cacheRoot,
  });
  const runtime = await resolveFixtureSetRuntime({
    ref: input.fixtureSetRef,
    cacheRoot: input.cacheRoot,
  });
  if (!runtime.evalPromptsPath) {
    throw new Error(`Fixture set ${runtime.ref} does not declare evalPrompts.`);
  }
  if (input.split && !runtime.splitsPath) {
    throw new Error(`Fixture set ${runtime.ref} does not declare splits; cannot select split ${input.split}.`);
  }

  const [taskSpecs, evalPrompts, splits, replayWorld] = await Promise.all([
    readTaskSpecs(runtime),
    readEvalPrompts(runtime.evalPromptsPath),
    runtime.splitsPath ? readTaskSplits(runtime.splitsPath) : Promise.resolve(undefined),
    buildReplayWorld(runtime),
  ]);
  assertSplitMatchesFixtureSet(runtime.ref, splits);
  const selectedPrompts = selectEvalPrompts(evalPrompts, splits, input.split, input.maxTasks);
  const client = input.chatCompletionClient ?? buildOpenAiCompatibleClient(input);
  const createdAt = (input.now ?? new Date()).toISOString();
  const rows: JsonObject[] = [];
  const taskResults: FixtureSetEvalTaskResult[] = [];

  for (const evalPrompt of selectedPrompts) {
    const taskSpec = evalPrompt.taskSpecId ? taskSpecs.get(evalPrompt.taskSpecId) : undefined;
    const taskRun = await runOneTask({
      input,
      runtime,
      evalPrompt,
      taskSpec,
      replayWorld,
      client,
      createdAt,
    });
    rows.push(taskRun.row);
    taskResults.push(taskRun.result);
  }

  const outputPath = path.resolve(input.outputPath ?? defaultFixtureRunOutputPath(runtime.ref));
  await mkdir(path.dirname(outputPath), { recursive: true });
  await writeFile(
    outputPath,
    rows.length === 0 ? "" : `${rows.map((row) => JSON.stringify(row)).join("\n")}\n`,
    "utf8",
  );

  return {
    fixtureSetRef: runtime.ref,
    ...(input.cacheRoot !== undefined ? { cacheRoot: input.cacheRoot } : {}),
    outputPath,
    liveFallback: false,
    installed,
    runtime: {
      activeFixtureRefs: runtime.activeFixtureRefs,
      bundlePaths: runtime.bundlePaths,
      toolCount: replayWorld.tools.length,
    },
    tasks: taskResults,
  };
}

async function runOneTask(input: {
  input: EvalFixtureSetOpenAiCompatibleInput;
  runtime: FixtureSetRuntime;
  evalPrompt: EvalPrompt;
  taskSpec?: TaskSpec;
  replayWorld: ReplayWorld;
  client: OpenAiChatCompletionClient;
  createdAt: string;
}): Promise<{ row: JsonObject; result: FixtureSetEvalTaskResult }> {
  const maxTurns = input.input.maxTurns ?? 8;
  const messages: OpenAiChatMessage[] = [
    {
      role: "system",
      content: buildSystemPrompt(input.runtime),
    },
    {
      role: "user",
      content: buildUserPrompt(input.evalPrompt, input.taskSpec),
    },
  ];
  const replayMisses: FixtureRunReplayMiss[] = [];
  const toolCalls: Array<{
    tool_name: string;
    arguments: unknown;
    request_hash?: string;
    sequence_index?: number;
    observation?: ToolIoObservationV1;
  }> = [];
  let finalAnswer = "";
  let status: FixtureRunTaskStatus = "max_turns_exceeded";

  for (let turn = 0; turn < maxTurns; turn += 1) {
    const response = await input.client({
      model: input.input.model,
      messages,
      tools: input.replayWorld.tools,
      tool_choice: "auto",
      temperature: 0,
    });
    const message = firstAssistantMessage(response);
    const modelToolCalls = message.tool_calls ?? [];

    if (modelToolCalls.length === 0) {
      finalAnswer = message.content ?? "";
      status = replayMisses.length > 0 ? "completed_with_replay_miss" : "completed";
      messages.push({
        role: "assistant",
        content: finalAnswer,
      });
      break;
    }

    messages.push({
      role: "assistant",
      content: message.content ?? null,
      tool_calls: modelToolCalls,
    });
    for (const toolCall of modelToolCalls) {
      const toolRun = runToolCall(input.runtime, input.replayWorld, toolCall);
      messages.push(toolRun.message);
      if (toolRun.miss) {
        replayMisses.push(toolRun.miss);
      }
      toolCalls.push({
        tool_name: toolRun.toolName,
        arguments: toolRun.arguments,
        ...(toolRun.miss
          ? {
            request_hash: toolRun.miss.requestHash,
            sequence_index: toolRun.miss.sequenceIndex,
          }
          : {}),
        ...(toolRun.observation ? { observation: toolRun.observation } : {}),
      });
    }
  }

  const result: FixtureSetEvalTaskResult = {
    evalPromptId: input.evalPrompt.id,
    ...(input.evalPrompt.taskSpecId !== undefined ? { taskSpecId: input.evalPrompt.taskSpecId } : {}),
    status,
    finalAnswer,
    replayMisses,
    toolCallCount: toolCalls.length,
  };

  return {
    result,
    row: buildFixtureRunRow({
      input: input.input,
      runtime: input.runtime,
      evalPrompt: input.evalPrompt,
      taskSpec: input.taskSpec,
      createdAt: input.createdAt,
      messages,
      toolCalls,
      replayMisses,
      finalAnswer,
      status,
    }),
  };
}

function runToolCall(
  runtime: FixtureSetRuntime,
  replayWorld: ReplayWorld,
  toolCall: OpenAiToolCall,
): ToolCallRunResult {
  const toolName = toolCall.function.name;
  const toolArguments = parseToolArguments(toolCall.function.arguments);
  const requestHash = buildToolIoRequestHash(toolName, toolArguments);
  const sequenceIndex = nextReplaySequenceIndex(replayWorld.replayCounters, requestHash);
  const record = replayWorld.recordsByReplayKey.get(`${requestHash}:${sequenceIndex}`);
  if (!record) {
    const miss: FixtureRunReplayMiss = {
      toolName,
      requestHash,
      sequenceIndex,
      liveFallback: false,
    };
    return {
      message: {
        role: "tool",
        tool_call_id: toolCall.id,
        content: JSON.stringify({
          error: {
            code: "replay_miss",
            message: `No tool_io_record.v1 replay record for request_hash=${requestHash} sequence_index=${sequenceIndex}.`,
            request_hash: requestHash,
            sequence_index: sequenceIndex,
            tool_name: toolName,
            active_fixture_refs: runtime.activeFixtureRefs,
            available_tool_names: Array.from(replayWorld.toolNames).sort(),
            liveFallback: false,
          },
        }),
      },
      miss,
      toolName,
      arguments: toolArguments,
    };
  }
  return {
    message: {
      role: "tool",
      tool_call_id: toolCall.id,
      content: observationToToolMessageContent(record.observation),
    },
    toolName,
    arguments: toolArguments,
    observation: record.observation,
  };
}

async function buildReplayWorld(runtime: FixtureSetRuntime): Promise<ReplayWorld> {
  const records = (await Promise.all(runtime.bundlePaths.map((bundlePath) => (
    readReplayBundleToolIoRecords({ bundlePath })
  )))).flat();
  const catalogs = (await Promise.all(runtime.bundlePaths.map((bundlePath) => (
    readReplayBundleMcpToolCatalogs({ bundlePath })
  )))).flat();
  const recordsByReplayKey = indexBundleToolIoRecords(records);
  const listToolsResult = buildReplayListToolsResult(catalogs, records);
  const toolNames = new Set(listToolsResult.tools.map((tool) => tool.name));
  const tools = listToolsResult.tools.map(openAiToolFromMcpTool);
  return {
    tools,
    toolNames,
    recordsByReplayKey,
    replayCounters: new Map(),
  };
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

function openAiToolFromMcpTool(tool: ListToolsResult["tools"][number]): OpenAiFunctionTool {
  return {
    type: "function",
    function: {
      name: tool.name,
      ...(tool.description !== undefined ? { description: tool.description } : {}),
      parameters: asJsonObject(tool.inputSchema),
    },
  };
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

async function readTaskSpecs(runtime: FixtureSetRuntime): Promise<Map<string, TaskSpec>> {
  const specs = new Map<string, TaskSpec>();
  for (const resolvedSpec of runtime.specs.taskSpecs) {
    const spec = parseTaskSpec(JSON.parse(await readFile(resolvedSpec.absolutePath, "utf8")));
    specs.set(spec.id, spec);
  }
  return specs;
}

async function readEvalPrompts(evalPromptsPath: string): Promise<EvalPrompt[]> {
  const rows = (await readFile(evalPromptsPath, "utf8"))
    .split(/\r?\n/u)
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
    .map((line) => parseEvalPrompt(JSON.parse(line)));
  return rows;
}

function parseEvalPrompt(input: unknown): EvalPrompt {
  if (!input || typeof input !== "object" || Array.isArray(input)) {
    throw new Error("Eval prompt rows must be JSON objects.");
  }
  const row = input as Record<string, unknown>;
  if (typeof row.id !== "string" || row.id.length === 0) {
    throw new Error("Eval prompt row requires id.");
  }
  if (typeof row.prompt !== "string" || row.prompt.length === 0) {
    throw new Error(`Eval prompt ${row.id} requires prompt.`);
  }
  return {
    id: row.id,
    ...(typeof row.taskSpecId === "string" ? { taskSpecId: row.taskSpecId } : {}),
    ...(typeof row.title === "string" ? { title: row.title } : {}),
    ...(typeof row.objective === "string" ? { objective: row.objective } : {}),
    prompt: row.prompt,
    ...(Array.isArray(row.allowedFixtures) ? { allowedFixtures: row.allowedFixtures.filter(isString) } : {}),
    ...(isExpectedOutcome(row.expectedOutcome) ? { expectedOutcome: row.expectedOutcome } : {}),
    ...(isReplayMetadata(row.replay) ? { replay: row.replay } : {}),
  };
}

async function readTaskSplits(splitsPath: string): Promise<TaskSplits> {
  const parsed = JSON.parse(await readFile(splitsPath, "utf8"));
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("Task splits must be a JSON object.");
  }
  const splits = parsed as Record<string, unknown>;
  if (splits.schema_version !== "datalox_task_splits.v1") {
    throw new Error("Task splits schema_version must be datalox_task_splits.v1.");
  }
  if (typeof splits.fixtureSetRef !== "string") {
    throw new Error("Task splits require fixtureSetRef.");
  }
  if (!splits.splits || typeof splits.splits !== "object" || Array.isArray(splits.splits)) {
    throw new Error("Task splits require splits.");
  }
  const groups = splits.splits as Record<string, unknown>;
  return {
    schema_version: "datalox_task_splits.v1",
    fixtureSetRef: splits.fixtureSetRef,
    splits: {
      train: parseSplitTaskIds(groups.train, "train"),
      dev: parseSplitTaskIds(groups.dev, "dev"),
      test: parseSplitTaskIds(groups.test, "test"),
    },
  };
}

function selectEvalPrompts(
  evalPrompts: EvalPrompt[],
  splits: TaskSplits | undefined,
  split: FixtureRunSplit | undefined,
  maxTasks: number | undefined,
): EvalPrompt[] {
  let selected = evalPrompts;
  if (split) {
    const taskIds = new Set((splits?.splits[split] ?? []));
    selected = evalPrompts.filter((prompt) => prompt.taskSpecId && taskIds.has(prompt.taskSpecId));
  }
  return typeof maxTasks === "number" ? selected.slice(0, maxTasks) : selected;
}

function assertSplitMatchesFixtureSet(ref: string, splits: TaskSplits | undefined): void {
  if (splits && splits.fixtureSetRef !== ref) {
    throw new Error(`Task splits fixtureSetRef mismatch: expected ${ref}, got ${splits.fixtureSetRef}.`);
  }
}

function buildSystemPrompt(runtime: FixtureSetRuntime): string {
  return [
    `You are running in Datalox replay fixture set ${runtime.ref}.`,
    "Use only the model-visible tools provided by this replay world.",
    "Do not call live tools, claim live service access, or invent observations.",
    "If a tool returns replay_miss, treat it as a finite replay-world boundary and recover from the available evidence.",
    "The replay contract has liveFallback=false.",
  ].join("\n");
}

function buildUserPrompt(evalPrompt: EvalPrompt, taskSpec: TaskSpec | undefined): string {
  return JSON.stringify({
    eval_prompt_id: evalPrompt.id,
    task_spec_id: evalPrompt.taskSpecId,
    title: evalPrompt.title,
    objective: evalPrompt.objective,
    prompt: evalPrompt.prompt,
    task_goal: taskSpec?.goal,
    success_criteria: taskSpec?.successCriteria,
    constraints: taskSpec?.constraints,
    expected_outcome: evalPrompt.expectedOutcome,
  }, null, 2);
}

function buildFixtureRunRow(input: {
  input: EvalFixtureSetOpenAiCompatibleInput;
  runtime: FixtureSetRuntime;
  evalPrompt: EvalPrompt;
  taskSpec?: TaskSpec;
  createdAt: string;
  messages: OpenAiChatMessage[];
  toolCalls: Array<{
    tool_name: string;
    arguments: unknown;
    request_hash?: string;
    sequence_index?: number;
    observation?: ToolIoObservationV1;
  }>;
  replayMisses: FixtureRunReplayMiss[];
  finalAnswer: string;
  status: FixtureRunTaskStatus;
}): JsonObject {
  return {
    schema_version: "datalox_fixture_run.v1",
    id: `${input.runtime.ref}:${input.evalPrompt.id}`,
    created_at: input.createdAt,
    fixture_set_ref: input.runtime.ref,
    split: input.input.split,
    model: {
      provider: "openai_compatible",
      name: input.input.model,
      base_url: input.input.baseUrl,
    },
    task: {
      eval_prompt_id: input.evalPrompt.id,
      task_spec_id: input.evalPrompt.taskSpecId,
      task_family: input.taskSpec?.taskFamily,
      difficulty: input.taskSpec?.difficulty,
      expected_tools: input.taskSpec?.expectedTools,
      forbidden_behavior: input.taskSpec?.forbiddenBehavior,
      prompt: input.evalPrompt.prompt,
    },
    messages: input.messages,
    tool_calls: input.toolCalls,
    replay: {
      live_fallback: false,
      active_fixture_refs: input.runtime.activeFixtureRefs,
      bundle_paths: input.runtime.bundlePaths,
      misses: input.replayMisses.map((miss) => ({
        tool_name: miss.toolName,
        request_hash: miss.requestHash,
        sequence_index: miss.sequenceIndex,
        live_fallback: false,
      })),
    },
    sft: {
      use: input.taskSpec?.sftEligible ?? false,
    },
    preference: {
      use: input.taskSpec?.preferenceEligible ?? false,
    },
    quality: "unlabeled",
    status: input.status,
    final_answer: input.finalAnswer,
  };
}

function buildOpenAiCompatibleClient(input: EvalFixtureSetOpenAiCompatibleInput): OpenAiChatCompletionClient {
  return async (request) => {
    const response = await fetch(`${input.baseUrl.replace(/\/+$/u, "")}/chat/completions`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: `Bearer ${input.apiKey}`,
      },
      body: JSON.stringify(request),
    });
    const body = await response.text();
    if (!response.ok) {
      throw new Error(`OpenAI-compatible chat completion failed with HTTP ${response.status}: ${body}`);
    }
    return JSON.parse(body) as OpenAiChatCompletionResponse;
  };
}

function firstAssistantMessage(response: OpenAiChatCompletionResponse): OpenAiChatCompletionResponse["choices"][number]["message"] {
  const choice = response.choices[0];
  if (!choice) {
    throw new Error("OpenAI-compatible chat completion response contained no choices.");
  }
  return choice.message;
}

function observationToToolMessageContent(observation: ToolIoObservationV1): string {
  if (observation.status === "ok") {
    return JSON.stringify({
      status: "ok",
      content: observation.content ?? null,
    });
  }
  return JSON.stringify({
    error: {
      code: observation.error_code ?? "recorded_tool_error",
      message: observation.error_message ?? "Recorded tool call failed.",
      recorded: true,
      liveFallback: false,
    },
  });
}

function parseToolArguments(value: string): JsonObject {
  const parsed = JSON.parse(value) as unknown;
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("OpenAI-compatible tool call arguments must be a JSON object.");
  }
  return parsed as JsonObject;
}

function asJsonObject(value: unknown): JsonObject {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return {
      type: "object",
      additionalProperties: true,
    };
  }
  return value as JsonObject;
}

function parseSplitTaskIds(input: unknown, split: FixtureRunSplit): string[] {
  if (!Array.isArray(input) || !input.every(isString)) {
    throw new Error(`Task split ${split} must be an array of task ids.`);
  }
  return input;
}

function isString(value: unknown): value is string {
  return typeof value === "string";
}

function isExpectedOutcome(value: unknown): value is NonNullable<EvalPrompt["expectedOutcome"]> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function isReplayMetadata(value: unknown): value is NonNullable<EvalPrompt["replay"]> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function defaultFixtureRunOutputPath(fixtureSetRef: string): string {
  return path.join(
    "exports",
    "fixture-runs",
    `${fixtureSetRef.replace(/[^a-z0-9.-]+/giu, "-")}.datalox_fixture_run.v1.jsonl`,
  );
}
