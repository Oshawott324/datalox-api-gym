import { spawnSync } from "node:child_process";
import { constants as fsConstants, existsSync } from "node:fs";
import { access, chmod, copyFile, lstat, mkdir, readFile, readdir, readlink, realpath, rm, symlink, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import {
  getHostCapability,
  type EnforcementLevel,
  type HostSurfaceId,
} from "../adapters/capabilities.js";
import { getEventBacklogStatus, probeBootstrapCandidate } from "./packCore.js";

export type InstallHost = "all" | "codex" | "claude";

export interface InstallHostIntegrationsInput {
  host?: InstallHost;
  packRootPath: string;
}

export interface InstallLinkSummary {
  linked: string[];
  skipped: string[];
}

export interface InstallHostShimResult {
  selected: boolean;
  installed: boolean;
  shimPath: string;
  realBinary: string | null;
  stableLinks: string[];
}

export interface InstallHostIntegrationsResult {
  host: InstallHost;
  packRootPath: string;
  packCachePath: string;
  skillLinks: InstallLinkSummary;
  codex: InstallHostShimResult;
  claude: InstallHostShimResult;
  claudeHookPath: string | null;
  claudeSettingsPath: string | null;
  pathExportsUpdated: string[];
  status: EnforcementStatusSnapshot;
}

export interface DisableLinkSummary {
  removed: string[];
  skipped: string[];
}

export interface DisableHostShimResult {
  selected: boolean;
  removed: boolean;
  shimPath: string;
  stableLinksRemoved: string[];
}

export interface DisableHostIntegrationsResult {
  host: InstallHost;
  packRootPath: string;
  skillLinks: DisableLinkSummary;
  codex: DisableHostShimResult;
  claude: DisableHostShimResult;
  claudeHookRemoved: string | null;
  claudeSettingsPath: string | null;
  pathExportsRemoved: string[];
  status: EnforcementStatusSnapshot;
}

export interface HostSurfaceStatus {
  hostId: HostSurfaceId;
  enforcementLevel: EnforcementLevel;
  automatic: boolean;
  available: boolean;
  installed: boolean;
  shimPath: string | null;
  stableLinks: string[];
  hookInstalled: boolean;
  supportsPreRunInjection: boolean;
  supportsPostRunHook: boolean;
  supportsSecondPassReview: boolean;
  requiresPromptPlaceholder: boolean;
  nativeSkillLinks?: NativeSkillLinkStatus;
  surfaces?: ClaudeSurfaceSummary;
  notes: string[];
}

export interface NativeSkillLinkStatus {
  installed: boolean;
  canonical: boolean;
  root: string;
  linked: string[];
  missing: string[];
  legacyPackLink: string | null;
}

export interface ClaudeSurfaceSummary {
  wrapper: {
    installed: boolean;
    automatic: boolean;
    active: boolean;
    preRunEnforced: boolean;
    enforcementLevel: EnforcementLevel;
    shimPath: string;
    stableLinks: string[];
    notes: string[];
  };
  stopHook: {
    installed: boolean;
    postTurnSidecar: true;
    recordsAfterTurn: boolean;
    preRunEnforced: false;
    notes: string[];
  };
  nativeSkills: {
    installed: boolean;
    canonical: boolean;
    restartSensitive: true;
    modelChosen: true;
    preRunEnforced: false;
    root: string;
    linked: string[];
    missing: string[];
    legacyPackLink: string | null;
    notes: string[];
  };
  mcp: {
    available: boolean;
    guidanceOnly: true;
    modelChosen: true;
    preRunEnforced: false;
    notes: string[];
  };
}

export interface EnforcementStatusSnapshot {
  generatedAt: string;
  packRootPath: string;
  reviewDefaults: {
    postRunMode: string;
    reviewModel: string;
  };
  adapters: Record<HostSurfaceId, HostSurfaceStatus>;
  currentSession: CurrentSessionStatus;
  repo: {
    repoPath: string;
    bootstrapStatus: "ready" | "bootstrappable" | "repairable" | "blocked";
    guidanceSurface: boolean;
    automaticReady: boolean;
    enforcementLevel: EnforcementLevel;
    reasons: string[];
    maintenanceBacklog: Awaited<ReturnType<typeof getEventBacklogStatus>> | null;
  };
}

export interface CurrentSessionStatus {
  detectedHostKind: string | null;
  activeWrapper: string | null;
  wrapperEnforced: boolean;
  enforcementLevel: EnforcementLevel;
  sessionId: string | null;
  codexThreadId: string | null;
  notes: string[];
}

const STABLE_BIN_DIRS = ["/opt/homebrew/bin", "/usr/local/bin"];
const PATH_EXPORT_LINE = 'export PATH="$HOME/.local/bin:$PATH"';
const INSTALL_STATUS_RELATIVE_PATH = path.join(".datalox", "install.json");

function normalizePath(value: string): string {
  return value.replaceAll("\\", "/");
}

function optionalEnv(name: string): string | null {
  const value = process.env[name];
  return typeof value === "string" && value.trim().length > 0 ? value.trim() : null;
}

function inspectCurrentSession(input: { claudeHookInstalled?: boolean } = {}): CurrentSessionStatus {
  const activeWrapper = optionalEnv("DATALOX_ACTIVE_WRAPPER");
  const hostKind = optionalEnv("DATALOX_HOST_KIND");
  const enforcement = optionalEnv("DATALOX_ENFORCEMENT");
  const sessionId = optionalEnv("DATALOX_SESSION_ID");
  const codexThreadId = optionalEnv("CODEX_THREAD_ID");
  const codexOrigin = optionalEnv("CODEX_INTERNAL_ORIGINATOR_OVERRIDE");
  const detectedHostKind = hostKind
    ?? activeWrapper
    ?? (codexThreadId || codexOrigin ? "codex" : null);
  const wrapperEnforced = activeWrapper !== null && enforcement === "wrapper";
  const notes: string[] = [];

  if (wrapperEnforced) {
    notes.push(`Current process is inside the Datalox ${activeWrapper} wrapper.`);
  } else if (detectedHostKind === "codex") {
    notes.push("Native Codex session detected without a Datalox wrapper sentinel; MCP use depends on explicit tool calls.");
  } else if (detectedHostKind === "claude") {
    notes.push("Claude host detected without a complete Datalox wrapper sentinel; pre-run guidance injection is not enforced.");
    if (activeWrapper === "claude" && enforcement !== "wrapper") {
      notes.push("DATALOX_ACTIVE_WRAPPER=claude is present without DATALOX_ENFORCEMENT=wrapper, so this is not counted as wrapper-enforced.");
    }
    if (input.claudeHookInstalled) {
      notes.push("Claude Stop-hook automation is installed, but it runs after the model turn.");
    }
  } else {
    notes.push("No active Datalox wrapper sentinel detected; status describes installed capability, not active-session enforcement.");
  }

  return {
    detectedHostKind,
    activeWrapper,
    wrapperEnforced,
    enforcementLevel: wrapperEnforced ? "enforced" : "guidance_only",
    sessionId,
    codexThreadId,
    notes,
  };
}

function buildClaudeSurfaceSummary(input: {
  shimPath: string;
  stableLinks: string[];
  installed: boolean;
  automatic: boolean;
  hookInstalled: boolean;
  nativeSkillLinks: NativeSkillLinkStatus;
  currentSession: CurrentSessionStatus;
}): ClaudeSurfaceSummary {
  const wrapperPreRunEnforced = input.currentSession.activeWrapper === "claude"
    && input.currentSession.wrapperEnforced === true;
  const wrapperNotes = input.automatic
    ? ["Claude shim wrapper is installed and reachable for prompt runs that route through the shim."]
    : input.installed
      ? ["Claude shim wrapper is installed, but no stable link or shell PATH export was detected yet."]
      : ["Claude shim wrapper is not installed; Claude pre-run guidance injection is unavailable through the shim."];
  if (wrapperPreRunEnforced) {
    wrapperNotes.push("Current process is inside the Datalox Claude wrapper.");
  }
  if (!input.installed && input.hookInstalled) {
    wrapperNotes.push("Claude Stop hook is installed, but it cannot enforce pre-run guidance injection.");
  }

  const stopHookNotes = input.hookInstalled
    ? [
        "Claude Stop hook is installed.",
        "Stop-hook automation records, compiles, or maintains after Claude finishes a turn.",
      ]
    : ["Claude Stop hook is not installed."];
  stopHookNotes.push("The Stop hook is post-turn sidecar automation, not pre-run enforcement.");

  const nativeSkillNotes = input.nativeSkillLinks.canonical
    ? ["Canonical Claude native skill links are installed at ~/.claude/skills/<skill-name>."]
    : ["Claude native skill links are not fully canonical at ~/.claude/skills/<skill-name>."];
  nativeSkillNotes.push("Claude native skill use is model-chosen and may require a Claude Code restart before newly linked skills appear.");

  return {
    wrapper: {
      installed: input.installed,
      automatic: input.automatic,
      active: input.currentSession.activeWrapper === "claude",
      preRunEnforced: wrapperPreRunEnforced,
      enforcementLevel: wrapperPreRunEnforced ? "enforced" : input.automatic ? "enforced" : "guidance_only",
      shimPath: normalizePath(input.shimPath),
      stableLinks: input.stableLinks.map(normalizePath),
      notes: wrapperNotes,
    },
    stopHook: {
      installed: input.hookInstalled,
      postTurnSidecar: true,
      recordsAfterTurn: input.hookInstalled,
      preRunEnforced: false,
      notes: stopHookNotes,
    },
    nativeSkills: {
      installed: input.nativeSkillLinks.installed,
      canonical: input.nativeSkillLinks.canonical,
      restartSensitive: true,
      modelChosen: true,
      preRunEnforced: false,
      root: input.nativeSkillLinks.root,
      linked: input.nativeSkillLinks.linked,
      missing: input.nativeSkillLinks.missing,
      legacyPackLink: input.nativeSkillLinks.legacyPackLink,
      notes: nativeSkillNotes,
    },
    mcp: {
      available: true,
      guidanceOnly: true,
      modelChosen: true,
      preRunEnforced: false,
      notes: ["Claude MCP tools are guidance-only unless Claude Code actually calls them."],
    },
  };
}

function claudeSkillsDir(): string {
  return path.join(os.homedir(), ".claude", "skills");
}

function claudeLegacyPackSkillsLink(): string {
  return path.join(claudeSkillsDir(), "datalox-pack");
}

function validFullPackRoot(candidate: string): boolean {
  return (
    existsSync(path.join(candidate, "package.json"))
    && existsSync(path.join(candidate, "scripts", "lib", "agent-pack.mjs"))
  );
}

async function ensureLocalPackCache(packRootPath: string): Promise<string> {
  const cacheRoot = path.join(os.homedir(), ".datalox", "cache");
  const cachePath = path.join(cacheRoot, "datalox-trajectory-mcp");

  if (path.resolve(packRootPath) === path.resolve(cachePath)) {
    return cachePath;
  }

  await mkdir(cacheRoot, { recursive: true });
  if (existsSync(cachePath)) {
    if (validFullPackRoot(cachePath)) {
      return cachePath;
    }
    await rm(cachePath, { recursive: true, force: true });
  }

  await symlink(packRootPath, cachePath, "dir");
  return cachePath;
}

interface SkillLinkSpec {
  target: string;
  destination: string;
}

async function linkIfMissing(target: string, destination: string, summary: InstallLinkSummary): Promise<void> {
  await mkdir(path.dirname(destination), { recursive: true });

  if (existsSync(destination)) {
    try {
      const stats = await lstat(destination);
      if (stats.isSymbolicLink()) {
        const existing = await readlink(destination);
        if (path.resolve(path.dirname(destination), existing) === path.resolve(target)) {
          summary.skipped.push(destination);
          return;
        }
      }
    } catch {
      // Fall through and preserve existing path.
    }
    summary.skipped.push(destination);
    return;
  }

  await symlink(target, destination, "dir");
  summary.linked.push(destination);
}

async function listPackSkillNames(packRootPath: string): Promise<string[]> {
  const skillsDir = path.join(packRootPath, "skills");
  let entries;
  try {
    entries = await readdir(skillsDir, { withFileTypes: true });
  } catch {
    return [];
  }

  return entries
    .filter((entry) => (entry.isDirectory() || entry.isSymbolicLink()) && existsSync(path.join(skillsDir, entry.name, "SKILL.md")))
    .map((entry) => entry.name)
    .sort((left, right) => left.localeCompare(right));
}

async function claudeSkillLinkSpecs(packRootPath: string): Promise<SkillLinkSpec[]> {
  const skillNames = await listPackSkillNames(packRootPath);
  return skillNames.map((skillName) => ({
    target: path.join(packRootPath, "skills", skillName),
    destination: path.join(claudeSkillsDir(), skillName),
  }));
}

async function skillLinkSpecs(host: InstallHost, packRootPath: string): Promise<SkillLinkSpec[]> {
  const skillsDir = path.join(packRootPath, "skills");
  const specs: SkillLinkSpec[] = [];
  const selected = new Set(selectedHosts(host));

  if (selected.has("codex")) {
    specs.push({
      target: skillsDir,
      destination: path.join(os.homedir(), ".codex", "skills", "datalox-trajectory-mcp"),
    });
  }

  if (selected.has("claude")) {
    specs.push(...await claudeSkillLinkSpecs(packRootPath));
  }

  if (host === "all") {
    specs.push(
      {
        target: skillsDir,
        destination: path.join(os.homedir(), ".opencode", "skills", "datalox-trajectory-mcp"),
      },
      {
        target: skillsDir,
        destination: path.join(os.homedir(), ".gemini", "skills", "datalox-trajectory-mcp"),
      },
      {
        target: skillsDir,
        destination: path.join(packRootPath, ".cursor", "skills"),
      },
      {
        target: skillsDir,
        destination: path.join(packRootPath, ".windsurf", "skills"),
      },
    );
  }

  return specs;
}

async function installSkillLinks(host: InstallHost, packRootPath: string): Promise<InstallLinkSummary> {
  const summary: InstallLinkSummary = { linked: [], skipped: [] };
  const skillsDir = path.join(packRootPath, "skills");
  if (selectedHosts(host).includes("claude")) {
    await removeSymlinkIfTargetMatches(claudeLegacyPackSkillsLink(), skillsDir);
  }
  for (const spec of await skillLinkSpecs(host, packRootPath)) {
    await linkIfMissing(spec.target, spec.destination, summary);
  }

  return summary;
}

async function symlinkTargetMatches(linkPath: string, expectedTarget: string): Promise<boolean> {
  try {
    const stats = await lstat(linkPath);
    if (!stats.isSymbolicLink()) {
      return false;
    }
    const existing = await readlink(linkPath);
    const resolvedExisting = path.resolve(path.dirname(linkPath), existing);
    const [existingRealPath, expectedRealPath] = await Promise.all([
      realpath(resolvedExisting).catch(() => path.resolve(resolvedExisting)),
      realpath(expectedTarget).catch(() => path.resolve(expectedTarget)),
    ]);
    return existingRealPath === expectedRealPath;
  } catch {
    return false;
  }
}

async function removeSymlinkIfTargetMatches(linkPath: string, expectedTarget: string): Promise<boolean> {
  try {
    if (!await symlinkTargetMatches(linkPath, expectedTarget)) {
      return false;
    }
    await rm(linkPath, { force: true });
    return true;
  } catch {
    return false;
  }
}

async function uninstallSkillLinks(host: InstallHost, packRootPath: string): Promise<DisableLinkSummary> {
  const summary: DisableLinkSummary = { removed: [], skipped: [] };
  const skillsDir = path.join(packRootPath, "skills");

  for (const spec of await skillLinkSpecs(host, packRootPath)) {
    if (await removeSymlinkIfTargetMatches(spec.destination, spec.target)) {
      summary.removed.push(spec.destination);
      continue;
    }
    if (existsSync(spec.destination)) {
      summary.skipped.push(spec.destination);
    }
  }

  if (selectedHosts(host).includes("claude")) {
    const legacyLink = claudeLegacyPackSkillsLink();
    if (await removeSymlinkIfTargetMatches(legacyLink, skillsDir)) {
      summary.removed.push(legacyLink);
    } else if (existsSync(legacyLink)) {
      summary.skipped.push(legacyLink);
    }
  }

  return summary;
}

function selectedHosts(host: InstallHost): Array<Exclude<InstallHost, "all">> {
  return host === "all" ? ["codex", "claude"] : [host];
}

function findRealBinary(hostName: "codex" | "claude", shimPath: string, envOverride?: string): string | null {
  if (envOverride && existsSync(envOverride)) {
    return envOverride;
  }

  const result = spawnSync("which", ["-a", hostName], {
    encoding: "utf8",
  });
  if (result.status !== 0) {
    return null;
  }

  const ignored = new Set([
    shimPath,
    ...STABLE_BIN_DIRS.map((dir) => path.join(dir, hostName)),
  ].map((item) => path.resolve(item)));

  for (const candidate of result.stdout.split("\n").map((line) => line.trim()).filter(Boolean)) {
    if (ignored.has(path.resolve(candidate))) {
      continue;
    }
    return candidate;
  }
  return null;
}

async function installStableLinks(hostName: "codex" | "claude", shimPath: string): Promise<string[]> {
  const linked: string[] = [];

  for (const dir of STABLE_BIN_DIRS) {
    if (!existsSync(dir)) {
      continue;
    }
    try {
      await access(dir, fsConstants.W_OK);
    } catch {
      continue;
    }

    const target = path.join(dir, hostName);
    let stats = null;
    try {
      stats = await lstat(target);
    } catch {
      stats = null;
    }
    if (stats) {
      if (!stats.isSymbolicLink()) {
        continue;
      }
      const existing = await readlink(target);
      if (path.resolve(path.dirname(target), existing) === path.resolve(shimPath)) {
        continue;
      }
      continue;
    }

    await symlink(shimPath, target);
    linked.push(target);
  }

  return linked;
}

async function ensurePathExport(filePath: string): Promise<boolean> {
  let existing = "";
  try {
    existing = await readFile(filePath, "utf8");
  } catch {
    existing = "";
  }
  if (existing.includes(PATH_EXPORT_LINE)) {
    return false;
  }
  const next = `${existing}${existing.endsWith("\n") || existing.length === 0 ? "" : "\n"}# Prefer local host shims such as the Datalox Codex wrapper.\n${PATH_EXPORT_LINE}\n`;
  await writeFile(filePath, next, "utf8");
  return true;
}

async function removePathExport(filePath: string): Promise<boolean> {
  let existing = "";
  try {
    existing = await readFile(filePath, "utf8");
  } catch {
    return false;
  }

  const block = `# Prefer local host shims such as the Datalox Codex wrapper.\n${PATH_EXPORT_LINE}\n`;
  if (!existing.includes(block)) {
    return false;
  }

  const next = existing.replace(block, "");
  if (next === existing) {
    return false;
  }
  await writeFile(filePath, next, "utf8");
  return true;
}

async function removeManagedShim(filePath: string, marker: string): Promise<boolean> {
  try {
    const stats = await lstat(filePath);
    if (!stats.isFile()) {
      return false;
    }
    const contents = await readFile(filePath, "utf8");
    if (
      !contents.includes(marker)
      || !contents.includes("PACK_ROOT=")
      || !contents.includes("DATALOX_DEFAULT_POST_RUN_MODE")
    ) {
      return false;
    }
    await rm(filePath, { force: true });
    return true;
  } catch {
    return false;
  }
}

async function readJsonIfPresent<T>(filePath: string): Promise<T | null> {
  try {
    return JSON.parse(await readFile(filePath, "utf8")) as T;
  } catch {
    return null;
  }
}

async function fileContains(filePath: string, needle: string): Promise<boolean> {
  try {
    return (await readFile(filePath, "utf8")).includes(needle);
  } catch {
    return false;
  }
}

async function hasManagedShim(filePath: string, marker: string): Promise<boolean> {
  try {
    const stats = await lstat(filePath);
    if (!stats.isFile()) {
      return false;
    }
  } catch {
    return false;
  }

  return fileContains(filePath, marker);
}

async function stableLinksPointingTo(shimPath: string, hostName: "codex" | "claude"): Promise<string[]> {
  const linked: string[] = [];

  for (const dir of STABLE_BIN_DIRS) {
    const target = path.join(dir, hostName);
    try {
      const stats = await lstat(target);
      if (!stats.isSymbolicLink()) {
        continue;
      }
      const existing = await readlink(target);
      if (path.resolve(path.dirname(target), existing) === path.resolve(shimPath)) {
        linked.push(target);
      }
    } catch {
      // Ignore missing or unrelated entries.
    }
  }

  return linked;
}

async function pathExportsPresent(): Promise<string[]> {
  const matches: string[] = [];
  for (const filePath of [path.join(os.homedir(), ".zshrc"), path.join(os.homedir(), ".zprofile")]) {
    if (await fileContains(filePath, PATH_EXPORT_LINE)) {
      matches.push(filePath);
    }
  }
  return matches;
}

interface InstallStatusFile {
  version: 1;
  installedAt?: string;
  updatedAt?: string;
  installMode?: "manual" | "auto" | "repair";
  packRootPath: string;
  enforcement?: EnforcementStatusSnapshot;
}

async function writePackInstallStatusFile(
  packRootPath: string,
  snapshot: EnforcementStatusSnapshot,
): Promise<string> {
  const installPath = path.join(packRootPath, INSTALL_STATUS_RELATIVE_PATH);
  await mkdir(path.dirname(installPath), { recursive: true });
  const existing = await readJsonIfPresent<InstallStatusFile>(installPath);
  const now = new Date().toISOString();
  const payload: InstallStatusFile = {
    version: 1,
    installedAt: existing?.installedAt ?? now,
    updatedAt: now,
    installMode: existing?.installMode,
    packRootPath,
    enforcement: snapshot,
  };
  await writeFile(installPath, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
  return installPath;
}

function buildCodexShim(realBinary: string, packRootPath: string): string {
  const stableCodexPaths = STABLE_BIN_DIRS.map((dir) => path.join(dir, "codex"));
  return `#!/usr/bin/env bash
set -euo pipefail

REAL_CODEX_BIN_FALLBACK=${JSON.stringify(realBinary)}
PACK_ROOT=${JSON.stringify(packRootPath)}
SHIM_PATH=${JSON.stringify(path.join(os.homedir(), ".local", "bin", "codex"))}
STABLE_CODEX_PATHS=(${stableCodexPaths.map((item) => JSON.stringify(item)).join(" ")})

resolve_repo() {
  local repo="$(pwd)"
  local args=("$@")
  for ((i=0; i<\${#args[@]}; i++)); do
    case "\${args[i]}" in
      -C|--cd)
        if (( i + 1 < \${#args[@]} )); then
          repo="\${args[i+1]}"
        fi
        ;;
    esac
  done
  (cd "$repo" >/dev/null 2>&1 && pwd) || printf '%s\\n' "$repo"
}

should_wrap() {
  local args=("$@")
  for arg in "\${args[@]}"; do
    case "$arg" in
      exec|e|review)
        return 0
        ;;
    esac
  done
  return 1
}

resolve_real_codex_bin() {
  if [[ -n "\${DATALOX_REAL_CODEX_BIN:-}" && -x "\${DATALOX_REAL_CODEX_BIN}" ]]; then
    printf '%s\\n' "\${DATALOX_REAL_CODEX_BIN}"
    return 0
  fi

  if [[ -x "$REAL_CODEX_BIN_FALLBACK" ]]; then
    printf '%s\\n' "$REAL_CODEX_BIN_FALLBACK"
    return 0
  fi

  local candidate
  while IFS= read -r candidate; do
    [[ -z "$candidate" ]] && continue
    if [[ "$candidate" == "$SHIM_PATH" ]]; then
      continue
    fi
    local skip=0
    for stable in "\${STABLE_CODEX_PATHS[@]}"; do
      if [[ "$candidate" == "$stable" ]]; then
        skip=1
        break
      fi
    done
    if (( skip == 1 )); then
      continue
    fi
    if [[ -x "$candidate" ]]; then
      printf '%s\\n' "$candidate"
      return 0
    fi
  done < <(which -a codex 2>/dev/null || true)

  printf 'datalox-codex shim could not resolve a real codex binary. Re-run setup or set DATALOX_REAL_CODEX_BIN.\\n' >&2
  return 1
}

REAL_CODEX_BIN="$(resolve_real_codex_bin)"
repo="$(resolve_repo "$@")"
if should_wrap "$@"; then
  export DATALOX_ACTIVE_WRAPPER="codex"
  export DATALOX_HOST_KIND="codex"
  export DATALOX_ENFORCEMENT="wrapper"
  export DATALOX_CODEX_BIN="$REAL_CODEX_BIN"
  : "\${DATALOX_DEFAULT_POST_RUN_MODE:=trajectory}"
  : "\${DATALOX_DEFAULT_REVIEW_MODEL:=gpt-5.4-mini}"
  export DATALOX_DEFAULT_POST_RUN_MODE
  export DATALOX_DEFAULT_REVIEW_MODEL
  exec node "$PACK_ROOT/bin/datalox-codex.js" --repo "$repo" -- "$@"
fi

exec "$REAL_CODEX_BIN" "$@"
`;
}

function buildClaudeShim(realBinary: string, packRootPath: string): string {
  const stableClaudePaths = STABLE_BIN_DIRS.map((dir) => path.join(dir, "claude"));
  return `#!/usr/bin/env bash
set -euo pipefail

REAL_CLAUDE_BIN_FALLBACK=${JSON.stringify(realBinary)}
PACK_ROOT=${JSON.stringify(packRootPath)}
SHIM_PATH=${JSON.stringify(path.join(os.homedir(), ".local", "bin", "claude"))}
STABLE_CLAUDE_PATHS=(${stableClaudePaths.map((item) => JSON.stringify(item)).join(" ")})

resolve_repo() {
  local repo="$(pwd)"
  local args=("$@")
  for ((i=0; i<\${#args[@]}; i++)); do
    case "\${args[i]}" in
      -C|--cd|--cwd)
        if (( i + 1 < \${#args[@]} )); then
          repo="\${args[i+1]}"
        fi
        ;;
    esac
  done
  (cd "$repo" >/dev/null 2>&1 && pwd) || printf '%s\\n' "$repo"
}

should_wrap() {
  local args=("$@")
  if (( \${#args[@]} == 0 )); then
    return 1
  fi
  case "\${args[0]}" in
    mcp|update|config|-h|--help|-v|--version)
      return 1
      ;;
  esac
  for arg in "\${args[@]}"; do
    case "$arg" in
      -p|--print)
        return 0
        ;;
    esac
  done
  for arg in "\${args[@]}"; do
    case "$arg" in
      -*)
        ;;
      *)
        return 0
        ;;
    esac
  done
  return 1
}

resolve_real_claude_bin() {
  if [[ -n "\${DATALOX_REAL_CLAUDE_BIN:-}" && -x "\${DATALOX_REAL_CLAUDE_BIN}" ]]; then
    printf '%s\\n' "\${DATALOX_REAL_CLAUDE_BIN}"
    return 0
  fi

  if [[ -x "$REAL_CLAUDE_BIN_FALLBACK" ]]; then
    printf '%s\\n' "$REAL_CLAUDE_BIN_FALLBACK"
    return 0
  fi

  local candidate
  while IFS= read -r candidate; do
    [[ -z "$candidate" ]] && continue
    if [[ "$candidate" == "$SHIM_PATH" ]]; then
      continue
    fi
    local skip=0
    for stable in "\${STABLE_CLAUDE_PATHS[@]}"; do
      if [[ "$candidate" == "$stable" ]]; then
        skip=1
        break
      fi
    done
    if (( skip == 1 )); then
      continue
    fi
    if [[ -x "$candidate" ]]; then
      printf '%s\\n' "$candidate"
      return 0
    fi
  done < <(which -a claude 2>/dev/null || true)

  printf 'datalox-claude shim could not resolve a real claude binary. Re-run setup or set DATALOX_REAL_CLAUDE_BIN.\\n' >&2
  return 1
}

REAL_CLAUDE_BIN="$(resolve_real_claude_bin)"
repo="$(resolve_repo "$@")"
if should_wrap "$@"; then
  export DATALOX_ACTIVE_WRAPPER="claude"
  export DATALOX_HOST_KIND="claude"
  export DATALOX_ENFORCEMENT="wrapper"
  export DATALOX_CLAUDE_BIN="$REAL_CLAUDE_BIN"
  : "\${DATALOX_DEFAULT_POST_RUN_MODE:=trajectory}"
  : "\${DATALOX_DEFAULT_REVIEW_MODEL:=gpt-5.4-mini}"
  export DATALOX_DEFAULT_POST_RUN_MODE
  export DATALOX_DEFAULT_REVIEW_MODEL
  exec node "$PACK_ROOT/bin/datalox-claude.js" --repo "$repo" -- "$@"
fi

exec "$REAL_CLAUDE_BIN" "$@"
`;
}

async function writeExecutable(filePath: string, content: string): Promise<void> {
  await mkdir(path.dirname(filePath), { recursive: true });
  await writeFile(filePath, content, "utf8");
  await chmod(filePath, 0o755);
}

async function installClaudeHook(packRootPath: string): Promise<{ hookPath: string; settingsPath: string }> {
  const claudeHome = path.join(os.homedir(), ".claude");
  const hooksDir = path.join(claudeHome, "hooks");
  const settingsPath = path.join(claudeHome, "settings.json");
  const hookPath = path.join(hooksDir, "datalox-auto-promote.sh");

  await mkdir(hooksDir, { recursive: true });
  await copyFile(path.join(packRootPath, "bin", "claude-global-auto-promote.sh"), hookPath);
  await chmod(hookPath, 0o755);

  let parsed: Record<string, unknown> = {};
  try {
    parsed = JSON.parse(await readFile(settingsPath, "utf8")) as Record<string, unknown>;
  } catch {
    parsed = {};
  }

  const hooks = (parsed.hooks && typeof parsed.hooks === "object" ? parsed.hooks : {}) as Record<string, unknown>;
  parsed.hooks = hooks;
  for (const eventName of ["Stop", "SubagentStop"]) {
    const entries = Array.isArray(hooks[eventName]) ? hooks[eventName] as Array<Record<string, unknown>> : [];
    const hasDatalox = entries.some((entry) => Array.isArray(entry.hooks) && entry.hooks.some((hook) => (
      hook
      && typeof hook === "object"
      && (hook as { type?: unknown }).type === "command"
      && typeof (hook as { command?: unknown }).command === "string"
      && (hook as { command: string }).command.includes("datalox-auto-promote.sh")
    )));
    if (!hasDatalox) {
      entries.push({
        hooks: [
          {
            type: "command",
            command: hookPath,
            timeout: 60,
          },
        ],
      });
    }
    hooks[eventName] = entries;
  }

  await writeFile(settingsPath, `${JSON.stringify(parsed, null, 2)}\n`, "utf8");
  return { hookPath, settingsPath };
}

async function uninstallClaudeHook(): Promise<{ hookPath: string | null; settingsPath: string | null }> {
  const claudeHome = path.join(os.homedir(), ".claude");
  const hookPath = path.join(claudeHome, "hooks", "datalox-auto-promote.sh");
  const settingsPath = path.join(claudeHome, "settings.json");

  let removedHookPath: string | null = null;
  try {
    const hookStats = await lstat(hookPath);
    if (hookStats.isFile()) {
      const contents = await readFile(hookPath, "utf8");
      if (contents.includes("datalox-auto-promote.js")) {
        await rm(hookPath, { force: true });
        removedHookPath = hookPath;
      }
    }
  } catch {
    // Ignore missing or unrelated hook files.
  }

  try {
    const parsed = JSON.parse(await readFile(settingsPath, "utf8")) as Record<string, unknown>;
    const hooks = (parsed.hooks && typeof parsed.hooks === "object") ? parsed.hooks as Record<string, unknown> : null;
    if (!hooks) {
      return { hookPath: removedHookPath, settingsPath: existsSync(settingsPath) ? settingsPath : null };
    }

    let changed = false;
    for (const eventName of ["Stop", "SubagentStop"]) {
      const entries = Array.isArray(hooks[eventName]) ? hooks[eventName] as Array<Record<string, unknown>> : [];
      const filtered = entries.filter((entry) => !(
        Array.isArray(entry.hooks)
        && entry.hooks.some((hook) => (
          hook
          && typeof hook === "object"
          && (hook as { type?: unknown }).type === "command"
          && typeof (hook as { command?: unknown }).command === "string"
          && (hook as { command: string }).command.includes("datalox-auto-promote.sh")
        ))
      ));
      if (filtered.length !== entries.length) {
        changed = true;
      }
      if (filtered.length > 0) {
        hooks[eventName] = filtered;
      } else if (eventName in hooks) {
        delete hooks[eventName];
      }
    }

    if (changed) {
      if (Object.keys(hooks).length === 0) {
        delete parsed.hooks;
      }
      await writeFile(settingsPath, `${JSON.stringify(parsed, null, 2)}\n`, "utf8");
    }
    return { hookPath: removedHookPath, settingsPath };
  } catch {
    return { hookPath: removedHookPath, settingsPath: existsSync(settingsPath) ? settingsPath : null };
  }
}

async function isClaudeHookInstalled(): Promise<boolean> {
  const hookPath = path.join(os.homedir(), ".claude", "hooks", "datalox-auto-promote.sh");
  const settingsPath = path.join(os.homedir(), ".claude", "settings.json");
  const hookFileMatches = await fileContains(hookPath, "datalox-auto-promote.js");
  if (!hookFileMatches) {
    return false;
  }

  const parsed = await readJsonIfPresent<Record<string, unknown>>(settingsPath);
  const hooks = parsed?.hooks && typeof parsed.hooks === "object"
    ? parsed.hooks as Record<string, unknown>
    : null;
  if (!hooks) {
    return false;
  }

  for (const eventName of ["Stop", "SubagentStop"]) {
    const entries = Array.isArray(hooks[eventName]) ? hooks[eventName] as Array<Record<string, unknown>> : [];
    const hasDatalox = entries.some((entry) => Array.isArray(entry.hooks) && entry.hooks.some((hook) => (
      hook
      && typeof hook === "object"
      && (hook as { type?: unknown }).type === "command"
      && typeof (hook as { command?: unknown }).command === "string"
      && (hook as { command: string }).command.includes("datalox-auto-promote.sh")
    )));
    if (hasDatalox) {
      return true;
    }
  }

  return false;
}

async function inspectClaudeNativeSkillLinks(packRootPath: string): Promise<NativeSkillLinkStatus> {
  const specs = await claudeSkillLinkSpecs(packRootPath);
  const linked: string[] = [];
  const missing: string[] = [];

  for (const spec of specs) {
    if (await symlinkTargetMatches(spec.destination, spec.target)) {
      linked.push(spec.destination);
      continue;
    }
    missing.push(spec.destination);
  }

  const legacyPackLink = await symlinkTargetMatches(
    claudeLegacyPackSkillsLink(),
    path.join(packRootPath, "skills"),
  )
    ? claudeLegacyPackSkillsLink()
    : null;

  return {
    installed: specs.length > 0 && missing.length === 0,
    canonical: specs.length > 0 && missing.length === 0 && legacyPackLink === null,
    root: claudeSkillsDir(),
    linked: linked.map(normalizePath),
    missing: missing.map(normalizePath),
    legacyPackLink: legacyPackLink ? normalizePath(legacyPackLink) : null,
  };
}

function computeRepoEnforcementLevel(
  automaticReady: boolean,
  conditionalReady: boolean,
): EnforcementLevel {
  if (automaticReady) {
    return "enforced";
  }
  if (conditionalReady) {
    return "conditional";
  }
  return "guidance_only";
}

export async function inspectEnforcementStatus(input: {
  packRootPath: string;
  repoPath?: string;
}): Promise<EnforcementStatusSnapshot> {
  const packRootPath = path.resolve(input.packRootPath);
  const repoPath = path.resolve(input.repoPath ?? packRootPath);
  const localBin = path.join(os.homedir(), ".local", "bin");
  const codexShimPath = path.join(localBin, "codex");
  const claudeShimPath = path.join(localBin, "claude");
  const pathExportFiles = await pathExportsPresent();
  const pathActivationAvailable = pathExportFiles.length > 0;

  const codexInstalled = await hasManagedShim(codexShimPath, "datalox-codex.js");
  const codexStableLinks = await stableLinksPointingTo(codexShimPath, "codex");
  const codexAutomatic = codexInstalled && (codexStableLinks.length > 0 || pathActivationAvailable);

  const claudeInstalled = await hasManagedShim(claudeShimPath, "datalox-claude.js");
  const claudeStableLinks = await stableLinksPointingTo(claudeShimPath, "claude");
  const claudeHookInstalled = await isClaudeHookInstalled();
  const claudeNativeSkillLinks = await inspectClaudeNativeSkillLinks(packRootPath);
  const claudeAutomatic = claudeInstalled && (claudeStableLinks.length > 0 || pathActivationAvailable);
  const currentSession = inspectCurrentSession({ claudeHookInstalled });
  const claudeSurfaces = buildClaudeSurfaceSummary({
    shimPath: claudeShimPath,
    stableLinks: claudeStableLinks,
    installed: claudeInstalled,
    automatic: claudeAutomatic,
    hookInstalled: claudeHookInstalled,
    nativeSkillLinks: claudeNativeSkillLinks,
    currentSession,
  });

  const repoProbe = await probeBootstrapCandidate(repoPath);
  const repoReady = repoProbe.status === "ready"
    || repoProbe.status === "bootstrappable"
    || repoProbe.status === "repairable";
  const guidanceSurface = repoProbe.detected.hasDataloxMd
    || repoProbe.detected.hasConfig
    || repoProbe.detected.hasAgentWiki
    || repoProbe.detected.hasInstallStamp;

  const adapters: Record<HostSurfaceId, HostSurfaceStatus> = {
    codex: {
      hostId: "codex",
      enforcementLevel: getHostCapability("codex").enforcementLevel,
      automatic: codexAutomatic,
      available: true,
      installed: codexInstalled,
      shimPath: normalizePath(codexShimPath),
      stableLinks: codexStableLinks.map(normalizePath),
      hookInstalled: false,
      supportsPreRunInjection: getHostCapability("codex").supportsPreRunInjection,
      supportsPostRunHook: getHostCapability("codex").supportsPostRunHook,
      supportsSecondPassReview: getHostCapability("codex").supportsSecondPassReview,
      requiresPromptPlaceholder: getHostCapability("codex").requiresPromptPlaceholder,
      notes: codexAutomatic
        ? []
        : codexInstalled
          ? ["Codex shim is installed, but no stable link or shell PATH export was detected yet."]
          : ["Codex shim is not installed."],
    },
    claude: {
      hostId: "claude",
      enforcementLevel: getHostCapability("claude").enforcementLevel,
      automatic: claudeAutomatic,
      available: true,
      installed: claudeInstalled,
      shimPath: normalizePath(claudeShimPath),
      stableLinks: claudeStableLinks.map(normalizePath),
      hookInstalled: claudeHookInstalled,
      supportsPreRunInjection: getHostCapability("claude").supportsPreRunInjection,
      supportsPostRunHook: getHostCapability("claude").supportsPostRunHook,
      supportsSecondPassReview: getHostCapability("claude").supportsSecondPassReview,
      requiresPromptPlaceholder: getHostCapability("claude").requiresPromptPlaceholder,
      nativeSkillLinks: claudeNativeSkillLinks,
      surfaces: claudeSurfaces,
      notes: claudeAutomatic
        ? [
            ...(claudeHookInstalled ? [] : ["Claude shim is automatic; hook is optional sidecar automation and is not installed."]),
            ...(claudeNativeSkillLinks.canonical ? [] : ["Claude native skill links are not installed at canonical ~/.claude/skills/<skill-name> paths."]),
          ]
        : claudeInstalled
          ? [
              "Claude shim is installed, but no stable link or shell PATH export was detected yet.",
              ...(claudeHookInstalled ? ["Claude Stop hook is installed, but it is post-turn sidecar automation and cannot enforce pre-run guidance injection."] : []),
              ...(claudeNativeSkillLinks.canonical ? [] : ["Claude native skill links are not installed at canonical ~/.claude/skills/<skill-name> paths."]),
            ]
          : [
              "Claude shim wrapper is not installed, so pre-run Datalox guidance injection is unavailable for native Claude Code.",
              ...(claudeHookInstalled ? ["Claude Stop hook is installed, but it runs after the model turn and cannot prove pre-turn skill use."] : []),
              ...(claudeNativeSkillLinks.canonical ? [] : ["Claude native skill links are not installed at canonical ~/.claude/skills/<skill-name> paths."]),
            ],
    },
    generic_cli: {
      hostId: "generic_cli",
      enforcementLevel: getHostCapability("generic_cli").enforcementLevel,
      automatic: false,
      available: true,
      installed: true,
      shimPath: null,
      stableLinks: [],
      hookInstalled: false,
      supportsPreRunInjection: getHostCapability("generic_cli").supportsPreRunInjection,
      supportsPostRunHook: getHostCapability("generic_cli").supportsPostRunHook,
      supportsSecondPassReview: getHostCapability("generic_cli").supportsSecondPassReview,
      requiresPromptPlaceholder: getHostCapability("generic_cli").requiresPromptPlaceholder,
      notes: ["Generic CLI enforcement only works when the host exposes __DATALOX_PROMPT__."],
    },
    mcp_only: {
      hostId: "mcp_only",
      enforcementLevel: getHostCapability("mcp_only").enforcementLevel,
      automatic: false,
      available: true,
      installed: true,
      shimPath: null,
      stableLinks: [],
      hookInstalled: false,
      supportsPreRunInjection: getHostCapability("mcp_only").supportsPreRunInjection,
      supportsPostRunHook: getHostCapability("mcp_only").supportsPostRunHook,
      supportsSecondPassReview: getHostCapability("mcp_only").supportsSecondPassReview,
      requiresPromptPlaceholder: getHostCapability("mcp_only").requiresPromptPlaceholder,
      notes: ["MCP tools are available, but the model still chooses whether to call them."],
    },
    repo_instructions: {
      hostId: "repo_instructions",
      enforcementLevel: getHostCapability("repo_instructions").enforcementLevel,
      automatic: false,
      available: guidanceSurface,
      installed: guidanceSurface,
      shimPath: null,
      stableLinks: [],
      hookInstalled: false,
      supportsPreRunInjection: getHostCapability("repo_instructions").supportsPreRunInjection,
      supportsPostRunHook: getHostCapability("repo_instructions").supportsPostRunHook,
      supportsSecondPassReview: getHostCapability("repo_instructions").supportsSecondPassReview,
      requiresPromptPlaceholder: getHostCapability("repo_instructions").requiresPromptPlaceholder,
      notes: guidanceSurface
        ? ["Repo instruction files are visible, but they do not enforce loop boundaries."]
        : ["No repo instruction surface was detected."],
    },
  };

  const automaticReady = repoReady && Object.values(adapters).some((adapter) => (
    adapter.enforcementLevel === "enforced" && adapter.automatic
  ));
  const conditionalReady = repoReady && !automaticReady && Object.values(adapters).some((adapter) => (
    adapter.enforcementLevel === "conditional" && adapter.available
  ));
  const canReadMaintenanceBacklog = repoProbe.detected.hasConfig && repoProbe.detected.hasAgentWiki;
  const maintenanceBacklog = canReadMaintenanceBacklog
    ? await getEventBacklogStatus({ repoPath })
    : null;

  return {
    generatedAt: new Date().toISOString(),
    packRootPath: normalizePath(packRootPath),
    reviewDefaults: {
      postRunMode: process.env.DATALOX_DEFAULT_POST_RUN_MODE ?? "trajectory",
      reviewModel: process.env.DATALOX_DEFAULT_REVIEW_MODEL ?? "gpt-5.4-mini",
    },
    adapters,
    currentSession,
    repo: {
      repoPath: normalizePath(repoPath),
      bootstrapStatus: repoProbe.status,
      guidanceSurface,
      automaticReady,
      enforcementLevel: computeRepoEnforcementLevel(automaticReady, conditionalReady),
      reasons: repoProbe.reasons,
      maintenanceBacklog,
    },
  };
}

function createSkippedHostResult(hostName: "codex" | "claude", selected: boolean): InstallHostShimResult {
  return {
    selected,
    installed: false,
    shimPath: path.join(os.homedir(), ".local", "bin", hostName),
    realBinary: null,
    stableLinks: [],
  };
}

function createSkippedDisableHostResult(hostName: "codex" | "claude", selected: boolean): DisableHostShimResult {
  return {
    selected,
    removed: false,
    shimPath: path.join(os.homedir(), ".local", "bin", hostName),
    stableLinksRemoved: [],
  };
}

export async function installHostIntegrations(input: InstallHostIntegrationsInput): Promise<InstallHostIntegrationsResult> {
  const host = input.host ?? "all";
  const packRootPath = path.resolve(input.packRootPath);
  const localBin = path.join(os.homedir(), ".local", "bin");
  await mkdir(localBin, { recursive: true });
  const packCachePath = await ensureLocalPackCache(packRootPath);
  const skillLinks = await installSkillLinks(host, packRootPath);

  const selected = new Set(selectedHosts(host));
  const codexShimPath = path.join(localBin, "codex");
  const claudeShimPath = path.join(localBin, "claude");

  let codex = createSkippedHostResult("codex", selected.has("codex"));
  if (selected.has("codex")) {
    const realBinary = findRealBinary("codex", codexShimPath, process.env.DATALOX_REAL_CODEX_BIN);
    if (realBinary) {
      await writeExecutable(codexShimPath, buildCodexShim(realBinary, packRootPath));
      codex = {
        selected: true,
        installed: true,
        shimPath: codexShimPath,
        realBinary,
        stableLinks: await installStableLinks("codex", codexShimPath),
      };
    }
  }

  let claude = createSkippedHostResult("claude", selected.has("claude"));
  let claudeHookPath: string | null = null;
  let claudeSettingsPath: string | null = null;
  if (selected.has("claude")) {
    const realBinary = findRealBinary("claude", claudeShimPath, process.env.DATALOX_REAL_CLAUDE_BIN);
    if (realBinary) {
      await writeExecutable(claudeShimPath, buildClaudeShim(realBinary, packRootPath));
      claude = {
        selected: true,
        installed: true,
        shimPath: claudeShimPath,
        realBinary,
        stableLinks: await installStableLinks("claude", claudeShimPath),
      };
    }
    const hook = await installClaudeHook(packRootPath);
    claudeHookPath = hook.hookPath;
    claudeSettingsPath = hook.settingsPath;
  }

  const pathExportsUpdated: string[] = [];
  if (await ensurePathExport(path.join(os.homedir(), ".zshrc"))) {
    pathExportsUpdated.push(path.join(os.homedir(), ".zshrc"));
  }
  if (await ensurePathExport(path.join(os.homedir(), ".zprofile"))) {
    pathExportsUpdated.push(path.join(os.homedir(), ".zprofile"));
  }

  const status = await inspectEnforcementStatus({
    packRootPath,
    repoPath: packRootPath,
  });
  await writePackInstallStatusFile(packRootPath, status);

  return {
    host,
    packRootPath: normalizePath(packRootPath),
    packCachePath: normalizePath(packCachePath),
    skillLinks: {
      linked: skillLinks.linked.map(normalizePath),
      skipped: skillLinks.skipped.map(normalizePath),
    },
    codex: {
      ...codex,
      shimPath: normalizePath(codex.shimPath),
      realBinary: codex.realBinary ? normalizePath(codex.realBinary) : null,
      stableLinks: codex.stableLinks.map(normalizePath),
    },
    claude: {
      ...claude,
      shimPath: normalizePath(claude.shimPath),
      realBinary: claude.realBinary ? normalizePath(claude.realBinary) : null,
      stableLinks: claude.stableLinks.map(normalizePath),
    },
    claudeHookPath: claudeHookPath ? normalizePath(claudeHookPath) : null,
    claudeSettingsPath: claudeSettingsPath ? normalizePath(claudeSettingsPath) : null,
    pathExportsUpdated: pathExportsUpdated.map(normalizePath),
    status,
  };
}

export async function disableHostIntegrations(input: InstallHostIntegrationsInput): Promise<DisableHostIntegrationsResult> {
  const host = input.host ?? "all";
  const packRootPath = path.resolve(input.packRootPath);
  const selected = new Set(selectedHosts(host));
  const skillLinks = await uninstallSkillLinks(host, packRootPath);

  const localBin = path.join(os.homedir(), ".local", "bin");
  const codexShimPath = path.join(localBin, "codex");
  const claudeShimPath = path.join(localBin, "claude");

  let codex = createSkippedDisableHostResult("codex", selected.has("codex"));
  if (selected.has("codex")) {
    const removed = await removeManagedShim(codexShimPath, "datalox-codex.js");
    const stableLinksRemoved: string[] = [];
    for (const dir of STABLE_BIN_DIRS) {
      const target = path.join(dir, "codex");
      if (await removeSymlinkIfTargetMatches(target, codexShimPath)) {
        stableLinksRemoved.push(target);
      }
    }
    codex = {
      selected: true,
      removed,
      shimPath: codexShimPath,
      stableLinksRemoved,
    };
  }

  let claude = createSkippedDisableHostResult("claude", selected.has("claude"));
  let claudeHookRemoved: string | null = null;
  let claudeSettingsPath: string | null = null;
  if (selected.has("claude")) {
    const removed = await removeManagedShim(claudeShimPath, "datalox-claude.js");
    const stableLinksRemoved: string[] = [];
    for (const dir of STABLE_BIN_DIRS) {
      const target = path.join(dir, "claude");
      if (await removeSymlinkIfTargetMatches(target, claudeShimPath)) {
        stableLinksRemoved.push(target);
      }
    }
    claude = {
      selected: true,
      removed,
      shimPath: claudeShimPath,
      stableLinksRemoved,
    };
    const hook = await uninstallClaudeHook();
    claudeHookRemoved = hook.hookPath;
    claudeSettingsPath = hook.settingsPath;
  }

  const pathExportsRemoved: string[] = [];
  if (host === "all") {
    for (const shellPath of [path.join(os.homedir(), ".zshrc"), path.join(os.homedir(), ".zprofile")]) {
      if (await removePathExport(shellPath)) {
        pathExportsRemoved.push(shellPath);
      }
    }
  }

  const status = await inspectEnforcementStatus({
    packRootPath,
    repoPath: packRootPath,
  });
  await writePackInstallStatusFile(packRootPath, status);

  return {
    host,
    packRootPath: normalizePath(packRootPath),
    skillLinks: {
      removed: skillLinks.removed.map(normalizePath),
      skipped: skillLinks.skipped.map(normalizePath),
    },
    codex: {
      ...codex,
      shimPath: normalizePath(codex.shimPath),
      stableLinksRemoved: codex.stableLinksRemoved.map(normalizePath),
    },
    claude: {
      ...claude,
      shimPath: normalizePath(claude.shimPath),
      stableLinksRemoved: claude.stableLinksRemoved.map(normalizePath),
    },
    claudeHookRemoved: claudeHookRemoved ? normalizePath(claudeHookRemoved) : null,
    claudeSettingsPath: claudeSettingsPath ? normalizePath(claudeSettingsPath) : null,
    pathExportsRemoved: pathExportsRemoved.map(normalizePath),
    status,
  };
}
