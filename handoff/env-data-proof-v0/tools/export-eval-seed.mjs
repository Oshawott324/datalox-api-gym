#!/usr/bin/env node
import Ajv from "ajv";
import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const envRoot = path.resolve(scriptDir, "..");
const repoRoot = path.resolve(envRoot, "../..");
const familiesRoot = path.join(envRoot, "families");
const exportsRoot = path.join(envRoot, "exports");
const outPath = process.argv.find((arg) => arg.startsWith("--out="))?.slice("--out=".length)
  ?? path.join(exportsRoot, "eval.seed.jsonl");

async function main() {
  const validateRow = await loadValidator();
  const taskDirs = await findTaskDirs();
  await fs.mkdir(path.dirname(outPath), { recursive: true });

  const rows = [];
  for (const task of taskDirs) {
    const row = await buildEvalRow(task);
    if (!validateRow(row)) {
      throw new Error(`${task.spec.task_id}: eval row failed schema validation ${JSON.stringify(validateRow.errors)}`);
    }
    rows.push(row);
  }

  await fs.writeFile(outPath, `${rows.map((row) => JSON.stringify(row)).join("\n")}\n`, "utf8");
  await writeBaselineCommand();
  process.stdout.write(`${JSON.stringify({ ok: true, out: path.relative(repoRoot, outPath), rows: rows.length }, null, 2)}\n`);
}

async function loadValidator() {
  const schema = await readJson(path.join(envRoot, "schema", "eval-seed-row.schema.json"));
  return new Ajv({ allErrors: true, strict: false }).compile(schema);
}

async function findTaskDirs() {
  const specFiles = await findFiles(familiesRoot, "task.spec.json");
  const entries = [];
  for (const specPath of specFiles.sort()) {
    entries.push({ taskDir: path.dirname(specPath), spec: await readJson(specPath) });
  }
  return entries;
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

async function buildEvalRow({ taskDir, spec }) {
  const observations = await readObservations(taskDir);
  const evidenceIds = [...new Set(observations.flatMap((row) => row.evidence_ids))];
  const contextObservations = observations.map((row) => ({
    sequence_index: row.sequence_index,
    tool_name: row.tool_name,
    evidence_ids: row.evidence_ids,
    workspace_revision: row.workspace_revision,
    observation: summarizeObservation(row.tool_name, row.observation),
  }));
  const compactContext = {
    allowed_tools: spec.allowed_tools,
    forbidden_tools: spec.forbidden_tools,
    expected_tool_path: spec.expected_tool_path,
    observations: contextObservations,
  };
  return {
    schema_version: "agent_native_seed_eval_row.v0",
    task_id: spec.task_id,
    family: spec.family,
    split: spec.split,
    messages: [
      {
        role: "system",
        content: [
          "You are running a post-training seed evaluation.",
          "Return only one JSON object that validates against the shared Datalox task-output schema.",
          "Use only the provided replay observation context and cite evidence_ids exactly.",
          "Do not call live services, invent evidence ids, or describe tool calls that are not in the context.",
        ].join(" "),
      },
      {
        role: "user",
        content: [
          spec.prompt,
          "",
          `Task id: ${spec.task_id}`,
          `Family: ${spec.family}`,
          `Shared output schema: ${spec.output_schema}`,
          `Family output schema: ${spec.family_output_schema}`,
          "",
          "Replay observation context:",
          JSON.stringify(compactContext, null, 2),
        ].join("\n"),
      },
    ],
    output_schema_path: path.relative(repoRoot, path.resolve(taskDir, spec.output_schema)),
    family_output_schema_path: path.relative(repoRoot, path.resolve(taskDir, spec.family_output_schema)),
    verifier_spec_path: path.relative(repoRoot, path.join(taskDir, "verifier", "verifier.spec.json")),
    observation_path: path.relative(repoRoot, path.join(taskDir, "tools", "tool-observations.jsonl")),
    evidence_ids: evidenceIds,
    model_context: compactContext,
  };
}

function summarizeObservation(toolName, observation) {
  if (observation?.ok === false) return { ok: false, errors: observation.errors ?? observation.error ?? observation };
  if (toolName === "get_plot_context") {
    return pick(observation, ["ok", "workspacePath", "revision", "sampleId", "x", "y", "bounds", "previewSummary", "recommendedGate", "nextAction"]);
  }
  if (toolName === "open_fcs") {
    return { ...pick(observation, ["ok", "workspacePath", "sampleId", "sourceKind", "revision", "recommendedViews"]), channels: observation.channels?.map(({ name, marker }) => ({ name, marker })) };
  }
  if (["compute_gate_stats", "validate_gate_qc", "submit_report"].includes(toolName)) {
    return pick(observation, ["ok", "workspacePath", "sampleId", "gateId", "revision", "evidenceRef", "stats", "validation", "errors", "reportId"]);
  }
  if (["open_sequence", "get_sequence_context", "upsert_feature", "upsert_primer", "find_restriction_sites", "simulate_digest", "simulate_pcr", "validate_workspace"].includes(toolName)) {
    return summarizeMoleculeObservation(observation);
  }
  return pruneLargeArrays(observation);
}

function summarizeMoleculeObservation(observation) {
  const data = pruneLargeArrays(observation.data ?? {});
  if (data.sequence) data.sequence = `[${data.sequence.length} bp sequence omitted]`;
  return {
    ok: observation.ok,
    tool: observation.tool,
    workspacePath: observation.workspacePath,
    revision: observation.revision,
    data,
  };
}

function pruneLargeArrays(value) {
  if (Array.isArray(value)) {
    if (value.length > 24) return { omitted_array_length: value.length };
    return value.map(pruneLargeArrays);
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, entry]) => [key, pruneLargeArrays(entry)]));
  }
  return value;
}

function pick(value, keys) {
  return Object.fromEntries(keys.filter((key) => value?.[key] !== undefined).map((key) => [key, pruneLargeArrays(value[key])]));
}

async function readObservations(taskDir) {
  const content = await fs.readFile(path.join(taskDir, "tools", "tool-observations.jsonl"), "utf8");
  return content.trim().split(/\r?\n/).filter(Boolean).map((line) => JSON.parse(line));
}

async function writeBaselineCommand() {
  const commandPath = path.join(exportsRoot, "eval_command.md");
  const content = `# Env Data Proof v0 Eval Command

Primary model-team baseline command:

\`\`\`bash
node handoff/env-data-proof-v0/tools/run-seed-baseline.mjs \\
  --input handoff/env-data-proof-v0/exports/eval.seed.jsonl \\
  --out handoff/env-data-proof-v0/exports/eval.baseline.jsonl \\
  --mode openai-compatible \\
  --model Qwen/Qwen2.5-1.5B-Instruct \\
  --base-url http://127.0.0.1:8000/v1 \\
  --api-key token \\
  --min-failures 10
\`\`\`

Local verifier plumbing smoke command, used only when no cheap model endpoint is
available:

\`\`\`bash
node handoff/env-data-proof-v0/tools/run-seed-baseline.mjs \\
  --input handoff/env-data-proof-v0/exports/eval.seed.jsonl \\
  --out handoff/env-data-proof-v0/exports/eval.baseline.smoke.jsonl \\
  --mode verifier-smoke \\
  --model deterministic-weak-baseline \\
  --min-failures 10
\`\`\`
`;
  await fs.mkdir(exportsRoot, { recursive: true });
  await fs.writeFile(commandPath, content, "utf8");
}

async function readJson(filePath) {
  return JSON.parse(await fs.readFile(filePath, "utf8"));
}

main().catch((error) => {
  process.stderr.write(`${error.stack ?? error.message}\n`);
  process.exitCode = 1;
});
