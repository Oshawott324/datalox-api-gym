#!/usr/bin/env node
import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const envRoot = path.resolve(scriptDir, "..");
const repoRoot = path.resolve(envRoot, "../..");
const familiesRoot = path.join(envRoot, "families");

const flowcytoRoot = path.resolve(process.env.DATALOX_FLOWCYTO_REPO ?? path.resolve(repoRoot, "../datalox-flow-cyto-mcp"));
const moleculeRoot = path.resolve(process.env.DATALOX_MOLECULE_REPO ?? path.resolve(repoRoot, "../datalox-molecule-biology"));

const capturedAt = process.env.DATALOX_CAPTURED_AT ?? new Date().toISOString();

const taskFilter = process.argv.find((arg) => arg.startsWith("--task="))?.slice("--task=".length);
const familyFilter = process.argv.find((arg) => arg.startsWith("--family="))?.slice("--family=".length);
const keepWorkspace = process.argv.includes("--keep-workspace");

const pathTokens = [
  { prefix: repoRoot, token: "${DATALOX_AGENT_REPLAY}" },
  { prefix: flowcytoRoot, token: "${DATALOX_FLOWCYTO_REPO}" },
  { prefix: moleculeRoot, token: "${DATALOX_MOLECULE_REPO}" },
];

async function main() {
  const specs = await loadTaskSpecs();
  const selected = specs.filter(({ spec }) =>
    (taskFilter === undefined || spec.task_id === taskFilter)
    && (familyFilter === undefined || spec.family === familyFilter)
  );
  if (selected.length === 0) throw new Error("No task specs matched the requested filter.");

  const summary = [];
  for (const entry of selected) {
    const rows = await captureTask(entry);
    await writeObservations(entry.taskDir, rows);
    if (!keepWorkspace) await removeCaptureWorkspace(entry.taskDir);
    summary.push({ task_id: entry.spec.task_id, family: entry.spec.family, observations: rows.length });
  }

  process.stdout.write(`${JSON.stringify({ ok: true, captured_at: capturedAt, summary }, null, 2)}\n`);
}

async function loadTaskSpecs() {
  const files = await findFiles(familiesRoot, "task.spec.json");
  const entries = [];
  for (const file of files.sort()) {
    const spec = JSON.parse(await fs.readFile(file, "utf8"));
    entries.push({ spec, taskDir: path.dirname(file), specPath: file });
  }
  return entries;
}

async function findFiles(root, name) {
  const entries = await fs.readdir(root, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const full = path.join(root, entry.name);
    if (entry.isDirectory()) files.push(...await findFiles(full, name));
    if (entry.isFile() && entry.name === name) files.push(full);
  }
  return files;
}

async function captureTask(entry) {
  if (entry.spec.family === "flowcyto") return captureFlowcyto(entry);
  if (entry.spec.family === "molecule-biology") return captureMolecule(entry);
  if (entry.spec.family === "scientific-data-qc") return captureScientificData(entry);
  throw new Error(`Unsupported family ${entry.spec.family}`);
}

function makeRecorder(spec, captureSource) {
  const rows = [];
  return {
    rows,
    record(toolName, request, observation, options = {}) {
      const sequenceIndex = rows.length;
      rows.push({
        schema_version: "agent_visible_tool_observation.v0",
        task_id: spec.task_id,
        family: spec.family,
        sequence_index: sequenceIndex,
        tool_name: toolName,
        request: normalizeArtifactPaths(request),
        observation: normalizeArtifactPaths(observation),
        workspace_revision: workspaceRevision(observation),
        evidence_ids: evidenceIds(spec.task_id, toolName, sequenceIndex, observation, options.evidenceIds),
        capture_source: normalizeArtifactPaths(captureSource),
        captured_at: capturedAt,
      });
      return observation;
    },
  };
}

function normalizeArtifactPaths(value) {
  if (typeof value === "string") return normalizePathString(value);
  if (Array.isArray(value)) return value.map((entry) => normalizeArtifactPaths(entry));
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, entry]) => [key, normalizeArtifactPaths(entry)]),
    );
  }
  return value;
}

function normalizePathString(value) {
  let result = value;
  for (const { prefix, token } of pathTokens) {
    const nativePrefix = path.resolve(prefix);
    const posixPrefix = nativePrefix.split(path.sep).join("/");
    result = result.split(nativePrefix).join(token);
    result = result.split(posixPrefix).join(token);
  }
  return result;
}

function workspaceRevision(observation) {
  if (observation && Number.isInteger(observation.revision)) return observation.revision;
  if (observation?.data && Number.isInteger(observation.data.revision)) return observation.data.revision;
  if (observation?.workspace && Number.isInteger(observation.workspace.revision)) return observation.workspace.revision;
  return null;
}

function evidenceIds(taskId, toolName, sequenceIndex, observation, explicit = []) {
  const ids = new Set([`tool_io:${taskId}/${toolName}/${sequenceIndex}`, ...explicit]);
  collectEvidence(observation, ids);
  return [...ids].filter((id) => /^[A-Za-z_]+[:/]/.test(id));
}

function collectEvidence(value, ids) {
  if (value === null || value === undefined) return;
  if (Array.isArray(value)) {
    value.forEach((entry) => collectEvidence(entry, ids));
    return;
  }
  if (typeof value !== "object") return;
  for (const [key, entry] of Object.entries(value)) {
    if (typeof entry === "string") {
      if (key === "evidenceRef") ids.add(entry.replace(/^flowcyto:gate-stats:/, "stats:").replace(/^flowcyto:gate-qc:/, "qc:"));
      if (key === "reportId") ids.add(`report:${entry}`);
      if (key === "featureId") ids.add(`feature:${entry}`);
      if (key === "primerId") ids.add(`primer:${entry}`);
      if (key === "moleculeId") ids.add(`molecule:${entry}`);
    }
    collectEvidence(entry, ids);
  }
}

async function captureFlowcyto({ spec, taskDir }) {
  const flowCore = await import(path.join(flowcytoRoot, "dist/src/core/index.js"));
  const flowApp = await import(path.join(flowcytoRoot, "dist/src/app/gate-editor/server.js"));
  const workspaceDir = path.join(taskDir, "capture-workspace");
  await fs.rm(workspaceDir, { recursive: true, force: true });
  await fs.mkdir(workspaceDir, { recursive: true });

  const sourcePath = path.join(flowcytoRoot, spec.source_ref.fixture_path);
  const recorder = makeRecorder(spec, { kind: "live_domain_tool", repo: "datalox-flow-cyto-mcp" });

  const openRequest = { path: sourcePath, workspaceDir, sampleId: "sample_001" };
  const open = recorder.record("open_fcs", openRequest, await flowCore.openFcsArtifact({
    path: openRequest.path,
    workspaceDir: openRequest.workspaceDir,
    sampleId: openRequest.sampleId,
  }));

  const contextRequest = {
    workspacePath: open.workspacePath,
    sampleId: open.sampleId,
    x: "FSC-A",
    y: "SSC-A",
    maxEvents: 10000,
    format: "bins",
  };
  const context = recorder.record("get_plot_context", contextRequest, await flowApp.getPlotContext(contextRequest));
  const gate = gateFromContext(context);

  const upsertRequest = { workspacePath: open.workspacePath, gate, expectedRevision: context.revision };
  const upsert = recorder.record("upsert_gate", upsertRequest, await flowCore.upsertGate(upsertRequest));

  const statsRequest = { workspacePath: open.workspacePath, sampleId: open.sampleId, gateId: gate.id };
  const stats = recorder.record("compute_gate_stats", statsRequest, await flowCore.computeGateStats(statsRequest));

  const qcRequest = { workspacePath: open.workspacePath, sampleId: open.sampleId, gateId: gate.id, statsRef: stats.evidenceRef };
  const qc = recorder.record("validate_gate_qc", qcRequest, await flowCore.validateGateQc(qcRequest));

  const report = {
    title: "Main population QC",
    summary: "Main FSC/SSC gate was created and validated with deterministic FlowCyto evidence.",
    gate_id: gate.id,
    stats_ref: stats.evidenceRef,
    qc_ref: qc.evidenceRef,
    caveats: [],
  };

  if (spec.task_id === "flowcyto-gating-qc-stale-revision-failure") {
    const staleRequest = { workspacePath: open.workspacePath, expectedRevision: 0, report };
    recorder.record("submit_report", staleRequest, await flowCore.submitReport(staleRequest));
    const recoveryRequest = { workspacePath: open.workspacePath, expectedRevision: upsert.revision, report };
    recorder.record("submit_report", recoveryRequest, await flowCore.submitReport(recoveryRequest));
    return recorder.rows;
  }

  if (spec.task_id === "flowcyto-gating-qc-report-validation-failure") {
    const badReport = { title: report.title, summary: report.summary, gate_id: report.gate_id, caveats: [] };
    const badRequest = { workspacePath: open.workspacePath, expectedRevision: upsert.revision, report: badReport };
    recorder.record("submit_report", badRequest, await flowCore.submitReport(badRequest));
    const recoveryRequest = { workspacePath: open.workspacePath, expectedRevision: upsert.revision, report };
    recorder.record("submit_report", recoveryRequest, await flowCore.submitReport(recoveryRequest));
    return recorder.rows;
  }

  const submitRequest = { workspacePath: open.workspacePath, expectedRevision: upsert.revision, report };
  recorder.record("submit_report", submitRequest, await flowCore.submitReport(submitRequest));
  return recorder.rows;
}

function gateFromContext(context) {
  const template = context?.recommendedGate?.gateTemplate;
  const bounds = context?.bounds;
  if (!template || !bounds) throw new Error("FlowCyto plot context did not return gate template and bounds.");
  return {
    ...template,
    vertices: [
      [bounds.xMin, bounds.yMin],
      [bounds.xMax, bounds.yMin],
      [bounds.xMax, bounds.yMax],
      [bounds.xMin, bounds.yMax],
    ],
  };
}

async function captureMolecule({ spec, taskDir }) {
  const { runToolHandler } = await import(path.join(moleculeRoot, "dist/src/tools/index.js"));
  const workspaceDir = path.join(taskDir, "capture-workspace");
  await fs.rm(workspaceDir, { recursive: true, force: true });
  await fs.mkdir(workspaceDir, { recursive: true });

  const fixturePath = path.join(moleculeRoot, spec.source_ref.fixture_path);
  const moleculeId = moleculeIdForTask(spec.task_id);
  const format = fixturePath.endsWith(".fa") ? "fasta" : "genbank";
  const recorder = makeRecorder(spec, { kind: "live_domain_tool", repo: "datalox-molecule-biology" });

  async function call(toolName, request) {
    return recorder.record(toolName, request, await runToolHandler(toolName, request));
  }

  const open = await call("open_sequence", { inputPath: fixturePath, workspaceDir, format, moleculeId });
  const workspacePath = open.workspacePath;
  const context = await call("get_sequence_context", { workspacePath, moleculeId, includeSequence: true });

  if (spec.task_id === "molecule-fasta-import-context-001") {
    await call("validate_workspace", { workspacePath });
    return recorder.rows;
  }

  if (spec.task_id === "molecule-genbank-feature-annotation-001") {
    await call("upsert_feature", {
      workspacePath,
      expectedRevision: context.revision,
      feature: {
        id: "feat_seed_annotation",
        moleculeId,
        name: "seed annotation",
        type: "misc_feature",
        segments: [{ start: 1, end: 4, strand: "+" }],
        qualifiers: { note: "captured by Datalox seed task" },
        source: { kind: "agent", tool: "upsert_feature" },
      },
    });
    await call("validate_workspace", { workspacePath });
    return recorder.rows;
  }

  if (spec.task_id === "molecule-primer-validation-001") {
    await call("upsert_primer", {
      workspacePath,
      expectedRevision: context.revision,
      bindToMolecule: true,
      primer: {
        id: "primer_seed_fwd",
        name: "seed forward primer",
        sequence: "ACGT",
        moleculeId,
        metadata: { captured_by: "datalox_seed_task" },
      },
    });
    await call("validate_workspace", { workspacePath });
    return recorder.rows;
  }

  if (spec.task_id === "molecule-restriction-digest-001") {
    const enzymes = ["EcoRI", "BamHI", "HindIII"];
    await call("find_restriction_sites", { workspacePath, moleculeId, enzymes });
    await call("simulate_digest", { workspacePath, moleculeId, enzymes });
    return recorder.rows;
  }

  if (spec.task_id === "molecule-pcr-simulation-001") {
    await call("upsert_primer", {
      workspacePath,
      expectedRevision: context.revision,
      bindToMolecule: true,
      primer: {
        id: "primer_seed_forward",
        name: "seed PCR forward",
        sequence: "ACGTAC",
        moleculeId,
        metadata: { captured_by: "datalox_seed_task" },
      },
    });
    await call("upsert_primer", {
      workspacePath,
      expectedRevision: context.revision + 1,
      bindToMolecule: true,
      primer: {
        id: "primer_seed_reverse",
        name: "seed PCR reverse",
        sequence: "GTACGT",
        moleculeId,
        metadata: { captured_by: "datalox_seed_task" },
      },
    });
    await call("simulate_pcr", { workspacePath, moleculeId, forwardPrimer: "ACGTAC", reversePrimer: "GTACGT" });
    await call("validate_workspace", { workspacePath });
    return recorder.rows;
  }

  throw new Error(`No Molecule Biology capture path for ${spec.task_id}`);
}

function moleculeIdForTask(taskId) {
  if (taskId.includes("fasta")) return "mol_single";
  if (taskId.includes("circular") || taskId.includes("primer") || taskId.includes("digest")) return "mol_circular";
  return "mol_linear";
}

async function captureScientificData({ spec, taskDir }) {
  const worldId = spec.task_id;
  const sourcePath = path.join(envRoot, "worlds", worldId, "tools", "tool-observations.jsonl");
  const content = await fs.readFile(sourcePath, "utf8");
  const rows = content.trim().split(/\r?\n/).filter(Boolean).map((line, index) => {
    const source = JSON.parse(line);
    return {
      schema_version: "agent_visible_tool_observation.v0",
      task_id: spec.task_id,
      family: spec.family,
      sequence_index: index,
      tool_name: source.tool_name,
      request: normalizeArtifactPaths(source.arguments ?? {}),
      observation: normalizeArtifactPaths(source.observation),
      workspace_revision: null,
      evidence_ids: [...new Set([
        source.evidence_id,
        `tool_io:${spec.task_id}/${source.tool_name}/${index}`,
      ].filter(Boolean))],
      capture_source: {
        kind: "existing_deterministic_fixture_observation",
        source_path: path.relative(repoRoot, sourcePath),
      },
      captured_at: capturedAt,
    };
  });
  await fs.mkdir(path.join(taskDir, "tools"), { recursive: true });
  return rows;
}

async function writeObservations(taskDir, rows) {
  const toolsDir = path.join(taskDir, "tools");
  await fs.mkdir(toolsDir, { recursive: true });
  const outPath = path.join(toolsDir, "tool-observations.jsonl");
  await fs.writeFile(outPath, `${rows.map((row) => JSON.stringify(row)).join("\n")}\n`, "utf8");
}

async function removeCaptureWorkspace(taskDir) {
  await fs.rm(path.join(taskDir, "capture-workspace"), { recursive: true, force: true });
}

main().catch((error) => {
  process.stderr.write(`${error.stack ?? error.message}\n`);
  process.exitCode = 1;
});
