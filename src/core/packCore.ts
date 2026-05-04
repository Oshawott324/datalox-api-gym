import { spawnSync } from "node:child_process";
import { constants as fsConstants, existsSync } from "node:fs";
import { access, cp, mkdir, readdir, readFile, rm, symlink, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { extractTraceSource } from "./sourceBundle.js";
import { createRuntimeClient } from "./runtimeClient.js";
import {
  appendTrajectorySourceEventPath,
  type DebuggingTrajectoryV1,
  parseDebuggingTrajectoryV1,
} from "./trajectorySchema.js";
import { loadAgentConfig } from "../agent/loadAgentConfig.js";

export type EventClass = "trace" | "candidate";

export interface ResolveLoopInput {
  repoPath?: string;
  task?: string;
  workflow?: string;
  step?: string;
  skill?: string;
  limit?: number;
  includeContent?: boolean;
}

export interface SyncNoteRetrievalInput {
  repoPath?: string;
}

export interface PatchKnowledgeInput {
  repoPath?: string;
  task?: string;
  workflow?: string;
  step?: string;
  skillId?: string;
  summary?: string;
  observations?: string[];
  transcript?: string;
  tags?: string[];
  title?: string;
  signal?: string;
  interpretation?: string;
  recommendedAction?: string;
  eventPath?: string;
  sessionId?: string;
  hostKind?: string;
  adminOverride?: boolean;
}

export interface RecordTurnResultInput {
  repoPath?: string;
  sourceKind?: "trace" | "web" | "pdf";
  task?: string;
  workflow?: string;
  step?: string;
  skillId?: string;
  matchedSkillIdHint?: string;
  adjudicationDecision?: string;
  adjudicationSkillId?: string;
  candidateSkills?: Array<{
    skillId: string;
    displayName?: string;
    workflow?: string | null;
    supportingNotes?: Array<{
      path: string;
      title: string;
    }>;
    whyMatched?: string[];
  }>;
  summary?: string;
  observations?: string[];
  changedFiles?: string[];
  transcript?: string;
  tags?: string[];
  title?: string;
  signal?: string;
  interpretation?: string;
  recommendedAction?: string;
  outcome?: string;
  eventKind?: string;
  eventClass?: EventClass;
  matchedNotePaths?: string[];
  sessionId?: string;
  hostKind?: string;
  trajectoryRow?: unknown;
}

export interface PromoteGapInput extends RecordTurnResultInput {
  minWikiOccurrences?: number;
  minSkillOccurrences?: number;
  eventPath?: string;
  adminOverride?: boolean;
}

export interface CompileRecordedEventInput {
  repoPath?: string;
  eventPath?: string;
  minWikiOccurrences?: number;
  minSkillOccurrences?: number;
}

export interface MaintainKnowledgeInput {
  repoPath?: string;
  maxEvents?: number;
  includeCovered?: boolean;
  minNoteOccurrences?: number;
  minSkillOccurrences?: number;
  synthesizeSkills?: boolean;
}

export interface EventBacklogStatusInput {
  repoPath?: string;
}

export interface AutomaticMaintenanceInput {
  repoPath?: string;
  reason?: string;
}

export interface RecordLoopApplicationInput {
  repoPath?: string;
  notePaths: string[];
}

export interface LintPackInput {
  repoPath?: string;
}

export interface RefreshControlArtifactsInput {
  repoPath?: string;
  logEntry?: {
    action: string;
    detail: string;
    path?: string;
  };
  lintResult?: unknown;
}

export interface AdoptPackInput {
  hostRepoPath: string;
  packSource?: string;
  installMode?: "manual" | "auto" | "repair";
}

interface AdoptPackResult {
  hostRepoPath: string;
  packRootPath: string;
  copied: string[];
  injected: string[];
  skipped: string[];
  installStampPath: string;
  installMode: "manual" | "auto" | "repair";
}

interface InstallStamp {
  version: 1;
  installedAt: string;
  installMode: "manual" | "auto" | "repair";
  packRootPath: string;
}

export interface BootstrapProbeResult {
  repoPath: string;
  status: "ready" | "bootstrappable" | "repairable" | "blocked";
  canAutoBootstrap: boolean;
  reasons: string[];
  recommendedAction?: "explicit_adopt_from_source_pack";
  recoveryCommands?: string[];
  installStampPath: string;
  installStamp: InstallStamp | null;
  detected: {
    isGitRepo: boolean;
    isWritable: boolean;
    hasDataloxMd: boolean;
    hasManifest: boolean;
    hasConfig: boolean;
    hasAgentWiki: boolean;
    hasInstallStamp: boolean;
    ownedRootSignals: string[];
  };
}

export interface AutoBootstrapInput {
  repoPath?: string;
  packSource?: string;
}

export interface AutoBootstrapResult {
  repoPath: string;
  probeBefore: BootstrapProbeResult;
  action: "none" | "adopted" | "repaired";
  adoption: AdoptPackResult | null;
  probeAfter: BootstrapProbeResult;
}

function resolvePackRootPath(): string {
  const candidates = [
    fileURLToPath(new URL("../../", import.meta.url)),
    fileURLToPath(new URL("../../../", import.meta.url)),
  ];

  for (const candidate of candidates) {
    if (
      existsSync(path.join(candidate, "package.json"))
      && existsSync(path.join(candidate, "scripts", "lib", "agent-pack.mjs"))
    ) {
      return candidate;
    }
  }

  return candidates[candidates.length - 1];
}

const PACK_ROOT = resolvePackRootPath();
const DEFAULT_PACK_URL = "https://github.com/Complexity-LLC/datalox-trajectory-mcp.git";

function shellDoubleQuote(value: string): string {
  return JSON.stringify(value);
}

function buildExplicitAdoptionRecoveryCommands(repoPath: string): string[] {
  return [
    `TARGET_REPO=${shellDoubleQuote(repoPath)}`,
    `git clone ${DEFAULT_PACK_URL}`,
    "cd datalox-trajectory-mcp",
    "bash bin/adopt-host-repo.sh \"$TARGET_REPO\"",
  ];
}

const SINGLE_FILE_ADOPTION_PATHS = [
  "DATALOX.md",
  "AGENTS.md",
  "CLAUDE.md",
  "WIKI.md",
  "GEMINI.md",
  "START_HERE.md",
  ".claude/settings.json",
  ".claude/hooks/auto-promote.sh",
  ".github/copilot-instructions.md",
  ".cursor/rules/datalox-pack.mdc",
  ".windsurf/rules/datalox-pack.md",
  ".datalox/config.json",
  ".datalox/config.schema.json",
  ".datalox/manifest.json",
  ".datalox/skill.schema.md",
  "bin/claude-global-auto-promote.sh",
  "bin/datalox-auto-promote.js",
  "bin/datalox-claude.js",
  "bin/datalox-codex.js",
  "bin/datalox-mcp.js",
  "bin/datalox-pack-mcp.js",
  "bin/datalox.js",
  "bin/datalox-wrap.js",
  "bin/disable-default-host-integrations.sh",
  "bin/install-default-host-integrations.sh",
  "bin/setup-multi-agent.sh",
  "agent-wiki/note.schema.md",
];
const CORE_BUNDLE_TREE_PATHS = [
  "skills/maintain-datalox-pack",
  "skills/use-datalox-through-host-cli",
];
const CORE_BUNDLE_FILE_PATHS = [
  "agent-wiki/notes/maintain-datalox-pack.md",
  "agent-wiki/notes/use-datalox-through-host-cli.md",
  "agent-wiki/notes/repo-engineering-multi-agent-bootstrap-surfaces.md",
];
const ADOPTION_INJECTION_BEGIN = "<!-- DATALOX_PACK:BEGIN -->";
const ADOPTION_INJECTION_END = "<!-- DATALOX_PACK:END -->";
type ExistingInstructionInjectionMode = "append" | "after_frontmatter";
interface ExistingInstructionInjectionSpec {
  mode: ExistingInstructionInjectionMode;
  lines: string[];
}
const EXISTING_INSTRUCTION_INJECTIONS: Record<string, ExistingInstructionInjectionSpec> = {
  "AGENTS.md": {
    mode: "after_frontmatter",
    lines: [
      "## Datalox Pack",
      "If `DATALOX.md` exists in this repo, read it after this file and treat it as the repo-local Datalox contract.",
      "Use reusable local knowledge in `agent-wiki/notes/` and grounded event records in `agent-wiki/events/`.",
    ],
  },
  "CLAUDE.md": {
    mode: "after_frontmatter",
    lines: [
      "@DATALOX.md",
    ],
  },
  "WIKI.md": {
    mode: "after_frontmatter",
    lines: [
      "## Datalox Pack",
      "If `DATALOX.md` exists in this repo, read it after this file and use it as the repo-local Datalox loop contract.",
      "Keep reusable knowledge in `agent-wiki/notes/` and grounded event traces in `agent-wiki/events/`.",
    ],
  },
  "GEMINI.md": {
    mode: "after_frontmatter",
    lines: [
      "## Datalox Pack",
      "If `DATALOX.md` exists in this repo, read it after this file and use it as the repo-local Datalox loop contract.",
      "Keep reusable knowledge in `agent-wiki/notes/` and grounded event traces in `agent-wiki/events/`.",
    ],
  },
  ".github/copilot-instructions.md": {
    mode: "append",
    lines: [
      "## Datalox Pack",
      "Also consult `AGENTS.md` and `DATALOX.md` when they exist.",
      "Use `agent-wiki/notes/` for reusable repo knowledge and `agent-wiki/events/` for grounded event traces.",
    ],
  },
};
const INSTALL_STAMP_RELATIVE_PATH = ".datalox/install.json";
const EVENTS_RELATIVE_DIR = path.join("agent-wiki", "events");
const NOTES_RELATIVE_DIR = path.join("agent-wiki", "notes");

interface NoteUsageStats {
  readCount: number;
  lastReadAt: string | null;
  applyCount: number;
  lastAppliedAt: string | null;
  evidenceCount: number;
}

interface RecordedEventPayload {
  id?: string;
  timestamp?: string;
  task?: string | null;
  title?: string | null;
  summary?: string | null;
  workflow?: string | null;
  step?: string | null;
  eventKind?: string | null;
  eventClass?: EventClass | null;
  signal?: string | null;
  interpretation?: string | null;
  recommendedAction?: string | null;
  outcome?: string | null;
  fingerprint?: string | null;
  explicitSkillId?: string | null;
  matchedSkillId?: string | null;
  matchedNotePaths?: string[] | null;
  observations?: string[] | null;
  changedFiles?: string[] | null;
  transcript?: string | null;
  sessionId?: string | null;
  hostKind?: string | null;
  coveredByNotePath?: string | null;
  coveredAt?: string | null;
  summarizedByNotePath?: string | null;
  summarizedAt?: string | null;
  maintenanceRollupKind?: string | null;
  maintenanceStatus?: string | null;
  trajectoryRow?: DebuggingTrajectoryV1 | null;
}

function normalizePath(value: string): string {
  return value.replaceAll("\\", "/");
}

function firstNonEmpty(values: Array<string | null | undefined>): string | null {
  for (const value of values) {
    if (typeof value === "string" && value.trim().length > 0) {
      return value.trim();
    }
  }
  return null;
}

function truncateLine(value: string, maxLength: number = 160): string {
  const normalized = value.replace(/\s+/g, " ").trim();
  if (normalized.length <= maxLength) {
    return normalized;
  }
  return `${normalized.slice(0, maxLength - 1).trim()}…`;
}

function parseTimestamp(value: string | null | undefined): number {
  const parsed = value ? Date.parse(value) : Number.NaN;
  return Number.isNaN(parsed) ? 0 : parsed;
}

async function readJsonIfPresent<T>(filePath: string): Promise<T | null> {
  try {
    const raw = await readFile(filePath, "utf8");
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

async function readJsonFiles(dirPath: string): Promise<string[]> {
  try {
    const entries = await readdir(dirPath, { withFileTypes: true });
    return entries
      .filter((entry) => entry.isFile() && entry.name.endsWith(".json"))
      .sort((left, right) => left.name.localeCompare(right.name))
      .map((entry) => path.join(dirPath, entry.name));
  } catch {
    return [];
  }
}

async function listMarkdownFiles(dirPath: string): Promise<string[]> {
  try {
    const entries = await readdir(dirPath, { withFileTypes: true });
    const nested = await Promise.all(
      entries.map(async (entry) => {
        const entryPath = path.join(dirPath, entry.name);
        if (entry.isDirectory()) {
          return listMarkdownFiles(entryPath);
        }
        if (entry.isFile() && entry.name.endsWith(".md")) {
          return [entryPath];
        }
        return [];
      }),
    );
    return nested.flat().sort((left, right) => left.localeCompare(right));
  } catch {
    return [];
  }
}

function splitFrontmatter(content: string): { frontmatterLines: string[]; body: string } | null {
  if (!content.startsWith("---\n")) {
    return null;
  }
  const endIndex = content.indexOf("\n---\n", 4);
  if (endIndex === -1) {
    return null;
  }
  return {
    frontmatterLines: content.slice(4, endIndex).split("\n"),
    body: content.slice(endIndex + 5),
  };
}

function parseUsageStats(frontmatterLines: string[]): NoteUsageStats {
  const defaults: NoteUsageStats = {
    readCount: 0,
    lastReadAt: null,
    applyCount: 0,
    lastAppliedAt: null,
    evidenceCount: 0,
  };
  const usageIndex = frontmatterLines.findIndex((line) => line.trim() === "usage:");
  if (usageIndex === -1) {
    return defaults;
  }

  const next: NoteUsageStats = { ...defaults };
  for (let index = usageIndex + 1; index < frontmatterLines.length; index += 1) {
    const line = frontmatterLines[index];
    if (!line.startsWith("  ")) {
      break;
    }
    const trimmed = line.trim();
    const [key, ...rest] = trimmed.split(":");
    const rawValue = rest.join(":").trim();
    switch (key) {
      case "read_count":
        next.readCount = Number.parseInt(rawValue, 10) || 0;
        break;
      case "last_read_at":
        next.lastReadAt = rawValue || null;
        break;
      case "apply_count":
        next.applyCount = Number.parseInt(rawValue, 10) || 0;
        break;
      case "last_applied_at":
        next.lastAppliedAt = rawValue || null;
        break;
      case "evidence_count":
        next.evidenceCount = Number.parseInt(rawValue, 10) || 0;
        break;
      default:
        break;
    }
  }
  return next;
}

function renderUsageBlock(usage: NoteUsageStats): string[] {
  return [
    "usage:",
    `  read_count: ${usage.readCount}`,
    `  last_read_at: ${usage.lastReadAt ?? ""}`,
    `  apply_count: ${usage.applyCount}`,
    `  last_applied_at: ${usage.lastAppliedAt ?? ""}`,
    `  evidence_count: ${usage.evidenceCount}`,
  ];
}

function withUsageBlock(frontmatterLines: string[], usage: NoteUsageStats): string[] {
  const usageBlock = renderUsageBlock(usage);
  const usageIndex = frontmatterLines.findIndex((line) => line.trim() === "usage:");
  if (usageIndex !== -1) {
    let endIndex = usageIndex + 1;
    while (endIndex < frontmatterLines.length && frontmatterLines[endIndex].startsWith("  ")) {
      endIndex += 1;
    }
    return [
      ...frontmatterLines.slice(0, usageIndex),
      ...usageBlock,
      ...frontmatterLines.slice(endIndex),
    ];
  }

  const updatedIndex = frontmatterLines.findIndex((line) => line.startsWith("updated:"));
  if (updatedIndex !== -1) {
    return [
      ...frontmatterLines.slice(0, updatedIndex),
      ...usageBlock,
      ...frontmatterLines.slice(updatedIndex),
    ];
  }

  return [...frontmatterLines, ...usageBlock];
}

function joinFrontmatter(frontmatterLines: string[], body: string): string {
  return `---\n${frontmatterLines.join("\n")}\n---\n${body.startsWith("\n") ? body.slice(1) : body}`;
}

async function updateNoteUsage(
  repoPath: string,
  relativeNotePath: string,
  updater: (current: NoteUsageStats) => NoteUsageStats,
): Promise<string | null> {
  const normalized = normalizePath(relativeNotePath);
  const filePath = path.resolve(repoPath, normalized);
  if (!(await fileExists(filePath))) {
    return null;
  }

  const content = await readFile(filePath, "utf8");
  const split = splitFrontmatter(content);
  if (!split) {
    return null;
  }

  const current = parseUsageStats(split.frontmatterLines);
  const next = updater(current);
  const frontmatterLines = withUsageBlock(split.frontmatterLines, next);
  await writeFile(filePath, joinFrontmatter(frontmatterLines, split.body), "utf8");
  return normalized;
}

async function updateManyNotesUsage(
  repoPath: string,
  notePaths: string[],
  updater: (current: NoteUsageStats) => NoteUsageStats,
): Promise<string[]> {
  const updated: string[] = [];
  for (const notePath of [...new Set(notePaths.map(normalizePath))]) {
    const next = await updateNoteUsage(repoPath, notePath, updater);
    if (next) {
      updated.push(next);
    }
  }
  return updated;
}

async function listRecordedEventPayloads(repoPath: string): Promise<Array<{ filePath: string; relativePath: string; value: RecordedEventPayload }>> {
  const eventsDir = path.join(repoPath, EVENTS_RELATIVE_DIR);
  const files = await readJsonFiles(eventsDir);
  const events = await Promise.all(
    files.map(async (filePath) => ({
      filePath,
      relativePath: normalizePath(path.relative(repoPath, filePath)),
      value: (await readJsonIfPresent<RecordedEventPayload>(filePath)) ?? {},
    })),
  );
  return events.sort((left, right) => parseTimestamp(right.value.timestamp) - parseTimestamp(left.value.timestamp));
}

async function patchRecordedEvent(
  repoPath: string,
  relativePath: string,
  patch: Partial<RecordedEventPayload>,
): Promise<RecordedEventPayload | null> {
  const eventPath = path.join(repoPath, relativePath);
  const event = await readJsonIfPresent<RecordedEventPayload>(eventPath);
  if (!event) {
    return null;
  }

  const next = { ...event, ...patch };
  await writeFile(eventPath, `${JSON.stringify(next, null, 2)}\n`, "utf8");
  return next;
}

function collectSupportingNotePaths(result: any): string[] {
  const topMatch = result?.matches?.[0];
  const linkedNotes = Array.isArray(topMatch?.linkedNotes)
    ? topMatch.linkedNotes
    : Array.isArray(result?.directNoteMatches)
      ? result.directNoteMatches.map((entry: { note?: unknown }) => entry.note).filter(Boolean)
      : [];
  return linkedNotes
    .map((noteDoc: { path?: string }) => noteDoc?.path)
    .filter((value: unknown): value is string => typeof value === "string" && value.length > 0);
}

async function loadLegacyPackModule() {
  return import(pathToFileURL(path.join(PACK_ROOT, "scripts", "lib", "agent-pack.mjs")).href);
}

function resolveRepoPath(repoPath?: string): string {
  return path.resolve(repoPath ?? process.cwd());
}

function isGitUrl(value: string): boolean {
  return /^https?:\/\//.test(value) || value.endsWith(".git");
}

async function fileExists(filePath: string): Promise<boolean> {
  try {
    await access(filePath);
    return true;
  } catch {
    return false;
  }
}

function isGitRepo(repoPath: string): boolean {
  const result = spawnSync("git", ["rev-parse", "--show-toplevel"], {
    cwd: repoPath,
    encoding: "utf8",
  });
  return result.status === 0;
}

async function isWritableDirectory(repoPath: string): Promise<boolean> {
  try {
    await access(repoPath, fsConstants.W_OK);
    return true;
  } catch {
    return false;
  }
}

async function readInstallStamp(installStampPath: string): Promise<InstallStamp | null> {
  try {
    const raw = await readFile(installStampPath, "utf8");
    const parsed = JSON.parse(raw) as InstallStamp;
    if (parsed && parsed.version === 1 && typeof parsed.installedAt === "string") {
      return parsed;
    }
  } catch {
    return null;
  }
  return null;
}

async function validateDurableWriteProvenance(input: {
  repoPath: string;
  eventPath?: string;
  sessionId?: string;
  hostKind?: string;
  adminOverride?: boolean;
}, operation: "patch" | "promote"): Promise<void> {
  if (input.adminOverride === true) {
    return;
  }

  if (typeof input.eventPath === "string" && input.eventPath.trim().length > 0) {
    const candidate = path.isAbsolute(input.eventPath)
      ? input.eventPath
      : path.join(input.repoPath, input.eventPath);
    if (!await fileExists(candidate)) {
      throw new Error(`${operation} requires a valid recorded event path when eventPath is provided.`);
    }
    return;
  }

  if (
    typeof input.sessionId === "string"
    && input.sessionId.trim().length > 0
    && typeof input.hostKind === "string"
    && input.hostKind.trim().length > 0
  ) {
    return;
  }

  throw new Error(
    `${operation} requires durable-write provenance. Pass eventPath, or both sessionId and hostKind, or set adminOverride=true.`,
  );
}

async function writeInstallStamp(
  hostRepoPath: string,
  packRootPath: string,
  installMode: "manual" | "auto" | "repair",
): Promise<string> {
  const installStampPath = path.join(hostRepoPath, INSTALL_STAMP_RELATIVE_PATH);
  await mkdir(path.dirname(installStampPath), { recursive: true });
  const payload: InstallStamp = {
    version: 1,
    installedAt: new Date().toISOString(),
    installMode,
    packRootPath,
  };
  await writeFile(installStampPath, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
  return installStampPath;
}

function detectLineEnding(content: string): string {
  return content.includes("\r\n") ? "\r\n" : "\n";
}

function splitLeadingFrontmatter(content: string): { prefix: string; rest: string } {
  const match = /^(---\r?\n[\s\S]*?\r?\n---(?:\r?\n|$))([\s\S]*)$/u.exec(content);
  if (!match) {
    return { prefix: "", rest: content };
  }
  return {
    prefix: match[1],
    rest: match[2],
  };
}

function buildAdoptionInjectionBlock(spec: ExistingInstructionInjectionSpec, eol: string): string {
  return [ADOPTION_INJECTION_BEGIN, ...spec.lines, ADOPTION_INJECTION_END].join(eol);
}

function injectAdoptionInstructions(
  content: string,
  spec: ExistingInstructionInjectionSpec,
): string {
  if (content.includes(ADOPTION_INJECTION_BEGIN) && content.includes(ADOPTION_INJECTION_END)) {
    return content;
  }

  const eol = detectLineEnding(content);
  const block = buildAdoptionInjectionBlock(spec, eol);

  if (spec.mode === "append") {
    const trimmed = content.trimEnd();
    if (trimmed.length === 0) {
      return `${block}${eol}`;
    }
    return `${trimmed}${eol}${eol}${block}${eol}`;
  }

  const { prefix, rest } = splitLeadingFrontmatter(content);
  if (prefix.length > 0) {
    if (rest.length === 0) {
      return `${prefix}${block}${eol}`;
    }
    return `${prefix}${block}${eol}${eol}${rest}`;
  }

  if (content.length === 0) {
    return `${block}${eol}`;
  }
  return `${block}${eol}${eol}${content}`;
}

async function copyOrInjectInstructionFile(
  sourcePath: string,
  destinationPath: string,
  relativePath: string,
  copied: string[],
  injected: string[],
  skipped: string[],
): Promise<void> {
  await mkdir(path.dirname(destinationPath), { recursive: true });
  if (!await fileExists(destinationPath)) {
    await cp(sourcePath, destinationPath, { recursive: false });
    copied.push(destinationPath);
    return;
  }

  if (path.resolve(sourcePath) === path.resolve(destinationPath)) {
    skipped.push(destinationPath);
    return;
  }

  const spec = EXISTING_INSTRUCTION_INJECTIONS[relativePath];
  if (!spec) {
    skipped.push(destinationPath);
    return;
  }

  const current = await readFile(destinationPath, "utf8");
  const source = await readFile(sourcePath, "utf8");
  if (current === source) {
    skipped.push(destinationPath);
    return;
  }
  const next = injectAdoptionInstructions(current, spec);
  if (next === current) {
    skipped.push(destinationPath);
    return;
  }

  await writeFile(destinationPath, next, "utf8");
  injected.push(destinationPath);
}

async function copyTreeEntriesIfMissing(
  sourceDir: string,
  destinationDir: string,
  copied: string[],
  skipped: string[],
): Promise<void> {
  await mkdir(destinationDir, { recursive: true });
  const entries = await readdir(sourceDir, { withFileTypes: true });
  for (const entry of entries) {
    const sourcePath = path.join(sourceDir, entry.name);
    const destinationPath = path.join(destinationDir, entry.name);
    if (await fileExists(destinationPath)) {
      skipped.push(destinationPath);
      continue;
    }
    await cp(sourcePath, destinationPath, { recursive: true });
    copied.push(destinationPath);
  }
}

function runGit(args: string[], cwd?: string): void {
  const result = spawnSync("git", args, {
    cwd,
    encoding: "utf8",
  });
  if (result.status !== 0) {
    throw new Error(result.stderr.trim() || result.stdout.trim() || `git ${args.join(" ")} failed`);
  }
}

async function resolvePackRoot(packSource?: string): Promise<string> {
  if (!packSource) {
    return PACK_ROOT;
  }

  if (!isGitUrl(packSource)) {
    return path.resolve(packSource);
  }

  const cacheRoot = path.join(os.homedir(), ".datalox", "cache");
  const cacheName = path.basename(packSource).replace(/\.git$/, "") || "datalox-trajectory-mcp";
  const cachePath = path.join(cacheRoot, cacheName);
  await mkdir(cacheRoot, { recursive: true });

  if (await fileExists(path.join(cachePath, ".git"))) {
    runGit(["pull", "--ff-only"], cachePath);
  } else {
    if (await fileExists(cachePath)) {
      await rm(cachePath, { recursive: true, force: true });
    }
    runGit(["clone", "--depth", "1", packSource, cachePath]);
  }

  return cachePath;
}

async function ensureLocalPackCache(packRootPath: string): Promise<void> {
  const cacheRoot = path.join(os.homedir(), ".datalox", "cache");
  const cachePath = path.join(cacheRoot, "datalox-trajectory-mcp");

  if (path.resolve(packRootPath) === path.resolve(cachePath)) {
    return;
  }

  await mkdir(cacheRoot, { recursive: true });
  if (await fileExists(cachePath)) {
    return;
  }

  await symlink(packRootPath, cachePath, "dir");
}

export async function probeBootstrapCandidate(repoPath?: string): Promise<BootstrapProbeResult> {
  const resolvedRepoPath = resolveRepoPath(repoPath);
  const installStampPath = path.join(resolvedRepoPath, INSTALL_STAMP_RELATIVE_PATH);
  const hasDataloxMd = await fileExists(path.join(resolvedRepoPath, "DATALOX.md"));
  const hasManifest = await fileExists(path.join(resolvedRepoPath, ".datalox", "manifest.json"));
  const hasConfig = await fileExists(path.join(resolvedRepoPath, ".datalox", "config.json"));
  const hasAgentWiki = await fileExists(path.join(resolvedRepoPath, "agent-wiki"));
  const hasInstallStamp = await fileExists(installStampPath);
  const installStamp = hasInstallStamp ? await readInstallStamp(installStampPath) : null;
  const detectedRoots = [
    hasDataloxMd ? "DATALOX.md" : null,
    hasManifest || hasConfig || hasInstallStamp ? ".datalox/" : null,
    hasAgentWiki ? "agent-wiki/" : null,
  ].filter((value): value is string => Boolean(value));
  const completeCore = hasDataloxMd && hasManifest && hasConfig && hasAgentWiki;
  const gitRepo = isGitRepo(resolvedRepoPath);
  const writable = await isWritableDirectory(resolvedRepoPath);

  if (!writable) {
    return {
      repoPath: resolvedRepoPath,
      status: "blocked",
      canAutoBootstrap: false,
      reasons: ["repo is not writable"],
      installStampPath,
      installStamp,
      detected: {
        isGitRepo: gitRepo,
        isWritable: writable,
        hasDataloxMd,
        hasManifest,
        hasConfig,
        hasAgentWiki,
        hasInstallStamp,
        ownedRootSignals: detectedRoots,
      },
    };
  }

  if (installStamp && completeCore) {
    return {
      repoPath: resolvedRepoPath,
      status: "ready",
      canAutoBootstrap: false,
      reasons: ["repo already has a stamped Datalox installation"],
      installStampPath,
      installStamp,
      detected: {
        isGitRepo: gitRepo,
        isWritable: writable,
        hasDataloxMd,
        hasManifest,
        hasConfig,
        hasAgentWiki,
        hasInstallStamp,
        ownedRootSignals: detectedRoots,
      },
    };
  }

  if ((installStamp && !completeCore) || (!installStamp && completeCore)) {
    return {
      repoPath: resolvedRepoPath,
      status: "repairable",
      canAutoBootstrap: true,
      reasons: [
        installStamp
          ? "stamped Datalox install is missing critical files and can be repaired safely"
          : "repo has a complete legacy Datalox layout but no install stamp; stamping and refill are safe",
      ],
      installStampPath,
      installStamp,
      detected: {
        isGitRepo: gitRepo,
        isWritable: writable,
        hasDataloxMd,
        hasManifest,
        hasConfig,
        hasAgentWiki,
        hasInstallStamp,
        ownedRootSignals: detectedRoots,
      },
    };
  }

  if (!gitRepo) {
    return {
      repoPath: resolvedRepoPath,
      status: "blocked",
      canAutoBootstrap: false,
      reasons: ["automatic bootstrap only runs inside a git worktree"],
      installStampPath,
      installStamp,
      detected: {
        isGitRepo: gitRepo,
        isWritable: writable,
        hasDataloxMd,
        hasManifest,
        hasConfig,
        hasAgentWiki,
        hasInstallStamp,
        ownedRootSignals: detectedRoots,
      },
    };
  }

  if (detectedRoots.length === 0) {
    return {
      repoPath: resolvedRepoPath,
      status: "bootstrappable",
      canAutoBootstrap: true,
      reasons: ["repo has no Datalox-owned files yet and can be bootstrapped safely"],
      installStampPath,
      installStamp,
      detected: {
        isGitRepo: gitRepo,
        isWritable: writable,
        hasDataloxMd,
        hasManifest,
        hasConfig,
        hasAgentWiki,
        hasInstallStamp,
        ownedRootSignals: detectedRoots,
      },
    };
  }

  return {
    repoPath: resolvedRepoPath,
    status: "blocked",
    canAutoBootstrap: false,
    reasons: [
      `repo already contains partial Datalox-owned paths (${detectedRoots.join(", ")}) without a safe repair marker`,
    ],
    recommendedAction: "explicit_adopt_from_source_pack",
    recoveryCommands: buildExplicitAdoptionRecoveryCommands(resolvedRepoPath),
    installStampPath,
    installStamp,
    detected: {
      isGitRepo: gitRepo,
      isWritable: writable,
      hasDataloxMd,
      hasManifest,
      hasConfig,
      hasAgentWiki,
      hasInstallStamp,
      ownedRootSignals: detectedRoots,
    },
  };
}

export async function resolveLoop(input: ResolveLoopInput) {
  const repoPath = resolveRepoPath(input.repoPath);
  const legacy = await loadLegacyPackModule();
  const result = await legacy.resolveLocalKnowledge(
    {
      task: input.task,
      workflow: input.workflow,
      step: input.step,
      skill: input.skill,
      limit: input.limit ?? 3,
      includeContent: input.includeContent ?? false,
    },
    repoPath,
  );
  const supportingNotePaths = collectSupportingNotePaths(result);
  if (supportingNotePaths.length > 0) {
    const timestamp = new Date().toISOString();
    await updateManyNotesUsage(repoPath, supportingNotePaths, (current) => ({
      ...current,
      readCount: current.readCount + 1,
      lastReadAt: timestamp,
    }));
  }

  // Enrich with remote guidance when runtime is enabled
  let runtimeGuidance = null;
  try {
    const { config } = await loadAgentConfig(repoPath);
    const client = createRuntimeClient(config);
    if (client && input.task) {
      runtimeGuidance = await client.compileGuidance({
        task: input.task,
        workflow: input.workflow ?? config.runtime.defaultWorkflow,
        step: input.step,
      });
    }
  } catch {
    // Runtime unreachable — continue with local-only result
  }

  return { ...result, runtimeGuidance };
}

export async function syncNoteRetrieval(input: SyncNoteRetrievalInput = {}) {
  const repoPath = resolveRepoPath(input.repoPath);
  const legacy = await loadLegacyPackModule();
  return legacy.syncNoteRetrieval(repoPath);
}

export async function patchKnowledge(input: PatchKnowledgeInput) {
  const repoPath = resolveRepoPath(input.repoPath);
  await validateDurableWriteProvenance({
    repoPath,
    eventPath: input.eventPath,
    sessionId: input.sessionId,
    hostKind: input.hostKind,
    adminOverride: input.adminOverride,
  }, "patch");
  const legacy = await loadLegacyPackModule();
  const result = await legacy.learnFromInteraction(
    {
      task: input.task,
      workflow: input.workflow,
      step: input.step,
      skillId: input.skillId,
      summary: input.summary,
      observations: input.observations ?? [],
      transcript: input.transcript,
      tags: input.tags ?? [],
      title: input.title,
      signal: input.signal,
      interpretation: input.interpretation,
      recommendedAction: input.recommendedAction,
    },
    repoPath,
  );
  return {
    ...result,
    note: result.note,
  };
}

export async function recordTurnResult(input: RecordTurnResultInput) {
  const repoPath = resolveRepoPath(input.repoPath);
  const trajectoryRow = input.trajectoryRow === undefined
    ? undefined
    : parseDebuggingTrajectoryV1(input.trajectoryRow);
  const legacy = await loadLegacyPackModule();
  const result = await legacy.recordTurnResult(
    {
      sourceKind: input.sourceKind,
      task: input.task,
      workflow: input.workflow,
      step: input.step,
      skillId: input.skillId,
      matchedSkillIdHint: input.matchedSkillIdHint,
      adjudicationDecision: input.adjudicationDecision,
      adjudicationSkillId: input.adjudicationSkillId,
      candidateSkills: input.candidateSkills ?? [],
      summary: input.summary,
      observations: input.observations ?? [],
      changedFiles: input.changedFiles ?? [],
      transcript: input.transcript,
      tags: input.tags ?? [],
      title: input.title,
      signal: input.signal,
      interpretation: input.interpretation,
      recommendedAction: input.recommendedAction,
      outcome: input.outcome,
      eventKind: input.eventKind,
      eventClass: input.eventClass,
    },
    repoPath,
  );
  return {
    ...result,
    traceBundle: extractTraceSource({
      id: result.event.payload.id,
      title: result.event.payload.title,
      capturedAt: result.event.payload.timestamp,
      task: result.event.payload.task ?? input.task,
      workflow: result.event.payload.workflow ?? input.workflow,
      step: result.event.payload.step ?? input.step,
      transcript: result.event.payload.transcript ?? input.transcript,
      summary: result.event.payload.summary ?? input.summary,
      observations: result.event.payload.observations ?? input.observations ?? [],
      signal: result.event.payload.signal ?? input.signal,
      interpretation: result.event.payload.interpretation ?? input.interpretation,
      action: result.event.payload.recommendedAction ?? input.recommendedAction,
      matchedSkillId: result.event.payload.matchedSkillId ?? input.matchedSkillIdHint ?? input.skillId,
      changedFiles: result.event.payload.changedFiles ?? input.changedFiles ?? [],
      outcome: result.event.payload.outcome ?? input.outcome,
    }),
    event: {
      ...result.event,
      payload: await patchRecordedEvent(repoPath, result.event.relativePath, {
        ...(input.matchedNotePaths !== undefined ? { matchedNotePaths: input.matchedNotePaths } : {}),
        ...(input.sessionId !== undefined ? { sessionId: input.sessionId ?? null } : {}),
        ...(input.hostKind !== undefined ? { hostKind: input.hostKind ?? null } : {}),
        ...(trajectoryRow !== undefined
          ? { trajectoryRow: appendTrajectorySourceEventPath(trajectoryRow, result.event.relativePath) }
          : {}),
      }) ?? result.event.payload,
    },
  };
}

export async function promoteGap(input: PromoteGapInput) {
  const repoPath = resolveRepoPath(input.repoPath);
  await validateDurableWriteProvenance({
    repoPath,
    eventPath: input.eventPath,
    sessionId: input.sessionId,
    hostKind: input.hostKind,
    adminOverride: input.adminOverride,
  }, "promote");
  const legacy = await loadLegacyPackModule();
  const result = await legacy.promoteGap(
    {
      sourceKind: input.sourceKind,
      task: input.task,
      workflow: input.workflow,
      step: input.step,
      skillId: input.skillId,
      matchedSkillIdHint: input.matchedSkillIdHint,
      adjudicationDecision: input.adjudicationDecision,
      adjudicationSkillId: input.adjudicationSkillId,
      candidateSkills: input.candidateSkills ?? [],
      summary: input.summary,
      observations: input.observations ?? [],
      changedFiles: input.changedFiles ?? [],
      transcript: input.transcript,
      tags: input.tags ?? [],
      title: input.title,
      signal: input.signal,
      interpretation: input.interpretation,
      recommendedAction: input.recommendedAction,
      outcome: input.outcome,
      eventKind: input.eventKind,
      eventClass: "candidate",
      minWikiOccurrences: input.minWikiOccurrences,
      minSkillOccurrences: input.minSkillOccurrences,
    },
    repoPath,
  );

  // Auto-publish promoted skills to the runtime registry
  let runtimePublish = null;
  try {
    const promotion = result.promotion;
    if (promotion?.skill) {
      const { config } = await loadAgentConfig(repoPath);
      const client = createRuntimeClient(config);
      if (client) {
        const skillContent = typeof promotion.skill.content === "string"
          ? promotion.skill.content
          : "";
        runtimePublish = await client.publishSkill({
          name: promotion.skill.name ?? promotion.skill.id ?? "unnamed",
          description: promotion.skill.description ?? input.summary ?? "",
          workflow: input.workflow ?? config.runtime.defaultWorkflow,
          trigger: input.signal ?? "",
          skillMd: skillContent,
          tags: input.tags ?? [],
        });
      }
    }
  } catch {
    // Runtime unreachable — continue without publishing
  }

  return {
    ...result,
    runtimePublish,
    promotion: result.promotion
      ? {
        ...result.promotion,
        note: result.promotion.note ?? null,
      }
      : null,
    traceBundle: extractTraceSource({
      id: result.event.payload.id,
      title: result.event.payload.title,
      capturedAt: result.event.payload.timestamp,
      task: result.event.payload.task ?? input.task,
      workflow: result.event.payload.workflow ?? input.workflow,
      step: result.event.payload.step ?? input.step,
      transcript: result.event.payload.transcript ?? input.transcript,
      summary: result.event.payload.summary ?? input.summary,
      observations: result.event.payload.observations ?? input.observations ?? [],
      signal: result.event.payload.signal ?? input.signal,
      interpretation: result.event.payload.interpretation ?? input.interpretation,
      action: result.event.payload.recommendedAction ?? input.recommendedAction,
      matchedSkillId: result.event.payload.matchedSkillId ?? input.matchedSkillIdHint ?? input.skillId,
      changedFiles: result.event.payload.changedFiles ?? input.changedFiles ?? [],
      outcome: result.event.payload.outcome ?? input.outcome,
    }),
    event: {
      ...result.event,
      payload: await patchRecordedEvent(repoPath, result.event.relativePath, {
        ...(input.matchedNotePaths !== undefined ? { matchedNotePaths: input.matchedNotePaths } : {}),
        ...(input.sessionId !== undefined ? { sessionId: input.sessionId ?? null } : {}),
        ...(input.hostKind !== undefined ? { hostKind: input.hostKind ?? null } : {}),
      }) ?? result.event.payload,
    },
  };
}

export async function compileRecordedEvent(input: CompileRecordedEventInput) {
  const repoPath = resolveRepoPath(input.repoPath);
  const legacy = await loadLegacyPackModule();
  const result = await legacy.compileRecordedEvent(
    {
      eventPath: input.eventPath,
      minWikiOccurrences: input.minWikiOccurrences,
      minSkillOccurrences: input.minSkillOccurrences,
    },
    repoPath,
  );
  return {
    ...result,
    promotion: result.promotion
      ? {
        ...result.promotion,
        note: result.promotion.note ?? null,
      }
      : null,
  };
}

export async function maintainKnowledge(input: MaintainKnowledgeInput = {}) {
  const repoPath = resolveRepoPath(input.repoPath);
  const legacy = await loadLegacyPackModule();
  return legacy.maintainKnowledge(
    {
      maxEvents: input.maxEvents,
      includeCovered: input.includeCovered,
      minNoteOccurrences: input.minNoteOccurrences,
      minSkillOccurrences: input.minSkillOccurrences,
      synthesizeSkills: input.synthesizeSkills,
    },
    repoPath,
  );
}

export async function runAutomaticMaintenance(input: AutomaticMaintenanceInput = {}) {
  const repoPath = resolveRepoPath(input.repoPath);
  const legacy = await loadLegacyPackModule();
  return legacy.runAutomaticMaintenance(
    {
      reason: input.reason,
    },
    repoPath,
  );
}

export async function getEventBacklogStatus(input: EventBacklogStatusInput = {}) {
  const repoPath = resolveRepoPath(input.repoPath);
  const legacy = await loadLegacyPackModule();
  return legacy.getEventBacklogStatus({}, repoPath);
}

export async function lintLocalPack(input: LintPackInput = {}) {
  const legacy = await loadLegacyPackModule();
  const repoPath = resolveRepoPath(input.repoPath);
  const base = await legacy.lintPack(repoPath);
  const supportingIssues = await (async () => {
    const issues: Array<{ level: string; code: string; path: string; message: string }> = [];
    const notesDir = path.join(repoPath, NOTES_RELATIVE_DIR);
    const noteFiles = await listMarkdownFiles(notesDir);
    for (const entryPath of noteFiles) {
      const split = splitFrontmatter(await readFile(entryPath, "utf8"));
      if (!split) {
        continue;
      }
      const usage = parseUsageStats(split.frontmatterLines);
      if (usage.applyCount > usage.readCount) {
        issues.push({
          level: "warning",
          code: "note_usage_apply_exceeds_read",
          path: normalizePath(path.relative(repoPath, entryPath)),
          message: "Note apply_count should not exceed read_count.",
        });
      }
    }
    return issues;
  })();

  const issues = [...base.issues, ...supportingIssues];
  return {
    ...base,
    issues,
    issueCount: issues.length,
    ok: issues.filter((issue: { level: string }) => issue.level === "error").length === 0,
  };
}

export async function refreshControlArtifacts(input: RefreshControlArtifactsInput = {}) {
  const legacy = await loadLegacyPackModule();
  return legacy.refreshControlArtifacts(resolveRepoPath(input.repoPath), {
    logEntry: input.logEntry,
    lintResult: input.lintResult,
  });
}

export async function adoptPack(input: AdoptPackInput): Promise<AdoptPackResult> {
  const hostRepoPath = resolveRepoPath(input.hostRepoPath);
  const packRootPath = await resolvePackRoot(input.packSource);
  const installMode = input.installMode ?? "manual";
  await ensureLocalPackCache(packRootPath);
  const copied: string[] = [];
  const injected: string[] = [];
  const skipped: string[] = [];

  await mkdir(path.join(hostRepoPath, ".datalox"), { recursive: true });
  await mkdir(path.join(hostRepoPath, ".claude", "hooks"), { recursive: true });
  await mkdir(path.join(hostRepoPath, ".github"), { recursive: true });
  await mkdir(path.join(hostRepoPath, ".cursor", "rules"), { recursive: true });
  await mkdir(path.join(hostRepoPath, ".windsurf", "rules"), { recursive: true });
  await mkdir(path.join(hostRepoPath, "bin"), { recursive: true });
  await mkdir(path.join(hostRepoPath, "skills"), { recursive: true });
  await mkdir(path.join(hostRepoPath, "agent-wiki", "events"), { recursive: true });

  for (const relativePath of SINGLE_FILE_ADOPTION_PATHS) {
    await copyOrInjectInstructionFile(
      path.join(packRootPath, relativePath),
      path.join(hostRepoPath, relativePath),
      relativePath,
      copied,
      injected,
      skipped,
    );
  }

  for (const relativePath of CORE_BUNDLE_FILE_PATHS) {
    await copyOrInjectInstructionFile(
      path.join(packRootPath, relativePath),
      path.join(hostRepoPath, relativePath),
      relativePath,
      copied,
      injected,
      skipped,
    );
  }

  for (const relativePath of CORE_BUNDLE_TREE_PATHS) {
    await copyTreeEntriesIfMissing(
      path.join(packRootPath, relativePath),
      path.join(hostRepoPath, relativePath),
      copied,
      skipped,
    );
  }

  const installStampPath = await writeInstallStamp(hostRepoPath, packRootPath, installMode);
  copied.push(installStampPath);

  return {
    hostRepoPath,
    packRootPath,
    copied: copied.map((item) => path.relative(hostRepoPath, item) || "."),
    injected: injected.map((item) => path.relative(hostRepoPath, item) || "."),
    skipped: skipped.map((item) => path.relative(hostRepoPath, item) || "."),
    installStampPath: path.relative(hostRepoPath, installStampPath) || ".",
    installMode,
  };
}

export async function autoBootstrapIfSafe(input: AutoBootstrapInput = {}): Promise<AutoBootstrapResult> {
  const repoPath = resolveRepoPath(input.repoPath);
  const probeBefore = await probeBootstrapCandidate(repoPath);
  if (!probeBefore.canAutoBootstrap) {
    return {
      repoPath,
      probeBefore,
      action: "none",
      adoption: null,
      probeAfter: probeBefore,
    };
  }

  const installMode = probeBefore.status === "repairable" ? "repair" : "auto";
  const adoption = await adoptPack({
    hostRepoPath: repoPath,
    packSource: input.packSource,
    installMode,
  });
  const probeAfter = await probeBootstrapCandidate(repoPath);

  return {
    repoPath,
    probeBefore,
    action: installMode === "repair" ? "repaired" : "adopted",
    adoption,
    probeAfter,
  };
}

export function getDefaultPackUrl(): string {
  return DEFAULT_PACK_URL;
}

export async function recordLoopApplication(input: RecordLoopApplicationInput): Promise<{ updatedNotes: string[] }> {
  const repoPath = resolveRepoPath(input.repoPath);
  const timestamp = new Date().toISOString();
  const updatedNotes = await updateManyNotesUsage(repoPath, input.notePaths, (current) => ({
    ...current,
    readCount: current.readCount + (current.readCount === 0 ? 1 : 0),
    lastReadAt: current.lastReadAt ?? timestamp,
    applyCount: current.applyCount + 1,
    lastAppliedAt: timestamp,
  }));
  return {
    updatedNotes,
  };
}
