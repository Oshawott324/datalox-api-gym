#!/usr/bin/env node
import { createServer } from "node:http";
import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { runWorldTask, toolNameToModelName } from "./run-world-task.mjs";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const envRoot = path.resolve(scriptDir, "..");
const repoRoot = path.resolve(envRoot, "../..");
const defaultWorldPath = path.join(envRoot, "world.spec.json");
const defaultTaskIds = [
  "flowcyto-gating-qc-success",
  "molecule-primer-validation-001",
  "fastq-qc-nanopore-fail-001",
];

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const worldPath = path.resolve(typeof args.world === "string" ? args.world : defaultWorldPath);
  const taskIds = parseTaskIds(args["task-id"] ?? args.tasks) ?? defaultTaskIds;
  const outRoot = path.resolve(typeof args.out === "string" ? args.out : path.join(envRoot, "runs", "world-smoke"));
  const results = [];

  for (const taskId of taskIds) {
    const taskDir = await findTaskDir({ worldPath, taskId });
    const observations = await readJsonl(path.join(taskDir, "tools", "tool-observations.jsonl"));
    const finalAnswer = await readJson(path.join(taskDir, "verifier", "expected.pass.json"));
    const { server, baseUrl } = await startSmokeServer({ observations, finalAnswer });
    try {
      const result = await runWorldTask({
        worldPath,
        taskId,
        model: "deterministic-world-smoke-agent",
        baseUrl,
        apiKey: "smoke-token",
        outDir: path.join(outRoot, taskId),
        maxSteps: observations.length + 2,
        now: "2026-06-04T00:00:00.000Z",
        runId: `world-smoke-${taskId}`,
      });
      results.push({
        task_id: taskId,
        ok: result.ok,
        stop_reason: result.run.stop_reason,
        tool_call_count: result.run.tool_call_count,
        verifier_passed: result.run.verifier_passed,
        out_dir: path.relative(repoRoot, result.outDir),
      });
    } finally {
      await closeServer(server);
    }
  }

  const failed = results.filter((result) => !result.ok);
  process.stdout.write(`${JSON.stringify({
    ok: failed.length === 0,
    world: path.relative(repoRoot, worldPath),
    out_root: path.relative(repoRoot, outRoot),
    tasks: results,
  }, null, 2)}\n`);
  if (failed.length > 0) process.exitCode = 1;
}

async function startSmokeServer({ observations, finalAnswer }) {
  const server = createServer((request, response) => {
    void handleSmokeRequest({ request, response, observations, finalAnswer }).catch((error) => {
      response.writeHead(500, { "content-type": "application/json" });
      response.end(JSON.stringify({ error: error instanceof Error ? error.message : String(error) }));
    });
  });
  await new Promise((resolve) => {
    server.listen(0, "127.0.0.1", resolve);
  });
  const address = server.address();
  if (address === null || typeof address === "string") throw new Error("Expected TCP server address.");
  return {
    server,
    baseUrl: `http://127.0.0.1:${address.port}/v1`,
  };
}

async function handleSmokeRequest({ request, response, observations, finalAnswer }) {
  if (request.method !== "POST" || request.url !== "/v1/chat/completions") {
    response.writeHead(404, { "content-type": "application/json" });
    response.end(JSON.stringify({ error: "not_found" }));
    return;
  }
  const body = await readRequestJson(request);
  const toolMessages = Array.isArray(body.messages) ? body.messages.filter((message) => message.role === "tool") : [];
  const next = observations[toolMessages.length];
  response.writeHead(200, { "content-type": "application/json" });
  if (next) {
    response.end(JSON.stringify({
      choices: [
        {
          finish_reason: "tool_calls",
          message: {
            role: "assistant",
            content: null,
            tool_calls: [
              {
                id: `call_${String(next.sequence_index).padStart(3, "0")}_${toolNameToModelName(next.tool_name)}`,
                type: "function",
                function: {
                  name: toolNameToModelName(next.tool_name),
                  arguments: JSON.stringify(next.request),
                },
              },
            ],
          },
        },
      ],
    }));
    return;
  }
  response.end(JSON.stringify({
    choices: [
      {
        finish_reason: "stop",
        message: {
          role: "assistant",
          content: JSON.stringify(finalAnswer),
        },
      },
    ],
  }));
}

async function findTaskDir({ worldPath, taskId }) {
  const world = await readJson(worldPath);
  const worldRoot = path.dirname(worldPath);
  const roots = Array.isArray(world.task_roots) && world.task_roots.length > 0 ? world.task_roots : ["families"];
  for (const root of roots) {
    const taskSpecPaths = await findFiles(path.resolve(worldRoot, root), "task.spec.json");
    for (const taskSpecPath of taskSpecPaths) {
      const spec = await readJson(taskSpecPath);
      if (spec.task_id === taskId) return path.dirname(taskSpecPath);
    }
  }
  throw new Error(`Task ${taskId} not found in ${worldPath}.`);
}

async function findFiles(root, fileName) {
  const entries = await fs.readdir(root, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const fullPath = path.join(root, entry.name);
    if (entry.isDirectory()) files.push(...await findFiles(fullPath, fileName));
    if (entry.isFile() && entry.name === fileName) files.push(fullPath);
  }
  return files;
}

async function readRequestJson(request) {
  const chunks = [];
  for await (const chunk of request) {
    chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
  }
  return JSON.parse(Buffer.concat(chunks).toString("utf8"));
}

async function closeServer(server) {
  await new Promise((resolve, reject) => {
    server.close((error) => {
      if (error) reject(error);
      else resolve();
    });
  });
}

async function readJson(filePath) {
  return JSON.parse(await fs.readFile(filePath, "utf8"));
}

async function readJsonl(filePath) {
  const content = await fs.readFile(filePath, "utf8");
  return content.trim().split(/\r?\n/).filter(Boolean).map((line) => JSON.parse(line));
}

function parseTaskIds(value) {
  if (value === undefined || value === true) return undefined;
  const values = Array.isArray(value) ? value : [value];
  return values.flatMap((entry) => entry.split(",")).map((entry) => entry.trim()).filter(Boolean);
}

function parseArgs(argv) {
  const args = { _: [] };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (!arg.startsWith("--")) {
      args._.push(arg);
      continue;
    }
    const key = arg.slice(2);
    const next = argv[index + 1];
    const value = next !== undefined && !next.startsWith("--") ? next : true;
    if (value !== true) index += 1;
    if (args[key] === undefined) args[key] = value;
    else if (Array.isArray(args[key])) args[key].push(value);
    else args[key] = [args[key], value];
  }
  return args;
}

main().catch((error) => {
  process.stderr.write(`${error.stack ?? error.message}\n`);
  process.exitCode = 1;
});
