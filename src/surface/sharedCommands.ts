import { readFile } from "node:fs/promises";
import path from "node:path";

import { z } from "zod";

import { adoptPack } from "../core/packCore.js";
import {
  exportAgentTaskTrajectories,
  recordAgentTaskTrajectory,
} from "../core/agentTaskTrajectoryExport.js";
import { exportTrajectories, recordTrajectory } from "../core/trajectoryExport.js";
import { gradeTrajectories } from "../core/trajectoryGrade.js";
import { repairTrajectory } from "../core/trajectoryRepair.js";

type CliArgsLike = Record<string, string | string[] | boolean> & { _: string[] };

type SharedArgKind = "string" | "boolean" | "string[]" | "int" | "enum" | "json";

interface SharedArgOption {
  canonical: string;
  cli?: string;
}

interface SharedArgSpec {
  key: string;
  description: string;
  kind: SharedArgKind;
  cliFlag?: string;
  cliPositionalIndex?: number;
  cliPositionalLabel?: string;
  mcpKey?: string;
  cliRequired?: boolean;
  mcpRequired?: boolean;
  positive?: boolean;
  options?: readonly SharedArgOption[];
}

export interface SharedCommandSpec {
  cliCommand?: string;
  mcpTool: string;
  description: string;
  args: readonly SharedArgSpec[];
  run(input: Record<string, unknown>): Promise<unknown>;
}

const repoPathArg: SharedArgSpec = {
  key: "repoPath",
  description: "Absolute or relative path to the host repo.",
  kind: "string",
  cliFlag: "repo",
  mcpKey: "repo_path",
  mcpRequired: true,
};

const packSourceArg: SharedArgSpec = {
  key: "packSource",
  description: "Optional local path or git URL for the source pack.",
  kind: "string",
  cliFlag: "pack-source",
  mcpKey: "pack_source",
};

const hostRepoPathArg: SharedArgSpec = {
  key: "hostRepoPath",
  description: "Absolute or relative path to the host repo.",
  kind: "string",
  cliPositionalIndex: 0,
  cliPositionalLabel: "<host-repo-path>",
  mcpKey: "host_repo_path",
  cliRequired: true,
  mcpRequired: true,
};

const eventPathArg: SharedArgSpec = {
  key: "eventPath",
  description: "Relative or absolute path to a previously recorded .datalox trajectory event.",
  kind: "string",
  cliFlag: "event-path",
  mcpKey: "event_path",
};

const requiredEventPathArg: SharedArgSpec = {
  ...eventPathArg,
  cliRequired: true,
  mcpRequired: true,
};

const trajectoryOutputPathArg: SharedArgSpec = {
  key: "outputPath",
  description: "Optional output path for the JSONL trajectory export.",
  kind: "string",
  cliFlag: "output",
  mcpKey: "output_path",
};

const trajectoryRowFileArg: SharedArgSpec = {
  key: "trajectoryRowFile",
  description: "Path to a JSON file containing one debugging_trajectory.v1 row.",
  kind: "string",
  cliFlag: "trajectory-row",
};

const requiredTrajectoryRowFileArg: SharedArgSpec = {
  ...trajectoryRowFileArg,
  cliRequired: true,
};

const trajectoryRowArg: SharedArgSpec = {
  key: "trajectoryRow",
  description: "One debugging_trajectory.v1 row object.",
  kind: "json",
  mcpKey: "trajectory_row",
};

const requiredTrajectoryRowArg: SharedArgSpec = {
  ...trajectoryRowArg,
  mcpRequired: true,
};

const agentTaskTrajectoryOutputPathArg: SharedArgSpec = {
  key: "outputPath",
  description: "Optional output path for the JSONL agent_task_trajectory.v1 export.",
  kind: "string",
  cliFlag: "output",
  mcpKey: "output_path",
};

const agentTaskTrajectoryRowFileArg: SharedArgSpec = {
  key: "agentTaskTrajectoryFile",
  description: "Path to a JSON file containing one agent_task_trajectory.v1 row.",
  kind: "string",
  cliFlag: "agent-task-trajectory",
};

const requiredAgentTaskTrajectoryRowFileArg: SharedArgSpec = {
  ...agentTaskTrajectoryRowFileArg,
  cliRequired: true,
};

const agentTaskTrajectoryArg: SharedArgSpec = {
  key: "agentTaskTrajectory",
  description: "One agent_task_trajectory.v1 row object.",
  kind: "json",
  mcpKey: "agent_task_trajectory",
};

const requiredAgentTaskTrajectoryArg: SharedArgSpec = {
  ...agentTaskTrajectoryArg,
  mcpRequired: true,
};

const blockedReportPathArg: SharedArgSpec = {
  key: "blockedReportPath",
  description: "Optional path for an export report that includes blocked trajectory rows.",
  kind: "string",
  cliFlag: "include-blocked-report",
  mcpKey: "include_blocked_report",
};

const splitOptions = [
  { canonical: "train", cli: "train" },
  { canonical: "validation", cli: "validation" },
  { canonical: "test", cli: "test" },
  { canonical: "eval", cli: "eval" },
] as const;

const splitArg: SharedArgSpec = {
  key: "split",
  description: "Optional export-time curation split override.",
  kind: "enum",
  cliFlag: "split",
  mcpKey: "split",
  options: splitOptions,
};

const qualityOptions = [
  { canonical: "use", cli: "use" },
  { canonical: "needs_review", cli: "needs-review" },
  { canonical: "discard", cli: "discard" },
] as const;

const qualityArg: SharedArgSpec = {
  key: "quality",
  description: "Optional curation quality filter.",
  kind: "enum",
  cliFlag: "quality",
  mcpKey: "quality",
  options: qualityOptions,
};

const maxRowCharsArg: SharedArgSpec = {
  key: "maxRowChars",
  description: "Maximum estimated JSON row chars before training readiness fails.",
  kind: "int",
  cliFlag: "max-row-chars",
  mcpKey: "max_row_chars",
  positive: true,
};

const maxPatchCharsArg: SharedArgSpec = {
  key: "maxPatchChars",
  description: "Maximum inline final.patch chars before training readiness fails.",
  kind: "int",
  cliFlag: "max-patch-chars",
  mcpKey: "max_patch_chars",
  positive: true,
};

const maxSnippetCharsArg: SharedArgSpec = {
  key: "maxSnippetChars",
  description: "Maximum inline relevant file snippet chars before training readiness fails.",
  kind: "int",
  cliFlag: "max-snippet-chars",
  mcpKey: "max_snippet_chars",
  positive: true,
};

const maxMetadataCharsArg: SharedArgSpec = {
  key: "maxMetadataChars",
  description: "Maximum inline metadata chars before training readiness fails.",
  kind: "int",
  cliFlag: "max-metadata-chars",
  mcpKey: "max_metadata_chars",
  positive: true,
};

function maybeString(value: unknown): string | undefined {
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

function maybeNumber(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function maybeUnknownObject(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : undefined;
}

function lastScalar(value: string | string[] | boolean | undefined): string | undefined {
  if (Array.isArray(value)) {
    for (let index = value.length - 1; index >= 0; index -= 1) {
      if (typeof value[index] === "string") {
        return value[index];
      }
    }
    return undefined;
  }
  return typeof value === "string" ? value : undefined;
}

function parseCliBoolean(value: string | string[] | boolean | undefined): boolean | undefined {
  if (typeof value === "boolean") {
    return value;
  }
  const raw = lastScalar(value);
  if (raw === undefined) {
    return undefined;
  }
  const normalized = raw.trim().toLowerCase();
  if (["1", "true", "yes", "on"].includes(normalized)) {
    return true;
  }
  if (["0", "false", "no", "off"].includes(normalized)) {
    return false;
  }
  return true;
}

function parseCliInt(spec: SharedArgSpec, value: string | string[] | boolean | undefined): number | undefined {
  const raw = lastScalar(value);
  if (raw === undefined) {
    return undefined;
  }
  const parsed = Number.parseInt(raw, 10);
  if (!Number.isFinite(parsed)) {
    throw new Error(`--${spec.cliFlag} must be an integer`);
  }
  if (spec.positive && parsed <= 0) {
    throw new Error(`--${spec.cliFlag} must be a positive integer`);
  }
  return parsed;
}

function parseCliEnum(spec: SharedArgSpec, value: string | string[] | boolean | undefined): string | undefined {
  const raw = lastScalar(value);
  if (raw === undefined) {
    return undefined;
  }
  const option = spec.options?.find((candidate) => candidate.cli === raw || candidate.canonical === raw);
  if (!option) {
    throw new Error(`--${spec.cliFlag} has unsupported value ${raw}`);
  }
  return option.canonical;
}

function parseCliValue(spec: SharedArgSpec, value: string | string[] | boolean | undefined): unknown {
  switch (spec.kind) {
    case "string":
      return lastScalar(value);
    case "string[]":
      if (value === undefined || value === false || value === true) {
        return [];
      }
      return Array.isArray(value) ? value : [value];
    case "boolean":
      return parseCliBoolean(value);
    case "int":
      return parseCliInt(spec, value);
    case "enum":
      return parseCliEnum(spec, value);
    case "json":
      return undefined;
    default:
      return undefined;
  }
}

function isMissingCliValue(value: unknown): boolean {
  return value === undefined;
}

function mcpArgIsRequired(spec: SharedArgSpec): boolean {
  return spec.mcpRequired ?? false;
}

function buildMcpArgSchema(spec: SharedArgSpec): z.ZodTypeAny {
  let schema: z.ZodTypeAny;
  switch (spec.kind) {
    case "string":
      schema = z.string();
      break;
    case "string[]":
      schema = z.array(z.string());
      break;
    case "boolean":
      schema = z.boolean();
      break;
    case "int":
      schema = spec.positive ? z.number().int().positive() : z.number().int();
      break;
    case "enum": {
      const options = (spec.options ?? []).map((option) => option.canonical);
      schema = z.enum(options as [string, ...string[]]);
      break;
    }
    case "json":
      schema = z.record(z.string(), z.unknown());
      break;
    default:
      schema = z.unknown();
      break;
  }
  if (!mcpArgIsRequired(spec)) {
    schema = schema.optional();
  }
  return schema.describe(spec.description);
}

async function loadJsonRowInput(
  input: Record<string, unknown>,
  directRowKey: string,
  rowFileKey: string,
  required: boolean,
  errorMessage: string,
): Promise<unknown | undefined> {
  const directRow = maybeUnknownObject(input[directRowKey]);
  if (directRow !== undefined) {
    return directRow;
  }
  const rowFile = maybeString(input[rowFileKey]);
  if (rowFile !== undefined) {
    const repoPath = maybeString(input.repoPath);
    const basePath = repoPath ? path.resolve(repoPath) : process.cwd();
    const resolvedPath = path.isAbsolute(rowFile)
      ? rowFile
      : path.join(basePath, rowFile);
    return JSON.parse(await readFile(resolvedPath, "utf8"));
  }
  if (required) {
    throw new Error(errorMessage);
  }
  return undefined;
}

async function loadTrajectoryRowInput(input: Record<string, unknown>, required: boolean): Promise<unknown | undefined> {
  return loadJsonRowInput(
    input,
    "trajectoryRow",
    "trajectoryRowFile",
    required,
    "A debugging_trajectory.v1 row is required.",
  );
}

async function loadAgentTaskTrajectoryInput(
  input: Record<string, unknown>,
  required: boolean,
): Promise<unknown | undefined> {
  return loadJsonRowInput(
    input,
    "agentTaskTrajectory",
    "agentTaskTrajectoryFile",
    required,
    "An agent_task_trajectory.v1 row is required.",
  );
}

const sharedCommandsInternal: SharedCommandSpec[] = [
  {
    cliCommand: "adopt",
    mcpTool: "adopt_pack",
    description: "Copy the Datalox product surfaces into a host repo from the current repo or a git URL.",
    args: [hostRepoPathArg, packSourceArg],
    async run(input) {
      return adoptPack({
        hostRepoPath: maybeString(input.hostRepoPath) ?? "",
        packSource: maybeString(input.packSource),
      });
    },
  },
  {
    cliCommand: "record-trajectory",
    mcpTool: "record_trajectory",
    description: "Record one validated debugging_trajectory.v1 row as a dataset candidate event.",
    args: [repoPathArg, requiredTrajectoryRowFileArg, requiredTrajectoryRowArg],
    async run(input) {
      return recordTrajectory({
        repoPath: maybeString(input.repoPath),
        trajectoryRow: await loadTrajectoryRowInput(input, true),
      });
    },
  },
  {
    cliCommand: "export-trajectories",
    mcpTool: "export_trajectories",
    description: "Export sellable debugging_trajectory.v1 rows from .datalox events into deterministic JSONL.",
    args: [repoPathArg, trajectoryOutputPathArg, blockedReportPathArg, splitArg, qualityArg],
    async run(input) {
      return exportTrajectories({
        repoPath: maybeString(input.repoPath),
        outputPath: maybeString(input.outputPath),
        blockedReportPath: maybeString(input.blockedReportPath),
        split: maybeString(input.split) as "train" | "validation" | "test" | "eval" | undefined,
        quality: maybeString(input.quality) as "use" | "needs_review" | "discard" | undefined,
      });
    },
  },
  {
    cliCommand: "record-agent-task-trajectory",
    mcpTool: "record_agent_task_trajectory",
    description: "Record one validated agent_task_trajectory.v1 row as a mixed-domain dataset candidate event.",
    args: [repoPathArg, requiredAgentTaskTrajectoryRowFileArg, requiredAgentTaskTrajectoryArg],
    async run(input) {
      return recordAgentTaskTrajectory({
        repoPath: maybeString(input.repoPath),
        agentTaskTrajectory: await loadAgentTaskTrajectoryInput(input, true),
      });
    },
  },
  {
    cliCommand: "export-agent-task-trajectories",
    mcpTool: "export_agent_task_trajectories",
    description: "Export sellable agent_task_trajectory.v1 rows from .datalox events into deterministic JSONL.",
    args: [repoPathArg, agentTaskTrajectoryOutputPathArg, blockedReportPathArg, splitArg, qualityArg],
    async run(input) {
      return exportAgentTaskTrajectories({
        repoPath: maybeString(input.repoPath),
        outputPath: maybeString(input.outputPath),
        blockedReportPath: maybeString(input.blockedReportPath),
        split: maybeString(input.split) as "train" | "validation" | "test" | "eval" | undefined,
        quality: maybeString(input.quality) as "use" | "needs_review" | "discard" | undefined,
      });
    },
  },
  {
    cliCommand: "grade-trajectories",
    mcpTool: "grade_trajectories",
    description: "Grade recorded debugging_trajectory.v1 rows for training readiness without mutating events.",
    args: [
      repoPathArg,
      eventPathArg,
      maxRowCharsArg,
      maxPatchCharsArg,
      maxSnippetCharsArg,
      maxMetadataCharsArg,
    ],
    async run(input) {
      return gradeTrajectories({
        repoPath: maybeString(input.repoPath),
        eventPath: maybeString(input.eventPath),
        maxRowChars: maybeNumber(input.maxRowChars),
        maxPatchChars: maybeNumber(input.maxPatchChars),
        maxSnippetChars: maybeNumber(input.maxSnippetChars),
        maxMetadataChars: maybeNumber(input.maxMetadataChars),
      });
    },
  },
  {
    cliCommand: "repair-trajectory",
    mcpTool: "repair_trajectory",
    description: "Record a corrected debugging_trajectory.v1 row as a new .datalox event linked to the original row event.",
    args: [repoPathArg, requiredEventPathArg, requiredTrajectoryRowFileArg, requiredTrajectoryRowArg],
    async run(input) {
      return repairTrajectory({
        repoPath: maybeString(input.repoPath),
        eventPath: maybeString(input.eventPath) ?? "",
        trajectoryRow: await loadTrajectoryRowInput(input, true),
      });
    },
  },
];

export const SHARED_COMMANDS: readonly SharedCommandSpec[] = sharedCommandsInternal;

export function getSharedCliCommand(commandName: string | undefined): SharedCommandSpec | undefined {
  if (!commandName) {
    return undefined;
  }
  return SHARED_COMMANDS.find((spec) => spec.cliCommand === commandName);
}

export function getSharedMcpCommands(): readonly SharedCommandSpec[] {
  return SHARED_COMMANDS;
}

export function parseSharedCliInput(spec: SharedCommandSpec, args: CliArgsLike): Record<string, unknown> {
  const input: Record<string, unknown> = {};
  const positionals = args._.slice(1);
  for (const arg of spec.args) {
    const raw = arg.cliPositionalIndex !== undefined
      ? positionals[arg.cliPositionalIndex]
      : arg.cliFlag
        ? args[arg.cliFlag]
        : undefined;
    const parsed = parseCliValue(arg, raw);
    if (arg.cliRequired && isMissingCliValue(parsed)) {
      if (arg.cliPositionalLabel) {
        throw new Error(`${spec.cliCommand} requires ${arg.cliPositionalLabel}`);
      }
      throw new Error(`${spec.cliCommand} requires --${arg.cliFlag}`);
    }
    if (!isMissingCliValue(parsed)) {
      input[arg.key] = parsed;
    }
  }
  return input;
}

export function buildSharedMcpInputSchema(spec: SharedCommandSpec): Record<string, z.ZodTypeAny> {
  const schema: Record<string, z.ZodTypeAny> = {};
  for (const arg of spec.args) {
    if (!arg.mcpKey) {
      continue;
    }
    schema[arg.mcpKey] = buildMcpArgSchema(arg);
  }
  return schema;
}

export function parseSharedMcpInput(spec: SharedCommandSpec, input: Record<string, unknown>): Record<string, unknown> {
  const normalized: Record<string, unknown> = {};
  for (const arg of spec.args) {
    if (!arg.mcpKey) {
      continue;
    }
    if (input[arg.mcpKey] !== undefined) {
      normalized[arg.key] = input[arg.mcpKey];
    }
  }
  return normalized;
}
