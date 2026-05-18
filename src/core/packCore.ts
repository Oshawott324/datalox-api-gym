import { spawnSync } from "node:child_process";
import { constants as fsConstants, existsSync } from "node:fs";
import { access, cp, mkdir, readdir, readFile, rm, symlink, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

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
      && existsSync(path.join(candidate, "bin", "datalox.js"))
    ) {
      return candidate;
    }
  }

  return candidates[candidates.length - 1];
}

const PACK_ROOT = resolvePackRootPath();
const DEFAULT_PACK_URL = "https://github.com/Oshawott324/datalox-agent-replay.git";
const DEFAULT_PACK_CLONE_DIR = "datalox-agent-replay";

function shellDoubleQuote(value: string): string {
  return JSON.stringify(value);
}

function buildExplicitAdoptionRecoveryCommands(repoPath: string): string[] {
  return [
    `TARGET_REPO=${shellDoubleQuote(repoPath)}`,
    `PACK_REPO="$HOME/.datalox/cache/${DEFAULT_PACK_CLONE_DIR}"`,
    "mkdir -p \"$(dirname \"$PACK_REPO\")\"",
    `[ -d "$PACK_REPO/.git" ] && git -C "$PACK_REPO" pull --ff-only || git clone ${DEFAULT_PACK_URL} "$PACK_REPO"`,
    "cd \"$PACK_REPO\"",
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
  "docs/project-definition.md",
  "docs/project-overview.md",
  "docs/action-observation-schema.md",
  "docs/tool-io-store-schema.md",
  "docs/replay-bundle-schema.md",
  "docs/agent-turn-schema.md",
  "docs/agent-configuration.md",
  "docs/agent-replay-option-a-implementation-plan.md",
  "docs/automatic-enforcement-plan.md",
  "docs/task-orchestration.md",
  "docs/derivatives/trajectory/trajectory-dataset-schema.md",
  "docs/derivatives/trajectory/agent-task-trajectory-schema.md",
  "docs/derivatives/trajectory/trajectory-training-readiness.md",
  ".github/copilot-instructions.md",
  ".cursor/rules/datalox-agent-replay.mdc",
  ".windsurf/rules/datalox-agent-replay.md",
  ".datalox/config.json",
  ".datalox/config.schema.json",
  ".datalox/manifest.json",
  "bin/datalox-claude.js",
  "bin/datalox-codex.js",
  "bin/datalox-mcp.js",
  "bin/datalox-agent-replay-mcp.js",
  "bin/datalox.js",
  "bin/datalox-wrap.js",
  "bin/disable-default-host-integrations.sh",
  "bin/install-default-host-integrations.sh",
  "bin/setup-multi-agent.sh",
];
const ADOPTION_INJECTION_BEGIN = "<!-- DATALOX_AGENT_REPLAY:BEGIN -->";
const ADOPTION_INJECTION_END = "<!-- DATALOX_AGENT_REPLAY:END -->";
const LEGACY_ADOPTION_INJECTION_TOKEN = `DATALOX_${"PACK"}`;
type ExistingInstructionInjectionMode = "append" | "after_frontmatter";
interface ExistingInstructionInjectionSpec {
  mode: ExistingInstructionInjectionMode;
  lines: string[];
}
const EXISTING_INSTRUCTION_INJECTIONS: Record<string, ExistingInstructionInjectionSpec> = {
  "AGENTS.md": {
    mode: "after_frontmatter",
    lines: [
      "## Datalox Agent Replay",
      "If `DATALOX.md` exists in this repo, read it after this file and treat it as the repo-local Datalox contract.",
      "Use `.datalox/tool-io/records/`, `.datalox/events/agent-turns/`, and `.datalox/replay-bundles/` for replay capture data.",
      "Do not create a parallel wiki/note/event store.",
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
      "## Datalox Agent Replay",
      "If `DATALOX.md` exists in this repo, read it after this file and use it as the repo-local Datalox loop contract.",
      "Keep replay capture data under `.datalox/tool-io/records/`, `.datalox/events/agent-turns/`, and `.datalox/replay-bundles/`.",
      "Do not create a parallel wiki/note/event store.",
    ],
  },
  "GEMINI.md": {
    mode: "after_frontmatter",
    lines: [
      "## Datalox Agent Replay",
      "If `DATALOX.md` exists in this repo, read it after this file and use it as the repo-local Datalox loop contract.",
      "Keep replay capture data under `.datalox/tool-io/records/`, `.datalox/events/agent-turns/`, and `.datalox/replay-bundles/`.",
      "Do not create a parallel wiki/note/event store.",
    ],
  },
  ".github/copilot-instructions.md": {
    mode: "append",
    lines: [
      "## Datalox Agent Replay",
      "Also consult `AGENTS.md` and `DATALOX.md` when they exist.",
      "Use `.datalox/tool-io/records/`, `.datalox/events/agent-turns/`, and `.datalox/replay-bundles/` for replay capture data.",
      "Do not create a parallel wiki/note/event store.",
    ],
  },
};
const INSTALL_STAMP_RELATIVE_PATH = ".datalox/install.json";

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

function stripManagedAdoptionInjection(content: string, token: string): string {
  const pattern = new RegExp(`<!-- ${token}:BEGIN -->\\r?\\n[\\s\\S]*?<!-- ${token}:END -->\\r?\\n\\r?\\n?`, "gu");
  return content.replace(pattern, "");
}

function injectAdoptionInstructions(
  content: string,
  spec: ExistingInstructionInjectionSpec,
): string {
  const normalizedContent = stripManagedAdoptionInjection(
    stripManagedAdoptionInjection(content, LEGACY_ADOPTION_INJECTION_TOKEN),
    "DATALOX_AGENT_REPLAY",
  );

  if (normalizedContent.includes(ADOPTION_INJECTION_BEGIN) && normalizedContent.includes(ADOPTION_INJECTION_END)) {
    return normalizedContent;
  }

  const eol = detectLineEnding(normalizedContent);
  const block = buildAdoptionInjectionBlock(spec, eol);

  if (spec.mode === "append") {
    const trimmed = normalizedContent.trimEnd();
    if (trimmed.length === 0) {
      return `${block}${eol}`;
    }
    return `${trimmed}${eol}${eol}${block}${eol}`;
  }

  const { prefix, rest } = splitLeadingFrontmatter(normalizedContent);
  if (prefix.length > 0) {
    if (rest.length === 0) {
      return `${prefix}${block}${eol}`;
    }
    return `${prefix}${block}${eol}${eol}${rest}`;
  }

  if (normalizedContent.length === 0) {
    return `${block}${eol}`;
  }
  return `${block}${eol}${eol}${normalizedContent}`;
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
  const cacheName = path.basename(packSource).replace(/\.git$/, "") || "datalox-agent-replay";
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
  const cachePath = path.join(cacheRoot, "datalox-agent-replay");

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
  const hasInstallStamp = await fileExists(installStampPath);
  const installStamp = hasInstallStamp ? await readInstallStamp(installStampPath) : null;
  const detectedRoots = [
    hasDataloxMd ? "DATALOX.md" : null,
    hasManifest || hasConfig || hasInstallStamp ? ".datalox/" : null,
  ].filter((value): value is string => Boolean(value));
  const completeCore = hasDataloxMd && hasManifest && hasConfig;
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
      hasInstallStamp,
      ownedRootSignals: detectedRoots,
    },
  };
}

function removedLegacyWriteResult(operation: string, repoPath?: string) {
  return {
    repoPath: resolveRepoPath(repoPath),
    operation,
    status: "removed_from_this_branch",
    written: false,
    reason: "This branch records source replay data through tool I/O records, agent turns, and replay bundles.",
  };
}

export async function resolveLoop(input: ResolveLoopInput) {
  return {
    workflow: input.workflow ?? "unknown",
    selectionBasis: "removed_from_this_branch",
    matchedSkillId: null,
    matches: [],
    directNoteMatches: [],
    loopGuidance: null,
    runtimeGuidance: null,
  };
}

export async function syncNoteRetrieval(input: SyncNoteRetrievalInput = {}) {
  return {
    repoPath: resolveRepoPath(input.repoPath),
    status: "removed_from_this_branch",
    synced: false,
  };
}

export async function patchKnowledge(input: PatchKnowledgeInput) {
  return removedLegacyWriteResult("patchKnowledge", input.repoPath);
}

export async function recordTurnResult(input: RecordTurnResultInput) {
  return removedLegacyWriteResult("recordTurnResult", input.repoPath);
}

export async function promoteGap(input: PromoteGapInput) {
  return removedLegacyWriteResult("promoteGap", input.repoPath);
}

export async function compileRecordedEvent(input: CompileRecordedEventInput) {
  return removedLegacyWriteResult("compileRecordedEvent", input.repoPath);
}

export async function maintainKnowledge(input: MaintainKnowledgeInput = {}) {
  return removedLegacyWriteResult("maintainKnowledge", input.repoPath);
}

export async function runAutomaticMaintenance(input: AutomaticMaintenanceInput = {}) {
  return {
    status: "skipped",
    skippedReason: "removed_from_this_branch",
    reason: input.reason ?? null,
    beforeBacklog: await getEventBacklogStatus({ repoPath: input.repoPath }),
    afterBacklog: await getEventBacklogStatus({ repoPath: input.repoPath }),
    maintenance: null,
  };
}

export async function getEventBacklogStatus(input: EventBacklogStatusInput = {}) {
  return {
    repoPath: resolveRepoPath(input.repoPath),
    maintenanceRecommended: false,
    uncoveredEvents: 0,
    maintainableUnresolvedTraceGroupCount: 0,
    recommendedCommand: null,
    policy: {
      level: "off",
      reason: "legacy maintenance was removed from this branch",
    },
  };
}

export async function lintLocalPack(input: LintPackInput = {}) {
  return {
    repoPath: resolveRepoPath(input.repoPath),
    ok: true,
    issues: [],
    issueCount: 0,
    status: "removed_from_this_branch",
  };
}

export async function refreshControlArtifacts(input: RefreshControlArtifactsInput = {}) {
  return {
    repoPath: resolveRepoPath(input.repoPath),
    status: "removed_from_this_branch",
    logEntry: input.logEntry ?? null,
    lintResult: input.lintResult ?? null,
  };
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
  await mkdir(path.join(hostRepoPath, ".github"), { recursive: true });
  await mkdir(path.join(hostRepoPath, ".cursor", "rules"), { recursive: true });
  await mkdir(path.join(hostRepoPath, ".windsurf", "rules"), { recursive: true });
  await mkdir(path.join(hostRepoPath, "bin"), { recursive: true });

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
