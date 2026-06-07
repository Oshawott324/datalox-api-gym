import path from "node:path";

import type { McpToolCatalogToolV1 } from "../mcpToolCatalogSchema.js";
import { OpenAiCompatibleClient, type OpenAiCompatibleMessage, type OpenAiCompatibleTool } from "../model/openAiCompatibleClient.js";
import { parseOpenAiCompatibleModelConfig, type OpenAiCompatibleModelConfigInput } from "../model/modelConfig.js";
import { sha256Hex } from "../hash.js";
import {
  createReplayToolRuntime,
  type ReplayToolRuntime,
} from "./replayToolRuntime.js";
import { writeRunTranscript } from "./runStore.js";
import { parseDataloxRunV1, type DataloxRunV1, type RunMessage, type RunStep } from "./runTranscriptSchema.js";

export interface RunFixtureAgentInput {
  repoPath?: string;
  cacheRoot?: string;
  fixtureRef?: string;
  fixtureRefs?: string[];
  fixtureSetRef?: string;
  bundlePaths?: string[];
  activeFixtureRefs?: string[];
  prompt: string;
  systemPrompt?: string;
  taskRef?: string;
  model: OpenAiCompatibleModelConfigInput;
  outDir: string;
  maxSteps?: number;
  now?: Date;
}

export interface RunFixtureAgentResult {
  runDir: string;
  runPath: string;
  transcriptPath: string;
  run: DataloxRunV1;
}

const DEFAULT_SYSTEM_PROMPT = [
  "You are an agent running inside a Datalox API world.",
  "Use only the provided tools when tool evidence is needed.",
  "When you have enough evidence, answer directly.",
].join(" ");

export async function runFixtureAgent(input: RunFixtureAgentInput): Promise<RunFixtureAgentResult> {
  const modelConfig = parseOpenAiCompatibleModelConfig(input.model);
  const runtime = await createReplayToolRuntime({
    repoPath: input.repoPath,
    cacheRoot: input.cacheRoot,
    fixtureRef: input.fixtureRef,
    fixtureRefs: input.fixtureRefs,
    fixtureSetRef: input.fixtureSetRef,
    bundlePaths: input.bundlePaths,
    activeFixtureRefs: input.activeFixtureRefs ?? input.fixtureRefs,
  });
  const tools = await runtime.listTools();
  const client = new OpenAiCompatibleClient(modelConfig);
  const messages: RunMessage[] = [
    {
      role: "system",
      content: input.systemPrompt ?? DEFAULT_SYSTEM_PROMPT,
    },
    {
      role: "user",
      content: input.prompt,
    },
  ];
  const steps: RunStep[] = [];
  const maxSteps = input.maxSteps ?? 12;
  let stopReason: DataloxRunV1["stop_reason"] = "max_steps";
  let finalAnswer: string | undefined;

  for (let index = 0; index < maxSteps; index += 1) {
    const assistant = await client.createChatCompletion({
      messages: messages.map(toOpenAiMessage),
      tools: tools.map(toolToOpenAiTool),
      toolChoice: "auto",
      parallelToolCalls: false,
    });
    const assistantMessage = assistantToRunMessage(assistant);
    messages.push(assistantMessage);

    if (assistant.toolCalls.length === 0) {
      finalAnswer = assistant.content ?? "";
      stopReason = "final_answer";
      steps.push({
        index,
        assistant_message: assistantMessage,
      });
      break;
    }

    const toolCall = assistant.toolCalls[0];
    const toolArguments = parseToolArguments(toolCall.argumentsJson, toolCall.name);
    const toolResult = await runtime.callTool({
      name: toolCall.name,
      arguments: toolArguments,
    });
    const toolMessage: RunMessage = {
      role: "tool",
      tool_call_id: toolCall.id,
      name: toolCall.name,
      content: JSON.stringify(toolResult.observation),
    };
    messages.push(toolMessage);
    steps.push({
      index,
      assistant_message: assistantMessage,
      tool_call: {
        id: toolCall.id,
        name: toolCall.name,
        arguments: toolArguments,
      },
      observation: toolResult.observation,
      ...(toolResult.replayMiss ? { replay_miss: toolResult.replayMiss } : {}),
      ...(toolResult.record ? { tool_record_ref: toolResult.record.id } : {}),
    });

    if (toolResult.replayMiss) {
      stopReason = "replay_miss";
      break;
    }
  }

  const createdAt = (input.now ?? new Date()).toISOString();
  const run = parseDataloxRunV1({
    schema_version: "datalox_run.v1",
    id: buildRunId({
      createdAt,
      model: modelConfig.model,
      prompt: input.prompt,
      fixtureRefs: runtime.activeFixtureRefs,
    }),
    created_at: createdAt,
    ...(input.taskRef !== undefined ? { task_ref: input.taskRef } : {}),
    ...(input.fixtureRef !== undefined ? { fixture_ref: input.fixtureRef } : {}),
    fixture_refs: runtime.activeFixtureRefs.length > 0 ? runtime.activeFixtureRefs : ["bundle:local"],
    ...(input.fixtureSetRef !== undefined ? { fixture_set_ref: input.fixtureSetRef } : {}),
    model: {
      provider: "openai_compatible",
      model: modelConfig.model,
      base_url: modelConfig.baseUrl,
      sampling: samplingMetadata(modelConfig),
    },
    messages,
    steps,
    ...(finalAnswer !== undefined ? { final_answer: finalAnswer } : {}),
    stop_reason: stopReason,
    metadata: {
      bundle_paths: runtime.bundlePaths,
      max_steps: maxSteps,
    },
    export: {
      allowed: true,
      redaction: "none_needed",
    },
  });

  return writeRunTranscript({
    run,
    outDir: input.outDir,
  });
}

function toOpenAiMessage(message: RunMessage): OpenAiCompatibleMessage {
  return {
    role: message.role,
    content: message.content,
    ...(message.name !== undefined ? { name: message.name } : {}),
    ...(message.tool_call_id !== undefined ? { tool_call_id: message.tool_call_id } : {}),
    ...(message.tool_calls !== undefined ? { tool_calls: message.tool_calls } : {}),
  };
}

function toolToOpenAiTool(tool: McpToolCatalogToolV1): OpenAiCompatibleTool {
  return {
    type: "function",
    function: {
      name: tool.name,
      ...(tool.description !== undefined ? { description: tool.description } : {}),
      parameters: tool.input_schema,
    },
  };
}

function assistantToRunMessage(assistant: {
  content: string | null;
  toolCalls: Array<{ id: string; name: string; argumentsJson: string }>;
}): RunMessage {
  return {
    role: "assistant",
    content: assistant.content,
    ...(assistant.toolCalls.length > 0
      ? {
        tool_calls: assistant.toolCalls.map((toolCall) => ({
          id: toolCall.id,
          type: "function",
          function: {
            name: toolCall.name,
            arguments: toolCall.argumentsJson,
          },
        })),
      }
      : {}),
  };
}

function parseToolArguments(argumentsJson: string, toolName: string): Record<string, unknown> {
  const parsed = JSON.parse(argumentsJson) as unknown;
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error(`Tool call ${toolName} arguments must parse to a JSON object.`);
  }
  return parsed as Record<string, unknown>;
}

function samplingMetadata(config: ReturnType<typeof parseOpenAiCompatibleModelConfig>): Record<string, unknown> {
  return {
    ...(config.temperature !== undefined ? { temperature: config.temperature } : {}),
    ...(config.topP !== undefined ? { top_p: config.topP } : {}),
    ...(config.maxTokens !== undefined ? { max_tokens: config.maxTokens } : {}),
  };
}

function buildRunId(input: {
  createdAt: string;
  model: string;
  prompt: string;
  fixtureRefs: string[];
}): string {
  return `run-${sha256Hex(JSON.stringify(input)).slice(0, 16)}`;
}

export function defaultRunOutDir(runId: string): string {
  return path.join("runs", runId);
}
