import { z } from "zod";

const nonEmptyString = z.string().min(1);

const curationQualitySchema = z.enum(["use", "needs_review", "discard"]);
const curationSplitSchema = z.enum(["train", "validation", "test", "eval"]);
const outcomeLabelSchema = z.enum(["success", "failure", "partial"]);
const verificationSchema = z.enum(["passed", "failed", "not_run", "reviewed"]);
const redactionSchema = z.enum(["none_needed", "applied", "blocked"]);
const trajectoryTypeSchema = z.enum(["success", "failure", "recovery"]);

const replayBundleRefSchema = z
  .object({
    bundle_id: nonEmptyString,
    bundle_path: z.string().optional(),
  })
  .strict();

const codeChangeEvidenceBlockSchema = z
  .object({
    type: z.literal("code_change"),
    path: nonEmptyString,
    language: z.string().optional(),
    symbol: z.string().optional(),
    before: z.string().optional(),
    after: z.string().optional(),
    patch: z.string().optional(),
    reason: z.string().optional(),
  })
  .strict()
  .superRefine((block, context) => {
    const hasBeforeAfter = block.before !== undefined
      && block.before.trim().length > 0
      && block.after !== undefined
      && block.after.trim().length > 0;
    const hasPatch = block.patch !== undefined && block.patch.trim().length > 0;
    if (!hasBeforeAfter && !hasPatch) {
      context.addIssue({
        code: "custom",
        message: "code_change evidence requires before+after or patch.",
        path: ["before"],
      });
    }
  });

const commandResultEvidenceBlockSchema = z
  .object({
    type: z.literal("command_result"),
    command: nonEmptyString,
    exit_code: z.number().int(),
    result_summary: nonEmptyString,
    evidence: z.string().optional(),
    artifact_paths: z.array(z.string()).optional(),
  })
  .strict();

const documentChangeEvidenceBlockSchema = z
  .object({
    type: z.literal("document_change"),
    artifact: nonEmptyString,
    format: z.string().optional(),
    before: nonEmptyString,
    after: nonEmptyString,
    section: z.string().optional(),
    reason: z.string().optional(),
  })
  .strict();

const spreadsheetChangeEvidenceBlockSchema = z
  .object({
    type: z.literal("spreadsheet_change"),
    artifact: nonEmptyString,
    sheet: z.string().optional(),
    range: z.string().optional(),
    before: nonEmptyString,
    after: nonEmptyString,
    formula: z.string().optional(),
    validation: z.string().optional(),
  })
  .strict();

const dataAnalysisEvidenceBlockSchema = z
  .object({
    type: z.literal("data_analysis"),
    artifact: nonEmptyString,
    question: nonEmptyString,
    method: nonEmptyString,
    result: nonEmptyString,
    input_summary: z.string().optional(),
    code_ref: z.string().optional(),
    validation: z.string().optional(),
  })
  .strict();

const labWorkflowEvidenceBlockSchema = z
  .object({
    type: z.literal("lab_workflow"),
    workflow: nonEmptyString,
    assay: z.string().optional(),
    measurement_context: nonEmptyString,
    before: nonEmptyString,
    after: nonEmptyString,
    criteria: z.string().optional(),
    validation: z.string().optional(),
  })
  .strict();

const sourceReferenceEvidenceBlockSchema = z
  .object({
    type: z.literal("source_reference"),
    source_kind: z.enum(["web", "pdf", "local_file"]),
    title: nonEmptyString,
    source_path: z.string().optional(),
    url: z.string().optional(),
    excerpt: z.string().optional(),
    relevance: z.string().optional(),
  })
  .strict();

export const agentTaskEvidenceBlockV1Schema = z.discriminatedUnion("type", [
  codeChangeEvidenceBlockSchema,
  commandResultEvidenceBlockSchema,
  documentChangeEvidenceBlockSchema,
  spreadsheetChangeEvidenceBlockSchema,
  dataAnalysisEvidenceBlockSchema,
  labWorkflowEvidenceBlockSchema,
  sourceReferenceEvidenceBlockSchema,
]);

export const agentTaskTrajectoryV1Schema = z
  .object({
    schema_version: z.literal("agent_task_trajectory.v1"),
    id: nonEmptyString,
    created_at: nonEmptyString,
    task: z
      .object({
        prompt: nonEmptyString,
        domains: z.array(nonEmptyString).min(1),
        workflows: z.array(nonEmptyString).optional(),
        environment: z.string().optional(),
        constraints: z.array(z.string()).optional(),
      })
      .strict(),
    context: z
      .object({
        problem: z.string().optional(),
        background: z.string().optional(),
        source_paths: z.array(z.string()).optional(),
        notes: z.array(z.string()).optional(),
      })
      .strict()
      .optional(),
    trajectory: z
      .array(
        z
          .object({
            role: z.enum(["user", "agent", "tool", "reviewer"]),
            content: nonEmptyString,
            tool: z.string().optional(),
            command: z.string().optional(),
            exit_code: z.number().int().optional(),
            artifacts: z.array(z.string()).optional(),
            files_changed: z.array(z.string()).optional(),
          })
          .strict(),
      )
      .min(1),
    evidence_blocks: z.array(agentTaskEvidenceBlockV1Schema).min(1),
    final: z
      .object({
        summary: nonEmptyString,
        changed_artifacts: z.array(z.string()).optional(),
        explanation: z.string().optional(),
      })
      .strict(),
    outcome: z
      .object({
        label: outcomeLabelSchema,
        verification: verificationSchema,
        command: z.string().optional(),
        evidence: z.string().optional(),
      })
      .strict(),
    trajectory_type: trajectoryTypeSchema.optional(),
    first_wrong_step: z.number().int().nonnegative().optional(),
    replay_bundle_ref: replayBundleRefSchema.optional(),
    export: z
      .object({
        allowed: z.boolean(),
        redaction: redactionSchema,
        source_event_paths: z.array(z.string()).optional(),
      })
      .strict(),
    curation: z
      .object({
        split: curationSplitSchema.optional(),
        quality: curationQualitySchema.optional(),
        tags: z.array(z.string()).optional(),
        notes: z.string().optional(),
      })
      .strict()
      .optional(),
    metadata: z.record(z.string(), z.unknown()).optional(),
  })
  .strict();

export type AgentTaskEvidenceBlockV1 = z.infer<typeof agentTaskEvidenceBlockV1Schema>;
export type AgentTaskTrajectoryV1 = z.infer<typeof agentTaskTrajectoryV1Schema>;
export type AgentTaskTrajectoryQuality = z.infer<typeof curationQualitySchema>;

export class AgentTaskTrajectoryValidationError extends Error {
  readonly issues: z.ZodIssue[];

  constructor(issues: z.ZodIssue[]) {
    super(`Invalid agent_task_trajectory.v1 row: ${formatZodIssues(issues)}`);
    this.name = "AgentTaskTrajectoryValidationError";
    this.issues = issues;
  }
}

export function parseAgentTaskTrajectoryV1(input: unknown): AgentTaskTrajectoryV1 {
  const parsed = agentTaskTrajectoryV1Schema.safeParse(input);
  if (!parsed.success) {
    throw new AgentTaskTrajectoryValidationError(parsed.error.issues);
  }
  return parsed.data;
}

export function appendAgentTaskTrajectorySourceEventPath(
  row: AgentTaskTrajectoryV1,
  sourceEventPath: string,
): AgentTaskTrajectoryV1 {
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

export function withDefaultAgentTaskTrajectoryCurationQuality(
  row: AgentTaskTrajectoryV1,
): AgentTaskTrajectoryV1 {
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

export function getAgentTaskTrajectorySellableBlockers(row: AgentTaskTrajectoryV1): string[] {
  const blockers: string[] = [];
  if (!row.export.allowed) {
    blockers.push("export.allowed_false");
  }
  if (row.export.redaction === "blocked") {
    blockers.push("export.redaction_blocked");
  }
  return blockers;
}

export function isSellableAgentTaskTrajectoryRow(row: AgentTaskTrajectoryV1): boolean {
  return getAgentTaskTrajectorySellableBlockers(row).length === 0;
}

export function serializeAgentTaskTrajectoryJsonlRow(row: AgentTaskTrajectoryV1): string {
  return JSON.stringify(row);
}

export function toAgentTaskTrajectoryJsonlLine(row: AgentTaskTrajectoryV1): string {
  return serializeAgentTaskTrajectoryJsonlRow(row);
}

function formatZodIssues(issues: z.ZodIssue[]): string {
  return issues
    .map((issue) => {
      const path = issue.path.length > 0 ? issue.path.join(".") : "<root>";
      return `${path}: ${issue.message}`;
    })
    .join("; ");
}
