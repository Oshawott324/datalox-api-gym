import { access, readFile } from "node:fs/promises";
import path from "node:path";

import {
  AGENT_INTERFACES,
  AGENT_PROFILES,
  DEFAULT_MAINTENANCE_CONFIG,
  PACK_MODES,
  SOURCE_KINDS,
  type AgentConfig,
  type MaintenanceBacklogThreshold,
} from "../domain/agentConfig.js";

const CONFIG_PATH_ENV = "DATALOX_CONFIG_JSON";
const BASE_URL_ENV = "DATALOX_BASE_URL";
const DEFAULT_WORKFLOW_ENV = "DATALOX_DEFAULT_WORKFLOW";
const AGENT_PROFILE_ENV = "DATALOX_AGENT_PROFILE";
const MODE_ENV = "DATALOX_MODE";

export interface LoadedAgentConfig {
  config: AgentConfig;
  sourcePath: string;
  localOverridePath?: string;
  appliedEnvOverrides: string[];
}

type JsonObject = Record<string, unknown>;

function isRecord(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function deepMerge(base: unknown, override: unknown): unknown {
  if (!isRecord(base) || !isRecord(override)) {
    return override;
  }

  const merged: JsonObject = { ...base };
  for (const [key, value] of Object.entries(override)) {
    const baseValue = merged[key];
    if (isRecord(baseValue) && isRecord(value)) {
      merged[key] = deepMerge(baseValue, value);
      continue;
    }
    merged[key] = value;
  }
  return merged;
}

async function fileExists(filePath: string): Promise<boolean> {
  try {
    await access(filePath);
    return true;
  } catch {
    return false;
  }
}

async function readJsonObject(filePath: string): Promise<JsonObject> {
  const content = await readFile(filePath, "utf8");
  const parsed = JSON.parse(content) as unknown;
  if (!isRecord(parsed)) {
    throw new Error(`Agent config at ${filePath} must be a JSON object`);
  }
  return parsed;
}

function expectString(value: unknown, fieldName: string): string {
  if (typeof value !== "string" || value.length === 0) {
    throw new Error(`Agent config field ${fieldName} must be a non-empty string`);
  }
  return value;
}

function expectBoolean(value: unknown, fieldName: string): boolean {
  if (typeof value !== "boolean") {
    throw new Error(`Agent config field ${fieldName} must be a boolean`);
  }
  return value;
}

function expectOptionalBoolean(value: unknown, fieldName: string): boolean | undefined {
  if (value === undefined) {
    return undefined;
  }
  return expectBoolean(value, fieldName);
}

function expectPositiveInteger(value: unknown, fieldName: string): number {
  if (!Number.isInteger(value) || (value as number) <= 0) {
    throw new Error(`Agent config field ${fieldName} must be a positive integer`);
  }
  return value as number;
}

function expectOptionalPositiveInteger(value: unknown, fieldName: string): number | undefined {
  if (value === undefined) {
    return undefined;
  }
  return expectPositiveInteger(value, fieldName);
}

function expectStringArray(value: unknown, fieldName: string): string[] {
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string")) {
    throw new Error(`Agent config field ${fieldName} must be an array of strings`);
  }
  return value;
}

function expectEnumArray<T extends readonly string[]>(
  value: unknown,
  fieldName: string,
  allowedValues: T,
): T[number][] {
  const values = expectStringArray(value, fieldName);
  for (const item of values) {
    if (!allowedValues.includes(item)) {
      throw new Error(`Agent config field ${fieldName} contains invalid value ${item}`);
    }
  }
  return values as T[number][];
}

function expectEnumValue<T extends readonly string[]>(
  value: unknown,
  fieldName: string,
  allowedValues: T,
): T[number] {
  const resolved = expectString(value, fieldName);
  if (!allowedValues.includes(resolved)) {
    throw new Error(`Agent config field ${fieldName} must be one of ${allowedValues.join(", ")}`);
  }
  return resolved as T[number];
}

function cloneBacklogThreshold(threshold: MaintenanceBacklogThreshold): MaintenanceBacklogThreshold {
  return Object.fromEntries(
    Object.entries(threshold).filter(([, value]) => value !== undefined),
  ) as MaintenanceBacklogThreshold;
}

function validateBacklogThreshold(
  raw: unknown,
  fieldName: string,
  fallback: MaintenanceBacklogThreshold,
): MaintenanceBacklogThreshold {
  if (raw === undefined) {
    return cloneBacklogThreshold(fallback);
  }
  if (!isRecord(raw)) {
    throw new Error(`Agent config field ${fieldName} must be an object`);
  }

  const threshold: MaintenanceBacklogThreshold = {};
  for (const key of ["uncovered", "oldestAgeDays", "maintainableGroups"] as const) {
    const value = expectOptionalPositiveInteger(raw[key], `${fieldName}.${key}`);
    if (value !== undefined) {
      threshold[key] = value;
    }
  }

  if (Object.keys(threshold).length === 0) {
    throw new Error(`Agent config field ${fieldName} must enable at least one backlog signal`);
  }

  return threshold;
}

function validateBacklogPolicy(raw: unknown, fieldName = "maintenance.backlog") {
  if (raw === undefined) {
    return {
      warn: cloneBacklogThreshold(DEFAULT_MAINTENANCE_CONFIG.backlog.warn),
      urgent: cloneBacklogThreshold(DEFAULT_MAINTENANCE_CONFIG.backlog.urgent),
    };
  }
  if (!isRecord(raw)) {
    throw new Error(`Agent config field ${fieldName} must be an object`);
  }

  return {
    warn: validateBacklogThreshold(raw.warn, `${fieldName}.warn`, DEFAULT_MAINTENANCE_CONFIG.backlog.warn),
    urgent: validateBacklogThreshold(raw.urgent, `${fieldName}.urgent`, DEFAULT_MAINTENANCE_CONFIG.backlog.urgent),
  };
}

function validateAutomaticMaintenanceConfig(raw: unknown): AgentConfig["maintenance"]["automatic"] {
  if (raw === undefined) {
    return {
      ...DEFAULT_MAINTENANCE_CONFIG.automatic,
    };
  }
  if (!isRecord(raw)) {
    throw new Error("Agent config field maintenance.automatic must be an object");
  }

  return {
    enabled: expectOptionalBoolean(raw.enabled, "maintenance.automatic.enabled")
      ?? DEFAULT_MAINTENANCE_CONFIG.automatic.enabled,
    write: expectOptionalBoolean(raw.write, "maintenance.automatic.write")
      ?? DEFAULT_MAINTENANCE_CONFIG.automatic.write,
    lockStaleMs: expectOptionalPositiveInteger(raw.lockStaleMs, "maintenance.automatic.lockStaleMs")
      ?? DEFAULT_MAINTENANCE_CONFIG.automatic.lockStaleMs,
  };
}

function validateMaintenanceConfig(raw: unknown): AgentConfig["maintenance"] {
  if (raw === undefined) {
    return {
      maxEvents: DEFAULT_MAINTENANCE_CONFIG.maxEvents,
      minNoteOccurrences: DEFAULT_MAINTENANCE_CONFIG.minNoteOccurrences,
      minSkillOccurrences: DEFAULT_MAINTENANCE_CONFIG.minSkillOccurrences,
      automatic: validateAutomaticMaintenanceConfig(undefined),
      backlog: validateBacklogPolicy(undefined),
    };
  }
  if (!isRecord(raw)) {
    throw new Error("Agent config field maintenance must be an object");
  }

  return {
    maxEvents: expectOptionalPositiveInteger(raw.maxEvents, "maintenance.maxEvents")
      ?? DEFAULT_MAINTENANCE_CONFIG.maxEvents,
    minNoteOccurrences: expectOptionalPositiveInteger(raw.minNoteOccurrences, "maintenance.minNoteOccurrences")
      ?? DEFAULT_MAINTENANCE_CONFIG.minNoteOccurrences,
    minSkillOccurrences: expectOptionalPositiveInteger(raw.minSkillOccurrences, "maintenance.minSkillOccurrences")
      ?? DEFAULT_MAINTENANCE_CONFIG.minSkillOccurrences,
    automatic: validateAutomaticMaintenanceConfig(raw.automatic),
    backlog: validateBacklogPolicy(raw.backlog),
  };
}

function validateAgentConfig(raw: JsonObject): AgentConfig {
  const project = raw.project;
  const sources = raw.sources;
  const agent = raw.agent;
  const paths = raw.paths;
  const runtime = raw.runtime;
  const auth = raw.auth;

  if (!isRecord(project)) {
    throw new Error("Agent config field project must be an object");
  }
  if (!Array.isArray(sources)) {
    throw new Error("Agent config field sources must be an array");
  }
  if (!isRecord(agent)) {
    throw new Error("Agent config field agent must be an object");
  }
  if (!isRecord(paths)) {
    throw new Error("Agent config field paths must be an object");
  }
  if (!isRecord(runtime)) {
    throw new Error("Agent config field runtime must be an object");
  }
  if (!isRecord(auth)) {
    throw new Error("Agent config field auth must be an object");
  }

  const endpoints = runtime.endpoints;
  if (!isRecord(endpoints)) {
    throw new Error("Agent config field runtime.endpoints must be an object");
  }

  return {
    version: expectPositiveInteger(raw.version, "version"),
    mode: expectEnumValue(raw.mode, "mode", PACK_MODES),
    project: {
      id: expectString(project.id, "project.id"),
      name: expectString(project.name, "project.name"),
    },
    sources: sources.map((source, index) => {
      if (!isRecord(source)) {
        throw new Error(`Agent config field sources[${index}] must be an object`);
      }
      return {
        kind: expectEnumValue(source.kind, `sources[${index}].kind`, SOURCE_KINDS),
        name: expectString(source.name, `sources[${index}].name`),
        enabled: expectBoolean(source.enabled, `sources[${index}].enabled`),
        root: expectString(source.root, `sources[${index}].root`),
      };
    }),
    agent: {
      profile: expectEnumValue(agent.profile, "agent.profile", AGENT_PROFILES),
      nativeSkillPolicy: expectEnumValue(
        agent.nativeSkillPolicy,
        "agent.nativeSkillPolicy",
        ["preserve"] as const,
      ),
      detectOnEveryLoop: expectBoolean(agent.detectOnEveryLoop, "agent.detectOnEveryLoop"),
      configReadOrder: expectStringArray(agent.configReadOrder, "agent.configReadOrder"),
      interfaceOrder: expectEnumArray(
        agent.interfaceOrder,
        "agent.interfaceOrder",
        AGENT_INTERFACES,
      ),
    },
    paths: {
      seedSkillsDir: expectString(paths.seedSkillsDir, "paths.seedSkillsDir"),
      seedNotesDir: paths.seedNotesDir === undefined
        ? expectString(paths.seedPatternsDir, "paths.seedPatternsDir")
        : expectString(paths.seedNotesDir, "paths.seedNotesDir"),
      hostSkillsDir: paths.hostSkillsDir === null ? null : expectString(paths.hostSkillsDir, "paths.hostSkillsDir"),
      hostNotesDir: paths.hostNotesDir === undefined
        ? (paths.hostPatternsDir === null ? null : expectString(paths.hostPatternsDir, "paths.hostPatternsDir"))
        : (paths.hostNotesDir === null ? null : expectString(paths.hostNotesDir, "paths.hostNotesDir")),
      seedPatternsDir: paths.seedPatternsDir === undefined ? null : expectString(paths.seedPatternsDir, "paths.seedPatternsDir"),
      hostPatternsDir: paths.hostPatternsDir === null || paths.hostPatternsDir === undefined
        ? null
        : expectString(paths.hostPatternsDir, "paths.hostPatternsDir"),
    },
    maintenance: validateMaintenanceConfig(raw.maintenance),
    runtime: {
      enabled: expectBoolean(runtime.enabled, "runtime.enabled"),
      baseUrl: expectString(runtime.baseUrl, "runtime.baseUrl"),
      defaultWorkflow: expectString(runtime.defaultWorkflow, "runtime.defaultWorkflow"),
      requestTimeoutMs: expectPositiveInteger(runtime.requestTimeoutMs, "runtime.requestTimeoutMs"),
      endpoints: {
        compile: expectString(endpoints.compile, "runtime.endpoints.compile"),
        guidance: expectString(endpoints.guidance, "runtime.endpoints.guidance"),
        publish: expectString(endpoints.publish, "runtime.endpoints.publish"),
        search: expectString(endpoints.search, "runtime.endpoints.search"),
        install: expectString(endpoints.install, "runtime.endpoints.install"),
        ingest: expectString(endpoints.ingest, "runtime.endpoints.ingest"),
        register: expectString(endpoints.register, "runtime.endpoints.register"),
      },
    },
    auth: {
      apiKeyEnv: expectString(auth.apiKeyEnv, "auth.apiKeyEnv"),
      contributorKeyEnv: expectString(auth.contributorKeyEnv, "auth.contributorKeyEnv"),
    },
  };
}

function applyEnvironmentOverrides(config: AgentConfig): {
  config: AgentConfig;
  appliedEnvOverrides: string[];
} {
  const appliedEnvOverrides: string[] = [];
  const nextConfig: AgentConfig = {
    ...config,
    agent: { ...config.agent },
    runtime: { ...config.runtime },
  };

  if (process.env[BASE_URL_ENV]) {
    nextConfig.runtime.baseUrl = process.env[BASE_URL_ENV]!;
    appliedEnvOverrides.push(BASE_URL_ENV);
  }

  if (process.env[DEFAULT_WORKFLOW_ENV]) {
    nextConfig.runtime.defaultWorkflow = process.env[DEFAULT_WORKFLOW_ENV]!;
    appliedEnvOverrides.push(DEFAULT_WORKFLOW_ENV);
  }

  if (process.env[AGENT_PROFILE_ENV]) {
    nextConfig.agent.profile = expectEnumValue(
      process.env[AGENT_PROFILE_ENV],
      AGENT_PROFILE_ENV,
      AGENT_PROFILES,
    );
    appliedEnvOverrides.push(AGENT_PROFILE_ENV);
  }

  if (process.env[MODE_ENV]) {
    nextConfig.mode = expectEnumValue(process.env[MODE_ENV], MODE_ENV, PACK_MODES);
    appliedEnvOverrides.push(MODE_ENV);
  }

  return { config: nextConfig, appliedEnvOverrides };
}

export async function loadAgentConfig(cwd: string = process.cwd()): Promise<LoadedAgentConfig> {
  const configuredPath = process.env[CONFIG_PATH_ENV];
  if (configuredPath) {
    const sourcePath = path.isAbsolute(configuredPath)
      ? configuredPath
      : path.resolve(cwd, configuredPath);
    const rawConfig = await readJsonObject(sourcePath);
    const validated = validateAgentConfig(rawConfig);
    const { config, appliedEnvOverrides } = applyEnvironmentOverrides(validated);
    return {
      config,
      sourcePath,
      appliedEnvOverrides: [CONFIG_PATH_ENV, ...appliedEnvOverrides],
    };
  }

  const sourcePath = path.resolve(cwd, ".datalox/config.json");
  const localOverridePath = path.resolve(cwd, ".datalox/config.local.json");
  const baseConfig = await readJsonObject(sourcePath);
  const mergedConfig = (await fileExists(localOverridePath))
    ? (deepMerge(baseConfig, await readJsonObject(localOverridePath)) as JsonObject)
    : baseConfig;

  const validated = validateAgentConfig(mergedConfig);
  const { config, appliedEnvOverrides } = applyEnvironmentOverrides(validated);

  return {
    config,
    sourcePath,
    localOverridePath: (await fileExists(localOverridePath)) ? localOverridePath : undefined,
    appliedEnvOverrides,
  };
}
