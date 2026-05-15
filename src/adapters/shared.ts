import { spawnSync } from "node:child_process";
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";

import {
  autoBootstrapIfSafe,
  type AutoBootstrapResult,
} from "../core/packCore.js";
import { recordTrajectory } from "../core/trajectoryExport.js";

export type WrapperPostRunMode = "off" | "trajectory";

export interface LoopEnvelopeInput {
  repoPath?: string;
  task?: string;
  workflow?: string;
  step?: string;
  skill?: string;
  limit?: number;
  includeContent?: boolean;
  prompt?: string;
  sessionId?: string;
  matcher?: WrapperMatchRunner | null;
}

export interface LoopEnvelope {
  repoPath: string;
  sessionId: string | null;
  active: boolean;
  originalPrompt: string;
  wrappedPrompt: string;
  resolution: null;
  bootstrap: AutoBootstrapResult;
  guidance: {
    workflow: string;
    selectionBasis: string;
    matchedSkillId: string | null;
    candidateSkills: [];
    whyMatched: string[];
    whatToDoNow: string[];
    watchFor: string[];
    nextReads: string[];
    supportingNotes: [];
  };
}

export interface WrappedCommandResult {
  command: string;
  args: string[];
  exitCode: number;
  stdout: string;
  stderr: string;
}

export interface WrapperPostRunInput {
  task?: string;
  workflow?: string;
  step?: string;
  skillId?: string;
  summary?: string;
  tags?: string[];
  eventKind?: string;
  postRunMode?: WrapperPostRunMode;
  minWikiOccurrences?: number;
  minSkillOccurrences?: number;
  sessionId?: string;
  reviewModel?: string;
}

export interface WrapperReviewDecision {
  action: "noop";
  reason: string;
  observations: string[];
  tags: string[];
}

export interface WrapperMatchDecision {
  matchedSkillId: string | null;
  noMatch: boolean;
  alternatives: string[];
  reason: string;
}

export interface WrapperMatchRunner {
  kind: string;
  model: string | null;
  run(prompt: string, envelope: LoopEnvelope): WrappedCommandResult;
}

export interface WrapperReviewRunner {
  kind: string;
  model: string | null;
  run(prompt: string, envelope: LoopEnvelope): WrappedCommandResult;
}

export interface WrapperReviewResult {
  status: "skipped";
  model: string | null;
  decision: null;
  persisted: null;
  error?: string;
}

export interface WrapperPostRunResult {
  mode: "off" | "trajectory";
  trigger: "disabled" | "missing_trajectory_row" | "trajectory_row";
  result: Awaited<ReturnType<typeof recordTrajectory>> | null;
  review: null;
  backlog: null;
  maintenance: null;
}

export interface WrappedLoopResult {
  envelope: LoopEnvelope;
  child: WrappedCommandResult | null;
  postRun: WrapperPostRunResult | null;
}

interface ParsedMarkers {
  cleanedText: string;
  trajectoryRow?: unknown;
  trajectoryRowFile?: string;
}

const CONTROL_TEXT_PATTERN = /[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/g;
const UNKNOWN_WORKFLOW = "unknown";
const EXPLICIT_PLACEHOLDER_VALUES = {
  __DATALOX_PROMPT__: (envelope: LoopEnvelope) => envelope.wrappedPrompt,
  __DATALOX_ORIGINAL_PROMPT__: (envelope: LoopEnvelope) => envelope.originalPrompt,
  __DATALOX_GUIDANCE_JSON__: (envelope: LoopEnvelope) => JSON.stringify(envelope.guidance),
  __DATALOX_REPO_PATH__: (envelope: LoopEnvelope) => envelope.repoPath,
  __DATALOX_MATCHED_SKILL__: (envelope: LoopEnvelope) => envelope.guidance.matchedSkillId ?? "",
  __DATALOX_WORKFLOW__: (envelope: LoopEnvelope) => envelope.guidance.workflow === UNKNOWN_WORKFLOW ? "" : envelope.guidance.workflow,
} as const;
const EXPLICIT_PLACEHOLDER_KEYS = Object.keys(EXPLICIT_PLACEHOLDER_VALUES) as Array<keyof typeof EXPLICIT_PLACEHOLDER_VALUES>;

function sanitizeWrappedText(text: string): string {
  return text.replace(/\r\n/g, "\n").replace(CONTROL_TEXT_PATTERN, "");
}

export function stripDataloxMarkers(text: string): string {
  return extractMarkers(sanitizeWrappedText(text)).cleanedText;
}

function toPrompt(input: LoopEnvelopeInput): string {
  if (typeof input.prompt === "string" && input.prompt.trim().length > 0) {
    return input.prompt;
  }
  if (typeof input.task === "string" && input.task.trim().length > 0) {
    return input.task;
  }
  return "";
}

export function renderWrappedPrompt(envelope: LoopEnvelope): string {
  if (!envelope.active) {
    return envelope.originalPrompt;
  }
  return [
    "# Datalox Trajectory Capture",
    "For coding-debugging or mixed-domain agent work, write one explicit row file after the fix or investigation is complete.",
    "Use `debugging_trajectory.v1` for narrow debugging rows and `agent_task_trajectory.v1` for broader mixed-domain task episodes.",
    "Rows must be grounded in observed prompts, tool actions, file edits, verification results, and outcome labels.",
    "Do not infer missing facts from prose. If a row is not justified for this run, omit the marker.",
    "When a row file exists, append this marker at the very end of your response:",
    "- DATALOX_TRAJECTORY_ROW_FILE: .datalox/trajectory-rows/<stable-id>.json",
    "",
    "# Original Prompt",
    envelope.originalPrompt,
  ].join("\n").trim();
}

export async function buildLoopEnvelope(input: LoopEnvelopeInput): Promise<LoopEnvelope> {
  const repoPath = path.resolve(input.repoPath ?? process.cwd());
  const originalPrompt = toPrompt(input);
  const bootstrap = await autoBootstrapIfSafe({ repoPath });
  const active = bootstrap.probeAfter.status === "ready";
  const workflow = input.workflow ?? UNKNOWN_WORKFLOW;
  const baseEnvelope: LoopEnvelope = {
    repoPath,
    sessionId: input.sessionId ?? null,
    active,
    originalPrompt,
    resolution: null,
    bootstrap,
    guidance: {
      workflow,
      selectionBasis: active ? "product_trajectory_capture" : "bootstrap_unavailable",
      matchedSkillId: null,
      candidateSkills: [],
      whyMatched: [],
      whatToDoNow: [],
      watchFor: [],
      nextReads: [],
      supportingNotes: [],
    },
    wrappedPrompt: "",
  };

  return {
    ...baseEnvelope,
    wrappedPrompt: renderWrappedPrompt(baseEnvelope),
  };
}

export function buildWrapperEnv(envelope: LoopEnvelope, hostKind?: string): NodeJS.ProcessEnv {
  return {
    DATALOX_REPO_PATH: envelope.repoPath,
    DATALOX_SESSION_ID: envelope.sessionId ?? "",
    DATALOX_ORIGINAL_PROMPT: envelope.originalPrompt,
    DATALOX_PROMPT: envelope.wrappedPrompt,
    DATALOX_GUIDANCE_JSON: JSON.stringify(envelope.guidance),
    DATALOX_SELECTION_BASIS: envelope.guidance.selectionBasis,
    DATALOX_WORKFLOW: envelope.guidance.workflow === UNKNOWN_WORKFLOW ? "" : envelope.guidance.workflow,
    DATALOX_MATCHED_SKILL: envelope.guidance.matchedSkillId ?? "",
    ...(hostKind
      ? {
          DATALOX_ACTIVE_WRAPPER: hostKind,
          DATALOX_HOST_KIND: hostKind,
          DATALOX_ENFORCEMENT: "wrapper",
        }
      : {}),
  };
}

function replaceExplicitPlaceholder(
  input: string,
  key: keyof typeof EXPLICIT_PLACEHOLDER_VALUES,
  value: string,
): string {
  if (input === key) {
    return value;
  }

  const assignmentSuffix = `=${key}`;
  if (input.endsWith(assignmentSuffix)) {
    return `${input.slice(0, -assignmentSuffix.length)}=${value}`;
  }

  return input;
}

export function hasExplicitPromptPlaceholder(input: string): boolean {
  return input === "__DATALOX_PROMPT__" || input.endsWith("=__DATALOX_PROMPT__");
}

export function replacePromptPlaceholders(input: string, envelope: LoopEnvelope): string {
  if (input === envelope.wrappedPrompt || input === envelope.originalPrompt) {
    return input;
  }

  return EXPLICIT_PLACEHOLDER_KEYS.reduce(
    (current, key) => replaceExplicitPlaceholder(current, key, EXPLICIT_PLACEHOLDER_VALUES[key](envelope)),
    input,
  );
}

export function runWrappedCommand(
  command: string,
  args: string[],
  envelope: LoopEnvelope,
  options: {
    cwd?: string;
    env?: NodeJS.ProcessEnv;
    hostKind?: string;
  } = {},
): WrappedCommandResult {
  const result = spawnSync(
    command,
    args.map((arg) => replacePromptPlaceholders(arg, envelope)),
    {
      cwd: options.cwd ?? envelope.repoPath,
      env: {
        ...process.env,
        ...buildWrapperEnv(envelope, options.hostKind),
        ...options.env,
      },
      encoding: "utf8",
    },
  );

  return {
    command,
    args: args.map((arg) => replacePromptPlaceholders(arg, envelope)),
    exitCode: result.status ?? 1,
    stdout: result.stdout ?? "",
    stderr: result.stderr ?? "",
  };
}

function parseMarkerLine(line: string, parsed: ParsedMarkers): boolean {
  const match = line.match(/^DATALOX_([A-Z_]+):\s*(.+)$/);
  if (!match) {
    return false;
  }
  const [, rawKey, rawValue] = match;
  const value = rawValue.trim();
  switch (rawKey) {
    case "TRAJECTORY_ROW":
      parsed.trajectoryRow = JSON.parse(value);
      return true;
    case "TRAJECTORY_ROW_FILE":
      parsed.trajectoryRowFile = value;
      return true;
    default:
      return false;
  }
}

function extractMarkers(text: string): ParsedMarkers {
  const parsed: ParsedMarkers = {
    cleanedText: "",
  };
  const keptLines: string[] = [];
  for (const line of text.split(/\r?\n/)) {
    if (!parseMarkerLine(line, parsed)) {
      keptLines.push(line);
    }
  }
  parsed.cleanedText = keptLines.join("\n").trim();
  return parsed;
}

function mergeMarkers(left: ParsedMarkers, right: ParsedMarkers): ParsedMarkers {
  return {
    cleanedText: "",
    trajectoryRow: left.trajectoryRow ?? right.trajectoryRow,
    trajectoryRowFile: left.trajectoryRowFile ?? right.trajectoryRowFile,
  };
}

export function sanitizeWrappedCommandResult(result: WrappedCommandResult): {
  child: WrappedCommandResult;
  markers: ParsedMarkers;
} {
  const stdoutMarkers = extractMarkers(sanitizeWrappedText(result.stdout));
  const stderrMarkers = extractMarkers(sanitizeWrappedText(result.stderr));
  return {
    child: {
      ...result,
      stdout: stdoutMarkers.cleanedText,
      stderr: stderrMarkers.cleanedText,
    },
    markers: mergeMarkers(stdoutMarkers, stderrMarkers),
  };
}

async function loadTrajectoryRowMarker(
  repoPath: string,
  markers: ParsedMarkers,
): Promise<unknown | null> {
  if (markers.trajectoryRow !== undefined && markers.trajectoryRowFile !== undefined) {
    throw new Error("Use either DATALOX_TRAJECTORY_ROW or DATALOX_TRAJECTORY_ROW_FILE, not both.");
  }
  if (markers.trajectoryRow !== undefined) {
    return markers.trajectoryRow;
  }
  if (markers.trajectoryRowFile === undefined) {
    return null;
  }

  const resolvedPath = path.isAbsolute(markers.trajectoryRowFile)
    ? path.resolve(markers.trajectoryRowFile)
    : path.resolve(repoPath, markers.trajectoryRowFile);
  const relativePath = path.relative(repoPath, resolvedPath);
  if (relativePath.startsWith("..") || path.isAbsolute(relativePath)) {
    throw new Error("DATALOX_TRAJECTORY_ROW_FILE must point inside the repo.");
  }
  return JSON.parse(await readFile(resolvedPath, "utf8"));
}

export async function sanitizeCodexOutputFile(repoPath: string, outputPath: string | undefined): Promise<void> {
  if (!outputPath) {
    return;
  }
  const resolvedPath = path.isAbsolute(outputPath)
    ? outputPath
    : path.resolve(repoPath, outputPath);

  try {
    const contents = await readFile(resolvedPath, "utf8");
    const sanitized = stripDataloxMarkers(contents);
    if (sanitized !== contents) {
      await writeFile(resolvedPath, sanitized, "utf8");
    }
  } catch {
    // Output files are optional for host CLIs.
  }
}

export async function finalizeWrappedRun(
  envelope: LoopEnvelope,
  child: WrappedCommandResult | null,
  input: WrapperPostRunInput & { hostKind: string; reviewer?: WrapperReviewRunner | null },
): Promise<WrapperPostRunResult> {
  const postRunMode = input.postRunMode ?? "trajectory";
  if (!child || !envelope.active || postRunMode === "off") {
    return {
      mode: "off",
      trigger: "disabled",
      result: null,
      review: null,
      backlog: null,
      maintenance: null,
    };
  }

  const sanitized = sanitizeWrappedCommandResult(child);
  const trajectoryRow = await loadTrajectoryRowMarker(envelope.repoPath, sanitized.markers);
  if (trajectoryRow === null) {
    return {
      mode: "trajectory",
      trigger: "missing_trajectory_row",
      result: null,
      review: null,
      backlog: null,
      maintenance: null,
    };
  }

  const recordedTrajectory = await recordTrajectory({
    repoPath: envelope.repoPath,
    trajectoryRow,
  });
  return {
    mode: "trajectory",
    trigger: "trajectory_row",
    result: recordedTrajectory,
    review: null,
    backlog: null,
    maintenance: null,
  };
}
