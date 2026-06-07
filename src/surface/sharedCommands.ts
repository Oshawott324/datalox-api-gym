import { z } from "zod";

import { adoptPack } from "../core/packCore.js";

type CliArgsLike = Record<string, string | string[] | boolean> & { _: string[] };
type SharedArgKind = "string";

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
}

export interface SharedCommandSpec {
  cliCommand?: string;
  mcpTool: string;
  description: string;
  args: readonly SharedArgSpec[];
  run(input: Record<string, unknown>): Promise<unknown>;
}

const packSourceArg: SharedArgSpec = {
  key: "packSource",
  description: "Optional local path or git URL for the source package.",
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

function maybeString(value: unknown): string | undefined {
  return typeof value === "string" && value.length > 0 ? value : undefined;
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

function parseCliValue(spec: SharedArgSpec, value: string | string[] | boolean | undefined): unknown {
  switch (spec.kind) {
    case "string":
      return lastScalar(value);
  }
}

function isMissingCliValue(value: unknown): boolean {
  return value === undefined;
}

function buildMcpArgSchema(spec: SharedArgSpec): z.ZodTypeAny {
  let schema: z.ZodTypeAny;
  switch (spec.kind) {
    case "string":
      schema = z.string();
      break;
  }
  if (!(spec.mcpRequired ?? false)) {
    schema = schema.optional();
  }
  return schema.describe(spec.description);
}

const sharedCommandsInternal: SharedCommandSpec[] = [
  {
    cliCommand: "adopt",
    mcpTool: "adopt_pack",
    description: "Copy the Datalox API Gym replay surfaces into a host repo from the current repo or a git URL.",
    args: [hostRepoPathArg, packSourceArg],
    async run(input) {
      return adoptPack({
        hostRepoPath: maybeString(input.hostRepoPath) ?? "",
        packSource: maybeString(input.packSource),
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
  const shape: Record<string, z.ZodTypeAny> = {};
  for (const arg of spec.args) {
    if (arg.mcpKey) {
      shape[arg.mcpKey] = buildMcpArgSchema(arg);
    }
  }
  return shape;
}

export function parseSharedMcpInput(spec: SharedCommandSpec, input: Record<string, unknown>): Record<string, unknown> {
  const normalized: Record<string, unknown> = {};
  for (const arg of spec.args) {
    if (!arg.mcpKey) {
      continue;
    }
    const value = input[arg.mcpKey];
    if (arg.mcpRequired && value === undefined) {
      throw new Error(`${spec.mcpTool} requires ${arg.mcpKey}`);
    }
    if (value !== undefined) {
      normalized[arg.key] = value;
    }
  }
  return normalized;
}
