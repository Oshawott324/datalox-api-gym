#!/usr/bin/env node

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { cp, mkdir, readdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { performance } from "node:perf_hooks";
import { fileURLToPath } from "node:url";

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

import {
  readReplayBundleMcpToolCatalogs,
  readReplayBundleToolIoRecords,
} from "../../dist/src/core/replayBundle.js";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, "../..");
const cliPath = path.join(repoRoot, "dist", "src", "cli", "main.js");
const fixturePath = path.join(scriptDir, "fixture-upstream.mjs");
const templateConfigPath = path.join(scriptDir, "datalox.record.json");
const outputRoot = path.join(scriptDir, "output");
const workspaceRoot = path.join(outputRoot, "workspace");
const bundleId = "verified-replay-demo";
const bundlePath = path.join(workspaceRoot, ".datalox", "replay-bundles", bundleId);
const tamperedBundlePath = path.join(outputRoot, "tampered", bundleId);
const upstreamLogPath = path.join(outputRoot, "upstream-calls.jsonl");

const asJson = process.argv.includes("--json");

const recordedCalls = [
  {
    name: "policy_lookup",
    arguments: {
      query: "Beijing taxi reimbursement",
      top_k: 2,
    },
  },
  {
    name: "policy_lookup",
    arguments: {
      query: "Shanghai hotel reimbursement",
      top_k: 1,
    },
  },
  {
    name: "status_ping",
    arguments: {
      label: "recorded",
    },
  },
];

const replayMissCall = {
  name: "status_ping",
  arguments: {
    label: "unrecorded",
  },
};

async function main() {
  const startedAt = performance.now();
  assertBuiltArtifacts();

  await rm(outputRoot, { recursive: true, force: true });
  await mkdir(workspaceRoot, { recursive: true });
  await writeRunConfig();

  logStep("record", "Starting Datalox MCP VCR proxy in record mode.");
  const recordClient = await connectProxy({
    mode: "record",
    configPath: path.join(workspaceRoot, "datalox.record.json"),
  });
  let recordedTools;
  const recordedResults = [];
  try {
    recordedTools = await recordClient.listTools();
    assert.deepEqual(
      recordedTools.tools.map((tool) => tool.name).sort(),
      ["policy_lookup", "status_ping"],
    );
    for (const call of recordedCalls) {
      recordedResults.push(await recordClient.callTool(call));
    }
  } finally {
    await recordClient.close();
  }

  const upstreamLogBeforeReplay = await readJsonLines(upstreamLogPath);
  assert.equal(upstreamLogBeforeReplay.length, recordedCalls.length);

  logStep("pack", `Packing replay bundle ${bundleId}.`);
  const packed = runCliJson([
    "bundle",
    "pack",
    "--repo",
    workspaceRoot,
    "--bundle-id",
    bundleId,
    "--json",
  ]);

  logStep("verify", "Verifying sealed replay bundle.");
  const verified = runCliJson([
    "bundle",
    "verify",
    "--repo",
    workspaceRoot,
    "--bundle",
    bundlePath,
    "--json",
  ]);
  assert.equal(verified.verified, true);

  const records = await readReplayBundleToolIoRecords({ bundlePath });
  const catalogs = await readReplayBundleMcpToolCatalogs({ bundlePath });
  assert.equal(records.length, recordedCalls.length);
  assert.equal(catalogs.length, 1);

  await rm(path.join(workspaceRoot, ".datalox", "tool-io"), { recursive: true, force: true });
  await rm(path.join(workspaceRoot, ".datalox", "mcp-tool-catalogs"), { recursive: true, force: true });

  logStep("replay", "Starting replay from bundle with upstream off.");
  const replayClient = await connectProxy({
    mode: "replay",
    bundlePath,
  });
  let replayMiss;
  let replayHits = 0;
  try {
    const replayTools = await replayClient.listTools();
    assert.deepEqual(replayTools, recordedTools);
    for (const [index, call] of recordedCalls.entries()) {
      const replayed = await replayClient.callTool(call);
      assert.deepEqual(replayed, recordedResults[index]);
      replayHits += 1;
    }
    replayMiss = await replayClient.callTool(replayMissCall);
    assert.equal(replayMiss.isError, true);
    assert.equal(replayMiss.structuredContent.error.code, "replay_miss");
  } finally {
    await replayClient.close();
  }

  const upstreamLogAfterReplay = await readJsonLines(upstreamLogPath);
  assert.deepEqual(upstreamLogAfterReplay, upstreamLogBeforeReplay);

  logStep("tamper", "Tampering with a bundle copy and verifying failure.");
  await cp(bundlePath, tamperedBundlePath, { recursive: true });
  await tamperWithFirstToolRecord(tamperedBundlePath);
  const tamperedVerify = runCli([
    "bundle",
    "verify",
    "--repo",
    workspaceRoot,
    "--bundle",
    tamperedBundlePath,
    "--json",
  ], { expectFailure: true });

  const elapsedMs = Math.round(performance.now() - startedAt);
  const summary = {
    status: "passed",
    bundle_id: bundleId,
    bundle_path: bundlePath,
    tool_record_count: records.length,
    mcp_tool_catalog_count: catalogs.length,
    replay_hit_count: replayHits,
    replay_miss_count: 1,
    upstream_call_count_before_replay: upstreamLogBeforeReplay.length,
    upstream_call_count_after_replay: upstreamLogAfterReplay.length,
    upstream_calls_during_replay: upstreamLogAfterReplay.length - upstreamLogBeforeReplay.length,
    replay_miss: replayMiss.structuredContent.error,
    tamper_detected: tamperedVerify.status !== 0,
    tamper_error: firstLine(tamperedVerify.stderr),
    elapsed_ms: elapsedMs,
    output_root: outputRoot,
    packed_bundle_path: packed.bundlePath,
  };

  assert.equal(summary.upstream_calls_during_replay, 0);
  assert.equal(summary.tamper_detected, true);

  if (asJson) {
    process.stdout.write(`${JSON.stringify(summary, null, 2)}\n`);
    return;
  }

  logStep("done", "Verified replay quickstart passed.");
  process.stdout.write(`${JSON.stringify(summary, null, 2)}\n`);
}

function assertBuiltArtifacts() {
  if (!existsSync(cliPath)) {
    throw new Error("Build artifacts are missing. Run `npm run build` or `npm run demo:verified-replay`.");
  }
  if (!existsSync(fixturePath)) {
    throw new Error(`Missing fixture upstream: ${fixturePath}`);
  }
}

async function writeRunConfig() {
  const template = JSON.parse(await readFile(templateConfigPath, "utf8"));
  const config = {
    ...template,
    upstream: {
      ...template.upstream,
      cwd: scriptDir,
      env: {
        ...(template.upstream.env ?? {}),
        DATALOX_VERIFIED_REPLAY_UPSTREAM_LOG: upstreamLogPath,
      },
    },
  };
  await writeFile(
    path.join(workspaceRoot, "datalox.record.json"),
    `${JSON.stringify(config, null, 2)}\n`,
    "utf8",
  );
}

async function connectProxy(input) {
  const args = [
    cliPath,
    "proxy",
    "--mode",
    input.mode,
    "--repo",
    workspaceRoot,
  ];
  if (input.configPath) {
    args.push("--config", input.configPath);
  }
  if (input.bundlePath) {
    args.push("--bundle", input.bundlePath);
  }

  const client = new Client(
    { name: "datalox-verified-replay-quickstart", version: "1.0.0" },
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

function runCliJson(args) {
  const result = runCli(args);
  try {
    return JSON.parse(result.stdout);
  } catch (error) {
    throw new Error(`CLI did not return JSON for ${args.join(" ")}: ${result.stdout}`, { cause: error });
  }
}

function runCli(args, options = {}) {
  const result = spawnSync(process.execPath, [cliPath, ...args], {
    cwd: repoRoot,
    encoding: "utf8",
  });
  const expectFailure = options.expectFailure === true;
  if (!expectFailure && result.status !== 0) {
    throw new Error([
      `CLI failed: node ${[cliPath, ...args].join(" ")}`,
      `stdout: ${result.stdout}`,
      `stderr: ${result.stderr}`,
    ].join("\n"));
  }
  if (expectFailure && result.status === 0) {
    throw new Error(`CLI unexpectedly succeeded: node ${[cliPath, ...args].join(" ")}`);
  }
  return result;
}

async function tamperWithFirstToolRecord(targetBundlePath) {
  const toolIoDir = path.join(targetBundlePath, "tool-io");
  const [firstToolRecord] = (await readdir(toolIoDir)).sort();
  if (!firstToolRecord) {
    throw new Error(`No tool I/O records in ${toolIoDir}`);
  }
  const targetPath = path.join(toolIoDir, firstToolRecord);
  const record = JSON.parse(await readFile(targetPath, "utf8"));
  record.call_id = `${record.call_id}-tampered`;
  await writeFile(targetPath, `${JSON.stringify(record, null, 2)}\n`, "utf8");
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

function logStep(label, message) {
  if (asJson) {
    return;
  }
  process.stdout.write(`[${label}] ${message}\n`);
}

function firstLine(value) {
  return value.trim().split("\n")[0] ?? "";
}

main().catch((error) => {
  const message = error instanceof Error ? error.stack ?? error.message : String(error);
  process.stderr.write(`${message}\n`);
  process.exit(1);
});
