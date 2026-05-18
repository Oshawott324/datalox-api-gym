import { readFile } from "node:fs/promises";
import path from "node:path";

import { getAgentTurnFromPayload } from "../../agentTurnStore.js";
import type { AgentTurnV1 } from "../../agentTurnSchema.js";
import {
  resolveReplayBundlePath,
  verifyReplayBundle,
  type VerifyReplayBundleResult,
} from "../../replayBundle.js";
import type { ReplayBundleV1 } from "../../replayBundleSchema.js";
import { parseToolIoRecordV1, type ToolIoRecordV1 } from "../../toolIoSchema.js";
import {
  gradeAgentTaskTrajectoryRow,
} from "./agentTaskTrajectoryExport.js";
import {
  parseAgentTaskTrajectoryV1,
  serializeAgentTaskTrajectoryJsonlRow,
  type AgentTaskEvidenceBlockV1,
  type AgentTaskTrajectoryQuality,
  type AgentTaskTrajectoryV1,
} from "./agentTaskTrajectorySchema.js";

type JsonObject = Record<string, unknown>;
type CurationSplit = "train" | "validation" | "test" | "eval";

export interface DeriveAgentTaskTrajectoryFromReplayBundleInput {
  repoPath?: string;
  bundlePath: string;
  trajectoryId?: string;
  now?: Date;
  quality?: AgentTaskTrajectoryQuality;
  split?: CurationSplit;
}

export interface DeriveAgentTaskTrajectoryFromReplayBundleResult {
  verified: true;
  replayBundle: {
    bundleId: string;
    bundlePath: string;
    manifest: ReplayBundleV1;
    checkedFiles: number;
  };
  row: AgentTaskTrajectoryV1;
  jsonl: string;
  readiness: ReturnType<typeof gradeAgentTaskTrajectoryRow>;
}

export class ReplayBundleDerivativeError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ReplayBundleDerivativeError";
  }
}

export async function deriveAgentTaskTrajectoryFromReplayBundle(
  input: DeriveAgentTaskTrajectoryFromReplayBundleInput,
): Promise<DeriveAgentTaskTrajectoryFromReplayBundleResult> {
  const verification = await verifyReplayBundle({
    repoPath: input.repoPath,
    bundlePath: input.bundlePath,
  });
  const repoRoot = path.resolve(input.repoPath ?? process.cwd());
  const absoluteBundlePath = resolveReplayBundlePath(input.repoPath, input.bundlePath);
  const bundlePath = normalizeRelativePath(path.relative(repoRoot, absoluteBundlePath));
  const [turns, toolRecords] = await Promise.all([
    readBundledAgentTurns(absoluteBundlePath, verification.manifest),
    readBundledToolRecords(absoluteBundlePath, verification.manifest),
  ]);
  const row = parseAgentTaskTrajectoryV1(buildAgentTaskTrajectoryRow({
    verification,
    bundlePath,
    turns,
    toolRecords,
    trajectoryId: input.trajectoryId,
    now: input.now,
    quality: input.quality,
    split: input.split,
  }));

  return {
    verified: true,
    replayBundle: {
      bundleId: verification.manifest.id,
      bundlePath,
      manifest: verification.manifest,
      checkedFiles: verification.checkedFiles,
    },
    row,
    jsonl: serializeAgentTaskTrajectoryJsonlRow(row),
    readiness: gradeAgentTaskTrajectoryRow(row),
  };
}

async function readBundledAgentTurns(
  absoluteBundlePath: string,
  manifest: ReplayBundleV1,
): Promise<AgentTurnV1[]> {
  const turns: AgentTurnV1[] = [];
  for (const relativePath of manifest.source.turn_event_paths) {
    const payload = JSON.parse(await readFile(resolveBundleRelativePath(absoluteBundlePath, relativePath), "utf8"));
    const turn = getAgentTurnFromPayload(payload);
    if (!turn) {
      throw new ReplayBundleDerivativeError(`Bundled agent turn does not contain agent_turn.v1: ${relativePath}`);
    }
    turns.push(turn);
  }
  return turns.sort((left, right) => (
    left.session_id.localeCompare(right.session_id)
    || left.turn_index - right.turn_index
    || left.id.localeCompare(right.id)
  ));
}

async function readBundledToolRecords(
  absoluteBundlePath: string,
  manifest: ReplayBundleV1,
): Promise<ToolIoRecordV1[]> {
  const records: ToolIoRecordV1[] = [];
  for (const relativePath of manifest.source.tool_io_record_paths) {
    records.push(parseToolIoRecordV1(JSON.parse(
      await readFile(resolveBundleRelativePath(absoluteBundlePath, relativePath), "utf8"),
    )));
  }
  return records.sort((left, right) => (
    (left.created_at ?? "").localeCompare(right.created_at ?? "")
    || (left.turn_id ?? "").localeCompare(right.turn_id ?? "")
    || left.call_id.localeCompare(right.call_id)
    || left.request_hash.localeCompare(right.request_hash)
    || left.sequence_index - right.sequence_index
  ));
}

function buildAgentTaskTrajectoryRow(input: {
  verification: VerifyReplayBundleResult;
  bundlePath: string;
  turns: AgentTurnV1[];
  toolRecords: ToolIoRecordV1[];
  trajectoryId?: string;
  now?: Date;
  quality?: AgentTaskTrajectoryQuality;
  split?: CurationSplit;
}): AgentTaskTrajectoryV1 {
  const manifest = input.verification.manifest;
  const evidenceBlocks = buildEvidenceBlocks(input.turns, input.toolRecords, manifest, input.bundlePath);
  const outcome = deriveOutcome(input.turns, evidenceBlocks);
  const changedArtifacts = collectChangedArtifacts(input.turns, evidenceBlocks);
  const row = {
    schema_version: "agent_task_trajectory.v1",
    id: input.trajectoryId ?? `derived-${safeId(manifest.id)}`,
    created_at: (input.now ?? new Date(manifest.created_at)).toISOString(),
    task: {
      prompt: manifest.task?.prompt ?? firstPrompt(input.turns) ?? `Replay bundle ${manifest.id}`,
      domains: manifest.task?.domains && manifest.task.domains.length > 0
        ? manifest.task.domains
        : ["agent_replay"],
      ...(manifest.task?.workflows !== undefined ? { workflows: manifest.task.workflows } : {}),
      environment: "Derived from a verified Datalox replay bundle.",
    },
    context: {
      problem: manifest.title ?? firstPrompt(input.turns) ?? `Replay bundle ${manifest.id}`,
      background: [
        `Source replay bundle ${manifest.id} verified with ${input.verification.checkedFiles} checksum entries.`,
        `Bundle contains ${manifest.replay.turn_count} agent turn(s) and ${manifest.replay.tool_record_count} tool I/O record(s).`,
      ].join(" "),
      source_paths: [
        normalizeRelativePath(path.join(input.bundlePath, "manifest.json")),
        ...manifest.source.turn_event_paths.map((sourcePath) => normalizeRelativePath(path.join(input.bundlePath, sourcePath))),
        ...manifest.source.tool_io_record_paths.map((sourcePath) => normalizeRelativePath(path.join(input.bundlePath, sourcePath))),
      ],
      notes: [
        "This derivative is a compact view; the replay bundle remains the source-of-truth artifact.",
      ],
    },
    trajectory: buildTrajectorySteps(input.turns, input.toolRecords),
    evidence_blocks: evidenceBlocks,
    final: {
      summary: finalSummary(input.turns, manifest),
      ...(changedArtifacts.length > 0 ? { changed_artifacts: changedArtifacts } : {}),
      explanation: "Derived only after replay bundle checksum verification; exact replay evidence stays in the source bundle.",
    },
    outcome,
    ...(outcome.label === "success" ? { trajectory_type: "success" as const } : {}),
    ...(outcome.label === "failure" ? { trajectory_type: "failure" as const } : {}),
    replay_bundle_ref: {
      bundle_id: manifest.id,
      bundle_path: input.bundlePath,
    },
    export: {
      allowed: manifest.export.allowed,
      redaction: manifest.export.redaction,
    },
    curation: {
      ...(input.split !== undefined ? { split: input.split } : {}),
      quality: input.quality ?? "needs_review",
      tags: buildTags(manifest, evidenceBlocks),
      notes: "Derived from a verified replay bundle. Review before use-quality export.",
    },
    metadata: {
      source_replay_bundle_id: manifest.id,
      source_replay_bundle_path: input.bundlePath,
      source_replay_bundle_checked_files: input.verification.checkedFiles,
      source_replay_tool_record_count: manifest.replay.tool_record_count,
      source_replay_turn_count: manifest.replay.turn_count,
    },
  } satisfies AgentTaskTrajectoryV1;

  return row;
}

function buildTrajectorySteps(
  turns: AgentTurnV1[],
  toolRecords: ToolIoRecordV1[],
): AgentTaskTrajectoryV1["trajectory"] {
  const steps: AgentTaskTrajectoryV1["trajectory"] = [];
  for (const turn of turns) {
    if (turn.user_prompt) {
      steps.push({
        role: "user",
        content: turn.user_prompt,
      });
    }
    if (turn.assistant_summary) {
      steps.push({
        role: "agent",
        content: turn.assistant_summary,
      });
    }
    for (const toolCall of turn.tool_calls) {
      steps.push({
        role: "tool",
        tool: toolCall.tool,
        ...(toolCall.command !== undefined ? { command: toolCall.command } : {}),
        ...(toolCall.exit_code !== undefined ? { exit_code: toolCall.exit_code } : {}),
        content: toolCall.output_summary
          ?? toolCall.args_summary
          ?? `Recorded ${toolCall.tool} call${toolCall.call_id ? ` ${toolCall.call_id}` : ""}.`,
      });
    }
  }

  if (steps.length > 0) {
    return steps;
  }

  return toolRecords.length > 0
    ? toolRecords.map((record) => ({
      role: "tool" as const,
      tool: record.tool_name,
      content: `Recorded ${record.tool_name} call ${record.call_id} with observation status ${record.observation.status}.`,
    }))
    : [{
      role: "agent",
      content: "Verified replay bundle contained no recorded turns or tool I/O records.",
    }];
}

function buildEvidenceBlocks(
  turns: AgentTurnV1[],
  toolRecords: ToolIoRecordV1[],
  manifest: ReplayBundleV1,
  bundlePath: string,
): AgentTaskEvidenceBlockV1[] {
  const evidenceBlocks: AgentTaskEvidenceBlockV1[] = [
    ...buildCodeChangeEvidence(toolRecords),
    ...buildCommandResultEvidence(turns, toolRecords),
  ];

  if (evidenceBlocks.length > 0) {
    return evidenceBlocks;
  }

  return [{
    type: "source_reference",
    source_kind: "local_file",
    title: "Verified replay bundle manifest",
    source_path: normalizeRelativePath(path.join(bundlePath, "manifest.json")),
    excerpt: `Replay bundle ${manifest.id} verified with ${manifest.replay.turn_count} turn(s) and ${manifest.replay.tool_record_count} tool I/O record(s).`,
    relevance: "The verified manifest is the source-of-truth provenance for this compact derivative candidate.",
  }];
}

function buildCodeChangeEvidence(toolRecords: ToolIoRecordV1[]): AgentTaskEvidenceBlockV1[] {
  const evidenceBlocks: AgentTaskEvidenceBlockV1[] = [];
  for (const record of toolRecords) {
    if (record.tool_name !== "apply_patch") {
      continue;
    }
    const patch = extractPatch(record.arguments);
    if (!patch) {
      continue;
    }
    for (const filePath of extractPatchFilePaths(patch)) {
      evidenceBlocks.push({
        type: "code_change",
        path: filePath,
        language: languageFromPath(filePath),
        patch,
        reason: `Captured from bundled apply_patch tool I/O record ${record.id}.`,
      });
    }
  }
  return evidenceBlocks;
}

function buildCommandResultEvidence(
  turns: AgentTurnV1[],
  toolRecords: ToolIoRecordV1[],
): AgentTaskEvidenceBlockV1[] {
  const evidenceBlocks: AgentTaskEvidenceBlockV1[] = [];

  for (const turn of turns) {
    if (!turn.verification?.command) {
      continue;
    }
    const exitCode = verificationExitCode(turn.verification.status);
    if (exitCode === undefined) {
      continue;
    }
    evidenceBlocks.push({
      type: "command_result",
      command: turn.verification.command,
      exit_code: exitCode,
      result_summary: turn.verification.evidence
        ?? `Verification ${turn.verification.status} for ${turn.verification.command}.`,
      ...(turn.verification.evidence !== undefined ? { evidence: turn.verification.evidence } : {}),
    });
  }

  for (const record of toolRecords) {
    const command = extractCommand(record.arguments);
    const exitCode = extractExitCode(record.observation.content);
    if (command === undefined || exitCode === undefined) {
      continue;
    }
    const evidence = extractCommandEvidence(record.observation.content);
    evidenceBlocks.push({
      type: "command_result",
      command,
      exit_code: exitCode,
      result_summary: extractCommandSummary(record.observation.content, exitCode),
      ...(evidence !== undefined ? { evidence } : {}),
    });
  }

  return dedupeCommandResultEvidence(evidenceBlocks);
}

function deriveOutcome(
  turns: AgentTurnV1[],
  evidenceBlocks: AgentTaskEvidenceBlockV1[],
): AgentTaskTrajectoryV1["outcome"] {
  const verificationStatuses = turns
    .map((turn) => turn.verification)
    .filter((verification): verification is NonNullable<AgentTurnV1["verification"]> => verification !== undefined);
  const failedVerification = verificationStatuses.find((verification) => verification.status === "failed");
  if (failedVerification) {
    return {
      label: "failure",
      verification: "failed",
      ...(failedVerification.command !== undefined ? { command: failedVerification.command } : {}),
      ...(failedVerification.evidence !== undefined ? { evidence: failedVerification.evidence } : {}),
    };
  }

  const passedVerification = verificationStatuses.find((verification) => verification.status === "passed");
  if (passedVerification) {
    return {
      label: "success",
      verification: "passed",
      ...(passedVerification.command !== undefined ? { command: passedVerification.command } : {}),
      ...(passedVerification.evidence !== undefined ? { evidence: passedVerification.evidence } : {}),
    };
  }

  const commandResults = evidenceBlocks.filter((block): block is Extract<AgentTaskEvidenceBlockV1, { type: "command_result" }> => (
    block.type === "command_result"
  ));
  const failedCommand = commandResults.find((block) => block.exit_code !== 0);
  if (failedCommand) {
    return {
      label: "failure",
      verification: "failed",
      command: failedCommand.command,
      evidence: failedCommand.result_summary,
    };
  }
  const passedCommand = commandResults.find((block) => block.exit_code === 0);
  if (passedCommand) {
    return {
      label: "success",
      verification: "passed",
      command: passedCommand.command,
      evidence: passedCommand.result_summary,
    };
  }

  return {
    label: "partial",
    verification: "not_run",
    evidence: "Replay bundle verified, but no explicit task verification command was bundled.",
  };
}

function collectChangedArtifacts(turns: AgentTurnV1[], evidenceBlocks: AgentTaskEvidenceBlockV1[]): string[] {
  const changedArtifacts = new Set<string>();
  for (const turn of turns) {
    for (const fileChange of turn.file_changes ?? []) {
      changedArtifacts.add(fileChange.path);
    }
  }
  for (const block of evidenceBlocks) {
    if (block.type === "code_change") {
      changedArtifacts.add(block.path);
    }
    if ("artifact" in block) {
      changedArtifacts.add(block.artifact);
    }
  }
  return Array.from(changedArtifacts).sort();
}

function finalSummary(turns: AgentTurnV1[], manifest: ReplayBundleV1): string {
  for (const turn of [...turns].reverse()) {
    if (turn.assistant_summary) {
      return turn.assistant_summary;
    }
  }
  return manifest.title ?? manifest.task?.prompt ?? `Derived replay bundle ${manifest.id}.`;
}

function firstPrompt(turns: AgentTurnV1[]): string | undefined {
  return turns.find((turn) => turn.user_prompt)?.user_prompt;
}

function buildTags(manifest: ReplayBundleV1, evidenceBlocks: AgentTaskEvidenceBlockV1[]): string[] {
  return Array.from(new Set([
    "replay-bundle-derived",
    "agent_task_trajectory.v1",
    ...(manifest.task?.domains ?? []),
    ...(manifest.task?.workflows ?? []),
    ...evidenceBlocks.map((block) => block.type),
  ])).sort();
}

function extractPatch(argumentsValue: unknown): string | undefined {
  if (typeof argumentsValue === "string" && argumentsValue.trim().length > 0) {
    return argumentsValue;
  }
  const object = getObject(argumentsValue);
  const patch = object.patch;
  return typeof patch === "string" && patch.trim().length > 0 ? patch : undefined;
}

function extractPatchFilePaths(patch: string): string[] {
  const filePaths = new Set<string>();
  for (const line of patch.split(/\r?\n/u)) {
    const dataloxPatchMatch = /^\*\*\* (?:Add|Update|Delete) File: (.+)$/u.exec(line);
    if (dataloxPatchMatch) {
      filePaths.add(dataloxPatchMatch[1]);
      continue;
    }
    const gitDiffMatch = /^diff --git a\/(.+?) b\/(.+)$/u.exec(line);
    if (gitDiffMatch) {
      filePaths.add(gitDiffMatch[2]);
      continue;
    }
    const plusPathMatch = /^\+\+\+ b\/(.+)$/u.exec(line);
    if (plusPathMatch) {
      filePaths.add(plusPathMatch[1]);
    }
  }
  return Array.from(filePaths).sort();
}

function extractCommand(argumentsValue: unknown): string | undefined {
  const object = getObject(argumentsValue);
  for (const key of ["command", "cmd"] as const) {
    const value = object[key];
    if (typeof value === "string" && value.trim().length > 0) {
      return value;
    }
  }
  return undefined;
}

function extractExitCode(content: unknown): number | undefined {
  const object = getObject(content);
  for (const key of ["exit_code", "exitCode"] as const) {
    const value = object[key];
    if (typeof value === "number" && Number.isInteger(value)) {
      return value;
    }
  }
  return undefined;
}

function extractCommandSummary(content: unknown, exitCode: number): string {
  const object = getObject(content);
  for (const key of ["result_summary", "summary"] as const) {
    const value = object[key];
    if (typeof value === "string" && value.trim().length > 0) {
      return compact(value);
    }
  }
  const stdout = object.stdout;
  if (typeof stdout === "string" && stdout.trim().length > 0) {
    return compact(stdout);
  }
  return `Command exited with code ${exitCode}.`;
}

function extractCommandEvidence(content: unknown): string | undefined {
  const object = getObject(content);
  const parts: string[] = [];
  for (const key of ["stdout", "stderr"] as const) {
    const value = object[key];
    if (typeof value === "string" && value.trim().length > 0) {
      parts.push(`${key}: ${compact(value)}`);
    }
  }
  return parts.length > 0 ? parts.join("\n") : undefined;
}

function verificationExitCode(
  status: NonNullable<AgentTurnV1["verification"]>["status"],
): number | undefined {
  switch (status) {
    case "passed":
      return 0;
    case "failed":
      return 1;
    default:
      return undefined;
  }
}

function dedupeCommandResultEvidence(evidenceBlocks: AgentTaskEvidenceBlockV1[]): AgentTaskEvidenceBlockV1[] {
  const seen = new Set<string>();
  const deduped: AgentTaskEvidenceBlockV1[] = [];
  for (const block of evidenceBlocks) {
    if (block.type !== "command_result") {
      deduped.push(block);
      continue;
    }
    const key = `${block.command}\0${block.exit_code}\0${block.result_summary}`;
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    deduped.push(block);
  }
  return deduped;
}

function languageFromPath(filePath: string): string | undefined {
  const extension = path.extname(filePath).toLowerCase();
  switch (extension) {
    case ".js":
    case ".jsx":
    case ".mjs":
      return "javascript";
    case ".ts":
    case ".tsx":
    case ".mts":
      return "typescript";
    case ".py":
      return "python";
    case ".rs":
      return "rust";
    case ".go":
      return "go";
    case ".java":
      return "java";
    case ".json":
      return "json";
    case ".md":
      return "markdown";
    case ".sh":
      return "shell";
    case ".sql":
      return "sql";
    case ".yaml":
    case ".yml":
      return "yaml";
    default:
      return undefined;
  }
}

function resolveBundleRelativePath(bundlePath: string, relativePath: string): string {
  if (path.isAbsolute(relativePath) || relativePath.includes("\\") || relativePath.split("/").includes("..")) {
    throw new ReplayBundleDerivativeError(`Bundle path must be relative and stay inside the bundle: ${relativePath}`);
  }
  const resolved = path.resolve(bundlePath, relativePath);
  const relative = path.relative(bundlePath, resolved);
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new ReplayBundleDerivativeError(`Bundle path escapes bundle directory: ${relativePath}`);
  }
  return resolved;
}

function getObject(value: unknown): JsonObject {
  return value && typeof value === "object" && !Array.isArray(value) ? value as JsonObject : {};
}

function compact(value: string): string {
  return value.trim().replace(/\s+/gu, " ").slice(0, 1000);
}

function safeId(value: string): string {
  const safe = value
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 96);
  return safe.length > 0 ? safe : "replay-bundle";
}

function normalizeRelativePath(filePath: string): string {
  return filePath.split(path.sep).join("/");
}
