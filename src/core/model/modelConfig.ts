export interface OpenAiCompatibleModelConfig {
  baseUrl: string;
  model: string;
  apiKey?: string;
  timeoutMs: number;
  temperature?: number;
  topP?: number;
  maxTokens?: number;
}

export interface OpenAiCompatibleModelConfigInput {
  baseUrl?: unknown;
  model?: unknown;
  apiKey?: unknown;
  apiKeyEnv?: unknown;
  timeoutMs?: unknown;
  temperature?: unknown;
  topP?: unknown;
  maxTokens?: unknown;
}

const DEFAULT_TIMEOUT_MS = 60_000;

export function parseOpenAiCompatibleModelConfig(
  input: OpenAiCompatibleModelConfigInput,
): OpenAiCompatibleModelConfig {
  const baseUrl = requireNonEmptyString(input.baseUrl, "baseUrl").replace(/\/+$/, "");
  const model = requireNonEmptyString(input.model, "model");
  const apiKey = optionalString(input.apiKey, "apiKey")
    ?? apiKeyFromEnv(input.apiKeyEnv);

  return {
    baseUrl,
    model,
    apiKey,
    timeoutMs: optionalPositiveInteger(input.timeoutMs, "timeoutMs") ?? DEFAULT_TIMEOUT_MS,
    temperature: optionalNumber(input.temperature, "temperature"),
    topP: optionalNumber(input.topP, "topP"),
    maxTokens: optionalPositiveInteger(input.maxTokens, "maxTokens"),
  };
}

function apiKeyFromEnv(value: unknown): string | undefined {
  const envName = optionalString(value, "apiKeyEnv");
  if (envName === undefined) return undefined;
  const apiKey = process.env[envName];
  return apiKey && apiKey.length > 0 ? apiKey : undefined;
}

function requireNonEmptyString(value: unknown, field: string): string {
  const parsed = optionalString(value, field);
  if (parsed === undefined) {
    throw new Error(`Model config field ${field} must be a non-empty string`);
  }
  return parsed;
}

function optionalString(value: unknown, field: string): string | undefined {
  if (value === undefined) return undefined;
  if (typeof value !== "string" || value.trim().length === 0) {
    throw new Error(`Model config field ${field} must be a non-empty string`);
  }
  return value.trim();
}

function optionalNumber(value: unknown, field: string): number | undefined {
  if (value === undefined) return undefined;
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error(`Model config field ${field} must be a finite number`);
  }
  return value;
}

function optionalPositiveInteger(value: unknown, field: string): number | undefined {
  if (value === undefined) return undefined;
  if (!Number.isInteger(value) || (value as number) <= 0) {
    throw new Error(`Model config field ${field} must be a positive integer`);
  }
  return value as number;
}
