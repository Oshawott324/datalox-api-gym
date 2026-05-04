#!/usr/bin/env node
import { existsSync, readFileSync } from "node:fs";
import { spawn } from "node:child_process";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function readInstallPackRoot(root) {
  const installPath = path.join(root, ".datalox", "install.json");
  if (!existsSync(installPath)) {
    return null;
  }
  try {
    const payload = JSON.parse(readFileSync(installPath, "utf8"));
    return typeof payload?.packRootPath === "string" ? payload.packRootPath : null;
  } catch {
    return null;
  }
}

function resolveRuntimeRoot(root) {
  const candidates = [
    root,
    readInstallPackRoot(root),
    path.join(os.homedir(), ".datalox", "cache", "datalox-trajectory-mcp"),
  ].filter(Boolean);

  for (const candidate of candidates) {
    const normalized = path.resolve(candidate);
    if (existsSync(path.join(normalized, "dist", "src", "cli", "main.js"))) {
      return normalized;
    }
  }

  throw new Error("Unable to resolve Datalox Trajectory MCP runtime root for datalox-codex.js");
}

const runtimeRoot = resolveRuntimeRoot(repoRoot);
const entrypoint = path.join(runtimeRoot, "dist", "src", "cli", "main.js");

const child = spawn(process.execPath, [entrypoint, "codex", ...process.argv.slice(2)], {
  stdio: "inherit",
  env: {
    ...process.env,
    DATALOX_ACTIVE_WRAPPER: "codex",
    DATALOX_HOST_KIND: "codex",
    DATALOX_ENFORCEMENT: "wrapper",
    DATALOX_DEFAULT_POST_RUN_MODE: process.env.DATALOX_DEFAULT_POST_RUN_MODE ?? "review",
    DATALOX_DEFAULT_REVIEW_MODEL: process.env.DATALOX_DEFAULT_REVIEW_MODEL ?? "gpt-5.4-mini",
  },
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 1);
});
