import { existsSync } from "node:fs";
import { readdir, readFile, stat } from "node:fs/promises";
import path from "node:path";

import { describe, expect, it } from "vitest";

const repoRoot = process.cwd();

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

async function collectActiveFiles(directory: string): Promise<string[]> {
  const entries = await readdir(directory, { withFileTypes: true });
  const files: string[] = [];

  for (const entry of entries) {
    const absolutePath = path.join(directory, entry.name);
    const relativePath = path.relative(repoRoot, absolutePath).replaceAll(path.sep, "/");

    if (entry.isDirectory()) {
      if (ignoredDirectories.has(entry.name)) {
        continue;
      }
      if (ignoredRelativePrefixes.some((prefix) => `${relativePath}/`.startsWith(prefix))) {
        continue;
      }
      files.push(...await collectActiveFiles(absolutePath));
      continue;
    }

    if (!entry.isFile()) {
      continue;
    }
    if (ignoredFiles.has(relativePath)) {
      continue;
    }
    if (ignoredRelativePrefixes.some((prefix) => relativePath.startsWith(prefix))) {
      continue;
    }

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
    const files = await collectActiveFiles(repoRoot);
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
});
