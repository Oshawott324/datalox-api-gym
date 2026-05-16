import { z } from "zod";

import { canonicalJson, CanonicalJsonError } from "./canonicalJson.js";
import { sha256Hex } from "./hash.js";

const nonEmptyString = z.string().min(1);
const sha256HexString = z.string().regex(/^[a-f0-9]{64}$/);

export const toolIoObservationV1Schema = z
  .object({
    status: z.enum(["ok", "error"]),
    content: z.unknown().optional(),
    error_code: z.string().optional(),
    error_message: z.string().optional(),
  })
  .strict();

export const toolIoRecordV1Schema = z
  .object({
    schema_version: z.literal("tool_io_record.v1"),
    id: nonEmptyString,
    session_id: z.string().optional(),
    turn_id: z.string().optional(),
    call_id: nonEmptyString,
    tool_name: nonEmptyString,
    arguments: z.unknown(),
    request_hash: sha256HexString,
    sequence_index: z.number().int().nonnegative(),
    observation: toolIoObservationV1Schema,
    created_at: nonEmptyString,
    source: z
      .object({
        host: z.string().optional(),
        mcp_server: z.string().optional(),
        command: z.string().optional(),
      })
      .strict()
      .optional(),
    export: z
      .object({
        allowed: z.boolean(),
        redaction: z.enum(["none_needed", "applied", "blocked"]),
      })
      .strict(),
  })
  .strict()
  .superRefine((record, context) => {
    try {
      canonicalJson(record);
    } catch (error) {
      addCanonicalJsonIssue(context, [], error);
    }

    try {
      canonicalJson(record.arguments);
    } catch (error) {
      addCanonicalJsonIssue(context, ["arguments"], error);
    }

    try {
      canonicalJson(record.observation);
    } catch (error) {
      addCanonicalJsonIssue(context, ["observation"], error);
    }

    try {
      const expectedHash = buildToolIoRequestHash(record.tool_name, record.arguments);
      if (record.request_hash !== expectedHash) {
        context.addIssue({
          code: "custom",
          path: ["request_hash"],
          message: `request_hash must equal sha256(canonical_json({ tool_name, arguments })); expected ${expectedHash}.`,
        });
      }
    } catch {
      return;
    }
  });

export type ToolIoObservationV1 = z.infer<typeof toolIoObservationV1Schema>;
export type ToolIoRecordV1 = z.infer<typeof toolIoRecordV1Schema>;

export class ToolIoRecordValidationError extends Error {
  readonly issues: z.ZodIssue[];

  constructor(issues: z.ZodIssue[]) {
    super(`Invalid tool_io_record.v1 record: ${formatZodIssues(issues)}`);
    this.name = "ToolIoRecordValidationError";
    this.issues = issues;
  }
}

export function buildToolIoRequestHash(toolName: string, toolArguments: unknown): string {
  return sha256Hex(canonicalJson({ arguments: toolArguments, tool_name: toolName }));
}

export function parseToolIoRecordV1(input: unknown): ToolIoRecordV1 {
  const parsed = toolIoRecordV1Schema.safeParse(input);
  if (!parsed.success) {
    throw new ToolIoRecordValidationError(parsed.error.issues);
  }
  return parsed.data;
}

function addCanonicalJsonIssue(
  context: z.RefinementCtx,
  path: Array<string | number>,
  error: unknown,
): void {
  context.addIssue({
    code: "custom",
    path,
    message: error instanceof CanonicalJsonError
      ? `value must be canonical JSON serializable: ${error.message}`
      : "value must be canonical JSON serializable.",
  });
}

function formatZodIssues(issues: z.ZodIssue[]): string {
  return issues
    .map((issue) => {
      const issuePath = issue.path.length > 0 ? issue.path.join(".") : "<root>";
      return `${issuePath}: ${issue.message}`;
    })
    .join("; ");
}
