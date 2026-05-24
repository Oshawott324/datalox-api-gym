import type { OpenAiCompatibleModelConfig } from "./modelConfig.js";

export interface OpenAiCompatibleMessage {
  role: "system" | "user" | "assistant" | "tool";
  content: string | null;
  name?: string;
  tool_call_id?: string;
  tool_calls?: Array<Record<string, unknown>>;
}

export interface OpenAiCompatibleTool {
  type: "function";
  function: {
    name: string;
    description?: string;
    parameters?: unknown;
  };
}

export type OpenAiCompatibleToolChoice =
  | "none"
  | "auto"
  | "required"
  | {
    type: "function";
    function: {
      name: string;
    };
  };

export interface CreateChatCompletionInput {
  messages: OpenAiCompatibleMessage[];
  tools?: OpenAiCompatibleTool[];
  temperature?: number;
  topP?: number;
  maxTokens?: number;
  toolChoice?: OpenAiCompatibleToolChoice;
  parallelToolCalls?: boolean;
}

export interface ModelToolCall {
  id: string;
  name: string;
  argumentsJson: string;
}

export interface ModelAssistantResponse {
  content: string | null;
  toolCalls: ModelToolCall[];
  finishReason?: string;
}

interface OpenAiChatCompletionResponse {
  choices?: Array<{
    finish_reason?: string;
    message?: {
      content?: unknown;
      tool_calls?: unknown;
    };
  }>;
}

export class OpenAiCompatibleClient {
  private readonly config: OpenAiCompatibleModelConfig;

  constructor(config: OpenAiCompatibleModelConfig) {
    this.config = config;
  }

  async createChatCompletion(input: CreateChatCompletionInput): Promise<ModelAssistantResponse> {
    const response = await this.post<OpenAiChatCompletionResponse>(
      `${this.config.baseUrl}/chat/completions`,
      this.buildRequestBody(input),
    );
    return parseAssistantResponse(response);
  }

  private buildRequestBody(input: CreateChatCompletionInput): Record<string, unknown> {
    const body: Record<string, unknown> = {
      model: this.config.model,
      messages: input.messages,
      parallel_tool_calls: input.parallelToolCalls ?? false,
    };

    const tools = input.tools;
    if (tools !== undefined) body.tools = tools;

    const temperature = input.temperature ?? this.config.temperature;
    if (temperature !== undefined) body.temperature = temperature;

    const topP = input.topP ?? this.config.topP;
    if (topP !== undefined) body.top_p = topP;

    const maxTokens = input.maxTokens ?? this.config.maxTokens;
    if (maxTokens !== undefined) body.max_tokens = maxTokens;

    if (input.toolChoice !== undefined) body.tool_choice = input.toolChoice;

    return body;
  }

  private async post<T>(url: string, body: unknown): Promise<T> {
    const headers: Record<string, string> = {
      "content-type": "application/json",
    };
    if (this.config.apiKey !== undefined) {
      headers.authorization = `Bearer ${this.config.apiKey}`;
    }

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.config.timeoutMs);
    try {
      const response = await fetch(url, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      if (!response.ok) {
        const text = await response.text().catch(() => "");
        throw new Error(`OpenAI-compatible POST ${url} failed (${response.status}): ${text}`);
      }
      return (await response.json()) as T;
    } finally {
      clearTimeout(timer);
    }
  }
}

function parseAssistantResponse(response: OpenAiChatCompletionResponse): ModelAssistantResponse {
  const choice = response.choices?.[0];
  if (choice?.message === undefined) {
    throw new Error("OpenAI-compatible response missing first assistant message");
  }

  return {
    content: parseContent(choice.message.content),
    toolCalls: parseToolCalls(choice.message.tool_calls),
    finishReason: choice.finish_reason,
  };
}

function parseContent(content: unknown): string | null {
  if (content === undefined || content === null) return null;
  if (typeof content !== "string") {
    throw new Error("OpenAI-compatible assistant content must be a string or null");
  }
  return content;
}

function parseToolCalls(value: unknown): ModelToolCall[] {
  if (value === undefined || value === null) return [];
  if (!Array.isArray(value)) {
    throw new Error("OpenAI-compatible assistant tool_calls must be an array");
  }
  return value.map((toolCall, index) => parseToolCall(toolCall, index));
}

function parseToolCall(value: unknown, index: number): ModelToolCall {
  if (!isRecord(value)) {
    throw new Error(`OpenAI-compatible tool call ${index} must be an object`);
  }
  if (typeof value.id !== "string" || value.id.length === 0) {
    throw new Error(`OpenAI-compatible tool call ${index} missing id`);
  }
  if (!isRecord(value.function)) {
    throw new Error(`OpenAI-compatible tool call ${index} missing function`);
  }
  if (typeof value.function.name !== "string" || value.function.name.length === 0) {
    throw new Error(`OpenAI-compatible tool call ${index} missing function.name`);
  }
  if (typeof value.function.arguments !== "string") {
    throw new Error(`OpenAI-compatible tool call ${index} missing function.arguments`);
  }

  return {
    id: value.id,
    name: value.function.name,
    argumentsJson: value.function.arguments,
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
