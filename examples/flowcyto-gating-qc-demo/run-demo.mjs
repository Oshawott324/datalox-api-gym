#!/usr/bin/env node

import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { createReplayToolRuntime } from "../../dist/src/core/run/replayToolRuntime.js";

import { startFakeOpenAiServer } from "./fake-openai-server.mjs";
import { writeDemoReport } from "./report.mjs";

const FIXTURE_SET_REF = "flowcyto-gating-qc-basic@2026-06.0";
const PROMPT = "Gate the main FSC/SSC population in the FlowCyto replay world, compute stats, validate QC, and submit an agent-authored report with caveats.";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, "../..");
const cliPath = path.join(repoRoot, "dist", "src", "cli", "main.js");
const defaultOutputRoot = path.join(scriptDir, "output");

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const catalogPath = options.catalog;
  const outputRoot = path.resolve(options.out ?? defaultOutputRoot);
  const cacheRoot = path.join(outputRoot, "cache");
  const runDir = path.join(outputRoot, "run");
  const sftPath = path.join(outputRoot, "flowcyto-qc.sft.jsonl");
  const terminalLog = [];

  assertBuiltArtifacts();
  assert.equal(typeof catalogPath, "string", "run-demo requires --catalog <catalog.json>");
  if (!existsSync(catalogPath)) {
    throw new Error(`Catalog not found: ${catalogPath}`);
  }

  await rm(outputRoot, { recursive: true, force: true });
  await mkdir(outputRoot, { recursive: true });

  const fakeModel = await startFakeOpenAiServer();
  try {
    const installResult = await runCliJson({
      args: [
        "fixture-sets",
        "install",
        FIXTURE_SET_REF,
        "--catalog",
        catalogPath,
        "--cache-root",
        cacheRoot,
        "--force",
        "--json",
      ],
      terminalLog,
    });
    await writeJsonFile(path.join(outputRoot, "install.json"), installResult);

    const runResult = await runCliJson({
      args: [
        "run",
        "--fixture-set",
        FIXTURE_SET_REF,
        "--cache-root",
        cacheRoot,
        "--base-url",
        fakeModel.baseUrl,
        "--model",
        "fake-cheap-flowcyto",
        "--api-key",
        "token",
        "--prompt",
        PROMPT,
        "--out",
        runDir,
        "--max-steps",
        "8",
        "--json",
      ],
      terminalLog,
    });
    await writeJsonFile(path.join(outputRoot, "run-result.json"), runResult);

    const exportResult = await runCliJson({
      args: [
        "export",
        "sft",
        "--run",
        runDir,
        "--out",
        sftPath,
        "--json",
      ],
      terminalLog,
    });
    await writeJsonFile(path.join(outputRoot, "export.json"), exportResult);

    const run = JSON.parse(await readFile(path.join(runDir, "run.json"), "utf8"));
    const replayMissProof = await proveReplayMiss({ cacheRoot });
    await writeJsonFile(path.join(outputRoot, "replay-miss-proof.json"), replayMissProof);

    const sftLines = (await readFile(sftPath, "utf8"))
      .trim()
      .split("\n")
      .filter(Boolean);
    assert.equal(run.stop_reason, "final_answer");
    assert.equal(exportResult.frameCount, 1);
    assert.equal(sftLines.length, 1);
    assert.equal(replayMissProof.replayMiss?.code, "replay_miss");
    assert.equal(replayMissProof.replayMiss?.liveFallback, false);

    await writeFile(path.join(outputRoot, "terminal.log"), terminalLog.join("\n"), "utf8");
    await writeDemoReport({
      outPath: path.join(outputRoot, "demo-report.html"),
      fixtureSetRef: FIXTURE_SET_REF,
      installResult,
      runResult,
      run,
      exportResult,
      replayMissProof,
      artifactPaths: {
        runPath: "run/run.json",
        transcriptPath: "run/transcript.jsonl",
        sftPath: "flowcyto-qc.sft.jsonl",
        replayMissPath: "replay-miss-proof.json",
        terminalLogPath: "terminal.log",
      },
    });

    process.stdout.write(`${JSON.stringify({
      status: "passed",
      fixtureSetRef: FIXTURE_SET_REF,
      outputRoot,
      reportPath: path.join(outputRoot, "demo-report.html"),
      runPath: path.join(runDir, "run.json"),
      transcriptPath: path.join(runDir, "transcript.jsonl"),
      sftPath,
      stopReason: run.stop_reason,
      stepCount: run.steps.length,
      frameCount: exportResult.frameCount,
      replayMiss: replayMissProof.replayMiss,
      fakeModelRequestCount: fakeModel.requests.length,
    }, null, 2)}\n`);
  } finally {
    await fakeModel.close();
  }
}

function assertBuiltArtifacts() {
  if (!existsSync(cliPath)) {
    throw new Error("Build artifacts are missing. Run `npm run build` first.");
  }
}

async function proveReplayMiss(input) {
  const runtime = await createReplayToolRuntime({
    cacheRoot: input.cacheRoot,
    fixtureSetRef: FIXTURE_SET_REF,
  });
  const call = {
    name: "compute_gate_stats",
    arguments: {
      workspace_path: "fixture://flowcyto-gating-qc-basic/workspace/flowcyto.workspace.json",
      sample_id: "sample_001",
      gate_id: "unrecorded_gate",
    },
  };
  const result = await runtime.callTool(call);
  return {
    toolName: call.name,
    arguments: call.arguments,
    observation: result.observation,
    replayMiss: result.replayMiss,
    activeFixtureRefs: runtime.activeFixtureRefs,
  };
}

async function runCliJson(input) {
  const result = await runCli(input);
  try {
    return JSON.parse(result.stdout);
  } catch (error) {
    throw new Error(`CLI did not return JSON for ${input.args.join(" ")}: ${result.stdout}`, { cause: error });
  }
}

async function runCli(input) {
  const command = process.execPath;
  const args = [cliPath, ...input.args];
  input.terminalLog.push(`$ ${[command, ...args].map(shellQuote).join(" ")}`);
  const result = await new Promise((resolve) => {
    const child = spawn(command, args, {
      cwd: repoRoot,
      stdio: ["ignore", "pipe", "pipe"],
    });
    const stdout = [];
    const stderr = [];
    child.stdout.on("data", (chunk) => stdout.push(chunk));
    child.stderr.on("data", (chunk) => stderr.push(chunk));
    child.on("close", (status) => {
      resolve({
        status,
        stdout: Buffer.concat(stdout).toString("utf8"),
        stderr: Buffer.concat(stderr).toString("utf8"),
      });
    });
  });
  input.terminalLog.push(result.stdout.trimEnd());
  if (result.stderr.trim().length > 0) {
    input.terminalLog.push(result.stderr.trimEnd());
  }
  input.terminalLog.push("");
  if (result.status !== 0) {
    throw new Error(`CLI command failed with status ${result.status}: ${input.args.join(" ")}\n${result.stderr}`);
  }
  return result;
}

function parseArgs(args) {
  const parsed = {};
  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (arg === "--catalog" || arg === "--out") {
      const value = args[index + 1];
      if (value === undefined || value.startsWith("--")) {
        throw new Error(`${arg} requires a value.`);
      }
      parsed[arg.slice(2)] = value;
      index += 1;
      continue;
    }
    if (arg === "--help") {
      process.stdout.write([
        "Usage:",
        "  node examples/flowcyto-gating-qc-demo/run-demo.mjs --catalog <catalog.json> [--out <dir>]",
        "",
      ].join("\n"));
      process.exit(0);
    }
    throw new Error(`Unknown argument: ${arg}`);
  }
  return parsed;
}

async function writeJsonFile(filePath, value) {
  await mkdir(path.dirname(filePath), { recursive: true });
  await writeFile(filePath, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

function shellQuote(value) {
  if (/^[A-Za-z0-9_./:@=-]+$/u.test(value)) {
    return value;
  }
  return `'${value.replaceAll("'", "'\"'\"'")}'`;
}

main().catch((error) => {
  process.stderr.write(`${error.stack ?? error.message}\n`);
  process.exit(1);
});
