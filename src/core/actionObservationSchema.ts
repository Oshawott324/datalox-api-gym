import { z } from "zod";

import { canonicalJson, CanonicalJsonError } from "./canonicalJson.js";
import { buildToolIoRequestHash } from "./toolIoSchema.js";

const nonEmptyString = z.string().min(1);
const sha256HexString = z.string().regex(/^[a-f0-9]{64}$/);

export const actionObservationV1Schema = z
  .object({
    schema_version: z.literal("action_observation.v1"),
    action: z
      .object({
        type: z.literal("tool_call"),
        name: nonEmptyString,
        version: z.string().optional(),
        arguments: z.unknown(),
        argument_schema_ref: z.string().optional(),
        request_hash: sha256HexString,
        sequence_index: z.number().int().nonnegative(),
      })
      .strict(),
    observation: z
      .object({
        status: z.enum(["ok", "error"]),
        content: z.unknown().optional(),
        error_code: z.string().optional(),
        error_message: z.string().optional(),
        observation_schema_ref: z.string().optional(),
      })
      .strict(),
    provenance: z
      .object({
        source_kind: z.enum(["mcp", "wrapper", "raw_trace"]),
        source_path: z.string().optional(),
        host: z.string().optional(),
        session_id: z.string().optional(),
        turn_id: z.string().optional(),
        call_id: nonEmptyString,
      })
      .strict(),
  })
  .strict()
  .superRefine((row, context) => {
    const hasArguments = hasOwnProperty(row.action, "arguments");
    if (!hasArguments) {
      context.addIssue({
        code: "custom",
        path: ["action", "arguments"],
        message: "arguments is required.",
      });
    }

    if (hasArguments) {
      try {
        canonicalJson(row.action.arguments);
      } catch (error) {
        addCanonicalJsonIssue(context, ["action", "arguments"], error);
      }

      try {
        const expectedHash = buildToolIoRequestHash(row.action.name, row.action.arguments);
        if (row.action.request_hash !== expectedHash) {
          context.addIssue({
            code: "custom",
            path: ["action", "request_hash"],
            message: `request_hash must equal sha256(canonical_json({ tool_name, arguments })); expected ${expectedHash}.`,
          });
        }
      } catch {
        return;
      }
    }

    try {
      canonicalJson(row.observation);
    } catch (error) {
      addCanonicalJsonIssue(context, ["observation"], error);
    }
  });

export type ActionObservationV1 = z.infer<typeof actionObservationV1Schema>;

export class ActionObservationValidationError extends Error {
  readonly issues: z.ZodIssue[];

  constructor(issues: z.ZodIssue[]) {
    super(`Invalid action_observation.v1 record: ${formatZodIssues(issues)}`);
    this.name = "ActionObservationValidationError";
    this.issues = issues;
  }
}

export function parseActionObservationV1(input: unknown): ActionObservationV1 {
  const parsed = actionObservationV1Schema.safeParse(input);
  if (!parsed.success) {
    throw new ActionObservationValidationError(parsed.error.issues);
  }
  return parsed.data;
}

function hasOwnProperty(value: object, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(value, key);
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
