import { z } from "zod";

const nonEmptyString = z.string().min(1);

export const debuggingTrajectoryV1Schema = z.object({
  schema_version: z.literal("debugging_trajectory.v1"),
  id: nonEmptyString,
  created_at: nonEmptyString,
  task: z
    .object({
      domain: z.literal("coding_debugging"),
      prompt: nonEmptyString,
      language: z.string().optional(),
      environment: z.string().optional(),
    })
    .strict(),
  context: z
    .object({
      error: z.string().optional(),
      relevant_files: z
        .array(
          z
            .object({
              path: nonEmptyString,
              before: z.string().optional(),
              after: z.string().optional(),
            })
            .strict(),
        )
        .optional(),
      notes: z.array(z.string()).optional(),
    })
    .strict(),
  trajectory: z
    .array(
      z
        .object({
          role: z.enum(["user", "agent", "tool"]),
          content: nonEmptyString,
          tool: z.string().optional(),
          command: z.string().optional(),
          exit_code: z.number().int().optional(),
          files_changed: z.array(z.string()).optional(),
        })
        .strict(),
    )
    .min(1),
  final: z
    .object({
      fix_summary: nonEmptyString,
      patch: z.string().optional(),
      changed_files: z.array(z.string()).optional(),
      explanation: z.string().optional(),
    })
    .strict(),
  outcome: z
    .object({
      label: z.enum(["success", "failure", "partial"]),
      verification: z.enum(["passed", "failed", "not_run", "reviewed"]),
      command: z.string().optional(),
      evidence: z.string().optional(),
    })
    .strict(),
  export: z
    .object({
      allowed: z.boolean(),
      redaction: z.enum(["none_needed", "applied", "blocked"]),
      source_event_paths: z.array(z.string()).optional(),
    })
    .strict(),
  curation: z
    .object({
      split: z.enum(["train", "validation", "test", "eval"]).optional(),
      quality: z.enum(["use", "needs_review", "discard"]).optional(),
      tags: z.array(z.string()).optional(),
      notes: z.string().optional(),
    })
    .strict()
    .optional(),
  metadata: z.record(z.string(), z.unknown()).optional(),
}).strict();

export type DebuggingTrajectoryV1 = z.infer<typeof debuggingTrajectoryV1Schema>;

export class TrajectoryValidationError extends Error {
  readonly issues: z.ZodIssue[];

  constructor(issues: z.ZodIssue[]) {
    super(`Invalid debugging_trajectory.v1 row: ${formatZodIssues(issues)}`);
    this.name = "TrajectoryValidationError";
    this.issues = issues;
  }
}

export function parseDebuggingTrajectoryV1(input: unknown): DebuggingTrajectoryV1 {
  const parsed = debuggingTrajectoryV1Schema.safeParse(input);
  if (!parsed.success) {
    throw new TrajectoryValidationError(parsed.error.issues);
  }
  return parsed.data;
}

export function appendTrajectorySourceEventPath(
  row: DebuggingTrajectoryV1,
  sourceEventPath: string,
): DebuggingTrajectoryV1 {
  const existingPaths = row.export.source_event_paths ?? [];
  const source_event_paths = Array.from(new Set([...existingPaths, sourceEventPath]));
  return {
    ...row,
    export: {
      ...row.export,
      source_event_paths,
    },
  };
}

export function withDefaultTrajectoryCurationQuality(row: DebuggingTrajectoryV1): DebuggingTrajectoryV1 {
  if (row.curation?.quality !== undefined) {
    return row;
  }
  return {
    ...row,
    curation: {
      ...(row.curation ?? {}),
      quality: "needs_review",
    },
  };
}

export function getTrajectorySellableBlockers(row: DebuggingTrajectoryV1): string[] {
  const blockers: string[] = [];
  if (!row.export.allowed) {
    blockers.push("export.allowed_false");
  }
  if (row.export.redaction === "blocked") {
    blockers.push("export.redaction_blocked");
  }
  return blockers;
}

export function isSellableTrajectoryRow(row: DebuggingTrajectoryV1): boolean {
  return getTrajectorySellableBlockers(row).length === 0;
}

export function serializeTrajectoryJsonlRow(row: DebuggingTrajectoryV1): string {
  return JSON.stringify(row);
}

export function toTrajectoryJsonlLine(row: DebuggingTrajectoryV1): string {
  return serializeTrajectoryJsonlRow(row);
}

function formatZodIssues(issues: z.ZodIssue[]): string {
  return issues
    .map((issue) => {
      const path = issue.path.length > 0 ? issue.path.join(".") : "<root>";
      return `${path}: ${issue.message}`;
    })
    .join("; ");
}
