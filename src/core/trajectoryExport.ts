import { existsSync } from "node:fs";
import { mkdir, readdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

import {
  appendTrajectorySourceEventPath,
  type DebuggingTrajectoryV1,
  getTrajectorySellableBlockers,
  parseDebuggingTrajectoryV1,
  serializeTrajectoryJsonlRow,
  TrajectoryValidationError,
} from "./trajectorySchema.js";

const EVENTS_RELATIVE_DIR = path.join("agent-wiki", "events");
const DEFAULT_EXPORT_RELATIVE_PATH = path.join(
  "exports",
  "trajectories",
  "debugging_trajectory.v1.jsonl",
);

type JsonObject = Record<string, unknown>;

export interface RecordTrajectoryInput {
  repoPath?: string;
  trajectoryRow: unknown;
  now?: Date;
}

export interface RecordTrajectoryResult {
  eventPath: string;
  trajectoryId: string;
  sellable: boolean;
  blockedReasons: string[];
  event: {
    relativePath: string;
    payload: JsonObject;
  };
}

export interface ExportTrajectoriesInput {
  repoPath?: string;
  outputPath?: string;
  blockedReportPath?: string;
  split?: "train" | "validation" | "test" | "eval";
}

export interface TrajectoryExportRejectedRow {
  eventPath: string;
  trajectoryId?: string;
  reason: string;
  detail?: unknown;
}

export interface TrajectoryExportReport {
  schema: "datalox.trajectory_export_report.v1";
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
  rejectedRows: TrajectoryExportRejectedRow[];
}

export class TrajectoryExportError extends Error {
  readonly report: TrajectoryExportReport;

  constructor(message: string, report: TrajectoryExportReport) {
    super(message);
    this.name = "TrajectoryExportError";
    this.report = report;
  }
}

export async function recordTrajectory(input: RecordTrajectoryInput): Promise<RecordTrajectoryResult> {
  const repoRoot = resolveRepoRoot(input.repoPath);
  const parsedRow = parseDebuggingTrajectoryV1(input.trajectoryRow);
  const now = input.now ?? new Date();
  const timestamp = now.toISOString();
  const relativePath = normalizeRelativePath(
    path.join(
      EVENTS_RELATIVE_DIR,
      `${safeTimestamp(timestamp)}--trajectory-${slugify(parsedRow.id)}.json`,
    ),
  );
  const row = appendTrajectorySourceEventPath(parsedRow, relativePath);
  const eventPath = path.join(repoRoot, relativePath);
  const payload = buildTrajectoryEventPayload(row, relativePath, timestamp);
  const blockedReasons = getTrajectorySellableBlockers(row);

  await mkdir(path.dirname(eventPath), { recursive: true });
  await writeFile(eventPath, `${JSON.stringify(payload, null, 2)}\n`, "utf8");

  return {
    eventPath: relativePath,
    trajectoryId: row.id,
    sellable: blockedReasons.length === 0,
    blockedReasons,
    event: {
      relativePath,
      payload,
    },
  };
}

export async function exportTrajectories(
  input: ExportTrajectoriesInput = {},
): Promise<TrajectoryExportReport> {
  const repoRoot = resolveRepoRoot(input.repoPath);
  const outputAbsolutePath = resolveOutputPath(
    repoRoot,
    input.outputPath ?? DEFAULT_EXPORT_RELATIVE_PATH,
  );
  const blockedReportAbsolutePath = input.blockedReportPath
    ? resolveOutputPath(repoRoot, input.blockedReportPath)
    : undefined;
  const eventPayloads = await readRecordedEventPayloads(repoRoot);
  const rejectedRows: TrajectoryExportRejectedRow[] = [];
  const validRows: Array<{
    eventPath: string;
    row: DebuggingTrajectoryV1;
  }> = [];

  for (const eventPayload of eventPayloads) {
    const rowInput = getObject(eventPayload.payload).trajectoryRow;
    if (rowInput === undefined) {
      continue;
    }
    try {
      validRows.push({
        eventPath: eventPayload.relativePath,
        row: parseDebuggingTrajectoryV1(rowInput),
      });
    } catch (error) {
      rejectedRows.push({
        eventPath: eventPayload.relativePath,
        reason: "invalid_schema",
        detail: error instanceof TrajectoryValidationError ? error.issues : String(error),
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
    throw new TrajectoryExportError("Trajectory export failed: invalid trajectory rows found.", baseReport);
  }

  const duplicateRows = findDuplicateRows(validRows);
  if (duplicateRows.length > 0) {
    const report = {
      ...baseReport,
      duplicateRows: duplicateRows.length,
      rejectedRows: duplicateRows,
    };
    throw new TrajectoryExportError("Trajectory export failed: duplicate trajectory row ids found.", report);
  }

  const exportRows: DebuggingTrajectoryV1[] = [];
  for (const candidate of validRows) {
    const blockers = getTrajectorySellableBlockers(candidate.row);
    if (blockers.length > 0) {
      rejectedRows.push({
        eventPath: candidate.eventPath,
        trajectoryId: candidate.row.id,
        reason: "not_exportable",
        detail: { blockers },
      });
      continue;
    }
    exportRows.push(applySplitOverride(candidate.row, input.split));
  }

  const output = exportRows.map(serializeTrajectoryJsonlRow).join("\n");
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

function buildTrajectoryEventPayload(
  row: DebuggingTrajectoryV1,
  relativePath: string,
  timestamp: string,
): JsonObject {
  return {
    version: 1,
    id: path.basename(relativePath, ".json"),
    timestamp,
    eventKind: "trajectory_row",
    eventClass: "trace",
    sourceKind: "trace",
    workflow: "coding_debugging",
    task: row.task.prompt,
    summary: row.final.fix_summary,
    observations: row.trajectory.slice(0, 8).map((step) => `${step.role}: ${step.content}`),
    changedFiles: row.final.changed_files ?? deriveChangedFiles(row),
    outcome: `${row.outcome.label}:${row.outcome.verification}`,
    tags: ["trajectory", "debugging_trajectory.v1", ...(row.curation?.tags ?? [])],
    trajectoryRow: row,
  };
}

function deriveChangedFiles(row: DebuggingTrajectoryV1): string[] {
  const changed = new Set<string>();
  for (const step of row.trajectory) {
    for (const filePath of step.files_changed ?? []) {
      changed.add(filePath);
    }
  }
  return Array.from(changed);
}

async function readRecordedEventPayloads(repoRoot: string): Promise<Array<{
  relativePath: string;
  timestamp: string;
  payload: unknown;
}>> {
  const eventsRoot = path.join(repoRoot, EVENTS_RELATIVE_DIR);
  if (!existsSync(eventsRoot)) {
    return [];
  }
  const filenames = (await readdir(eventsRoot)).filter((filename) => filename.endsWith(".json"));
  const payloads: Array<{
    relativePath: string;
    timestamp: string;
    payload: unknown;
  }> = [];
  for (const filename of filenames) {
    const relativePath = normalizeRelativePath(path.join(EVENTS_RELATIVE_DIR, filename));
    const absolutePath = path.join(repoRoot, relativePath);
    const text = await readFile(absolutePath, "utf8");
    const payload = JSON.parse(text);
    const timestampValue = getObject(payload).timestamp;
    const timestamp = typeof timestampValue === "string" ? timestampValue : "";
    payloads.push({ relativePath, timestamp, payload });
  }
  payloads.sort((left, right) => {
    const byTimestamp = left.timestamp.localeCompare(right.timestamp);
    return byTimestamp !== 0 ? byTimestamp : left.relativePath.localeCompare(right.relativePath);
  });
  return payloads;
}

function findDuplicateRows(
  validRows: Array<{ eventPath: string; row: DebuggingTrajectoryV1 }>,
): TrajectoryExportRejectedRow[] {
  const byId = new Map<string, Array<{ eventPath: string; row: DebuggingTrajectoryV1 }>>();
  for (const candidate of validRows) {
    const existing = byId.get(candidate.row.id) ?? [];
    existing.push(candidate);
    byId.set(candidate.row.id, existing);
  }

  const duplicates: TrajectoryExportRejectedRow[] = [];
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
  row: DebuggingTrajectoryV1,
  split: ExportTrajectoriesInput["split"],
): DebuggingTrajectoryV1 {
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
  rejectedRows: TrajectoryExportRejectedRow[];
}): TrajectoryExportReport {
  return {
    schema: "datalox.trajectory_export_report.v1",
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
  return slug.length > 0 ? slug : "trajectory";
}

function normalizeRelativePath(filePath: string): string {
  return filePath.split(path.sep).join("/");
}
