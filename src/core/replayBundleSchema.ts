import { z } from "zod";

const nonEmptyString = z.string().min(1);
const relativeBundlePath = nonEmptyString.superRefine((value, context) => {
  if (value.startsWith("/") || value.includes("\\") || value.split("/").includes("..")) {
    context.addIssue({
      code: "custom",
      message: "path must be a relative bundle path.",
    });
  }
});

const replayBundleTaskSchema = z
  .object({
    prompt: z.string().optional(),
    domains: z.array(z.string()).optional(),
    workflows: z.array(z.string()).optional(),
  })
  .strict();

const replayBundleSourceSchema = z
  .object({
    repo_path: z.string().optional(),
    session_ids: z.array(z.string()),
    turn_event_paths: z.array(relativeBundlePath),
    tool_io_record_paths: z.array(relativeBundlePath),
  })
  .strict();

const replayBundleReplaySchema = z
  .object({
    tool_record_count: z.number().int().nonnegative(),
    turn_count: z.number().int().nonnegative(),
    deterministic: z.boolean(),
  })
  .strict();

const replayBundleExportSchema = z
  .object({
    allowed: z.boolean(),
    redaction: z.enum(["none_needed", "applied", "blocked"]),
    approval_id: z.string().optional(),
  })
  .strict();

const replayBundleDerivativeSchema = z
  .object({
    kind: z.enum(["debugging_trajectory.v1", "agent_task_trajectory.v1", "eval_input.v1"]),
    path: relativeBundlePath,
  })
  .strict();

export const replayBundleV1Schema = z
  .object({
    schema_version: z.literal("replay_bundle.v1"),
    id: nonEmptyString,
    created_at: nonEmptyString,
    title: z.string().optional(),
    task: replayBundleTaskSchema.optional(),
    source: replayBundleSourceSchema,
    replay: replayBundleReplaySchema,
    checksums_path: z.literal("checksums.json"),
    export: replayBundleExportSchema,
    derivatives: z.array(replayBundleDerivativeSchema).optional(),
  })
  .strict();

const replayBundleChecksumFileSchema = z
  .object({
    path: relativeBundlePath,
    sha256: z.string().regex(/^[a-f0-9]{64}$/),
  })
  .strict();

export const replayBundleChecksumsV1Schema = z
  .object({
    schema_version: z.literal("replay_bundle_checksums.v1"),
    replay_bundle_id: nonEmptyString,
    algorithm: z.literal("sha256"),
    files: z.array(replayBundleChecksumFileSchema),
  })
  .strict();

export type ReplayBundleV1 = z.infer<typeof replayBundleV1Schema>;
export type ReplayBundleChecksumsV1 = z.infer<typeof replayBundleChecksumsV1Schema>;

export class ReplayBundleValidationError extends Error {
  readonly issues: z.ZodIssue[];

  constructor(kind: "replay_bundle.v1" | "replay_bundle_checksums.v1", issues: z.ZodIssue[]) {
    super(`Invalid ${kind}: ${formatZodIssues(issues)}`);
    this.name = "ReplayBundleValidationError";
    this.issues = issues;
  }
}

export function parseReplayBundleV1(input: unknown): ReplayBundleV1 {
  const parsed = replayBundleV1Schema.safeParse(input);
  if (!parsed.success) {
    throw new ReplayBundleValidationError("replay_bundle.v1", parsed.error.issues);
  }
  return parsed.data;
}

export function parseReplayBundleChecksumsV1(input: unknown): ReplayBundleChecksumsV1 {
  const parsed = replayBundleChecksumsV1Schema.safeParse(input);
  if (!parsed.success) {
    throw new ReplayBundleValidationError("replay_bundle_checksums.v1", parsed.error.issues);
  }
  return parsed.data;
}

function formatZodIssues(issues: z.ZodIssue[]): string {
  return issues
    .map((issue) => {
      const issuePath = issue.path.length > 0 ? issue.path.join(".") : "<root>";
      return `${issuePath}: ${issue.message}`;
    })
    .join("; ");
}
