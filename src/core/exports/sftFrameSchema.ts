import { z } from "zod";

import { runMessageSchema } from "../run/runTranscriptSchema.js";

const nonEmptyString = z.string().min(1);
const jsonObject = z.record(z.string(), z.unknown());

const exportGateSchema = z
  .object({
    allowed: z.boolean(),
    redaction: z.enum(["none_needed", "applied", "blocked"]),
    approval_id: z.string().optional(),
  })
  .strict();

export const sftFrameV1Schema = z
  .object({
    schema_version: z.literal("sft_frame.v1"),
    id: nonEmptyString,
    source_run_id: nonEmptyString,
    task_ref: z.string().optional(),
    fixture_refs: z.array(nonEmptyString).min(1),
    fixture_set_ref: z.string().optional(),
    input_messages: z.array(runMessageSchema).min(1),
    target_message: runMessageSchema.refine(
      (message) => message.role === "assistant" && typeof message.content === "string" && message.content.length > 0,
      "target_message must be a final assistant message with non-empty content",
    ),
    evidence_refs: z
      .object({
        run_path: nonEmptyString,
        tool_record_refs: z.array(nonEmptyString),
        replay_miss_count: z.number().int().nonnegative(),
      })
      .strict(),
    quality: z.enum(["success", "recovery"]),
    use_for_sft: z.literal(true),
    export: exportGateSchema,
    metadata: jsonObject.optional(),
  })
  .strict();

export type SftFrameV1 = z.infer<typeof sftFrameV1Schema>;

export class SftFrameValidationError extends Error {
  readonly issues: z.ZodIssue[];

  constructor(issues: z.ZodIssue[]) {
    super(`Invalid sft_frame.v1 artifact: ${issues.map(formatIssue).join("; ")}`);
    this.name = "SftFrameValidationError";
    this.issues = issues;
  }
}

export function parseSftFrameV1(input: unknown): SftFrameV1 {
  const parsed = sftFrameV1Schema.safeParse(input);
  if (!parsed.success) {
    throw new SftFrameValidationError(parsed.error.issues);
  }
  return parsed.data;
}

function formatIssue(issue: z.ZodIssue): string {
  return `${issue.path.length > 0 ? issue.path.join(".") : "<root>"}: ${issue.message}`;
}
