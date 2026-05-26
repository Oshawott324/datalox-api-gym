import { z } from "zod";

const nonEmptyString = z.string().min(1);
const jsonObject = z.record(z.string(), z.unknown());

const exportGateSchema = z
  .object({
    allowed: z.boolean(),
    redaction: z.enum(["none_needed", "applied", "blocked"]),
    approval_id: z.string().optional(),
  })
  .strict();

export const runMessageSchema = z
  .object({
    role: z.enum(["system", "user", "assistant", "tool"]),
    content: z.string().nullable(),
    name: z.string().optional(),
    tool_call_id: z.string().optional(),
    tool_calls: z.array(jsonObject).optional(),
  })
  .strict();

export const replayMissSchema = z
  .object({
    code: z.literal("replay_miss"),
    message: nonEmptyString,
    request_hash: nonEmptyString,
    sequence_index: z.number().int().nonnegative(),
    tool_name: nonEmptyString,
    active_fixture_refs: z.array(nonEmptyString),
    available_tool_names: z.array(nonEmptyString),
    liveFallback: z.literal(false),
  })
  .strict();

export const runStepSchema = z
  .object({
    index: z.number().int().nonnegative(),
    assistant_message: runMessageSchema.optional(),
    tool_call: z
      .object({
        id: nonEmptyString,
        name: nonEmptyString,
        arguments: jsonObject,
      })
      .strict()
      .optional(),
    observation: z
      .object({
        status: z.enum(["ok", "error"]),
        content: z.unknown().optional(),
        error_code: z.string().optional(),
        error_message: z.string().optional(),
      })
      .strict()
      .optional(),
    replay_miss: replayMissSchema.optional(),
    tool_record_ref: z.string().optional(),
  })
  .strict();

export const dataloxRunV1Schema = z
  .object({
    schema_version: z.literal("datalox_run.v1"),
    id: nonEmptyString,
    created_at: nonEmptyString,
    task_ref: z.string().optional(),
    fixture_ref: z.string().optional(),
    fixture_refs: z.array(nonEmptyString).min(1),
    fixture_set_ref: z.string().optional(),
    model: z
      .object({
        provider: z.literal("openai_compatible"),
        model: nonEmptyString,
        base_url: nonEmptyString,
        sampling: jsonObject.optional(),
      })
      .strict(),
    messages: z.array(runMessageSchema),
    steps: z.array(runStepSchema),
    final_answer: z.string().optional(),
    stop_reason: z.enum(["final_answer", "max_steps", "replay_miss", "model_error"]),
    verifier_result: z.unknown().optional(),
    reward_records: z.array(z.unknown()).optional(),
    metadata: jsonObject.optional(),
    export: exportGateSchema,
  })
  .strict();

export type RunMessage = z.infer<typeof runMessageSchema>;
export type RunStep = z.infer<typeof runStepSchema>;
export type DataloxRunV1 = z.infer<typeof dataloxRunV1Schema>;

export class DataloxRunValidationError extends Error {
  readonly issues: z.ZodIssue[];

  constructor(issues: z.ZodIssue[]) {
    super(`Invalid datalox_run.v1 artifact: ${issues.map(formatIssue).join("; ")}`);
    this.name = "DataloxRunValidationError";
    this.issues = issues;
  }
}

export function parseDataloxRunV1(input: unknown): DataloxRunV1 {
  const parsed = dataloxRunV1Schema.safeParse(input);
  if (!parsed.success) {
    throw new DataloxRunValidationError(parsed.error.issues);
  }
  return parsed.data;
}

function formatIssue(issue: z.ZodIssue): string {
  return `${issue.path.length > 0 ? issue.path.join(".") : "<root>"}: ${issue.message}`;
}
