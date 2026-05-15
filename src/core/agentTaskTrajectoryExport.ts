import { existsSync } from "node:fs";
import { mkdir, readdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

import {
  appendAgentTaskTrajectorySourceEventPath,
  type AgentTaskEvidenceBlockV1,
  type AgentTaskTrajectoryQuality,
  type AgentTaskTrajectoryV1,
  AgentTaskTrajectoryValidationError,
  getAgentTaskTrajectorySellableBlockers,
  parseAgentTaskTrajectoryV1,
  serializeAgentTaskTrajectoryJsonlRow,
  withDefaultAgentTaskTrajectoryCurationQuality,
} from "./agentTaskTrajectorySchema.js";

export const AGENT_TASK_TRAJECTORY_EVENTS_RELATIVE_DIR = path.join(
  ".datalox",
  "events",
  "agent-task-trajectories",
);

const DEFAULT_AGENT_TASK_EXPORT_RELATIVE_PATH = path.join(
  "exports",
  "trajectories",
  "agent_task_trajectory.v1.jsonl",
);

type JsonObject = Record<string, unknown>;

type ValidAgentTaskTrajectoryCandidate = {
  eventPath: string;
  row: AgentTaskTrajectoryV1;
};

export interface RecordAgentTaskTrajectoryInput {
  repoPath?: string;
  agentTaskTrajectory: unknown;
  now?: Date;
}

export interface RecordAgentTaskTrajectoryResult {
  eventPath: string;
  trajectoryId: string;
  sellable: boolean;
  blockedReasons: string[];
  readinessQuality: AgentTaskTrajectoryQuality;
  deterministicPassed: boolean;
  qualityDowngraded: boolean;
  qualityDowngradeIssueCodes: string[];
  event: {
    relativePath: string;
    payload: JsonObject;
  };
}

export interface ExportAgentTaskTrajectoriesInput {
  repoPath?: string;
  outputPath?: string;
  blockedReportPath?: string;
  split?: "train" | "validation" | "test" | "eval";
  quality?: AgentTaskTrajectoryQuality;
}

export interface AgentTaskTrajectoryExportRejectedRow {
  eventPath: string;
  trajectoryId?: string;
  reason: string;
  detail?: unknown;
}

export interface AgentTaskTrajectoryExportReport {
  schema: "datalox.agent_task_trajectory_export_report.v1";
  repoPath: string;
  outputPath: string;
  absoluteOutputPath: string;
  blockedReportPath?: string;
  absoluteBlockedReportPath?: string;
  scannedEvents: number;
  candidateRows: number;
  exportedRows: number;
  blockedRows: number;
  invalidRows: number;
  duplicateRows: number;
  rejectedRows: AgentTaskTrajectoryExportRejectedRow[];
}

export interface AgentTaskTrajectoryGradeIssue {
  code: string;
  path: string;
  message: string;
  repair_action: string;
}

export interface AgentTaskTrajectoryReadinessGrade {
  schema: "datalox.agent_task_trajectory_readiness.v1";
  trajectory_id: string;
  quality: AgentTaskTrajectoryQuality;
  exportable: boolean;
  deterministic_passed: boolean;
  blocking_issues: AgentTaskTrajectoryGradeIssue[];
  token_notes: {
    estimated_row_chars: number;
    largest_field_path?: string;
    largest_field_chars?: number;
    over_budget: boolean;
  };
}

export interface AgentTaskTrajectoryGradeOptions {
  maxRowChars?: number;
  maxPatchChars?: number;
  maxEvidenceChars?: number;
  maxMetadataChars?: number;
}

export interface RecordedAgentTaskTrajectoryEventPayload {
  relativePath: string;
  timestamp: string;
  payload: unknown;
  malformedError?: string;
}

export class AgentTaskTrajectoryExportError extends Error {
  readonly report: AgentTaskTrajectoryExportReport;

  constructor(message: string, report: AgentTaskTrajectoryExportReport) {
    super(message);
    this.name = "AgentTaskTrajectoryExportError";
    this.report = report;
  }
}

const DEFAULT_GRADE_OPTIONS: Required<AgentTaskTrajectoryGradeOptions> = {
  maxRowChars: 36000,
  maxPatchChars: 12000,
  maxEvidenceChars: 6000,
  maxMetadataChars: 4000,
};

const GENERIC_RESULT_SUMMARIES = new Set([
  "passed",
  "tests passed",
  "test passed",
  "success",
  "ok",
  "done",
]);

const CODE_HEAVY_DOMAINS = new Set([
  "code",
  "coding",
  "software",
  "engineering",
  "typescript",
  "javascript",
  "python",
  "rust",
  "go",
  "java",
  "tsx",
  "jsx",
  "react",
  "node",
  "nodejs",
  "mcp",
  "mcp_apps",
  "worker_threads",
  "packaging",
  "tests",
  "testing",
]);

const CODE_ARTIFACT_FILENAMES = new Set([
  "package.json",
  "package-lock.json",
  "pnpm-lock.yaml",
  "yarn.lock",
  "tsconfig.json",
  "vite.config.ts",
  "vitest.config.ts",
  "jest.config.js",
  "cargo.toml",
  "cargo.lock",
  "pyproject.toml",
  "requirements.txt",
]);

const CODE_ARTIFACT_EXTENSIONS = new Set([
  ".c",
  ".cc",
  ".cpp",
  ".cs",
  ".css",
  ".go",
  ".h",
  ".hpp",
  ".html",
  ".java",
  ".js",
  ".jsx",
  ".json",
  ".kt",
  ".mjs",
  ".mts",
  ".py",
  ".rs",
  ".sh",
  ".sql",
  ".swift",
  ".toml",
  ".ts",
  ".tsx",
  ".vue",
  ".yaml",
  ".yml",
]);

export async function recordAgentTaskTrajectory(
  input: RecordAgentTaskTrajectoryInput,
): Promise<RecordAgentTaskTrajectoryResult> {
  const repoRoot = resolveRepoRoot(input.repoPath);
  const parsedRow = withDefaultAgentTaskTrajectoryCurationQuality(
    parseAgentTaskTrajectoryV1(input.agentTaskTrajectory),
  );
  const now = input.now ?? new Date();
  const timestamp = now.toISOString();
  const relativePath = normalizeRelativePath(
    path.join(
      AGENT_TASK_TRAJECTORY_EVENTS_RELATIVE_DIR,
      `${safeTimestamp(timestamp)}--agent-task-trajectory-${slugify(parsedRow.id)}.json`,
    ),
  );
  const rowWithSourcePath = appendAgentTaskTrajectorySourceEventPath(parsedRow, relativePath);
  const normalized = normalizeRecordedAgentTaskTrajectoryQuality(rowWithSourcePath, timestamp);
  const row = normalized.row;
  const eventPath = path.join(repoRoot, relativePath);
  const payload = buildAgentTaskTrajectoryEventPayload(row, relativePath, timestamp);
  const blockedReasons = getAgentTaskTrajectorySellableBlockers(row);

  await mkdir(path.dirname(eventPath), { recursive: true });
  await writeFile(eventPath, `${JSON.stringify(payload, null, 2)}\n`, "utf8");

  return {
    eventPath: relativePath,
    trajectoryId: row.id,
    sellable: blockedReasons.length === 0,
    blockedReasons,
    readinessQuality: normalized.grade.quality,
    deterministicPassed: normalized.grade.deterministic_passed,
    qualityDowngraded: normalized.qualityDowngraded,
    qualityDowngradeIssueCodes: normalized.qualityDowngradeIssueCodes,
    event: {
      relativePath,
      payload,
    },
  };
}

function normalizeRecordedAgentTaskTrajectoryQuality(
  row: AgentTaskTrajectoryV1,
  timestamp: string,
): {
  row: AgentTaskTrajectoryV1;
  grade: AgentTaskTrajectoryReadinessGrade;
  qualityDowngraded: boolean;
  qualityDowngradeIssueCodes: string[];
} {
  const grade = gradeAgentTaskTrajectoryRow(row);
  if (row.curation?.quality !== "use" || grade.quality === "use") {
    return {
      row,
      grade,
      qualityDowngraded: false,
      qualityDowngradeIssueCodes: [],
    };
  }

  const issueCodes = grade.blocking_issues.map((issue) => issue.code);
  const downgradedRow: AgentTaskTrajectoryV1 = {
    ...row,
    curation: {
      ...(row.curation ?? {}),
      quality: "needs_review",
    },
    metadata: {
      ...(row.metadata ?? {}),
      datalox_quality_downgraded_from: "use",
      datalox_quality_downgrade_issue_codes: issueCodes,
      datalox_quality_downgraded_at: timestamp,
    },
  };

  return {
    row: downgradedRow,
    grade: gradeAgentTaskTrajectoryRow(downgradedRow),
    qualityDowngraded: true,
    qualityDowngradeIssueCodes: issueCodes,
  };
}

export async function exportAgentTaskTrajectories(
  input: ExportAgentTaskTrajectoriesInput = {},
): Promise<AgentTaskTrajectoryExportReport> {
  const repoRoot = resolveRepoRoot(input.repoPath);
  const outputAbsolutePath = resolveOutputPath(
    repoRoot,
    input.outputPath ?? DEFAULT_AGENT_TASK_EXPORT_RELATIVE_PATH,
  );
  const blockedReportAbsolutePath = input.blockedReportPath
    ? resolveOutputPath(repoRoot, input.blockedReportPath)
    : undefined;
  const eventPayloads = await readRecordedAgentTaskTrajectoryEventPayloads(repoRoot);
  const rejectedRows: AgentTaskTrajectoryExportRejectedRow[] = [];
  const validRows: ValidAgentTaskTrajectoryCandidate[] = [];

  for (const eventPayload of eventPayloads) {
    if (eventPayload.malformedError !== undefined) {
      rejectedRows.push({
        eventPath: eventPayload.relativePath,
        reason: "malformed_event",
        detail: eventPayload.malformedError,
      });
      continue;
    }
    const rowInput = getAgentTaskTrajectoryRowInput(eventPayload.payload);
    if (rowInput === undefined) {
      continue;
    }
    try {
      validRows.push({
        eventPath: eventPayload.relativePath,
        row: withDefaultAgentTaskTrajectoryCurationQuality(parseAgentTaskTrajectoryV1(rowInput)),
      });
    } catch (error) {
      rejectedRows.push({
        eventPath: eventPayload.relativePath,
        reason: "invalid_schema",
        detail: error instanceof AgentTaskTrajectoryValidationError ? error.issues : String(error),
      });
    }
  }

  const baseReport = buildReport({
    repoRoot,
    outputAbsolutePath,
    blockedReportAbsolutePath,
    scannedEvents: eventPayloads.length,
    candidateRows: validRows.length + rejectedRows.length,
    exportedRows: 0,
    blockedRows: 0,
    invalidRows: rejectedRows.length,
    duplicateRows: 0,
    rejectedRows,
  });

  if (rejectedRows.length > 0) {
    throw new AgentTaskTrajectoryExportError(
      "Agent task trajectory export failed: invalid trajectory rows found.",
      baseReport,
    );
  }

  const exportCandidates: ValidAgentTaskTrajectoryCandidate[] = [];
  for (const candidate of validRows) {
    const blockers = getAgentTaskTrajectorySellableBlockers(candidate.row);
    if (blockers.length > 0) {
      rejectedRows.push({
        eventPath: candidate.eventPath,
        trajectoryId: candidate.row.id,
        reason: "not_exportable",
        detail: { blockers },
      });
      continue;
    }
    if (input.quality === "use") {
      const grade = gradeAgentTaskTrajectoryRow(candidate.row);
      if (!grade.deterministic_passed || grade.blocking_issues.length > 0) {
        rejectedRows.push({
          eventPath: candidate.eventPath,
          trajectoryId: candidate.row.id,
          reason: "readiness_filter",
          detail: {
            quality: grade.quality,
            deterministic_passed: grade.deterministic_passed,
            issue_codes: grade.blocking_issues.map((issue) => issue.code),
          },
        });
        continue;
      }
    }
    if (input.quality && candidate.row.curation?.quality !== input.quality) {
      rejectedRows.push({
        eventPath: candidate.eventPath,
        trajectoryId: candidate.row.id,
        reason: "quality_filter",
        detail: {
          required_quality: input.quality,
          row_quality: candidate.row.curation?.quality ?? null,
        },
      });
      continue;
    }
    exportCandidates.push(candidate);
  }

  const duplicateRows = findDuplicateRows(exportCandidates);
  if (duplicateRows.length > 0) {
    const report = buildReport({
      repoRoot,
      outputAbsolutePath,
      blockedReportAbsolutePath,
      scannedEvents: eventPayloads.length,
      candidateRows: validRows.length,
      exportedRows: 0,
      blockedRows: rejectedRows.length + duplicateRows.length,
      invalidRows: 0,
      duplicateRows: duplicateRows.length,
      rejectedRows: [...rejectedRows, ...duplicateRows],
    });
    throw new AgentTaskTrajectoryExportError(
      "Agent task trajectory export failed: duplicate trajectory row ids found.",
      report,
    );
  }

  const exportRows = exportCandidates.map((candidate) => applySplitOverride(candidate.row, input.split));
  const output = exportRows.map(serializeAgentTaskTrajectoryJsonlRow).join("\n");
  await mkdir(path.dirname(outputAbsolutePath), { recursive: true });
  await writeFile(outputAbsolutePath, output.length > 0 ? `${output}\n` : "", "utf8");

  const report = buildReport({
    repoRoot,
    outputAbsolutePath,
    blockedReportAbsolutePath,
    scannedEvents: eventPayloads.length,
    candidateRows: validRows.length,
    exportedRows: exportRows.length,
    blockedRows: rejectedRows.length,
    invalidRows: 0,
    duplicateRows: 0,
    rejectedRows,
  });

  if (blockedReportAbsolutePath) {
    await mkdir(path.dirname(blockedReportAbsolutePath), { recursive: true });
    await writeFile(blockedReportAbsolutePath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  }

  return report;
}

export function gradeAgentTaskTrajectoryRow(
  row: AgentTaskTrajectoryV1,
  options: AgentTaskTrajectoryGradeOptions = {},
): AgentTaskTrajectoryReadinessGrade {
  const resolvedOptions = { ...DEFAULT_GRADE_OPTIONS, ...options };
  const blocking_issues: AgentTaskTrajectoryGradeIssue[] = [];

  for (const blocker of getAgentTaskTrajectorySellableBlockers(row)) {
    blocking_issues.push({
      code: "export_blocked",
      path: "export",
      message: `Agent task trajectory is not exportable: ${blocker}.`,
      repair_action: "Keep this row out of buyer-facing exports or fix the export gate after review.",
    });
  }

  if (row.evidence_blocks.length === 0) {
    blocking_issues.push({
      code: "missing_evidence_blocks",
      path: "evidence_blocks",
      message: "No evidence blocks were included.",
      repair_action: "Add at least one concrete evidence block from the completed task.",
    });
  }

  row.evidence_blocks.forEach((block, index) => {
    blocking_issues.push(...gradeEvidenceBlock(block, index));
  });
  blocking_issues.push(...gradeCodeHeavyEvidence(row));
  blocking_issues.push(...gradeSourceEventPaths(row));
  blocking_issues.push(...buildTokenBudgetIssues(row, resolvedOptions));

  const tokenNotes = buildTokenNotes(row, resolvedOptions);
  const deterministicPassed = blocking_issues.length === 0;
  const exportable = getAgentTaskTrajectorySellableBlockers(row).length === 0;
  const quality: AgentTaskTrajectoryQuality = !exportable
    ? "discard"
    : deterministicPassed && row.curation?.quality === "use"
      ? "use"
      : "needs_review";

  return {
    schema: "datalox.agent_task_trajectory_readiness.v1",
    trajectory_id: row.id,
    quality,
    exportable,
    deterministic_passed: deterministicPassed,
    blocking_issues,
    token_notes: tokenNotes,
  };
}

export async function readRecordedAgentTaskTrajectoryEventPayloads(
  repoRoot: string,
): Promise<RecordedAgentTaskTrajectoryEventPayload[]> {
  const relativePaths = await listRecordedAgentTaskTrajectoryEventPaths(repoRoot);
  const payloads: RecordedAgentTaskTrajectoryEventPayload[] = [];
  for (const relativePath of relativePaths) {
    const absolutePath = path.join(repoRoot, relativePath);
    try {
      const payload = JSON.parse(await readFile(absolutePath, "utf8"));
      const timestampValue = getObject(payload).timestamp;
      const timestamp = typeof timestampValue === "string" ? timestampValue : "";
      payloads.push({ relativePath, timestamp, payload });
    } catch (error) {
      payloads.push({
        relativePath,
        timestamp: "",
        payload: undefined,
        malformedError: error instanceof Error ? error.message : String(error),
      });
    }
  }
  payloads.sort((left, right) => {
    const byTimestamp = left.timestamp.localeCompare(right.timestamp);
    return byTimestamp !== 0 ? byTimestamp : left.relativePath.localeCompare(right.relativePath);
  });
  return payloads;
}

export async function listRecordedAgentTaskTrajectoryEventPaths(repoRoot: string): Promise<string[]> {
  const eventsRoot = path.join(repoRoot, AGENT_TASK_TRAJECTORY_EVENTS_RELATIVE_DIR);
  if (!existsSync(eventsRoot)) {
    return [];
  }
  const filenames = (await readdir(eventsRoot)).filter((filename) => filename.endsWith(".json"));
  return filenames
    .map((filename) => normalizeRelativePath(path.join(AGENT_TASK_TRAJECTORY_EVENTS_RELATIVE_DIR, filename)))
    .sort();
}

export function getAgentTaskTrajectoryRowInput(eventPayload: unknown): unknown {
  const payloadObject = getObject(eventPayload);
  return payloadObject.agentTaskTrajectory ?? getObject(payloadObject.payload).agentTaskTrajectory;
}

function buildAgentTaskTrajectoryEventPayload(
  row: AgentTaskTrajectoryV1,
  relativePath: string,
  timestamp: string,
): JsonObject {
  return {
    version: 1,
    id: path.basename(relativePath, ".json"),
    timestamp,
    eventKind: "agent_task_trajectory",
    eventClass: "trace",
    sourceKind: "trace",
    workflow: row.task.workflows?.[0] ?? row.task.domains[0],
    task: row.task.prompt,
    summary: row.final.summary,
    observations: row.trajectory.slice(0, 8).map((step) => `${step.role}: ${step.content}`),
    changedArtifacts: row.final.changed_artifacts ?? deriveChangedArtifacts(row),
    outcome: `${row.outcome.label}:${row.outcome.verification}`,
    tags: ["trajectory", "agent_task_trajectory.v1", ...(row.curation?.tags ?? [])],
    agentTaskTrajectory: row,
  };
}

function deriveChangedArtifacts(row: AgentTaskTrajectoryV1): string[] {
  const changed = new Set<string>();
  for (const artifact of row.final.changed_artifacts ?? []) {
    changed.add(artifact);
  }
  for (const step of row.trajectory) {
    for (const artifact of step.artifacts ?? []) {
      changed.add(artifact);
    }
    for (const filePath of step.files_changed ?? []) {
      changed.add(filePath);
    }
  }
  for (const block of row.evidence_blocks) {
    if (block.type === "code_change") {
      changed.add(block.path);
    }
    if ("artifact" in block) {
      changed.add(block.artifact);
    }
  }
  return Array.from(changed);
}

function gradeEvidenceBlock(
  block: AgentTaskEvidenceBlockV1,
  index: number,
): AgentTaskTrajectoryGradeIssue[] {
  const pathPrefix = `evidence_blocks.${index}`;
  const issues: AgentTaskTrajectoryGradeIssue[] = [];

  switch (block.type) {
    case "code_change":
      if (block.patch !== undefined && block.patch.trim().length > 0) {
        if (!looksLikeCodeOrPatchEvidence(block.patch)) {
          issues.push(buildIssue(
            "prose_only_evidence_block",
            `${pathPrefix}.patch`,
            "Code change patch does not look like exact code or unified diff evidence.",
            "Replace prose with compact exact unified diff hunks.",
          ));
        }
        if (hasPlaceholderEllipsis(block.patch) || isExternalReferenceOnly(block.patch)) {
          issues.push(buildIssue(
            "placeholder_evidence_block",
            `${pathPrefix}.patch`,
            "Code change patch contains placeholder or path-only evidence.",
            "Embed the exact minimal patch hunk instead of placeholders or file references.",
          ));
        }
        break;
      }
      if (!block.before || !block.after) {
        issues.push(buildIssue(
          "missing_type_specific_evidence",
          pathPrefix,
          "Code change evidence is missing before/after snippets.",
          "Add exact minimal before and after snippets, or a compact patch.",
        ));
        break;
      }
      if (!looksLikeCodeSnippet(block.before) || !looksLikeCodeSnippet(block.after)) {
        issues.push(buildIssue(
          "prose_only_evidence_block",
          pathPrefix,
          "Code change before/after evidence does not look like code.",
          "Replace prose summaries with exact minimal code snippets.",
        ));
      }
      if (
        hasPlaceholderEllipsis(block.before)
        || hasPlaceholderEllipsis(block.after)
        || isExternalReferenceOnly(block.before)
        || isExternalReferenceOnly(block.after)
      ) {
        issues.push(buildIssue(
          "placeholder_evidence_block",
          pathPrefix,
          "Code change before/after evidence contains placeholders or path-only references.",
          "Embed the exact minimal snippets needed to understand the change.",
        ));
      }
      break;
    case "command_result":
      if (isGenericResultSummary(block.result_summary)) {
        issues.push(buildIssue(
          "missing_command_result_evidence",
          `${pathPrefix}.result_summary`,
          "Command result summary is too generic.",
          "Name the observed result, including failure or pass details that matter for the task.",
        ));
      }
      break;
    case "document_change":
    case "spreadsheet_change":
    case "lab_workflow":
      if (!looksLikeConcreteBeforeAfter(block.before) || !looksLikeConcreteBeforeAfter(block.after)) {
        issues.push(buildIssue(
          "prose_only_evidence_block",
          pathPrefix,
          "Before/after evidence reads like a summary rather than exact task evidence.",
          "Use compact exact document, spreadsheet, or lab workflow excerpts.",
        ));
      }
      if (
        hasPlaceholderEllipsis(block.before)
        || hasPlaceholderEllipsis(block.after)
        || isExternalReferenceOnly(block.before)
        || isExternalReferenceOnly(block.after)
      ) {
        issues.push(buildIssue(
          "placeholder_evidence_block",
          pathPrefix,
          "Before/after evidence contains placeholders or path-only references.",
          "Embed compact exact evidence instead of placeholders or artifact references.",
        ));
      }
      break;
    case "source_reference":
      if (!block.excerpt || block.excerpt.trim().length === 0) {
        issues.push(buildIssue(
          "source_reference_missing_excerpt",
          `${pathPrefix}.excerpt`,
          "Source reference is missing an excerpt.",
          "Add the exact quoted or summarized excerpt needed to ground the trajectory.",
        ));
      } else if (isExternalReferenceOnly(block.excerpt) || matchesOnlySourceLocator(block.excerpt, block)) {
        issues.push(buildIssue(
          "source_reference_missing_excerpt",
          `${pathPrefix}.excerpt`,
          "Source reference excerpt only points to a URL or path.",
          "Add the concrete source text or observation, not only the locator.",
        ));
      }
      if (
        block.source_kind === "local_file"
        && typeof block.source_path === "string"
        && looksLikeCodeArtifactPath(block.source_path)
        && block.excerpt
        && !looksLikeCodeOrPatchEvidence(block.excerpt)
      ) {
        issues.push(buildIssue(
          "source_reference_prose_only_code_excerpt",
          `${pathPrefix}.excerpt`,
          "Source reference to a code artifact has a prose excerpt instead of exact code.",
          "Use source_reference for provenance/context and add exact code evidence in a code_change block.",
        ));
      }
      if (!block.relevance || block.relevance.trim().length === 0) {
        issues.push(buildIssue(
          "source_reference_missing_relevance",
          `${pathPrefix}.relevance`,
          "Source reference is missing relevance.",
          "State how this source supports the task trajectory.",
        ));
      }
      break;
    case "data_analysis":
      if (isGenericResultSummary(block.result)) {
        issues.push(buildIssue(
          "missing_type_specific_evidence",
          `${pathPrefix}.result`,
          "Data analysis result is too generic.",
          "Include the observed result that answers the analysis question.",
        ));
      }
      break;
    default:
      break;
  }

  return issues;
}

function gradeCodeHeavyEvidence(row: AgentTaskTrajectoryV1): AgentTaskTrajectoryGradeIssue[] {
  if (!rowAppearsCodeHeavy(row) || hasConcreteCodeChangeEvidence(row)) {
    return [];
  }
  return [
    buildIssue(
      "code_heavy_row_missing_code_change",
      "evidence_blocks",
      "Code-heavy agent task trajectory has no concrete code_change evidence.",
      "Add compact exact code_change before/after snippets or patch hunks for the key edit.",
    ),
  ];
}

function gradeSourceEventPaths(row: AgentTaskTrajectoryV1): AgentTaskTrajectoryGradeIssue[] {
  const issues: AgentTaskTrajectoryGradeIssue[] = [];
  row.export.source_event_paths?.forEach((sourcePath, index) => {
    const normalized = normalizeRelativePath(sourcePath);
    if (!normalized.startsWith(".datalox/events/")) {
      issues.push(buildIssue(
        "export_source_event_path_not_event",
        `export.source_event_paths.${index}`,
        "export.source_event_paths must contain .datalox event provenance paths only.",
        "Move source files into context.source_paths or final.changed_artifacts and keep only .datalox/events/... paths here.",
      ));
    }
  });
  return issues;
}

function rowAppearsCodeHeavy(row: AgentTaskTrajectoryV1): boolean {
  if (row.task.domains.some((domain) => CODE_HEAVY_DOMAINS.has(normalizeSignal(domain)))) {
    return true;
  }
  return collectArtifactPaths(row).some(looksLikeCodeArtifactPath);
}

function hasConcreteCodeChangeEvidence(row: AgentTaskTrajectoryV1): boolean {
  return row.evidence_blocks.some((block) => block.type === "code_change" && isConcreteCodeChangeBlock(block));
}

function isConcreteCodeChangeBlock(block: Extract<AgentTaskEvidenceBlockV1, { type: "code_change" }>): boolean {
  if (block.patch !== undefined && block.patch.trim().length > 0) {
    return looksLikeCodeOrPatchEvidence(block.patch)
      && !hasPlaceholderEllipsis(block.patch)
      && !isExternalReferenceOnly(block.patch);
  }
  if (!block.before || !block.after) {
    return false;
  }
  return looksLikeCodeSnippet(block.before)
    && looksLikeCodeSnippet(block.after)
    && !hasPlaceholderEllipsis(block.before)
    && !hasPlaceholderEllipsis(block.after)
    && !isExternalReferenceOnly(block.before)
    && !isExternalReferenceOnly(block.after);
}

function collectArtifactPaths(row: AgentTaskTrajectoryV1): string[] {
  const paths: string[] = [];
  paths.push(...(row.context?.source_paths ?? []));
  paths.push(...(row.final.changed_artifacts ?? []));
  for (const step of row.trajectory) {
    paths.push(...(step.artifacts ?? []));
    paths.push(...(step.files_changed ?? []));
  }
  for (const block of row.evidence_blocks) {
    if (block.type === "code_change") {
      paths.push(block.path);
    }
    if (block.type === "source_reference" && block.source_path) {
      paths.push(block.source_path);
    }
    if ("artifact" in block) {
      paths.push(block.artifact);
    }
  }
  return paths;
}

function buildIssue(
  code: string,
  pathValue: string,
  message: string,
  repairAction: string,
): AgentTaskTrajectoryGradeIssue {
  return {
    code,
    path: pathValue,
    message,
    repair_action: repairAction,
  };
}

function findDuplicateRows(
  validRows: ValidAgentTaskTrajectoryCandidate[],
): AgentTaskTrajectoryExportRejectedRow[] {
  const byId = new Map<string, ValidAgentTaskTrajectoryCandidate[]>();
  for (const candidate of validRows) {
    const existing = byId.get(candidate.row.id) ?? [];
    existing.push(candidate);
    byId.set(candidate.row.id, existing);
  }

  const duplicates: AgentTaskTrajectoryExportRejectedRow[] = [];
  for (const [trajectoryId, candidates] of byId.entries()) {
    if (candidates.length <= 1) {
      continue;
    }
    for (const candidate of candidates) {
      duplicates.push({
        eventPath: candidate.eventPath,
        trajectoryId,
        reason: "duplicate_id",
        detail: { duplicate_event_paths: candidates.map((entry) => entry.eventPath) },
      });
    }
  }
  return duplicates;
}

function applySplitOverride(
  row: AgentTaskTrajectoryV1,
  split: ExportAgentTaskTrajectoriesInput["split"],
): AgentTaskTrajectoryV1 {
  if (!split) {
    return row;
  }
  return {
    ...row,
    curation: {
      ...(row.curation ?? {}),
      split,
    },
  };
}

function buildReport(input: {
  repoRoot: string;
  outputAbsolutePath: string;
  blockedReportAbsolutePath?: string;
  scannedEvents: number;
  candidateRows: number;
  exportedRows: number;
  blockedRows: number;
  invalidRows: number;
  duplicateRows: number;
  rejectedRows: AgentTaskTrajectoryExportRejectedRow[];
}): AgentTaskTrajectoryExportReport {
  return {
    schema: "datalox.agent_task_trajectory_export_report.v1",
    repoPath: input.repoRoot,
    outputPath: normalizeRelativePath(path.relative(input.repoRoot, input.outputAbsolutePath)),
    absoluteOutputPath: input.outputAbsolutePath,
    blockedReportPath: input.blockedReportAbsolutePath
      ? normalizeRelativePath(path.relative(input.repoRoot, input.blockedReportAbsolutePath))
      : undefined,
    absoluteBlockedReportPath: input.blockedReportAbsolutePath,
    scannedEvents: input.scannedEvents,
    candidateRows: input.candidateRows,
    exportedRows: input.exportedRows,
    blockedRows: input.blockedRows,
    invalidRows: input.invalidRows,
    duplicateRows: input.duplicateRows,
    rejectedRows: input.rejectedRows,
  };
}

function buildTokenNotes(
  row: AgentTaskTrajectoryV1,
  options: Required<AgentTaskTrajectoryGradeOptions>,
): AgentTaskTrajectoryReadinessGrade["token_notes"] {
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
      || (field.kind === "evidence" && field.chars > options.maxEvidenceChars)
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
  row: AgentTaskTrajectoryV1,
  options: Required<AgentTaskTrajectoryGradeOptions>,
): AgentTaskTrajectoryGradeIssue[] {
  const issues: AgentTaskTrajectoryGradeIssue[] = [];
  const estimatedRowChars = JSON.stringify(row).length;
  if (estimatedRowChars > options.maxRowChars) {
    issues.push(buildIssue(
      "row_over_token_budget",
      "<row>",
      `Agent task trajectory row is ${estimatedRowChars} chars; budget is ${options.maxRowChars}.`,
      "Move long outputs or full artifacts into source paths and keep compact evidence inline.",
    ));
  }

  for (const field of collectMeasuredFields(row)) {
    if (field.kind === "patch" && field.chars > options.maxPatchChars) {
      issues.push(buildIssue(
        "row_over_token_budget",
        field.path,
        `Patch is ${field.chars} chars; budget is ${options.maxPatchChars}.`,
        "Trim the patch to the minimal exact hunks needed to understand the task.",
      ));
    }
    if (field.kind === "evidence" && field.chars > options.maxEvidenceChars) {
      issues.push(buildIssue(
        "row_over_token_budget",
        field.path,
        `Evidence field is ${field.chars} chars; budget is ${options.maxEvidenceChars}.`,
        "Trim this field to the smallest self-contained evidence excerpt.",
      ));
    }
    if (field.kind === "metadata" && field.chars > options.maxMetadataChars) {
      issues.push(buildIssue(
        "row_over_token_budget",
        field.path,
        `Metadata is ${field.chars} chars; budget is ${options.maxMetadataChars}.`,
        "Move large metadata into a source artifact and keep only compact references inline.",
      ));
    }
  }
  return issues;
}

function collectMeasuredFields(row: AgentTaskTrajectoryV1): Array<{
  path: string;
  chars: number;
  kind: "patch" | "evidence" | "metadata" | "other";
}> {
  const fields: Array<{ path: string; chars: number; kind: "patch" | "evidence" | "metadata" | "other" }> = [];
  row.evidence_blocks.forEach((block, index) => {
    for (const [key, value] of Object.entries(block)) {
      if (typeof value !== "string") {
        continue;
      }
      const kind = key === "patch" ? "patch" : "evidence";
      fields.push({ path: `evidence_blocks.${index}.${key}`, chars: value.length, kind });
    }
  });
  if (row.metadata !== undefined) {
    fields.push({ path: "metadata", chars: JSON.stringify(row.metadata).length, kind: "metadata" });
  }
  fields.push({ path: "<row>", chars: JSON.stringify(row).length, kind: "other" });
  return fields;
}

function looksLikeCodeSnippet(value: string): boolean {
  const trimmed = value.trim();
  if (trimmed.length === 0) {
    return false;
  }
  return /[{}()[\];=<>]|\n/u.test(trimmed);
}

function looksLikeCodeOrPatchEvidence(value: string): boolean {
  const trimmed = value.trim();
  if (trimmed.length === 0) {
    return false;
  }
  return /^diff --git\b/mu.test(trimmed)
    || /^@@\s/mu.test(trimmed)
    || /^[+-][^\r\n]+/mu.test(trimmed)
    || looksLikeCodeSnippet(trimmed);
}

function looksLikeConcreteBeforeAfter(value: string): boolean {
  const trimmed = value.trim();
  if (trimmed.length < 12) {
    return false;
  }
  if (isExternalReferenceOnly(trimmed)) {
    return false;
  }
  const normalized = trimmed.toLowerCase();
  return !/^(?:the previous|the new|the old|before,?|after,?|updated|changed|fixed)\b/u.test(normalized);
}

function looksLikeCodeArtifactPath(filePath: string): boolean {
  const normalized = normalizeRelativePath(filePath).toLowerCase();
  const basename = normalized.split("/").at(-1) ?? normalized;
  if (CODE_ARTIFACT_FILENAMES.has(basename)) {
    return true;
  }
  if (
    normalized.includes("/src/")
    || normalized.startsWith("src/")
    || normalized.includes("/tests/")
    || normalized.startsWith("tests/")
    || normalized.includes("/test/")
    || normalized.startsWith("test/")
  ) {
    const extension = path.posix.extname(normalized);
    return extension.length === 0 || CODE_ARTIFACT_EXTENSIONS.has(extension);
  }
  return CODE_ARTIFACT_EXTENSIONS.has(path.posix.extname(normalized));
}

function normalizeSignal(value: string): string {
  return value.trim().toLowerCase().replace(/[\s-]+/gu, "_");
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
  if (/^https?:\/\//u.test(normalized)) {
    return true;
  }
  if (/^(?:see|open|refer to|reference|check|inspect|look at)\b/u.test(normalized)) {
    return /\b(?:src\/|docs\/|\.datalox\/|exports\/|source_event_paths|changed_files|repo|repository|artifact|file path|url)\b/u
      .test(normalized);
  }
  return /^(?:src\/|docs\/|\.datalox\/|exports\/|\/[^\s]+)|^(?:source_event_paths|changed_files|path|url):\b/u
    .test(normalized);
}

function matchesOnlySourceLocator(value: string, block: Extract<AgentTaskEvidenceBlockV1, { type: "source_reference" }>): boolean {
  const trimmed = value.trim();
  return trimmed.length > 0 && (trimmed === block.url || trimmed === block.source_path);
}

function isGenericResultSummary(value: string): boolean {
  const normalized = value.trim().replace(/[.!]+$/u, "").toLowerCase();
  return normalized.length === 0 || GENERIC_RESULT_SUMMARIES.has(normalized);
}

function resolveRepoRoot(repoPath: string | undefined): string {
  return path.resolve(repoPath ?? process.cwd());
}

function resolveOutputPath(repoRoot: string, outputPath: string): string {
  return path.isAbsolute(outputPath) ? outputPath : path.join(repoRoot, outputPath);
}

function getObject(value: unknown): JsonObject {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as JsonObject) : {};
}

function safeTimestamp(timestamp: string): string {
  return timestamp.replace(/[:.]/g, "-");
}

function slugify(value: string): string {
  const slug = value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);
  return slug.length > 0 ? slug : "agent-task-trajectory";
}

function normalizeRelativePath(filePath: string): string {
  return filePath.split(path.sep).join("/");
}
