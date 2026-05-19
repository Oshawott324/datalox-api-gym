import { z } from "zod";

import {
  parseActionObservationV1,
  type ActionObservationV1,
} from "./actionObservationSchema.js";
import {
  buildToolIoRequestHash,
  toolIoObservationV1Schema,
  type ToolIoRecordV1,
} from "./toolIoSchema.js";

const rawActionObservationTraceInputSchema = z
  .object({
    source_kind: z.literal("raw_trace"),
    source_path: z.string().optional(),
    host: z.string().optional(),
    session_id: z.string().optional(),
    turn_id: z.string().optional(),
    call_id: z.string().min(1),
    tool_name: z.string().min(1),
    tool_version: z.string().optional(),
    arguments: z.unknown(),
    argument_schema_ref: z.string().optional(),
    observation: toolIoObservationV1Schema,
    observation_schema_ref: z.string().optional(),
    sequence_index: z.number().int().nonnegative().optional(),
  })
  .strict()
  .superRefine((row, context) => {
    if (!hasOwnProperty(row, "arguments")) {
      context.addIssue({
        code: "custom",
        path: ["arguments"],
        message: "arguments is required.",
      });
    }
  });

export type RawActionObservationTraceInput = z.infer<typeof rawActionObservationTraceInputSchema>;

export class RawActionObservationTraceValidationError extends Error {
  readonly issues: z.ZodIssue[];

  constructor(issues: z.ZodIssue[]) {
    super(`Invalid raw action/observation trace input: ${formatZodIssues(issues)}`);
    this.name = "RawActionObservationTraceValidationError";
    this.issues = issues;
  }
}

export function parseRawActionObservationTraceInput(input: unknown): RawActionObservationTraceInput {
  const parsed = rawActionObservationTraceInputSchema.safeParse(input);
  if (!parsed.success) {
    throw new RawActionObservationTraceValidationError(parsed.error.issues);
  }
  return parsed.data;
}

export function actionObservationFromToolIoRecord(
  record: ToolIoRecordV1,
  options: {
    sourceKind?: "mcp" | "wrapper" | "raw_trace";
    sourcePath?: string;
  } = {},
): ActionObservationV1 {
  return parseActionObservationV1({
    schema_version: "action_observation.v1",
    action: {
      type: "tool_call",
      name: record.tool_name,
      arguments: record.arguments,
      request_hash: record.request_hash,
      sequence_index: record.sequence_index,
    },
    observation: record.observation,
    provenance: {
      source_kind: options.sourceKind ?? inferToolIoRecordSourceKind(record),
      ...(options.sourcePath !== undefined ? { source_path: options.sourcePath } : {}),
      ...(record.source?.host !== undefined ? { host: record.source.host } : {}),
      ...(record.session_id !== undefined ? { session_id: record.session_id } : {}),
      ...(record.turn_id !== undefined ? { turn_id: record.turn_id } : {}),
      call_id: record.call_id,
    },
  });
}

export function actionObservationFromRawTrace(input: unknown): ActionObservationV1 {
  const raw = parseRawActionObservationTraceInput(input);
  return parseActionObservationV1({
    schema_version: "action_observation.v1",
    action: {
      type: "tool_call",
      name: raw.tool_name,
      ...(raw.tool_version !== undefined ? { version: raw.tool_version } : {}),
      arguments: raw.arguments,
      ...(raw.argument_schema_ref !== undefined ? { argument_schema_ref: raw.argument_schema_ref } : {}),
      request_hash: buildToolIoRequestHash(raw.tool_name, raw.arguments),
      sequence_index: raw.sequence_index ?? 0,
    },
    observation: {
      ...raw.observation,
      ...(raw.observation_schema_ref !== undefined ? { observation_schema_ref: raw.observation_schema_ref } : {}),
    },
    provenance: {
      source_kind: raw.source_kind,
      ...(raw.source_path !== undefined ? { source_path: raw.source_path } : {}),
      ...(raw.host !== undefined ? { host: raw.host } : {}),
      ...(raw.session_id !== undefined ? { session_id: raw.session_id } : {}),
      ...(raw.turn_id !== undefined ? { turn_id: raw.turn_id } : {}),
      call_id: raw.call_id,
    },
  });
}

function inferToolIoRecordSourceKind(record: ToolIoRecordV1): "mcp" | "wrapper" | "raw_trace" {
  if (record.source?.mcp_server) {
    return "mcp";
  }
  if (record.source?.host || record.source?.command) {
    return "wrapper";
  }
  return "raw_trace";
}

function hasOwnProperty(value: object, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(value, key);
}

function formatZodIssues(issues: z.ZodIssue[]): string {
  return issues
    .map((issue) => {
      const issuePath = issue.path.length > 0 ? issue.path.join(".") : "<root>";
      return `${issuePath}: ${issue.message}`;
    })
    .join("; ");
}
