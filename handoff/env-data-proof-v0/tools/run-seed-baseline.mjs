#!/usr/bin/env node
import Ajv from "ajv";
import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { verifyTaskAnswer } from "./verify-seed-answers.mjs";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const envRoot = path.resolve(scriptDir, "..");
const repoRoot = path.resolve(envRoot, "../..");

const options = parseArgs(process.argv.slice(2));
const mode = options.mode ?? "openai-compatible";
const inputPath = path.resolve(options.input ?? path.join(envRoot, "exports", "eval.seed.jsonl"));
const outPath = path.resolve(options.out ?? path.join(envRoot, "exports", "eval.baseline.jsonl"));
const model = options.model ?? "Qwen/Qwen3-1.7B";
const minFailures = Number.parseInt(options["min-failures"] ?? "10", 10);

async function main() {
  if (!["openai-compatible", "verifier-smoke"].includes(mode)) {
    throw new Error(`Unsupported mode ${mode}`);
  }
  if (mode === "openai-compatible" && !options["base-url"]) {
    throw new Error("openai-compatible mode requires --base-url.");
  }

  const validateBaselineRow = await loadBaselineValidator();
  const rows = await readJsonl(inputPath);
  const outputs = [];
  for (const row of rows) {
    const rawAnswer = mode === "verifier-smoke"
      ? await deterministicWeakAnswer(row)
      : await callOpenAICompatible(row);
    const { parsedAnswer, parseError } = parseAnswer(rawAnswer);
    const verifierResult = parsedAnswer
      ? await verifyTaskAnswer({
        taskDir: taskDirFor(row),
        answer: parsedAnswer,
        answerPath: `${path.relative(repoRoot, outPath)}#${row.task_id}`,
      })
      : null;
    const baselineRow = {
      schema_version: "agent_native_seed_baseline_row.v0",
      task_id: row.task_id,
      family: row.family,
      split: row.split,
      mode,
      model,
      answer_text: rawAnswer,
      parsed_answer: parsedAnswer,
      parse_error: parseError,
      verifier_result: verifierResult,
    };
    if (!validateBaselineRow(baselineRow)) {
      throw new Error(`${row.task_id}: baseline row failed schema validation ${JSON.stringify(validateBaselineRow.errors)}`);
    }
    outputs.push(baselineRow);
  }

  await fs.mkdir(path.dirname(outPath), { recursive: true });
  await fs.writeFile(outPath, `${outputs.map((row) => JSON.stringify(row)).join("\n")}\n`, "utf8");

  const parseFailures = outputs.filter((row) => row.parse_error).length;
  const verifierFailures = outputs.filter((row) => row.verifier_result?.passed === false).length;
  const verifierPasses = outputs.filter((row) => row.verifier_result?.passed === true).length;
  const failureCount = parseFailures + verifierFailures;
  const ok = failureCount >= minFailures;
  process.stdout.write(`${JSON.stringify({
    ok,
    mode,
    model,
    input: path.relative(repoRoot, inputPath),
    out: path.relative(repoRoot, outPath),
    tasks: outputs.length,
    parse_failures: parseFailures,
    verifier_failures: verifierFailures,
    verifier_passes: verifierPasses,
    min_failures: minFailures,
  }, null, 2)}\n`);
  if (!ok) process.exitCode = 1;
}

async function loadBaselineValidator() {
  const schema = JSON.parse(await fs.readFile(path.join(envRoot, "schema", "eval-baseline-row.schema.json"), "utf8"));
  return new Ajv({ allErrors: true, strict: false }).compile(schema);
}

async function deterministicWeakAnswer(row) {
  const taskDir = taskDirFor(row);
  const failAnswer = JSON.parse(await fs.readFile(path.join(taskDir, "verifier", "expected.fail.json"), "utf8"));
  return JSON.stringify(failAnswer);
}

async function callOpenAICompatible(row) {
  const baseUrl = options["base-url"].replace(/\/$/, "");
  const apiKey = options["api-key"] ?? "token";
  let response;
  try {
    response = await fetch(`${baseUrl}/chat/completions`, {
      method: "POST",
      headers: {
        "authorization": `Bearer ${apiKey}`,
        "content-type": "application/json",
      },
      body: JSON.stringify({
        model,
        messages: row.messages,
        temperature: Number.parseFloat(options.temperature ?? "0"),
        max_tokens: Number.parseInt(options["max-tokens"] ?? "1600", 10),
        response_format: { type: "json_object" },
      }),
    });
  } catch (error) {
    throw new Error(`Cannot reach OpenAI-compatible model endpoint at ${baseUrl}: ${error.cause?.message ?? error.message}`);
  }
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Model endpoint returned ${response.status}: ${body}`);
  }
  const body = await response.json();
  const content = body.choices?.[0]?.message?.content;
  if (typeof content !== "string") throw new Error("Model endpoint response did not include choices[0].message.content.");
  return content;
}

function parseAnswer(rawAnswer) {
  try {
    return { parsedAnswer: JSON.parse(rawAnswer), parseError: null };
  } catch (error) {
    return { parsedAnswer: null, parseError: error.message };
  }
}

function taskDirFor(row) {
  return path.join(envRoot, "families", row.family, "tasks", row.task_id);
}

async function readJsonl(filePath) {
  const content = await fs.readFile(filePath, "utf8");
  return content.trim().split(/\r?\n/).filter(Boolean).map((line) => JSON.parse(line));
}

function parseArgs(args) {
  const parsed = {};
  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (!arg.startsWith("--")) continue;
    const [key, ...rest] = arg.slice(2).split("=");
    if (rest.length > 0) {
      parsed[key] = rest.join("=");
      continue;
    }
    const next = args[index + 1];
    if (next && !next.startsWith("--")) {
      parsed[key] = next;
      index += 1;
      continue;
    }
    parsed[key] = "true";
  }
  return parsed;
}

main().catch((error) => {
  process.stderr.write(`${error.stack ?? error.message}\n`);
  process.exitCode = 1;
});
