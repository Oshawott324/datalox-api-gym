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
const splitOutPath = process.argv.find((arg) => arg.startsWith("--split-out="))?.slice("--split-out=".length)
  ?? path.join(exportsRoot, "split.mcp-seed-v0.json");
const toolEnvEvalOutPath = process.argv.find((arg) => arg.startsWith("--tool-env-out="))?.slice("--tool-env-out=".length)
  ?? path.join(exportsRoot, "eval.tool_env.seed.jsonl");
const toolEvidenceSftOutPath = process.argv.find((arg) => arg.startsWith("--tool-evidence-out="))?.slice("--tool-evidence-out=".length)
  ?? path.join(exportsRoot, "sft.tool_evidence.seed.jsonl");
const toolMessageSftOutPath = process.argv.find((arg) => arg.startsWith("--tool-message-out="))?.slice("--tool-message-out=".length)
  ?? path.join(exportsRoot, "sft.tool_messages.seed.jsonl");

const splitAssignments = new Map(Object.entries({
  "flowcyto-gating-qc-success": "train",
  "flowcyto-existing-gate-edit-revision": "train",
  "molecule-genbank-feature-annotation-001": "train",
  "molecule-restriction-digest-001": "train",
  "molecule-pcr-simulation-001": "train",
  "molecule-orf-translation-annotation": "train",
  "protein-binding-site-annotation": "train",
  "protein-view-revision-safe-style": "train",
  "flowcyto-gating-qc-stale-revision-failure": "dev",
  "molecule-export-genbank-after-edit": "dev",
  "flowcyto-gating-qc-report-validation-failure": "test",
  "protein-ligand-contact-scene-repair": "test",
}));

async function main() {
  const validateEvalRow = await loadSchemaValidator("eval-seed-row.schema.json");
  const validateToolEnvEvalRow = await loadSchemaValidator("tool-env-eval-row.schema.json");
  const validateToolEvidenceSftRow = await loadSchemaValidator("tool-evidence-sft-row.schema.json");
  const validateToolMessageSftRow = await loadSchemaValidator("tool-message-sft-row.schema.json");
  const validateSplitMetadata = await loadSchemaValidator("split-metadata.schema.json");
  const taskDirs = await findTaskDirs();
  await fs.mkdir(exportsRoot, { recursive: true });

  const rows = [];
  const toolEnvEvalRows = [];
  const toolEvidenceSftRows = [];
  const toolMessageSftRows = [];
  for (const task of taskDirs) {
    const row = await buildEvalRow(task);
    if (!validateEvalRow(row)) {
      throw new Error(`${task.spec.task_id}: eval row failed schema validation ${JSON.stringify(validateEvalRow.errors)}`);
    }
    rows.push(row);

    const toolEnvEvalRow = buildToolEnvEvalRow(task);
    if (!validateToolEnvEvalRow(toolEnvEvalRow)) {
      throw new Error(`${task.spec.task_id}: tool-env eval row failed schema validation ${JSON.stringify(validateToolEnvEvalRow.errors)}`);
    }
    toolEnvEvalRows.push(toolEnvEvalRow);

    if (row.split === "train") {
      const toolEvidenceSftRow = await buildToolEvidenceSftRow(task, row);
      if (!validateToolEvidenceSftRow(toolEvidenceSftRow)) {
        throw new Error(`${task.spec.task_id}: tool-evidence SFT row failed schema validation ${JSON.stringify(validateToolEvidenceSftRow.errors)}`);
      }
      toolEvidenceSftRows.push(toolEvidenceSftRow);

      const toolMessageSftRow = buildToolMessageSftRow(toolEvidenceSftRow);
      if (!validateToolMessageSftRow(toolMessageSftRow)) {
        throw new Error(`${task.spec.task_id}: tool-message SFT row failed schema validation ${JSON.stringify(validateToolMessageSftRow.errors)}`);
      }
      toolMessageSftRows.push(toolMessageSftRow);
    }
  }

  const splitMetadata = buildSplitMetadata(taskDirs);
  if (!validateSplitMetadata(splitMetadata)) {
    throw new Error(`split metadata failed schema validation ${JSON.stringify(validateSplitMetadata.errors)}`);
  }

  await fs.writeFile(outPath, `${rows.map((row) => JSON.stringify(row)).join("\n")}\n`, "utf8");
  await fs.writeFile(toolEnvEvalOutPath, `${toolEnvEvalRows.map((row) => JSON.stringify(row)).join("\n")}\n`, "utf8");
  await fs.writeFile(toolEvidenceSftOutPath, `${toolEvidenceSftRows.map((row) => JSON.stringify(row)).join("\n")}\n`, "utf8");
  await fs.writeFile(toolMessageSftOutPath, `${toolMessageSftRows.map((row) => JSON.stringify(row)).join("\n")}\n`, "utf8");
  await fs.writeFile(splitOutPath, `${JSON.stringify(splitMetadata, null, 2)}\n`, "utf8");
  await writeBaselineCommand();
  process.stdout.write(`${JSON.stringify({
    ok: true,
    eval_out: path.relative(repoRoot, outPath),
    tool_env_eval_out: path.relative(repoRoot, toolEnvEvalOutPath),
    tool_evidence_sft_out: path.relative(repoRoot, toolEvidenceSftOutPath),
    tool_message_sft_out: path.relative(repoRoot, toolMessageSftOutPath),
    split_out: path.relative(repoRoot, splitOutPath),
    eval_rows: rows.length,
    tool_env_eval_rows: toolEnvEvalRows.length,
    tool_evidence_sft_rows: toolEvidenceSftRows.length,
    tool_message_sft_rows: toolMessageSftRows.length,
    split_counts: splitMetadata.counts,
  }, null, 2)}\n`);
}

async function loadSchemaValidator(fileName) {
  const schema = await readJson(path.join(envRoot, "schema", fileName));
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
  const split = splitForTask(spec.task_id);
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
    split,
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
    split_metadata_path: path.relative(repoRoot, splitOutPath),
    evidence_ids: evidenceIds,
    model_context: compactContext,
  };
}

function buildToolEnvEvalRow({ taskDir, spec }) {
  const split = splitForTask(spec.task_id);
  return {
    schema_version: "agent_native_seed_tool_env_eval_row.v0",
    task_id: spec.task_id,
    family: spec.family,
    split,
    eval_mode: "tool_env",
    runtime_kind: runtimeKindForFamily(spec.family),
    messages: [
      {
        role: "system",
        content: [
          "You are operating a Datalox agent-native scientific tool environment.",
          "Do not answer from hidden target observations.",
          "Use the available domain tools, preserve workspace revision discipline, and return the final structured answer only after tool evidence supports it.",
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
          "Available tools:",
          JSON.stringify({
            allowed_tools: spec.allowed_tools,
            forbidden_tools: spec.forbidden_tools,
          }, null, 2),
        ].join("\n"),
      },
    ],
    allowed_tools: spec.allowed_tools,
    forbidden_tools: spec.forbidden_tools,
    expected_tool_path: spec.expected_tool_path,
    output_schema_path: path.relative(repoRoot, path.resolve(taskDir, spec.output_schema)),
    family_output_schema_path: path.relative(repoRoot, path.resolve(taskDir, spec.family_output_schema)),
    verifier_spec_path: path.relative(repoRoot, path.join(taskDir, "verifier", "verifier.spec.json")),
    split_metadata_path: path.relative(repoRoot, splitOutPath),
    source_task_spec_path: path.relative(repoRoot, path.join(taskDir, "task.spec.json")),
  };
}

async function buildToolEvidenceSftRow({ taskDir, spec }, evalRow) {
  const observations = await readObservations(taskDir);
  const passAnswerPath = path.join(taskDir, "verifier", "expected.pass.json");
  const passAnswer = await readJson(passAnswerPath);
  return {
    schema_version: "agent_native_seed_tool_evidence_sft_row.v0",
    task_id: spec.task_id,
    family: spec.family,
    split: evalRow.split,
    training_mode: "tool_env_evidence_sft_handoff",
    source_kind: sourceKindForObservations(observations),
    runtime_kind: runtimeKindForFamily(spec.family),
    messages: buildToolEnvEvalRow({ taskDir, spec }).messages,
    tool_steps: [
      ...observations.flatMap((row) => [
        {
          type: "assistant_action",
          sequence_index: row.sequence_index,
          tool_name: row.tool_name,
          arguments: pruneLargeArrays(row.request),
          evidence_ids: row.evidence_ids,
        },
        {
          type: "tool_observation",
          sequence_index: row.sequence_index,
          tool_name: row.tool_name,
          observation: summarizeObservation(row.tool_name, row.observation),
          evidence_ids: row.evidence_ids,
          workspace_revision: row.workspace_revision,
        },
      ]),
      {
        type: "assistant_final",
        answer: passAnswer,
        evidence_ids: passAnswer.evidence_ids,
      },
    ],
    source_answer_path: path.relative(repoRoot, passAnswerPath),
    verifier_spec_path: evalRow.verifier_spec_path,
    observation_path: evalRow.observation_path,
    split_metadata_path: evalRow.split_metadata_path,
    evidence_ids: passAnswer.evidence_ids,
    export_gate: {
      allowed: true,
      redaction: "none_needed",
    },
  };
}

function buildToolMessageSftRow(toolEvidenceSftRow) {
  return {
    schema_version: "agent_native_seed_tool_message_sft_row.v0",
    task_id: toolEvidenceSftRow.task_id,
    family: toolEvidenceSftRow.family,
    split: toolEvidenceSftRow.split,
    training_mode: "tool_env_message_sft_handoff",
    source_kind: toolEvidenceSftRow.source_kind,
    runtime_kind: toolEvidenceSftRow.runtime_kind,
    message_format: "openai_tool_messages",
    messages: [
      ...toolEvidenceSftRow.messages,
      ...toolEvidenceSftRow.tool_steps.flatMap((step) => {
        if (step.type === "assistant_action") {
          return [{
            role: "assistant",
            content: "",
            tool_calls: [
              {
                id: toolCallId(step),
                type: "function",
                function: {
                  name: step.tool_name,
                  arguments: JSON.stringify(step.arguments ?? {}),
                },
              },
            ],
          }];
        }
        if (step.type === "tool_observation") {
          return [{
            role: "tool",
            tool_call_id: toolCallId(step),
            name: step.tool_name,
            content: JSON.stringify({
              observation: step.observation,
              evidence_ids: step.evidence_ids,
              workspace_revision: step.workspace_revision,
            }),
          }];
        }
        if (step.type === "assistant_final") {
          return [{
            role: "assistant",
            content: JSON.stringify(step.answer),
          }];
        }
        throw new Error(`${toolEvidenceSftRow.task_id}: unsupported tool_steps step ${step.type}`);
      }),
    ],
    source_answer_path: toolEvidenceSftRow.source_answer_path,
    verifier_spec_path: toolEvidenceSftRow.verifier_spec_path,
    observation_path: toolEvidenceSftRow.observation_path,
    split_metadata_path: toolEvidenceSftRow.split_metadata_path,
    evidence_ids: toolEvidenceSftRow.evidence_ids,
    export_gate: toolEvidenceSftRow.export_gate,
  };
}

function toolCallId(step) {
  const safeToolName = step.tool_name.replace(/[^a-zA-Z0-9_-]/g, "_");
  return `call_${String(step.sequence_index).padStart(3, "0")}_${safeToolName}`;
}

function runtimeKindForFamily(family) {
  if (family === "flowcyto" || family === "molecule-biology" || family === "protein-mcp") return "sibling_domain_tool_runtime";
  throw new Error(`Unsupported family ${family}`);
}

function sourceKindForObservations(observations) {
  const kinds = new Set(observations.map((row) => row.capture_source?.kind ?? "unknown"));
  if (kinds.size === 1 && kinds.has("live_domain_tool")) return "live_domain_tool_rollout";
  throw new Error(`Expected live_domain_tool observations only; got ${[...kinds].join(", ")}`);
}

function buildSplitMetadata(taskDirs) {
  const tasks = taskDirs
    .map(({ spec }) => ({
      task_id: spec.task_id,
      family: spec.family,
      split: splitForTask(spec.task_id),
    }))
    .sort((a, b) => a.task_id.localeCompare(b.task_id));

  const actualTaskIds = new Set(tasks.map((task) => task.task_id));
  const staleAssignments = [...splitAssignments.keys()].filter((taskId) => !actualTaskIds.has(taskId));
  if (staleAssignments.length > 0) {
    throw new Error(`split assignment references missing task ids: ${staleAssignments.join(", ")}`);
  }

  const counts = tasks.reduce((acc, task) => {
    acc[task.split] = (acc[task.split] ?? 0) + 1;
    return acc;
  }, { train: 0, dev: 0, test: 0 });

  return {
    schema_version: "agent_native_seed_split.v0",
    split_name: "mcp-seed-v0",
    split_kind: "handoff_validation_not_lift_proof",
    created_at: "2026-06-02",
    intended_use: "Validate a MCP-backed handoff with real domain tools, leakage controls, tool-message SFT row shape, and held-out eval commands before collecting a lift-grade 80/20/20 dataset.",
    not_for: "Do not claim reliable SFT lift from this split; it is too small and exists to make the handoff executable.",
    policy: "Deterministic stratified split over active MCP-backed families only: FlowCyto, Molecule Biology, and Protein MCP. SFT rows are exported for train tasks only.",
    counts,
    tasks,
  };
}

function splitForTask(taskId) {
  const split = splitAssignments.get(taskId);
  if (!split) throw new Error(`${taskId}: missing split assignment`);
  return split;
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
  if (["open_sequence", "get_sequence_context", "upsert_feature", "upsert_primer", "find_restriction_sites", "simulate_digest", "simulate_pcr", "find_orfs", "translate_region", "export_genbank", "validate_workspace"].includes(toolName)) {
    return summarizeMoleculeObservation(observation);
  }
  if (["open_structure", "open_protein_viewer", "get_structure_context", "update_protein_view", "list_ligands", "annotate_binding_site", "get_scene_annotations"].includes(toolName)) {
    return summarizeProteinObservation(observation);
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

function summarizeProteinObservation(observation) {
  const result = pruneLargeArrays(observation.result ?? {});
  if (result.metadata?.chains) result.metadata.chains = pruneLargeArrays(result.metadata.chains);
  if (result.metadata?.ligands) result.metadata.ligands = pruneLargeArrays(result.metadata.ligands);
  if (result.workspace?.structures) result.workspace.structures = pruneLargeArrays(result.workspace.structures);
  return {
    ok: observation.ok,
    result,
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

## Corrected Training Boundary

\`exports/eval.seed.jsonl\` is a context-eval validation file: it preloads replay
observations in the prompt and checks whether the model can read evidence and
emit the target JSON.

\`exports/eval.tool_env.seed.jsonl\` is the primary environment-facing eval
contract: the model starts from the task prompt and must use domain tools.

\`exports/sft.tool_messages.seed.jsonl\` is the collaborator-facing SFT handoff:
standard \`system\`/\`user\`/\`assistant\`/\`tool\` messages with assistant tool
calls followed by tool observations.

\`exports/sft.tool_evidence.seed.jsonl\` keeps the same information in a
Datalox-rich evidence/audit shape.

## Context-Eval Baseline

\`\`\`bash
# Serve the same open-weight base model that will later receive LoRA SFT.
# Example local endpoint, replace with the model team's normal inference stack.
vllm serve Qwen/Qwen3-1.7B \\
  --host 127.0.0.1 \\
  --port 8000
\`\`\`

\`\`\`bash
node handoff/env-data-proof-v0/tools/run-seed-baseline.mjs \\
  --input handoff/env-data-proof-v0/exports/eval.seed.jsonl \\
  --out handoff/env-data-proof-v0/exports/eval.baseline.jsonl \\
  --mode openai-compatible \\
  --model Qwen/Qwen3-1.7B \\
  --base-url http://127.0.0.1:8000/v1 \\
  --api-key token \\
  --min-failures 5
\`\`\`

The key rule is that this baseline must use the same trainable open-weight base
model that will be fine-tuned. A closed API model can be useful as a reference
inference run, but it is not the SFT baseline unless that exact model can be
fine-tuned by the post-training workflow.

## Tool-Env Baseline Target

The tool-env eval requires an agent harness that exposes the family tools and
logs tool calls. The input contract is:

\`\`\`text
handoff/env-data-proof-v0/exports/eval.tool_env.seed.jsonl
  -> agent uses allowed domain tools
  -> verifier checks final answer and workspace/tool evidence
  -> baseline report by split/family
\`\`\`

The current \`run-seed-baseline.mjs\` script does not execute tool-env rows; it
only runs the context-eval rows above.

Optional closed-model reference command:

\`\`\`bash
node handoff/env-data-proof-v0/tools/run-seed-baseline.mjs \\
  --input handoff/env-data-proof-v0/exports/eval.seed.jsonl \\
  --out handoff/env-data-proof-v0/exports/eval.baseline.reference.jsonl \\
  --mode openai-compatible \\
  --model <reference-api-model> \\
  --base-url <openai-compatible-base-url> \\
  --api-key "$API_KEY" \\
  --min-failures 0
\`\`\`

Local verifier wiring command. This proves schemas, parsing, and verifier
wiring only; it is not model evidence:

\`\`\`bash
node handoff/env-data-proof-v0/tools/run-seed-baseline.mjs \\
  --input handoff/env-data-proof-v0/exports/eval.seed.jsonl \\
  --out handoff/env-data-proof-v0/exports/eval.baseline.verifier.jsonl \\
  --mode verifier-check \\
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
