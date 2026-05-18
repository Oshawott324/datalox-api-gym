import { existsSync } from "node:fs";
import { execFile } from "node:child_process";
import { readFile, stat } from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";

import { describe, expect, it } from "vitest";

const repoRoot = process.cwd();
const expectedRepoUrl = "https://github.com/Oshawott324/datalox-agent-replay.git";
const execFileAsync = promisify(execFile);

const ignoredDirectories = new Set([
  ".git",
  "dist",
  "exports",
  "node_modules",
]);

const ignoredRelativePrefixes = [
  ".datalox/events/",
  ".datalox/tasks/",
];

const ignoredFiles = new Set([
  ".claude/settings.local.json",
  ".datalox/install.json",
  ".git",
  "docs/rl-trajectory.md",
  "tests/repoIdentity.test.ts",
]);

const forbiddenActiveStrings = [
  "datalox-trajectory-mcp",
  "Datalox Trajectory MCP",
  "datalox-pack",
  "Datalox Pack",
  "datalox-pack-mcp",
  "DATALOX_PACK",
  "agent-wiki",
  "auto-promote",
  "Complexity-LLC/datalox-agent-replay",
];

const removedLegacyPaths = [
  ".claude/hooks",
  ".cursor/rules/datalox-pack.mdc",
  ".windsurf/rules/datalox-pack.md",
  "agent-wiki",
  "bin/claude-global-auto-promote.sh",
  "bin/datalox-auto-promote.js",
  "bin/datalox-pack-mcp.js",
  "skills/maintain-datalox-pack",
];

async function collectTrackedActiveFiles(): Promise<string[]> {
  const { stdout } = await execFileAsync("git", ["ls-files", "-z"], {
    cwd: repoRoot,
    encoding: "buffer",
    maxBuffer: 10 * 1024 * 1024,
  });
  const files: string[] = [];

  for (const rawRelativePath of stdout.toString("utf8").split("\0")) {
    if (rawRelativePath.length === 0) {
      continue;
    }
    const relativePath = rawRelativePath.replaceAll(path.sep, "/");
    if (ignoredFiles.has(relativePath)) {
      continue;
    }
    if (relativePath.split("/").some((part) => ignoredDirectories.has(part))) {
      continue;
    }
    if (ignoredRelativePrefixes.some((prefix) => relativePath.startsWith(prefix))) {
      continue;
    }

    const absolutePath = path.join(repoRoot, relativePath);
    const fileStat = await stat(absolutePath);
    if (fileStat.size > 2_000_000) {
      continue;
    }
    files.push(absolutePath);
  }

  return files;
}

describe("repo identity regression guard", () => {
  it("keeps active surfaces on the Datalox Agent Replay identity", async () => {
    const files = await collectTrackedActiveFiles();
    const violations: string[] = [];

    for (const file of files) {
      const content = await readFile(file, "utf8").catch(() => null);
      if (content === null) {
        continue;
      }
      for (const forbidden of forbiddenActiveStrings) {
        if (content.includes(forbidden)) {
          violations.push(`${path.relative(repoRoot, file)} contains ${forbidden}`);
        }
      }
    }

    expect(violations).toEqual([]);
  });

  it("does not restore removed legacy product paths", () => {
    const existing = removedLegacyPaths.filter((relativePath) => existsSync(path.join(repoRoot, relativePath)));

    expect(existing).toEqual([]);
  });

  it("keeps install-facing files pointed at the live GitHub repo", async () => {
    const checkedFiles = [
      "README.md",
      "START_HERE.md",
      "DATALOX.md",
      "docs/agent-configuration.md",
      "bin/adopt-from-github.sh",
      "src/core/packCore.ts",
    ];
    const missing = [];

    for (const relativePath of checkedFiles) {
      const content = await readFile(path.join(repoRoot, relativePath), "utf8");
      if (!content.includes(expectedRepoUrl)) {
        missing.push(relativePath);
      }
    }

    expect(missing).toEqual([]);
  });
});
