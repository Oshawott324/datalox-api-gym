import { z } from "zod";

const nonEmptyString = z.string().min(1);

const toolIoRefSchema = z
  .object({
    record_id: nonEmptyString,
    request_hash: z.string().regex(/^[a-f0-9]{64}$/),
    sequence_index: z.number().int().nonnegative(),
  })
  .strict();

const agentTurnToolCallSchema = z
  .object({
    tool: nonEmptyString,
    call_id: z.string().optional(),
    tool_io_ref: toolIoRefSchema.optional(),
    command: z.string().optional(),
    args_summary: z.string().optional(),
    exit_code: z.number().int().optional(),
    output_summary: z.string().optional(),
  })
  .strict();

const agentTurnFileChangeSchema = z
  .object({
    path: nonEmptyString,
    action: z.enum(["created", "modified", "deleted"]),
    diff_summary: z.string().optional(),
  })
  .strict();

const agentTurnVerificationSchema = z
  .object({
    command: z.string().optional(),
    status: z.enum(["passed", "failed", "not_run"]),
    evidence: z.string().optional(),
  })
  .strict();

const exportGateSchema = z
  .object({
    allowed: z.boolean(),
    redaction: z.enum(["none_needed", "applied", "blocked"]),
  })
  .strict();

export const agentTurnV1Schema = z
  .object({
    schema_version: z.literal("agent_turn.v1"),
    id: nonEmptyString,
    session_id: nonEmptyString,
    turn_index: z.number().int().nonnegative(),
    created_at: nonEmptyString,
    user_prompt: z.string().optional(),
    assistant_summary: z.string().optional(),
    tool_calls: z.array(agentTurnToolCallSchema),
    file_changes: z.array(agentTurnFileChangeSchema).optional(),
    verification: agentTurnVerificationSchema.optional(),
    export: exportGateSchema,
  })
  .strict();

export type AgentTurnV1 = z.infer<typeof agentTurnV1Schema>;

export class AgentTurnValidationError extends Error {
  readonly issues: z.ZodIssue[];

  constructor(issues: z.ZodIssue[]) {
    super(`Invalid agent_turn.v1 event: ${formatZodIssues(issues)}`);
    this.name = "AgentTurnValidationError";
    this.issues = issues;
  }
}

export function parseAgentTurnV1(input: unknown): AgentTurnV1 {
  const parsed = agentTurnV1Schema.safeParse(input);
  if (!parsed.success) {
    throw new AgentTurnValidationError(parsed.error.issues);
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
