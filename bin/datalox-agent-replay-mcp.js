#!/usr/bin/env node
import { spawn, spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
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

function isFullPackRoot(root) {
  return (
    existsSync(path.join(root, "package.json"))
    && existsSync(path.join(root, "bin", "datalox.js"))
  );
}

function ensureRuntimeReady(runtimeRoot) {
  const serverEntrypoint = path.join(runtimeRoot, "dist", "src", "mcp", "replayServer.js");
  if (existsSync(serverEntrypoint)) {
    return serverEntrypoint;
  }
  if (!isFullPackRoot(runtimeRoot)) {
    return null;
  }

  const npmBinary = process.platform === "win32" ? "npm.cmd" : "npm";
  const installCommand = existsSync(path.join(runtimeRoot, "package-lock.json")) ? ["ci"] : ["install"];
  if (!existsSync(path.join(runtimeRoot, "node_modules"))) {
    const install = spawnSync(npmBinary, installCommand, {
      cwd: runtimeRoot,
      stdio: "inherit",
    });
    if (install.status !== 0) {
      process.exit(install.status ?? 1);
    }
  }

  const build = spawnSync(npmBinary, ["run", "build"], {
    cwd: runtimeRoot,
    stdio: "inherit",
  });
  if (build.status !== 0) {
    process.exit(build.status ?? 1);
  }

  return existsSync(serverEntrypoint) ? serverEntrypoint : null;
}

function resolveRuntimeEntrypoint(root) {
  const candidates = [
    root,
    readInstallPackRoot(root),
    path.join(os.homedir(), ".datalox", "cache", "datalox-agent-replay"),
  ].filter(Boolean);

  for (const candidate of candidates) {
    const normalized = path.resolve(candidate);
    const entrypoint = ensureRuntimeReady(normalized);
    if (entrypoint) {
      return entrypoint;
    }
  }

  throw new Error("Unable to resolve Datalox Agent Replay replay MCP runtime root for datalox-agent-replay-mcp.js");
}

const entrypoint = resolveRuntimeEntrypoint(repoRoot);

const child = spawn(process.execPath, [entrypoint, ...process.argv.slice(2)], {
  stdio: "inherit",
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 1);
});
