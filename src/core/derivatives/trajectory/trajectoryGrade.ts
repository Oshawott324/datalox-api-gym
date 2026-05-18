import path from "node:path";

import {
  getTrajectoryRowInput,
  readRecordedTrajectoryEventPayloads,
} from "./trajectoryExport.js";
import {
  type DebuggingTrajectoryV1,
  getTrajectorySellableBlockers,
  parseDebuggingTrajectoryV1,
  TrajectoryValidationError,
} from "./trajectorySchema.js";

export type TrajectoryQuality = "use" | "needs_review" | "discard";

export interface TrajectoryGradeIssue {
  code: string;
  path: string;
  message: string;
  repair_action: string;
}

export interface TrajectoryGradeWarning {
  code: string;
  path: string;
  message: string;
}

export interface TrajectoryGradeV1 {
  schema: "datalox.trajectory_grade.v1";
  trajectory_id: string;
  quality: TrajectoryQuality;
  exportable: boolean;
  deterministic_passed: boolean;
  reviewer_required: boolean;
  blocking_issues: TrajectoryGradeIssue[];
  warnings: TrajectoryGradeWarning[];
  token_notes: {
    estimated_row_chars: number;
    largest_field_path?: string;
    largest_field_chars?: number;
    over_budget: boolean;
  };
}

export interface TrajectoryGradeInvalidRow {
  eventPath: string;
  reason: "malformed_event" | "invalid_schema";
  detail: unknown;
}

export interface TrajectoryGradeReport {
  schema: "datalox.trajectory_grade_report.v1";
  repoPath: string;
  scannedEvents: number;
  candidateRows: number;
  useRows: number;
  needsReviewRows: number;
  discardRows: number;
  invalidRows: number;
  issueCounts: Record<string, number>;
  grades: Array<{
    eventPath: string;
    grade: TrajectoryGradeV1;
  }>;
  invalid: TrajectoryGradeInvalidRow[];
}

export interface TrajectoryGradeOptions {
  maxRowChars?: number;
  maxPatchChars?: number;
  maxSnippetChars?: number;
  maxMetadataChars?: number;
}

export interface GradeTrajectoriesInput extends TrajectoryGradeOptions {
  repoPath?: string;
  eventPath?: string;
}

export class TrajectoryGradeError extends Error {
  readonly report: TrajectoryGradeReport;

  constructor(message: string, report: TrajectoryGradeReport) {
    super(message);
    this.name = "TrajectoryGradeError";
    this.report = report;
  }
}

const DEFAULT_GRADE_OPTIONS: Required<TrajectoryGradeOptions> = {
  maxRowChars: 24000,
  maxPatchChars: 12000,
  maxSnippetChars: 4000,
  maxMetadataChars: 4000,
};

const GENERIC_VERIFICATION_EVIDENCE = new Set([
  "passed",
  "tests passed",
  "test passed",
  "success",
  "ok",
]);

export function gradeTrajectoryRow(
  row: DebuggingTrajectoryV1,
  options: TrajectoryGradeOptions = {},
): TrajectoryGradeV1 {
  const resolvedOptions = { ...DEFAULT_GRADE_OPTIONS, ...options };
  const blocking_issues: TrajectoryGradeIssue[] = [];
  const warnings: TrajectoryGradeWarning[] = [];

  for (const blocker of getTrajectorySellableBlockers(row)) {
    blocking_issues.push({
      code: "export_blocked",
      path: "export",
      message: `Trajectory is not exportable: ${blocker}.`,
      repair_action: "Keep this row out of buyer-facing exports or fix the export gate after redaction review.",
    });
  }

  if (row.trajectory.length < 3) {
    blocking_issues.push({
      code: "trajectory_too_short",
      path: "trajectory",
      message: "Training-grade rows need at least 3 concise steps.",
      repair_action: "Add the key inspection, edit, and verification steps from observed facts.",
    });
  }
  if (row.trajectory.length > 20) {
    blocking_issues.push({
      code: "trajectory_too_long",
      path: "trajectory",
      message: "Training-grade rows should stay within 20 steps.",
      repair_action: "Compress repeated or low-signal steps into concise summaries.",
    });
  }

  const relevantFiles = row.context.relevant_files ?? [];
  if (relevantFiles.length === 0) {
    blocking_issues.push({
      code: "missing_before_after_snippet",
      path: "context.relevant_files",
      message: "No relevant before/after file snippets were included.",
      repair_action: "Add only the code snippets needed to understand the fix.",
    });
  }

  relevantFiles.forEach((file, index) => {
    const basePath = `context.relevant_files.${index}`;
    if (!file.before || !file.after) {
      blocking_issues.push({
        code: "missing_before_after_snippet",
        path: basePath,
        message: "Relevant file entry is missing a before or after snippet.",
        repair_action: "Include compact before and after snippets for this file.",
      });
      return;
    }
    if (isExternalReferenceOnly(file.before) || isExternalReferenceOnly(file.after)) {
      blocking_issues.push({
        code: "relevant_file_snippet_external_reference",
        path: basePath,
        message: "Relevant file before/after snippet points outside the row instead of carrying code evidence.",
        repair_action: "Replace source path references with the exact minimal before and after code snippets.",
      });
    }
    if (!looksLikeCodeSnippet(file.before) || !looksLikeCodeSnippet(file.after)) {
      blocking_issues.push({
        code: "relevant_file_snippet_not_code_like",
        path: basePath,
        message: "Relevant file before/after content does not look like code evidence.",
        repair_action: "Replace prose summaries with the exact minimal code snippets.",
      });
    }
    if (hasPlaceholderEllipsis(file.before) || hasPlaceholderEllipsis(file.after)) {
      blocking_issues.push({
        code: "placeholder_relevant_file",
        path: basePath,
        message: "Relevant file before/after snippet contains placeholder lines instead of exact code evidence.",
        repair_action: "Replace placeholder lines with exact minimal code snippets from the changed file.",
      });
    }
  });
  if (!hasStandaloneSnippetEvidence(row)) {
    const path = relevantFiles.length === 0 ? "context.relevant_files" : "context.relevant_files";
    blocking_issues.push({
      code: "not_self_contained",
      path,
      message: "Trajectory row does not contain meaningful inline before/after code evidence.",
      repair_action: "Add compact exact before/after snippets; paths and source events are provenance only.",
    });
  }

  if (!row.final.patch && !row.final.explanation) {
    blocking_issues.push({
      code: "missing_patch_or_explanation",
      path: "final",
      message: "No patch was included and no explanation says why the patch is unavailable.",
      repair_action: "Include a unified diff in final.patch, or explain why only changed_files are available.",
    });
  }
  if (row.final.patch && hasPlaceholderEllipsis(row.final.patch)) {
    blocking_issues.push({
      code: "placeholder_patch",
      path: "final.patch",
      message: "Patch contains placeholder lines instead of exact code evidence.",
      repair_action: "Replace placeholders with exact unified diff hunks, or remove final.patch and explain why unavailable.",
    });
  }
  if (row.final.patch && isExternalReferenceOnly(row.final.patch)) {
    blocking_issues.push({
      code: "not_self_contained",
      path: "final.patch",
      message: "Patch points to external files or events instead of carrying inline fix evidence.",
      repair_action: "Include compact unified diff hunks inline, or remove final.patch and add a concrete explanation.",
    });
  }
  if (row.final.explanation && !row.final.patch && isExternalReferenceOnly(row.final.explanation)) {
    blocking_issues.push({
      code: "not_self_contained",
      path: "final.explanation",
      message: "Explanation points to external files or events instead of explaining the fix from embedded snippets.",
      repair_action: "Explain the edit using the inline before/after snippets, or include compact diff hunks in final.patch.",
    });
  }

  if (!hasMeaningfulToolStep(row)) {
    blocking_issues.push({
      code: "missing_meaningful_tool_step",
      path: "trajectory",
      message: "No meaningful tool step with command and exit_code was included.",
      repair_action: "Add the verification or diagnostic command as a tool step with exit_code and short result.",
    });
  }

  if (isGenericVerificationEvidence(row.outcome.evidence)) {
    blocking_issues.push({
      code: "verification_evidence_too_generic",
      path: "outcome.evidence",
      message: "Verification evidence is missing or too generic.",
      repair_action: "Name the checks/tests and include the short result line that proves the outcome.",
    });
  }

  const tokenNotes = buildTokenNotes(row, resolvedOptions);
  blocking_issues.push(...buildTokenBudgetIssues(row, resolvedOptions));

  const deterministicPassed = blocking_issues.length === 0;
  const exportable = getTrajectorySellableBlockers(row).length === 0;
  const reviewerRequired = deterministicPassed && row.curation?.quality !== "use";
  const quality: TrajectoryQuality = !exportable
    ? "discard"
    : deterministicPassed && row.curation?.quality === "use"
      ? "use"
      : "needs_review";

  if (deterministicPassed && reviewerRequired) {
    warnings.push({
      code: "reviewer_required",
      path: "curation.quality",
      message: "Deterministic checks passed, but no accepted curation quality is present.",
    });
  }

  return {
    schema: "datalox.trajectory_grade.v1",
    trajectory_id: row.id,
    quality,
    exportable,
    deterministic_passed: deterministicPassed,
    reviewer_required: reviewerRequired,
    blocking_issues,
    warnings,
    token_notes: tokenNotes,
  };
}

export function gradeRecordedTrajectoryEvent(
  eventPayload: unknown,
  options: TrajectoryGradeOptions = {},
): TrajectoryGradeV1 | null {
  const rowInput = getTrajectoryRowInput(eventPayload);
  if (rowInput === undefined) {
    return null;
  }
  return gradeTrajectoryRow(parseDebuggingTrajectoryV1(rowInput), options);
}

export async function gradeTrajectories(
  input: GradeTrajectoriesInput = {},
): Promise<TrajectoryGradeReport> {
  const repoRoot = path.resolve(input.repoPath ?? process.cwd());
  const eventPayloads = await readRecordedTrajectoryEventPayloads(repoRoot, input.eventPath);
  const grades: TrajectoryGradeReport["grades"] = [];
  const invalid: TrajectoryGradeInvalidRow[] = [];

  for (const eventPayload of eventPayloads) {
    if (eventPayload.malformedError !== undefined) {
      invalid.push({
        eventPath: eventPayload.relativePath,
        reason: "malformed_event",
        detail: eventPayload.malformedError,
      });
      continue;
    }
    const rowInput = getTrajectoryRowInput(eventPayload.payload);
    if (rowInput === undefined) {
      continue;
    }
    try {
      const row = parseDebuggingTrajectoryV1(rowInput);
      grades.push({
        eventPath: eventPayload.relativePath,
        grade: gradeTrajectoryRow(row, input),
      });
    } catch (error) {
      invalid.push({
        eventPath: eventPayload.relativePath,
        reason: "invalid_schema",
        detail: error instanceof TrajectoryValidationError ? error.issues : String(error),
      });
    }
  }

  const report = buildGradeReport({
    repoRoot,
    scannedEvents: eventPayloads.length,
    grades,
    invalid,
  });

  if (invalid.length > 0) {
    throw new TrajectoryGradeError("Trajectory grading failed: invalid trajectory rows found.", report);
  }

  return report;
}

function hasMeaningfulToolStep(row: DebuggingTrajectoryV1): boolean {
  return row.trajectory.some((step) => (
    step.role === "tool"
    && typeof step.tool === "string"
    && step.tool.trim().length > 0
    && typeof step.command === "string"
    && step.command.trim().length > 0
    && typeof step.exit_code === "number"
  ));
}

function looksLikeCodeSnippet(value: string): boolean {
  const trimmed = value.trim();
  if (trimmed.length === 0) {
    return false;
  }
  return /[{}()[\];=<>]|\n/u.test(trimmed);
}

function hasStandaloneSnippetEvidence(row: DebuggingTrajectoryV1): boolean {
  return (row.context.relevant_files ?? []).some(hasMeaningfulSnippetPair);
}

function hasMeaningfulSnippetPair(file: NonNullable<DebuggingTrajectoryV1["context"]["relevant_files"]>[number]): boolean {
  if (!file.before || !file.after) {
    return false;
  }
  return looksLikeCodeSnippet(file.before)
    && looksLikeCodeSnippet(file.after)
    && !hasPlaceholderEllipsis(file.before)
    && !hasPlaceholderEllipsis(file.after)
    && !isExternalReferenceOnly(file.before)
    && !isExternalReferenceOnly(file.after);
}

function hasPlaceholderEllipsis(value: string): boolean {
  return value.split(/\r?\n/u).some((line) => {
    const trimmed = line.trim().replace(/^[+-]\s*/u, "");
    return /(^|[^\w$])\.\.\.(?=\s*(?:$|[,;})\]]))/u.test(trimmed);
  });
}

function isExternalReferenceOnly(value: string): boolean {
  const lines = value
    .split(/\r?\n/u)
    .map((line) => line.trim().replace(/^[+-]\s*/u, ""))
    .filter((line) => line.length > 0);
  return lines.length > 0 && lines.every(isExternalReferenceLine);
}

function isExternalReferenceLine(line: string): boolean {
  const normalized = line.toLowerCase();
  if (/^(?:see|open|refer to|reference|check|inspect|look at)\b/u.test(normalized)) {
    return /\b(?:src\/|\.datalox\/|source_event_paths|changed_files|repo|repository|artifact|attached file|file path)\b/u
      .test(normalized);
  }
  return /^(?:src\/|\.datalox\/|exports\/|\/[^\s]+)|^(?:source_event_paths|changed_files|path):\b/u
    .test(normalized);
}

function isGenericVerificationEvidence(value: string | undefined): boolean {
  if (!value) {
    return true;
  }
  const normalized = value.trim().replace(/[.!]+$/u, "").toLowerCase();
  return GENERIC_VERIFICATION_EVIDENCE.has(normalized);
}

function buildTokenNotes(
  row: DebuggingTrajectoryV1,
  options: Required<TrajectoryGradeOptions>,
): TrajectoryGradeV1["token_notes"] {
  const fields = collectMeasuredFields(row);
  let largest: { path: string; chars: number } | undefined;
  for (const field of fields) {
    if (!largest || field.chars > largest.chars) {
      largest = field;
    }
  }

  const estimatedRowChars = JSON.stringify(row).length;
  const overBudget = estimatedRowChars > options.maxRowChars
    || fields.some((field) => (
      (field.kind === "patch" && field.chars > options.maxPatchChars)
      || (field.kind === "snippet" && field.chars > options.maxSnippetChars)
      || (field.kind === "metadata" && field.chars > options.maxMetadataChars)
    ));

  return {
    estimated_row_chars: estimatedRowChars,
    largest_field_path: largest?.path,
    largest_field_chars: largest?.chars,
    over_budget: overBudget,
  };
}

function buildTokenBudgetIssues(
  row: DebuggingTrajectoryV1,
  options: Required<TrajectoryGradeOptions>,
): TrajectoryGradeIssue[] {
  const issues: TrajectoryGradeIssue[] = [];
  const estimatedRowChars = JSON.stringify(row).length;
  if (estimatedRowChars > options.maxRowChars) {
    issues.push({
      code: "row_over_token_budget",
      path: "<row>",
      message: `Trajectory row is ${estimatedRowChars} chars; budget is ${options.maxRowChars}.`,
      repair_action: "Move long output, full files, or large artifacts to source paths and keep only compact evidence inline.",
    });
  }

  for (const field of collectMeasuredFields(row)) {
    if (field.kind === "patch" && field.chars > options.maxPatchChars) {
      issues.push({
        code: "row_over_token_budget",
        path: field.path,
        message: `Patch is ${field.chars} chars; budget is ${options.maxPatchChars}.`,
        repair_action: "Replace the full diff with the minimal unified diff hunks needed to understand the fix.",
      });
    }
    if (field.kind === "snippet" && field.chars > options.maxSnippetChars) {
      issues.push({
        code: "row_over_token_budget",
        path: field.path,
        message: `Snippet is ${field.chars} chars; budget is ${options.maxSnippetChars}.`,
        repair_action: "Trim the snippet to the smallest before/after code needed to explain the fix.",
      });
    }
    if (field.kind === "metadata" && field.chars > options.maxMetadataChars) {
      issues.push({
        code: "row_over_token_budget",
        path: field.path,
        message: `Metadata is ${field.chars} chars; budget is ${options.maxMetadataChars}.`,
        repair_action: "Move large metadata into a source artifact and keep only a compact reference inline.",
      });
    }
  }
  return issues;
}

function collectMeasuredFields(row: DebuggingTrajectoryV1): Array<{
  path: string;
  chars: number;
  kind: "patch" | "snippet" | "metadata" | "other";
}> {
  const fields: Array<{ path: string; chars: number; kind: "patch" | "snippet" | "metadata" | "other" }> = [];
  if (row.final.patch !== undefined) {
    fields.push({ path: "final.patch", chars: row.final.patch.length, kind: "patch" });
  }
  row.context.relevant_files?.forEach((file, index) => {
    if (file.before !== undefined) {
      fields.push({ path: `context.relevant_files.${index}.before`, chars: file.before.length, kind: "snippet" });
    }
    if (file.after !== undefined) {
      fields.push({ path: `context.relevant_files.${index}.after`, chars: file.after.length, kind: "snippet" });
    }
  });
  if (row.metadata !== undefined) {
    fields.push({ path: "metadata", chars: JSON.stringify(row.metadata).length, kind: "metadata" });
  }
  fields.push({ path: "<row>", chars: JSON.stringify(row).length, kind: "other" });
  return fields;
}

function buildGradeReport(input: {
  repoRoot: string;
  scannedEvents: number;
  grades: TrajectoryGradeReport["grades"];
  invalid: TrajectoryGradeInvalidRow[];
}): TrajectoryGradeReport {
  const issueCounts: Record<string, number> = {};
  for (const entry of input.grades) {
    for (const issue of entry.grade.blocking_issues) {
      issueCounts[issue.code] = (issueCounts[issue.code] ?? 0) + 1;
    }
  }

  return {
    schema: "datalox.trajectory_grade_report.v1",
    repoPath: input.repoRoot,
    scannedEvents: input.scannedEvents,
    candidateRows: input.grades.length + input.invalid.length,
    useRows: input.grades.filter((entry) => entry.grade.quality === "use").length,
    needsReviewRows: input.grades.filter((entry) => entry.grade.quality === "needs_review").length,
    discardRows: input.grades.filter((entry) => entry.grade.quality === "discard").length,
    invalidRows: input.invalid.length,
    issueCounts,
    grades: input.grades,
    invalid: input.invalid,
  };
}
