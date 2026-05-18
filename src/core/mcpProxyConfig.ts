import { readFile } from "node:fs/promises";
import path from "node:path";

import { z } from "zod";

const nonEmptyString = z.string().min(1);

export const dataloxReplayProxyConfigV1Schema = z
  .object({
    schema_version: z.literal("datalox_replay_proxy_config.v1"),
    upstream: z
      .object({
        command: nonEmptyString,
        args: z.array(z.string()).default([]),
      })
      .strict(),
  })
  .strict();

export type DataloxReplayProxyConfigV1 = z.infer<typeof dataloxReplayProxyConfigV1Schema>;

export class McpProxyConfigValidationError extends Error {
  readonly issues: z.ZodIssue[];

  constructor(issues: z.ZodIssue[]) {
    super(`Invalid datalox_replay_proxy_config.v1: ${formatZodIssues(issues)}`);
    this.name = "McpProxyConfigValidationError";
    this.issues = issues;
  }
}

export function parseDataloxReplayProxyConfigV1(input: unknown): DataloxReplayProxyConfigV1 {
  const parsed = dataloxReplayProxyConfigV1Schema.safeParse(input);
  if (!parsed.success) {
    throw new McpProxyConfigValidationError(parsed.error.issues);
  }
  return parsed.data;
}

export async function readDataloxReplayProxyConfigFile(input: {
  repoPath?: string;
  configPath: string;
}): Promise<DataloxReplayProxyConfigV1> {
  const repoRoot = path.resolve(input.repoPath ?? process.cwd());
  const absoluteConfigPath = path.isAbsolute(input.configPath)
    ? input.configPath
    : path.join(repoRoot, input.configPath);
  return parseDataloxReplayProxyConfigV1(JSON.parse(await readFile(absoluteConfigPath, "utf8")));
}

function formatZodIssues(issues: z.ZodIssue[]): string {
  return issues
    .map((issue) => {
      const issuePath = issue.path.length > 0 ? issue.path.join(".") : "<root>";
      return `${issuePath}: ${issue.message}`;
    })
    .join("; ");
}
