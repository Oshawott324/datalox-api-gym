#!/usr/bin/env node
import { promises as fs } from "node:fs";
import { execFile } from "node:child_process";
import path from "node:path";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";

const execFileAsync = promisify(execFile);

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const envRoot = path.resolve(scriptDir, "..");
const repoRoot = path.resolve(envRoot, "../..");
const familiesRoot = path.join(envRoot, "families");

const flowcytoRoot = path.resolve(process.env.DATALOX_FLOWCYTO_REPO ?? path.resolve(repoRoot, "../datalox-flow-cyto-mcp"));
const moleculeRoot = path.resolve(process.env.DATALOX_MOLECULE_REPO ?? path.resolve(repoRoot, "../datalox-molecule-biology"));
const proteinRoot = path.resolve(process.env.DATALOX_PROTEIN_REPO ?? path.resolve(repoRoot, "../datalox-protein-mcp"));

const capturedAt = process.env.DATALOX_CAPTURED_AT ?? new Date().toISOString();

const taskFilter = process.argv.find((arg) => arg.startsWith("--task="))?.slice("--task=".length);
const familyFilter = process.argv.find((arg) => arg.startsWith("--family="))?.slice("--family=".length);
const keepWorkspace = process.argv.includes("--keep-workspace");

const pathTokens = [
  { prefix: repoRoot, token: "${DATALOX_AGENT_REPLAY}" },
  { prefix: flowcytoRoot, token: "${DATALOX_FLOWCYTO_REPO}" },
  { prefix: moleculeRoot, token: "${DATALOX_MOLECULE_REPO}" },
  { prefix: proteinRoot, token: "${DATALOX_PROTEIN_REPO}" },
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
  if (entry.spec.family === "protein-mcp") return captureProtein(entry);
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
  if (observation?.result && Number.isInteger(observation.result.revision)) return observation.result.revision;
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
      if (key === "structureId") ids.add(`structure:${entry}`);
      if (key === "viewId") ids.add(`view:${entry}`);
      if (key === "id" && typeof value.kind === "string" && value.kind === "distance") ids.add(`measurement:${entry}`);
      if (key === "id" && typeof value.kind === "string" && value.kind === "label") ids.add(`annotation:${entry}`);
      if (key === "id" && typeof value.residueName === "string" && typeof value.chain === "string") ids.add(`ligand:${entry}`);
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

  const sourcePath = resolveSourcePath(spec, flowcytoRoot);
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

  if (spec.task_id === "flowcyto-existing-gate-edit-revision") {
    const editedGate = {
      ...gate,
      label: "Edited main population gate",
      vertices: gate.vertices.map(([x, y], index) => [
        index === 0 || index === 3 ? x : x * 0.98,
        index === 0 || index === 1 ? y : y * 0.98,
      ]),
    };
    const editRequest = { workspacePath: open.workspacePath, gate: editedGate, expectedRevision: upsert.revision };
    const edited = recorder.record("upsert_gate", editRequest, await flowCore.upsertGate(editRequest));
    const statsRequest = { workspacePath: open.workspacePath, sampleId: open.sampleId, gateId: gate.id };
    const stats = recorder.record("compute_gate_stats", statsRequest, await flowCore.computeGateStats(statsRequest));
    const qcRequest = { workspacePath: open.workspacePath, sampleId: open.sampleId, gateId: gate.id, statsRef: stats.evidenceRef };
    const qc = recorder.record("validate_gate_qc", qcRequest, await flowCore.validateGateQc(qcRequest));
    const report = {
      title: "Edited main population QC",
      summary: "Existing FSC/SSC gate was revision-safely edited and validated with deterministic FlowCyto evidence.",
      gate_id: gate.id,
      stats_ref: stats.evidenceRef,
      qc_ref: qc.evidenceRef,
      caveats: [],
    };
    const submitRequest = { workspacePath: open.workspacePath, expectedRevision: edited.revision, report };
    recorder.record("submit_report", submitRequest, await flowCore.submitReport(submitRequest));
    return recorder.rows;
  }

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

  const fixturePath = resolveSourcePath(spec, moleculeRoot);
  const moleculeId = moleculeIdForTask(spec.task_id);
  const format = fixturePath.endsWith(".fa") ? "fasta" : "genbank";
  const recorder = makeRecorder(spec, { kind: "live_domain_tool", repo: "datalox-molecule-biology" });

  async function call(toolName, request) {
    const observation = await runToolHandler(toolName, request);
    recorder.record(toolName, request, stripRecordedSequence(observation));
    return observation;
  }

  const open = await call("open_sequence", { inputPath: fixturePath, workspaceDir, format, moleculeId });
  const workspacePath = open.workspacePath;
  const context = await call("get_sequence_context", { workspacePath, moleculeId, includeSequence: true });

  if (spec.task_id === "molecule-genbank-feature-annotation-001") {
    await call("upsert_feature", {
      workspacePath,
      expectedRevision: context.revision,
      feature: {
        id: "feat_agent_promoter_review",
        moleculeId,
        name: "agent promoter review region",
        type: "misc_feature",
        segments: [{ start: 34500, end: 34650, strand: "+" }],
        qualifiers: { note: "source-derived Datalox handoff annotation" },
        source: { kind: "agent", tool: "upsert_feature" },
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
    const sequence = context.data?.sequence;
    if (typeof sequence !== "string" || sequence.length < 1100) throw new Error(`${spec.task_id}: sequence context did not include enough sequence for primer selection.`);
    const forwardPrimer = sequence.slice(190, 210);
    const reversePrimer = reverseComplement(sequence.slice(900, 920));
    await call("upsert_primer", {
      workspacePath,
      expectedRevision: context.revision,
      bindToMolecule: true,
      primer: {
        id: "primer_seed_forward",
        name: "seed PCR forward",
        sequence: forwardPrimer,
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
        sequence: reversePrimer,
        moleculeId,
        metadata: { captured_by: "datalox_seed_task" },
      },
    });
    await call("simulate_pcr", { workspacePath, moleculeId, forwardPrimer, reversePrimer });
    await call("validate_workspace", { workspacePath });
    return recorder.rows;
  }

  if (spec.task_id === "molecule-orf-translation-annotation") {
    const orfs = await call("find_orfs", { workspacePath, moleculeId, minAaLength: 50 });
    const firstOrf = orfs.data?.orfs?.[0];
    if (!firstOrf) throw new Error(`${spec.task_id}: find_orfs returned no ORFs.`);
    const translation = await call("translate_region", {
      workspacePath,
      moleculeId,
      start: firstOrf.start,
      end: firstOrf.end,
      strand: firstOrf.strand,
    });
    const featureId = `feat_agent_orf_${firstOrf.start}_${firstOrf.end}`;
    await call("upsert_feature", {
      workspacePath,
      expectedRevision: context.revision,
      feature: {
        id: featureId,
        moleculeId,
        name: "agent ORF translation review",
        type: "CDS",
        segments: [{ start: firstOrf.start, end: firstOrf.end, strand: firstOrf.strand }],
        qualifiers: {
          note: "ORF selected and translated through deterministic molecule tools",
          translation_length: String(translation.data?.aminoAcidLength ?? ""),
        },
        source: { kind: "agent", tool: "upsert_feature" },
      },
    });
    await call("validate_workspace", { workspacePath });
    return recorder.rows;
  }

  if (spec.task_id === "molecule-export-genbank-after-edit") {
    await call("upsert_feature", {
      workspacePath,
      expectedRevision: context.revision,
      feature: {
        id: "feat_agent_export_marker",
        moleculeId,
        name: "agent export marker",
        type: "misc_feature",
        segments: [{ start: 42000, end: 42120, strand: "-" }],
        qualifiers: { note: "added before GenBank export in Datalox handoff" },
        source: { kind: "agent", tool: "upsert_feature" },
      },
    });
    await call("validate_workspace", { workspacePath });
    await call("export_genbank", {
      workspacePath,
      moleculeId,
      outputPath: path.join(workspaceDir, "lambda.agent-export.gb"),
    });
    await call("validate_workspace", { workspacePath });
    return recorder.rows;
  }

  throw new Error(`No Molecule Biology capture path for ${spec.task_id}`);
}

function moleculeIdForTask(taskId) {
  return "lambda_nc001416";
}

async function captureProtein({ spec, taskDir }) {
  const workspaceDir = path.join(taskDir, "capture-workspace");
  await fs.rm(workspaceDir, { recursive: true, force: true });
  await fs.mkdir(workspaceDir, { recursive: true });

  const sourcePath = resolveSourcePath(spec, proteinRoot);
  const recorder = makeRecorder(spec, { kind: "live_domain_tool", repo: "datalox-protein-mcp" });

  async function call(toolName, request) {
    return recorder.record(toolName, request, await callProteinTool(toolName, request));
  }

  const open = await call("open_structure", {
    structure_path: sourcePath,
    workspace_dir: workspaceDir,
    structure_id: "target",
    view_id: "default",
  });
  const workspacePath = open.result.workspacePath;

  if (spec.task_id === "protein-view-revision-safe-style") {
    await call("open_protein_viewer", { workspace_path: workspacePath, launch: "none", surface: "none", active_view_id: "default" });
    const context = await call("get_structure_context", { workspace_path: workspacePath, active_view_id: "default" });
    await call("update_protein_view", {
      workspace_path: workspacePath,
      expected_revision: context.result.revision,
      view_id: "default",
      edit: {
        selection: "target",
        style: "surface",
        color: "green",
      },
    });
    await call("validate_workspace", { workspace_path: workspacePath });
    return recorder.rows;
  }

  const ligands = await call("list_ligands", { workspace_path: workspacePath, structure_id: "target" });
  const ligand = preferredLigand(ligands);

  if (spec.task_id === "protein-ligand-contact-scene-repair") {
    await call("get_scene_annotations", { workspace_path: workspacePath });
  }

  await call("annotate_binding_site", {
    workspace_path: workspacePath,
    structure_id: "target",
    ligand_id: ligand.id,
    radius_angstrom: 4.5,
    max_contacts: spec.task_id === "protein-ligand-contact-scene-repair" ? 8 : 6,
    agent_note: spec.task_id === "protein-ligand-contact-scene-repair"
      ? "Recovered missing ligand-contact scene annotations through protein MCP."
      : "Stored agent note separately from backend contact facts.",
  });
  await call("get_scene_annotations", { workspace_path: workspacePath });
  await call("validate_workspace", { workspace_path: workspacePath });
  return recorder.rows;
}

async function callProteinTool(toolName, request) {
  const python = [
    "import json, sys",
    "from protein_mcp.mcp.tools import ProteinMcpToolContext, ProteinMcpTools",
    "tool_name = sys.argv[1]",
    "request = json.loads(sys.argv[2])",
    "tools = ProteinMcpTools(ProteinMcpToolContext(headless=True))",
    "result = getattr(tools, tool_name)(**request)",
    "print(json.dumps(result))",
  ].join("\n");
  const { stdout } = await execFileAsync("python3", ["-c", python, toolName, JSON.stringify(request)], {
    env: {
      ...process.env,
      PYTHONPATH: [
        path.join(proteinRoot, "packages/protein-mcp/src"),
        process.env.PYTHONPATH,
      ].filter(Boolean).join(path.delimiter),
    },
    maxBuffer: 1024 * 1024 * 20,
  });
  const parsed = JSON.parse(stdout);
  if (parsed?.ok === false) return parsed;
  return parsed;
}

function preferredLigand(ligandsObservation) {
  const ligands = ligandsObservation.result?.ligands ?? [];
  if (!Array.isArray(ligands) || ligands.length === 0) throw new Error("Protein MCP list_ligands returned no ligands.");
  return ligands.find((ligand) => ligand.residueName === "HEM") ?? ligands[0];
}

function reverseComplement(sequence) {
  const complements = { A: "T", C: "G", G: "C", T: "A", a: "t", c: "g", g: "c", t: "a" };
  return sequence.split("").reverse().map((base) => complements[base] ?? base).join("").toUpperCase();
}

function stripRecordedSequence(observation) {
  if (typeof observation?.data?.sequence !== "string") return observation;
  return {
    ...observation,
    data: {
      ...observation.data,
      sequence: `[${observation.data.sequence.length} bp sequence omitted; use sequenceDigest and tool evidence]`,
    },
  };
}

function resolveSourcePath(spec, defaultRoot) {
  const rawPath = spec.source_ref.fixture_path ?? spec.source_ref.task_path;
  if (!rawPath) throw new Error(`${spec.task_id}: source_ref fixture_path or task_path is required.`);
  if (path.isAbsolute(rawPath)) return rawPath;
  if (spec.source_ref.repo === "datalox-agent-replay" || rawPath.startsWith("handoff/")) return path.resolve(repoRoot, rawPath);
  return path.resolve(defaultRoot, rawPath);
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
