import { existsSync } from "node:fs";
import { copyFile, mkdir, readdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";

import { sha256Hex } from "./hash.js";
import {
  parseReplayBundleChecksumsV1,
  parseReplayBundleV1,
  type ReplayBundleChecksumsV1,
  type ReplayBundleV1,
} from "./replayBundleSchema.js";
import { parseToolIoRecordV1, type ToolIoRecordV1 } from "./toolIoSchema.js";
import { TOOL_IO_RECORDS_RELATIVE_DIR } from "./toolIoStore.js";

export const REPLAY_BUNDLES_RELATIVE_DIR = path.join(".datalox", "replay-bundles");
export const AGENT_TURNS_RELATIVE_DIR = path.join(".datalox", "events", "agent-turns");

type JsonObject = Record<string, unknown>;

interface SourceArtifact {
  sourcePath: string;
  targetPath: string;
  parsed?: unknown;
}

interface ParsedAgentTurn {
  id: string;
  sessionId: string;
}

export interface PackReplayBundleInput {
  repoPath?: string;
  bundleId: string;
  title?: string;
  task?: {
    prompt?: string;
    domains?: string[];
    workflows?: string[];
  };
  export?: {
    allowed: boolean;
    redaction: "none_needed" | "applied" | "blocked";
    approval_id?: string;
  };
  now?: Date;
}

export interface PackReplayBundleResult {
  bundlePath: string;
  manifestPath: string;
  checksumsPath: string;
  manifest: ReplayBundleV1;
  checksums: ReplayBundleChecksumsV1;
}

export interface VerifyReplayBundleInput {
  repoPath?: string;
  bundlePath: string;
}

export interface VerifyReplayBundleResult {
  bundlePath: string;
  manifest: ReplayBundleV1;
  checksums: ReplayBundleChecksumsV1;
  verified: true;
  checkedFiles: number;
}

export class ReplayBundleError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ReplayBundleError";
  }
}

export class ReplayBundleVerificationError extends Error {
  readonly issues: string[];

  constructor(issues: string[]) {
    super(`Replay bundle verification failed: ${issues.join("; ")}`);
    this.name = "ReplayBundleVerificationError";
    this.issues = issues;
  }
}

export async function packReplayBundle(input: PackReplayBundleInput): Promise<PackReplayBundleResult> {
  const repoRoot = resolveRepoRoot(input.repoPath);
  assertBundleId(input.bundleId);
  const absoluteBundlePath = path.join(repoRoot, REPLAY_BUNDLES_RELATIVE_DIR, input.bundleId);
  if (existsSync(absoluteBundlePath)) {
    throw new ReplayBundleError(`Replay bundle already exists: ${normalizeRelativePath(path.relative(repoRoot, absoluteBundlePath))}`);
  }

  const toolArtifacts = await collectToolIoArtifacts(repoRoot);
  const turnArtifacts = await collectAgentTurnArtifacts(repoRoot);
  const sessionIds = collectSessionIds(toolArtifacts, turnArtifacts);
  const manifest = parseReplayBundleV1({
    schema_version: "replay_bundle.v1",
    id: input.bundleId,
    created_at: (input.now ?? new Date()).toISOString(),
    ...(input.title !== undefined ? { title: input.title } : {}),
    ...(input.task !== undefined ? { task: input.task } : {}),
    source: {
      repo_path: repoRoot,
      session_ids: sessionIds,
      turn_event_paths: turnArtifacts.map((artifact) => artifact.targetPath),
      tool_io_record_paths: toolArtifacts.map((artifact) => artifact.targetPath),
    },
    replay: {
      tool_record_count: toolArtifacts.length,
      turn_count: turnArtifacts.length,
      deterministic: hasDeterministicToolReplayKeys(toolArtifacts),
    },
    checksums_path: "checksums.json",
    export: input.export ?? {
      allowed: false,
      redaction: "blocked",
    },
  });

  if (!manifest.replay.deterministic) {
    throw new ReplayBundleError("Replay bundle contains duplicate tool replay keys.");
  }

  await mkdir(path.dirname(absoluteBundlePath), { recursive: true });
  await mkdir(absoluteBundlePath, { recursive: false });
  try {
    await writeBundleArtifacts(absoluteBundlePath, [...toolArtifacts, ...turnArtifacts]);
    const absoluteManifestPath = path.join(absoluteBundlePath, "manifest.json");
    await writeJsonFile(absoluteManifestPath, manifest);
    const checksums = await buildReplayBundleChecksums(absoluteBundlePath, manifest.id);
    await writeJsonFile(path.join(absoluteBundlePath, "checksums.json"), checksums);

    return {
      bundlePath: normalizeRelativePath(path.relative(repoRoot, absoluteBundlePath)),
      manifestPath: normalizeRelativePath(path.relative(repoRoot, absoluteManifestPath)),
      checksumsPath: normalizeRelativePath(path.join(path.relative(repoRoot, absoluteBundlePath), "checksums.json")),
      manifest,
      checksums,
    };
  } catch (error) {
    await rm(absoluteBundlePath, { recursive: true, force: true });
    throw error;
  }
}

export async function verifyReplayBundle(input: VerifyReplayBundleInput): Promise<VerifyReplayBundleResult> {
  const repoRoot = resolveRepoRoot(input.repoPath);
  const absoluteBundlePath = resolveBundlePath(repoRoot, input.bundlePath);
  const issues: string[] = [];
  const manifestPath = path.join(absoluteBundlePath, "manifest.json");
  const checksumsPath = path.join(absoluteBundlePath, "checksums.json");

  let manifest: ReplayBundleV1 | null = null;
  let checksums: ReplayBundleChecksumsV1 | null = null;

  try {
    manifest = parseReplayBundleV1(JSON.parse(await readFile(manifestPath, "utf8")));
  } catch (error) {
    issues.push(`invalid_manifest: ${formatError(error)}`);
  }

  try {
    checksums = parseReplayBundleChecksumsV1(JSON.parse(await readFile(checksumsPath, "utf8")));
  } catch (error) {
    issues.push(`invalid_checksums: ${formatError(error)}`);
  }

  if (manifest && path.basename(absoluteBundlePath) !== manifest.id) {
    issues.push(`manifest_id_mismatch: bundle directory is ${path.basename(absoluteBundlePath)} but manifest id is ${manifest.id}`);
  }

  if (manifest && checksums && checksums.replay_bundle_id !== manifest.id) {
    issues.push(`checksums_bundle_id_mismatch: ${checksums.replay_bundle_id}`);
  }

  if (manifest) {
    issues.push(...verifyManifestBundlePaths(manifest));
  }

  if (checksums) {
    issues.push(...await verifyChecksums(absoluteBundlePath, checksums));
  }

  if (manifest) {
    issues.push(...await verifyBundledToolRecords(absoluteBundlePath, manifest));
  }

  if (issues.length > 0 || !manifest || !checksums) {
    throw new ReplayBundleVerificationError(issues.length > 0 ? issues : ["unknown_verification_failure"]);
  }

  return {
    bundlePath: normalizeRelativePath(path.isAbsolute(input.bundlePath)
      ? input.bundlePath
      : path.join(repoRoot, input.bundlePath)),
    manifest,
    checksums,
    verified: true,
    checkedFiles: checksums.files.length,
  };
}

async function collectToolIoArtifacts(repoRoot: string): Promise<SourceArtifact[]> {
  const recordsRoot = path.join(repoRoot, TOOL_IO_RECORDS_RELATIVE_DIR);
  if (!existsSync(recordsRoot)) {
    return [];
  }
  const sourcePaths = await listJsonFiles(recordsRoot);
  const artifacts: SourceArtifact[] = [];
  const targetPaths = new Set<string>();
  for (const sourcePath of sourcePaths.sort()) {
    const parsed = parseToolIoRecordV1(JSON.parse(await readFile(sourcePath, "utf8")));
    const targetPath = normalizeRelativePath(path.join("tool-io", `${safeFileName(parsed.id)}.json`));
    if (targetPaths.has(targetPath)) {
      throw new ReplayBundleError(`Duplicate bundled tool I/O target path: ${targetPath}`);
    }
    targetPaths.add(targetPath);
    artifacts.push({ sourcePath, targetPath, parsed });
  }
  return artifacts.sort((first, second) => first.targetPath.localeCompare(second.targetPath));
}

async function collectAgentTurnArtifacts(repoRoot: string): Promise<SourceArtifact[]> {
  const turnsRoot = path.join(repoRoot, AGENT_TURNS_RELATIVE_DIR);
  if (!existsSync(turnsRoot)) {
    return [];
  }
  const sourcePaths = await listJsonFiles(turnsRoot);
  const artifacts: SourceArtifact[] = [];
  const targetPaths = new Set<string>();
  for (const sourcePath of sourcePaths.sort()) {
    const payload = JSON.parse(await readFile(sourcePath, "utf8"));
    const parsed = parseAgentTurnPayload(payload, sourcePath);
    const targetPath = normalizeRelativePath(path.join("agent-turns", `${safeFileName(parsed.id)}.json`));
    if (targetPaths.has(targetPath)) {
      throw new ReplayBundleError(`Duplicate bundled agent turn target path: ${targetPath}`);
    }
    targetPaths.add(targetPath);
    artifacts.push({ sourcePath, targetPath, parsed });
  }
  return artifacts.sort((first, second) => first.targetPath.localeCompare(second.targetPath));
}

function parseAgentTurnPayload(payload: unknown, sourcePath: string): ParsedAgentTurn {
  const candidate = getAgentTurnCandidate(payload);
  if (!candidate) {
    throw new ReplayBundleError(`Agent turn event does not contain agent_turn.v1: ${sourcePath}`);
  }
  const id = getString(candidate.id);
  const sessionId = getString(candidate.session_id);
  const turnIndex = candidate.turn_index;
  const createdAt = getString(candidate.created_at);
  const toolCalls = candidate.tool_calls;
  const exportGate = getObject(candidate.export);
  if (
    !id
    || !sessionId
    || typeof turnIndex !== "number"
    || !Number.isInteger(turnIndex)
    || turnIndex < 0
    || !createdAt
    || !Array.isArray(toolCalls)
    || typeof exportGate.allowed !== "boolean"
    || !["none_needed", "applied", "blocked"].includes(String(exportGate.redaction))
  ) {
    throw new ReplayBundleError(`Invalid agent_turn.v1 event: ${sourcePath}`);
  }
  return {
    id,
    sessionId,
  };
}

function getAgentTurnCandidate(payload: unknown): JsonObject | null {
  const object = getObject(payload);
  if (object.schema_version === "agent_turn.v1") {
    return object;
  }
  const wrapped = getObject(object.agentTurn);
  if (wrapped.schema_version === "agent_turn.v1") {
    return wrapped;
  }
  return null;
}

function collectSessionIds(toolArtifacts: SourceArtifact[], turnArtifacts: SourceArtifact[]): string[] {
  const sessionIds = new Set<string>();
  for (const artifact of toolArtifacts) {
    const record = artifact.parsed as ToolIoRecordV1;
    if (record.session_id) {
      sessionIds.add(record.session_id);
    }
  }
  for (const artifact of turnArtifacts) {
    const turn = artifact.parsed as ParsedAgentTurn;
    sessionIds.add(turn.sessionId);
  }
  return Array.from(sessionIds).sort();
}

function hasDeterministicToolReplayKeys(toolArtifacts: SourceArtifact[]): boolean {
  const replayKeys = new Set<string>();
  for (const artifact of toolArtifacts) {
    const record = artifact.parsed as ToolIoRecordV1;
    const replayKey = `${record.request_hash}:${record.sequence_index}`;
    if (replayKeys.has(replayKey)) {
      return false;
    }
    replayKeys.add(replayKey);
  }
  return true;
}

async function writeBundleArtifacts(bundlePath: string, artifacts: SourceArtifact[]): Promise<void> {
  for (const artifact of artifacts) {
    const targetPath = resolveBundleRelativePath(bundlePath, artifact.targetPath);
    await mkdir(path.dirname(targetPath), { recursive: true });
    await copyFile(artifact.sourcePath, targetPath);
  }
}

async function buildReplayBundleChecksums(
  bundlePath: string,
  replayBundleId: string,
): Promise<ReplayBundleChecksumsV1> {
  const relativeFilePaths = await listBundleFiles(bundlePath);
  return parseReplayBundleChecksumsV1({
    schema_version: "replay_bundle_checksums.v1",
    replay_bundle_id: replayBundleId,
    algorithm: "sha256",
    files: await Promise.all(relativeFilePaths
      .filter((relativePath) => relativePath !== "checksums.json")
      .sort()
      .map(async (relativePath) => ({
        path: relativePath,
        sha256: sha256Hex(await readFile(resolveBundleRelativePath(bundlePath, relativePath))),
      }))),
  });
}

function verifyManifestBundlePaths(manifest: ReplayBundleV1): string[] {
  const issues: string[] = [];
  for (const sourcePath of manifest.source.tool_io_record_paths) {
    if (!sourcePath.startsWith("tool-io/")) {
      issues.push(`manifest_tool_io_path_outside_bundle: ${sourcePath}`);
    }
  }
  for (const sourcePath of manifest.source.turn_event_paths) {
    if (!sourcePath.startsWith("agent-turns/")) {
      issues.push(`manifest_turn_path_outside_bundle: ${sourcePath}`);
    }
  }
  if (manifest.checksums_path !== "checksums.json") {
    issues.push(`manifest_checksums_path_invalid: ${manifest.checksums_path}`);
  }
  return issues;
}

async function verifyChecksums(
  bundlePath: string,
  checksums: ReplayBundleChecksumsV1,
): Promise<string[]> {
  const issues: string[] = [];
  const actualFiles = (await listBundleFiles(bundlePath))
    .filter((relativePath) => relativePath !== "checksums.json")
    .sort();
  const listedFiles = checksums.files.map((entry) => entry.path).sort();

  for (const listedFile of listedFiles) {
    if (!actualFiles.includes(listedFile)) {
      issues.push(`listed_file_missing: ${listedFile}`);
      continue;
    }
    const actualHash = sha256Hex(await readFile(resolveBundleRelativePath(bundlePath, listedFile)));
    const expectedHash = checksums.files.find((entry) => entry.path === listedFile)?.sha256;
    if (expectedHash !== actualHash) {
      issues.push(`checksum_mismatch: ${listedFile}`);
    }
  }

  for (const actualFile of actualFiles) {
    if (!listedFiles.includes(actualFile)) {
      issues.push(`unlisted_file_present: ${actualFile}`);
    }
  }

  return issues;
}

async function verifyBundledToolRecords(
  bundlePath: string,
  manifest: ReplayBundleV1,
): Promise<string[]> {
  const issues: string[] = [];
  const replayKeys = new Set<string>();
  for (const sourcePath of manifest.source.tool_io_record_paths) {
    try {
      const record = parseToolIoRecordV1(JSON.parse(
        await readFile(resolveBundleRelativePath(bundlePath, sourcePath), "utf8"),
      ));
      const replayKey = `${record.request_hash}:${record.sequence_index}`;
      if (replayKeys.has(replayKey)) {
        issues.push(`duplicate_tool_replay_key: ${replayKey}`);
      }
      replayKeys.add(replayKey);
    } catch (error) {
      issues.push(`invalid_tool_io_record: ${sourcePath}: ${formatError(error)}`);
    }
  }

  const actualToolCount = manifest.source.tool_io_record_paths.length;
  const actualTurnCount = manifest.source.turn_event_paths.length;
  if (manifest.replay.tool_record_count !== actualToolCount) {
    issues.push(`tool_record_count_mismatch: manifest=${manifest.replay.tool_record_count} actual=${actualToolCount}`);
  }
  if (manifest.replay.turn_count !== actualTurnCount) {
    issues.push(`turn_count_mismatch: manifest=${manifest.replay.turn_count} actual=${actualTurnCount}`);
  }
  if (!manifest.replay.deterministic) {
    issues.push("manifest_replay_not_deterministic");
  }

  return issues;
}

async function listJsonFiles(directory: string): Promise<string[]> {
  const entries = await readdir(directory, { withFileTypes: true });
  const files: string[] = [];
  for (const entry of entries) {
    const absolutePath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      files.push(...await listJsonFiles(absolutePath));
    } else if (entry.isFile() && entry.name.endsWith(".json")) {
      files.push(absolutePath);
    }
  }
  return files.sort();
}

async function listBundleFiles(directory: string): Promise<string[]> {
  const entries = await readdir(directory, { withFileTypes: true });
  const files: string[] = [];
  for (const entry of entries) {
    const absolutePath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      const childFiles = await listBundleFiles(absolutePath);
      files.push(...childFiles.map((child) => normalizeRelativePath(path.join(entry.name, child))));
    } else if (entry.isFile()) {
      files.push(entry.name);
    }
  }
  return files.sort();
}

function resolveBundlePath(repoRoot: string, bundlePath: string): string {
  return path.resolve(path.isAbsolute(bundlePath) ? bundlePath : path.join(repoRoot, bundlePath));
}

function resolveBundleRelativePath(bundlePath: string, relativePath: string): string {
  if (path.isAbsolute(relativePath) || relativePath.includes("\\") || relativePath.split("/").includes("..")) {
    throw new ReplayBundleError(`Bundle path must be relative and stay inside the bundle: ${relativePath}`);
  }
  const resolved = path.resolve(bundlePath, relativePath);
  const relative = path.relative(bundlePath, resolved);
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new ReplayBundleError(`Bundle path escapes bundle directory: ${relativePath}`);
  }
  return resolved;
}

function assertBundleId(bundleId: string): void {
  if (!/^[A-Za-z0-9._-]+$/.test(bundleId)) {
    throw new ReplayBundleError("bundleId must contain only letters, numbers, dot, underscore, or hyphen.");
  }
}

function safeFileName(value: string): string {
  const safe = value
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 120);
  return safe.length > 0 ? safe : "artifact";
}

function getObject(value: unknown): JsonObject {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as JsonObject) : {};
}

function getString(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function resolveRepoRoot(repoPath: string | undefined): string {
  return path.resolve(repoPath ?? process.cwd());
}

async function writeJsonFile(filePath: string, payload: unknown): Promise<void> {
  await writeFile(filePath, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
}

function normalizeRelativePath(filePath: string): string {
  return filePath.split(path.sep).join("/");
}

function formatError(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
