#!/usr/bin/env node

import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, mkdtemp, readFile, rename, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import assert from "node:assert/strict";

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

import {
  packReplayBundle,
  readReplayBundleMcpToolCatalogs,
  readReplayBundleToolIoRecords,
  verifyReplayBundle,
} from "../../dist/src/core/replayBundle.js";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, "../..");
const cliPath = path.join(repoRoot, "dist", "src", "cli", "main.js");
const fixturePath = path.join(scriptDir, "fixtures", "reference-upstream.mjs");
const backupRoot = path.join(repoRoot, ".datalox", `.reference-bundle-backup-${process.pid}`);
const sourceRoots = [
  ".datalox/events",
  ".datalox/tool-io",
  ".datalox/mcp-tool-catalogs",
];

const bundleSpecs = [
  {
    id: "ref-mcp-success",
    title: "Reference MCP Success Replay Bundle",
    task: {
      prompt: "Record and replay one successful deterministic MCP tool call.",
      domains: ["mcp", "reference"],
      workflows: ["tool_io_replay"],
    },
    calls: [
      {
        name: "policy_lookup",
        arguments: {
          query: "Beijing taxi reimbursement limit",
          top_k: 2,
        },
      },
    ],
  },
  {
    id: "ref-mcp-repeated-call",
    title: "Reference MCP Repeated-Call Replay Bundle",
    task: {
      prompt: "Record and replay two identical MCP tool calls by sequence index.",
      domains: ["mcp", "reference"],
      workflows: ["tool_io_replay", "sequence_index"],
    },
    calls: [
      {
        name: "policy_lookup",
        arguments: {
          query: "identical policy lookup",
          top_k: 2,
        },
      },
      {
        name: "policy_lookup",
        arguments: {
          query: "identical policy lookup",
          top_k: 2,
        },
      },
    ],
  },
  {
    id: "ref-mcp-error-observation",
    title: "Reference MCP Error Observation Replay Bundle",
    task: {
      prompt: "Record and replay one deterministic agent-visible MCP error observation.",
      domains: ["mcp", "reference"],
      workflows: ["tool_io_replay", "error_observation"],
    },
    calls: [
      {
        name: "validation_error",
        arguments: {
          reason: "visible upstream validation",
        },
      },
    ],
  },
];

async function main() {
  assertBuiltArtifacts();
  if (existsSync(backupRoot)) {
    throw new Error(`Backup directory already exists: ${backupRoot}`);
  }

  const tempRoot = await mkdtemp(path.join(tmpdir(), "datalox-reference-bundles-"));
  await hideSourceRoots();
  try {
    const results = [];
    for (const spec of bundleSpecs) {
      results.push(await buildBundle(spec, tempRoot));
    }
    process.stdout.write(`${JSON.stringify({ generated: results }, null, 2)}\n`);
  } finally {
    await rm(path.join(repoRoot, ".datalox", "tool-io"), { recursive: true, force: true });
    await rm(path.join(repoRoot, ".datalox", "mcp-tool-catalogs"), { recursive: true, force: true });
    await restoreSourceRoots();
    await rm(tempRoot, { recursive: true, force: true });
  }
}

function assertBuiltArtifacts() {
  if (!existsSync(cliPath)) {
    throw new Error("Build artifacts are missing. Run npm run build first.");
  }
  if (!existsSync(fixturePath)) {
    throw new Error(`Reference upstream fixture is missing: ${fixturePath}`);
  }
}

async function hideSourceRoots() {
  await mkdir(backupRoot, { recursive: false });
  for (const relativePath of sourceRoots) {
    const absolutePath = path.join(repoRoot, relativePath);
    if (!existsSync(absolutePath)) {
      continue;
    }
    await mkdir(path.dirname(path.join(backupRoot, relativePath)), { recursive: true });
    await rename(absolutePath, path.join(backupRoot, relativePath));
  }
}

async function restoreSourceRoots() {
  try {
    for (const relativePath of sourceRoots) {
      const backupPath = path.join(backupRoot, relativePath);
      const absolutePath = path.join(repoRoot, relativePath);
      if (!existsSync(backupPath)) {
        continue;
      }
      await rm(absolutePath, { recursive: true, force: true });
      await mkdir(path.dirname(absolutePath), { recursive: true });
      await rename(backupPath, absolutePath);
    }
  } finally {
    await rm(backupRoot, { recursive: true, force: true });
  }
}

async function buildBundle(spec, tempRoot) {
  const bundlePath = path.join(repoRoot, ".datalox", "replay-bundles", spec.id);
  const configPath = path.join(tempRoot, `${spec.id}.proxy.json`);
  const upstreamLogPath = path.join(tempRoot, `${spec.id}.upstream.jsonl`);

  await rm(bundlePath, { recursive: true, force: true });
  await rm(path.join(repoRoot, ".datalox", "tool-io"), { recursive: true, force: true });
  await rm(path.join(repoRoot, ".datalox", "mcp-tool-catalogs"), { recursive: true, force: true });
  await writeProxyConfig(configPath, spec, upstreamLogPath);

  const recordClient = await connectProxy({
    mode: "record",
    configPath,
  });
  const recordedResults = [];
  let recordedTools;
  try {
    recordedTools = await recordClient.listTools();
    assert.deepEqual(
      recordedTools.tools.map((tool) => tool.name),
      ["policy_lookup", "validation_error"],
    );
    for (const call of spec.calls) {
      recordedResults.push(await recordClient.callTool({
        name: call.name,
        arguments: call.arguments,
      }));
    }
  } finally {
    await recordClient.close();
  }

  const upstreamLogBeforeReplay = await readJsonLines(upstreamLogPath);
  assert.equal(upstreamLogBeforeReplay.length, spec.calls.length);

  const packed = await packReplayBundle({
    repoPath: repoRoot,
    sourceRepoPath: ".",
    bundleId: spec.id,
    title: spec.title,
    task: spec.task,
    export: {
      allowed: true,
      redaction: "none_needed",
      approval_id: "reference-public",
    },
  });
  const verified = await verifyReplayBundle({
    repoPath: repoRoot,
    bundlePath: packed.bundlePath,
  });

  const records = await readReplayBundleToolIoRecords({
    repoPath: repoRoot,
    bundlePath: packed.bundlePath,
  });
  const catalogs = await readReplayBundleMcpToolCatalogs({
    repoPath: repoRoot,
    bundlePath: packed.bundlePath,
  });
  assert.equal(records.length, spec.calls.length);
  assert.equal(catalogs.length, 1);
  assert.equal(packed.manifest.source.repo_path, ".");
  assert.equal(packed.manifest.source.turn_event_paths.length, 0);
  assert.equal(packed.manifest.replay.tool_record_count, spec.calls.length);
  assert.equal(packed.manifest.export.allowed, true);

  if (spec.id === "ref-mcp-repeated-call") {
    assert.equal(new Set(records.map((record) => record.request_hash)).size, 1);
    assert.deepEqual(records.map((record) => record.sequence_index), [0, 1]);
  }
  if (spec.id === "ref-mcp-error-observation") {
    assert.equal(records[0].observation.status, "ok");
    assert.equal(records[0].observation.content.isError, true);
  }

  await rm(path.join(repoRoot, ".datalox", "tool-io"), { recursive: true, force: true });
  await rm(path.join(repoRoot, ".datalox", "mcp-tool-catalogs"), { recursive: true, force: true });

  const replayClient = await connectProxy({
    mode: "replay",
    bundlePath: packed.bundlePath,
  });
  try {
    const replayTools = await replayClient.listTools();
    assert.deepEqual(replayTools, recordedTools);
    for (const [index, call] of spec.calls.entries()) {
      const replayResult = await replayClient.callTool({
        name: call.name,
        arguments: call.arguments,
      });
      assert.deepEqual(replayResult, recordedResults[index]);
    }
  } finally {
    await replayClient.close();
  }

  const upstreamLogAfterReplay = await readJsonLines(upstreamLogPath);
  assert.deepEqual(upstreamLogAfterReplay, upstreamLogBeforeReplay);

  return {
    id: spec.id,
    bundlePath: packed.bundlePath,
    checkedFiles: verified.checkedFiles,
    toolRecords: records.length,
    mcpToolCatalogs: catalogs.length,
  };
}

async function writeProxyConfig(configPath, spec, upstreamLogPath) {
  await writeFile(configPath, `${JSON.stringify({
    schema_version: "datalox_replay_proxy_config.v1",
    upstream: {
      command: "node",
      args: [path.relative(repoRoot, fixturePath)],
      env: {
        DATALOX_REFERENCE_BUNDLE_ID: spec.id,
        DATALOX_REFERENCE_UPSTREAM_LOG: upstreamLogPath,
      },
    },
    record: {
      session_id: `${spec.id}-session`,
      turn_id: `${spec.id}-turn`,
      export: {
        allowed: true,
        redaction: "none_needed",
        approval_id: "reference-public",
      },
    },
  }, null, 2)}\n`, "utf8");
}

async function connectProxy(input) {
  const args = [
    cliPath,
    "proxy",
    "--mode",
    input.mode,
    "--repo",
    repoRoot,
  ];
  if (input.configPath) {
    args.push("--config", input.configPath);
  }
  if (input.bundlePath) {
    args.push("--bundle", input.bundlePath);
  }
  const client = new Client(
    { name: "datalox-reference-bundle-generator", version: "1.0.0" },
    { capabilities: {} },
  );
  await client.connect(new StdioClientTransport({
    command: process.execPath,
    args,
    cwd: repoRoot,
    stderr: "pipe",
  }));
  return client;
}

async function readJsonLines(filePath) {
  if (!existsSync(filePath)) {
    return [];
  }
  const raw = await readFile(filePath, "utf8");
  return raw.trim().length === 0
    ? []
    : raw.trim().split("\n").map((line) => JSON.parse(line));
}

const npmBuild = process.argv.includes("--build")
  ? spawnSync("npm", ["run", "build"], {
    cwd: repoRoot,
    encoding: "utf8",
    stdio: "inherit",
  })
  : null;

if (npmBuild && npmBuild.status !== 0) {
  process.exit(npmBuild.status ?? 1);
}

main().catch(async (error) => {
  await restoreSourceRoots().catch(() => {});
  const message = error instanceof Error ? error.stack ?? error.message : String(error);
  process.stderr.write(`${message}\n`);
  process.exit(1);
});
