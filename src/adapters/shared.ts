import { randomUUID } from "node:crypto";
import { spawnSync } from "node:child_process";
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";

import { recordAgentTurn } from "../core/agentTurnStore.js";
import { readToolIoRecords } from "../core/toolIoStore.js";
import type { ToolIoRecordV1 } from "../core/toolIoSchema.js";
import {
  autoBootstrapIfSafe,
  type AutoBootstrapResult,
} from "../core/packCore.js";

export type WrapperPostRunMode = "off" | "replay";

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
  replayEvidenceBefore?: WrapperReplayEvidenceSnapshot;
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
  mode: "off" | "replay";
  trigger: "disabled" | "replay_evidence_recorded" | "replay_capture_empty";
  reason: string;
  result: {
    toolRecordCount: number;
    toolRecordIds: string[];
    event?: {
      relativePath: string;
      turnId: string;
    };
  } | null;
  review: null;
  backlog: null;
  maintenance: null;
}

export interface WrapperReplayEvidenceSnapshot {
  toolRecordIds: string[];
}

export interface WrappedLoopResult {
  envelope: LoopEnvelope;
  child: WrappedCommandResult | null;
  postRun: WrapperPostRunResult | null;
}

interface ParsedMarkers {
  cleanedText: string;
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

function generatedSessionId(): string {
  return `datalox-wrapper-${randomUUID()}`;
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
    "# Datalox Agent Replay",
    "Record exact replay evidence first: tool I/O records, optional agent turns, and replay bundles.",
    "When MCP is available, call replay tools such as `record_tool_io`, `record_agent_turn`, and `pack_replay_bundle` for concrete evidence.",
    "Use `DATALOX_SESSION_ID` as `session_id` so wrapper post-run can attach new tool I/O to the completed turn.",
    "Do not synthesize replay data from prose summaries. If no agent-visible tool I/O was captured, leave post-run recording empty.",
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
  const sessionId = input.sessionId ?? nonEmptyString(process.env.DATALOX_SESSION_ID) ?? generatedSessionId();
  const baseEnvelope: LoopEnvelope = {
    repoPath,
    sessionId,
    active,
    originalPrompt,
    resolution: null,
    bootstrap,
    guidance: {
      workflow,
      selectionBasis: active ? "replay_capture" : "bootstrap_unavailable",
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

export async function captureReplayEvidenceSnapshot(repoPath: string): Promise<WrapperReplayEvidenceSnapshot> {
  const records = await readToolIoRecords(repoPath);
  return {
    toolRecordIds: records.map((record) => record.id),
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

function extractMarkers(text: string): ParsedMarkers {
  const parsed: ParsedMarkers = {
    cleanedText: text.trim(),
  };
  return parsed;
}

function mergeMarkers(left: ParsedMarkers, right: ParsedMarkers): ParsedMarkers {
  return {
    cleanedText: "",
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
  const postRunMode = input.postRunMode ?? "replay";
  if (!child || !envelope.active || postRunMode === "off") {
    return {
      mode: "off",
      trigger: "disabled",
      reason: !child
        ? "No child process ran, so wrapper post-run recording was skipped."
        : !envelope.active
          ? "Datalox was not active for this repo, so wrapper post-run recording was skipped."
          : "Wrapper post-run recording is disabled by DATALOX_DEFAULT_POST_RUN_MODE=off or --post-run-mode off.",
      result: null,
      review: null,
      backlog: null,
      maintenance: null,
    };
  }

  sanitizeWrappedCommandResult(child);
  const beforeIds = new Set(input.replayEvidenceBefore?.toolRecordIds ?? []);
  const recordsAfter = await readToolIoRecords(envelope.repoPath);
  const newToolRecords = recordsAfter.filter((record) => !beforeIds.has(record.id));
  if (newToolRecords.length === 0) {
    return {
      mode: "replay",
      trigger: "replay_capture_empty",
      reason: "No explicit tool_io_record.v1 records were created during this wrapped run; Datalox did not synthesize replay evidence from prose.",
      result: null,
      review: null,
      backlog: null,
      maintenance: null,
    };
  }

  const turnResult = await recordAgentTurn({
    repoPath: envelope.repoPath,
    agentTurn: buildWrapperAgentTurn(envelope, child, input.hostKind, newToolRecords),
  });

  return {
    mode: "replay",
    trigger: "replay_evidence_recorded",
    reason: `Recorded agent_turn.v1 from ${newToolRecords.length} explicit tool_io_record.v1 record(s) created during this wrapped run.`,
    result: {
      toolRecordCount: newToolRecords.length,
      toolRecordIds: newToolRecords.map((record) => record.id),
      event: {
        relativePath: turnResult.event.relativePath,
        turnId: turnResult.turnId,
      },
    },
    review: null,
    backlog: null,
    maintenance: null,
  };
}

function buildWrapperAgentTurn(
  envelope: LoopEnvelope,
  child: WrappedCommandResult,
  hostKind: string,
  toolRecords: ToolIoRecordV1[],
) {
  const now = new Date().toISOString();
  return {
    schema_version: "agent_turn.v1",
    id: `wrapper-${safeTimestamp(now)}`,
    session_id: envelope.sessionId ?? generatedSessionId(),
    turn_index: 0,
    created_at: now,
    ...(envelope.originalPrompt.trim().length > 0 ? { user_prompt: envelope.originalPrompt } : {}),
    assistant_summary: `Datalox wrapper recorded ${toolRecords.length} explicit tool I/O record(s) from the ${hostKind} child run.`,
    tool_calls: toolRecords.map((record) => ({
      tool: record.tool_name,
      call_id: record.call_id,
      tool_io_ref: {
        record_id: record.id,
        request_hash: record.request_hash,
        sequence_index: record.sequence_index,
      },
      ...(record.source?.command ? { command: record.source.command } : {}),
    })),
    verification: {
      command: [child.command, ...child.args].join(" "),
      status: child.exitCode === 0 ? "passed" : "failed",
      evidence: `Child process exited with code ${child.exitCode}.`,
    },
    export: {
      allowed: false,
      redaction: "blocked",
    },
  };
}

function safeTimestamp(timestamp: string): string {
  return timestamp.replace(/[:.]/g, "-");
}

function nonEmptyString(value: string | undefined): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value.trim() : null;
}
