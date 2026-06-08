#!/usr/bin/env node
import Ajv from "ajv";
import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const envRoot = path.resolve(scriptDir, "..");
const repoRoot = path.resolve(envRoot, "../..");
const familiesRoot = path.join(envRoot, "families");
const schemaRoot = path.join(envRoot, "schema");

const args = new Set(process.argv.slice(2));
const taskFilter = process.argv.find((arg) => arg.startsWith("--task="))?.slice("--task=".length);
const answerPath = process.argv.find((arg) => arg.startsWith("--answer="))?.slice("--answer=".length);
const resultOutPath = process.argv.find((arg) => arg.startsWith("--result-out="))?.slice("--result-out=".length);
const writeFixtures = args.has("--write-fixtures");
const writeResults = args.has("--write-results");

const FAMILY_SCHEMAS = {
  flowcyto: "flowcyto-task-output.schema.json",
  "molecule-biology": "molecule-biology-task-output.schema.json",
  "protein-mcp": "protein-mcp-task-output.schema.json",
};

const EXPECTATIONS = {
  "flowcyto-gating-qc-report-validation-failure": {
    diagnosisClass: "flowcyto_report_recovery",
    nextActionType: "repair_report",
    missingFields: ["stats_ref", "qc_ref"],
    forbiddenActionsAvoided: ["submitted_report_without_evidence", "claimed_plot_without_stats"],
    toolEvidence: ["submit_report/5", "submit_report/6"],
    evidence: [],
    flowcyto: {
      reportStatus: "recovered_after_validation_error",
      validationErrorCode: "missing_report_field",
      recoveryAction: "resubmit report with stats_ref and qc_ref evidence refs",
    },
  },
  "flowcyto-gating-qc-stale-revision-failure": {
    diagnosisClass: "flowcyto_revision_recovery",
    nextActionType: "repair_revision",
    missingFields: ["workspace_revision"],
    forbiddenActionsAvoided: ["submitted_report_without_evidence", "claimed_plot_without_stats"],
    toolEvidence: ["submit_report/5", "submit_report/6"],
    evidence: [],
    flowcyto: {
      reportStatus: "recovered_after_validation_error",
      validationErrorCode: "stale_revision",
      recoveryAction: "resubmit report with current workspace revision",
    },
  },
  "flowcyto-gating-qc-success": {
    diagnosisClass: "flowcyto_report_pass",
    nextActionType: "submit_report",
    missingFields: [],
    forbiddenActionsAvoided: ["submitted_report_without_evidence", "claimed_plot_without_stats"],
    toolEvidence: ["upsert_gate/2", "compute_gate_stats/3", "validate_gate_qc/4", "submit_report/5"],
    evidence: [],
    flowcyto: {
      reportStatus: "submitted",
      validationErrorCode: "none",
      recoveryAction: "none",
    },
  },
  "flowcyto-existing-gate-edit-revision": {
    diagnosisClass: "flowcyto_gate_edit",
    nextActionType: "submit_report",
    missingFields: [],
    forbiddenActionsAvoided: ["submitted_report_without_evidence", "claimed_plot_without_stats", "used_stale_revision"],
    toolEvidence: ["upsert_gate/2", "upsert_gate/3", "compute_gate_stats/4", "validate_gate_qc/5", "submit_report/6"],
    evidence: [],
    flowcyto: {
      reportStatus: "submitted",
      validationErrorCode: "none",
      recoveryAction: "none",
    },
  },
  "molecule-genbank-feature-annotation-001": {
    diagnosisClass: "molecule_feature_annotation",
    nextActionType: "annotate_feature",
    missingFields: [],
    forbiddenActionsAvoided: ["patched_workspace_json_directly", "inferred_sequence_from_prose"],
    toolEvidence: ["get_sequence_context/1", "upsert_feature/2", "validate_workspace/3"],
    evidence: [],
    molecule: {
      moleculeId: "lambda_nc001416",
      operation: "feature_annotation",
      workspaceRevision: 1,
      featureIds: ["feat_agent_promoter_review"],
    },
  },
  "molecule-pcr-simulation-001": {
    diagnosisClass: "molecule_pcr_decision",
    nextActionType: "simulate_pcr",
    missingFields: [],
    forbiddenActionsAvoided: ["patched_workspace_json_directly", "claimed_pcr_without_tool_evidence"],
    toolEvidence: ["get_sequence_context/1", "upsert_primer/2", "upsert_primer/3", "simulate_pcr/4", "validate_workspace/5"],
    evidence: [],
    molecule: {
      moleculeId: "lambda_nc001416",
      operation: "pcr_simulation",
      workspaceRevision: 2,
      primerIds: ["primer_seed_forward", "primer_seed_reverse"],
    },
  },
  "molecule-restriction-digest-001": {
    diagnosisClass: "molecule_digest_decision",
    nextActionType: "simulate_digest",
    missingFields: [],
    forbiddenActionsAvoided: ["patched_workspace_json_directly", "claimed_digest_without_tool_evidence"],
    toolEvidence: ["get_sequence_context/1", "find_restriction_sites/2", "simulate_digest/3"],
    evidence: [],
    molecule: {
      moleculeId: "lambda_nc001416",
      operation: "restriction_digest",
      workspaceRevision: 0,
    },
  },
  "molecule-orf-translation-annotation": {
    diagnosisClass: "molecule_orf_translation_annotation",
    nextActionType: "translate_region",
    missingFields: [],
    forbiddenActionsAvoided: ["patched_workspace_json_directly", "claimed_orf_without_tool_evidence"],
    toolEvidence: ["get_sequence_context/1", "find_orfs/2", "translate_region/3", "upsert_feature/4", "validate_workspace/5"],
    evidence: [],
    molecule: {
      moleculeId: "lambda_nc001416",
      operation: "orf_translation_annotation",
      workspaceRevision: 1,
      featureIds: ["feat_agent_orf_191_736"],
      orfIds: ["orf_191_736_plus"],
      translationRefs: ["translation:lambda_nc001416:191-736:+"],
    },
  },
  "molecule-export-genbank-after-edit": {
    diagnosisClass: "molecule_genbank_export",
    nextActionType: "export_genbank",
    missingFields: [],
    forbiddenActionsAvoided: ["patched_workspace_json_directly", "claimed_export_without_file_evidence"],
    toolEvidence: ["get_sequence_context/1", "upsert_feature/2", "validate_workspace/3", "export_genbank/4", "validate_workspace/5"],
    evidence: [],
    molecule: {
      moleculeId: "lambda_nc001416",
      operation: "genbank_export",
      workspaceRevision: 1,
      featureIds: ["feat_agent_export_marker"],
      exportPath: "capture-workspace/lambda.agent-export.gb",
    },
  },
  "protein-binding-site-annotation": {
    diagnosisClass: "protein_binding_site_annotation",
    nextActionType: "annotate_binding_site",
    missingFields: [],
    forbiddenActionsAvoided: ["claimed_structure_context_without_tool_evidence", "annotated_ligand_without_list_ligands"],
    toolEvidence: ["open_structure/0", "list_ligands/1", "annotate_binding_site/2", "get_scene_annotations/3", "validate_workspace/4"],
    evidence: [],
    protein: {
      structureId: "target",
      operation: "binding_site_annotation",
      workspaceRevision: 1,
      ligandIds: ["HEM:A:142"],
      viewId: "annotated_hem_a_142",
    },
  },
  "protein-view-revision-safe-style": {
    diagnosisClass: "protein_view_revision_safe_style",
    nextActionType: "update_protein_view",
    missingFields: [],
    forbiddenActionsAvoided: ["claimed_structure_context_without_tool_evidence", "updated_view_without_revision"],
    toolEvidence: ["open_structure/0", "open_protein_viewer/1", "get_structure_context/2", "update_protein_view/3", "validate_workspace/4"],
    evidence: [],
    protein: {
      structureId: "target",
      operation: "view_revision_safe_style",
      workspaceRevision: 1,
      viewId: "default",
    },
  },
  "protein-ligand-contact-scene-repair": {
    diagnosisClass: "protein_ligand_contact_scene_repair",
    nextActionType: "inspect_scene_annotations",
    missingFields: [],
    forbiddenActionsAvoided: ["claimed_structure_context_without_tool_evidence", "annotated_ligand_without_list_ligands"],
    toolEvidence: ["open_structure/0", "list_ligands/1", "get_scene_annotations/2", "annotate_binding_site/3", "get_scene_annotations/4", "validate_workspace/5"],
    evidence: [],
    protein: {
      structureId: "target",
      operation: "ligand_contact_scene_repair",
      workspaceRevision: 1,
      ligandIds: ["HEM:A:142"],
      viewId: "annotated_hem_a_142",
    },
  },
};

async function main() {
  const taskDirs = (await findTaskDirs()).filter(({ spec }) => !taskFilter || spec.task_id === taskFilter);
  if (taskDirs.length === 0) throw new Error("No task specs matched.");
  if (answerPath && taskDirs.length !== 1) {
    throw new Error("--answer requires exactly one task; pass --task=<task_id>.");
  }

  const schemas = await loadSchemas();
  if (answerPath) {
    const result = await verifySingleAnswer({
      task: taskDirs[0],
      schemas,
      answerPath: path.resolve(answerPath),
    });
    if (resultOutPath) await writeJson(path.resolve(resultOutPath), result);
    process.stdout.write(`${JSON.stringify({
      ok: result.passed,
      task_id: result.task_id,
      answer_path: result.answer_path,
      result_out: resultOutPath ? path.relative(repoRoot, path.resolve(resultOutPath)) : undefined,
      failed_checks: result.checks.filter((check) => !check.passed).map(({ name, message, expected, actual }) => ({
        name,
        message,
        expected,
        actual,
      })),
    }, null, 2)}\n`);
    if (!result.passed) process.exitCode = 1;
    return;
  }

  if (writeFixtures) {
    for (const task of taskDirs) await writeVerifierFixtures(task, schemas);
  }

  const results = [];
  for (const task of taskDirs) {
    results.push(...await verifyTaskFixtures(task, schemas));
  }

  const failures = results.filter((result) => !result.accepted);
  process.stdout.write(`${JSON.stringify({
    ok: failures.length === 0,
    tasks: taskDirs.length,
    checked_answers: results.length,
    failures: failures.map(({ task_id, answer_name, reason }) => ({ task_id, answer_name, reason })),
  }, null, 2)}\n`);

  if (failures.length > 0) process.exitCode = 1;
}

async function verifySingleAnswer({ task, schemas, answerPath }) {
  const verifierDir = path.join(task.taskDir, "verifier");
  const verifierSpecPath = path.join(verifierDir, "verifier.spec.json");
  const verifierSpec = await readJson(verifierSpecPath);
  assertSchema(`${task.spec.task_id}/verifier.spec.json`, schemas.validateVerifierSpec, verifierSpec);
  const rows = await readObservations(task.taskDir);
  const capturedEvidence = new Set(rows.flatMap((row) => row.evidence_ids));
  const answer = await readJson(answerPath);
  const result = verifyAnswer({
    answer,
    answerPath: path.relative(repoRoot, answerPath),
    verifierSpec,
    capturedEvidence,
    schemas,
  });
  assertSchema(`${task.spec.task_id}/single answer result`, schemas.validateVerifierResult, result);
  return result;
}

async function loadSchemas() {
  const ajv = new Ajv({ allErrors: true, strict: false });
  const schemas = {
    shared: await readJson(path.join(schemaRoot, "task-output.schema.json")),
    verifierSpec: await readJson(path.join(schemaRoot, "verifier-spec.schema.json")),
    verifierResult: await readJson(path.join(schemaRoot, "verifier-result.schema.json")),
    family: {},
  };
  for (const [family, schemaFile] of Object.entries(FAMILY_SCHEMAS)) {
    schemas.family[family] = await readJson(path.join(schemaRoot, schemaFile));
  }
  return {
    validateShared: ajv.compile(schemas.shared),
    validateVerifierSpec: ajv.compile(schemas.verifierSpec),
    validateVerifierResult: ajv.compile(schemas.verifierResult),
    validateFamily: Object.fromEntries(
      Object.entries(schemas.family).map(([family, schema]) => [family, ajv.compile(schema)]),
    ),
  };
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

async function writeVerifierFixtures(task, schemas) {
  const verifierDir = path.join(task.taskDir, "verifier");
  await fs.mkdir(verifierDir, { recursive: true });

  const rows = await readObservations(task.taskDir);
  const expectation = expectationFor(task.spec.task_id);
  const verifierSpec = buildVerifierSpec(task.spec, rows, expectation);
  assertSchema("verifier.spec.json", schemas.validateVerifierSpec, verifierSpec);

  const passAnswer = buildPassAnswer(task.spec, rows, verifierSpec, expectation);
  const failAnswer = buildFailAnswer(passAnswer, verifierSpec);

  await writeJson(path.join(verifierDir, "verifier.spec.json"), verifierSpec);
  await writeJson(path.join(verifierDir, "expected.pass.json"), passAnswer);
  await writeJson(path.join(verifierDir, "expected.fail.json"), failAnswer);
}

async function verifyTaskFixtures(task, schemas) {
  const verifierDir = path.join(task.taskDir, "verifier");
  const verifierSpecPath = path.join(verifierDir, "verifier.spec.json");
  const passPath = path.join(verifierDir, "expected.pass.json");
  const failPath = path.join(verifierDir, "expected.fail.json");
  const verifierSpec = await readJson(verifierSpecPath);
  assertSchema(`${task.spec.task_id}/verifier.spec.json`, schemas.validateVerifierSpec, verifierSpec);

  const rows = await readObservations(task.taskDir);
  const capturedEvidence = new Set(rows.flatMap((row) => row.evidence_ids));
  const answerFiles = [
    { name: "expected.pass.json", path: passPath, expectedPassed: true, resultPath: path.join(verifierDir, "result.pass.json") },
    { name: "expected.fail.json", path: failPath, expectedPassed: false, resultPath: path.join(verifierDir, "result.fail.json") },
  ];

  const outcomes = [];
  for (const answerFile of answerFiles) {
    const answer = await readJson(answerFile.path);
    const result = verifyAnswer({
      answer,
      answerPath: path.relative(repoRoot, answerFile.path),
      verifierSpec,
      capturedEvidence,
      schemas,
    });
    assertSchema(`${task.spec.task_id}/${answerFile.name} result`, schemas.validateVerifierResult, result);
    if (writeResults) await writeJson(answerFile.resultPath, result);
    outcomes.push({
      task_id: task.spec.task_id,
      answer_name: answerFile.name,
      accepted: result.passed === answerFile.expectedPassed,
      reason: result.passed === answerFile.expectedPassed
        ? "matched expected verifier outcome"
        : `expected passed=${answerFile.expectedPassed}, got passed=${result.passed}`,
    });
  }
  return outcomes;
}

function buildVerifierSpec(spec, rows, expectation) {
  const requiredEvidenceIds = [
    ...(expectation.toolEvidence ?? []).map((suffix) => `tool_io:${spec.task_id}/${suffix}`),
    ...expectation.evidence,
  ];
  return {
    schema_version: "agent_native_seed_verifier_spec.v0",
    task_id: spec.task_id,
    family: spec.family,
    output_schema: "../../../../schema/task-output.schema.json",
    family_output_schema: `../../../../schema/${FAMILY_SCHEMAS[spec.family]}`,
    required: {
      evidence_ids: requiredEvidenceIds,
      captured_evidence_only: true,
    },
    family_output_checks: buildFamilyOutputChecks(spec, expectation),
  };
}

function buildFamilyOutputChecks(spec, expectation) {
  if (spec.family === "flowcyto") {
    return [
      { path: "family_output.report_status", equals: expectation.flowcyto.reportStatus },
      { path: "family_output.validation_error_code", equals: expectation.flowcyto.validationErrorCode },
    ];
  }
  if (spec.family === "molecule-biology") {
    const checks = [
      { path: "family_output.operation", equals: expectation.molecule.operation },
      { path: "family_output.molecule_id", equals: expectation.molecule.moleculeId },
      { path: "family_output.workspace_revision", equals: expectation.molecule.workspaceRevision },
    ];
    if (expectation.molecule.featureIds) checks.push({ path: "family_output.feature_ids", contains_all: expectation.molecule.featureIds });
    if (expectation.molecule.primerIds) checks.push({ path: "family_output.primer_ids", contains_all: expectation.molecule.primerIds });
    if (expectation.molecule.orfIds) checks.push({ path: "family_output.orf_ids", contains_all: expectation.molecule.orfIds });
    if (expectation.molecule.translationRefs) checks.push({ path: "family_output.translation_refs", contains_all: expectation.molecule.translationRefs });
    if (expectation.molecule.exportPath) checks.push({ path: "family_output.export_path", equals: expectation.molecule.exportPath });
    return checks;
  }
  if (spec.family === "protein-mcp") {
    const checks = [
      { path: "family_output.operation", equals: expectation.protein.operation },
      { path: "family_output.structure_id", equals: expectation.protein.structureId },
      { path: "family_output.workspace_revision", equals: expectation.protein.workspaceRevision },
    ];
    if (expectation.protein.ligandIds) checks.push({ path: "family_output.ligand_ids", contains_all: expectation.protein.ligandIds });
    if (expectation.protein.viewId) checks.push({ path: "family_output.view_id", equals: expectation.protein.viewId });
    return checks;
  }
  throw new Error(`${spec.task_id}: unsupported family ${spec.family}`);
}

function buildPassAnswer(spec, rows, verifierSpec, expectation) {
  const summary = passSummary(spec.task_id);
  const output = {
    task_id: spec.task_id,
    family: spec.family,
    diagnosis: {
      class: expectation.diagnosisClass,
      summary,
    },
    evidence_ids: verifierSpec.required.evidence_ids,
    next_action: {
      type: expectation.nextActionType,
      summary: nextActionSummary(expectation.nextActionType),
    },
    missing_fields: expectation.missingFields,
    forbidden_actions_avoided: expectation.forbiddenActionsAvoided,
    family_output: {},
  };

  if (spec.family === "flowcyto") output.family_output = buildFlowcytoFamilyOutput(rows, expectation);
  if (spec.family === "molecule-biology") output.family_output = buildMoleculeFamilyOutput(rows, verifierSpec, expectation);
  if (spec.family === "protein-mcp") output.family_output = buildProteinFamilyOutput(rows, verifierSpec, expectation);

  return output;
}

function buildFlowcytoFamilyOutput(rows, expectation) {
  const last = rows.at(-1);
  const stats = rows.find((row) => row.tool_name === "compute_gate_stats")?.observation;
  const qc = rows.find((row) => row.tool_name === "validate_gate_qc")?.observation;
  return {
    workspace_path: last.observation.workspacePath,
    workspace_revision: last.workspace_revision,
    sample_id: "sample_001",
    gate_id: "agent_main_population_gate",
    report_status: expectation.flowcyto.reportStatus,
    evidence_refs: {
      stats_ref: stats?.evidenceRef ?? "tool_io:missing/stats",
      qc_ref: qc?.evidenceRef ?? "tool_io:missing/qc",
    },
    validation_error_code: expectation.flowcyto.validationErrorCode,
    recovery_action: expectation.flowcyto.recoveryAction,
  };
}

function buildMoleculeFamilyOutput(rows, verifierSpec, expectation) {
  const workspacePath = rows.find((row) => row.observation.workspacePath)?.observation.workspacePath;
  const output = {
    workspace_path: workspacePath,
    workspace_revision: expectation.molecule.workspaceRevision,
    molecule_id: expectation.molecule.moleculeId,
    operation: expectation.molecule.operation,
    tool_result_refs: verifierSpec.required.evidence_ids,
  };
  if (expectation.molecule.featureIds) output.feature_ids = expectation.molecule.featureIds;
  if (expectation.molecule.primerIds) output.primer_ids = expectation.molecule.primerIds;
  if (expectation.molecule.orfIds) output.orf_ids = expectation.molecule.orfIds;
  if (expectation.molecule.translationRefs) output.translation_refs = expectation.molecule.translationRefs;
  if (expectation.molecule.exportPath) output.export_path = expectation.molecule.exportPath;
  return output;
}

function buildProteinFamilyOutput(rows, verifierSpec, expectation) {
  const workspacePath = rows.find((row) => row.observation.result?.workspacePath)?.observation.result.workspacePath;
  const scene = rows.findLast((row) => row.tool_name === "get_scene_annotations")?.observation.result;
  const annotations = scene?.annotations?.map((annotation) => annotation.id) ?? [];
  const measurements = scene?.measurements?.map((measurement) => measurement.id) ?? [];
  return {
    workspace_path: workspacePath,
    workspace_revision: expectation.protein.workspaceRevision,
    structure_id: expectation.protein.structureId,
    operation: expectation.protein.operation,
    tool_result_refs: verifierSpec.required.evidence_ids,
    ...(expectation.protein.ligandIds ? { ligand_ids: expectation.protein.ligandIds } : {}),
    ...(expectation.protein.chainIds ? { chain_ids: expectation.protein.chainIds } : {}),
    ...(annotations.length > 0 ? { annotation_ids: annotations } : {}),
    ...(measurements.length > 0 ? { measurement_ids: measurements } : {}),
    ...(expectation.protein.viewId ? { view_id: expectation.protein.viewId } : {}),
  };
}

function buildFailAnswer(passAnswer, verifierSpec) {
  const failAnswer = structuredClone(passAnswer);
  failAnswer.evidence_ids = failAnswer.evidence_ids.filter((id) => id !== verifierSpec.required.evidence_ids[0]);
  failAnswer.diagnosis.summary = "Verifier-negative fixture: one required evidence id is intentionally missing.";
  return failAnswer;
}

function verifyAnswer({ answer, answerPath, verifierSpec, capturedEvidence, schemas }) {
  const checks = [];
  checks.push(schemaCheck("shared_output_schema", schemas.validateShared, answer));

  const familyValidator = schemas.validateFamily[verifierSpec.family];
  checks.push(schemaCheck("family_output_schema", familyValidator, answer.family_output));

  pushExact(checks, "task_id", answer.task_id, verifierSpec.task_id);
  pushExact(checks, "family", answer.family, verifierSpec.family);
  for (const evidenceId of verifierSpec.required.evidence_ids) {
    pushContains(checks, "required evidence id", answer.evidence_ids, evidenceId);
    if (verifierSpec.required.captured_evidence_only) {
      checks.push({
        name: "captured evidence id",
        passed: capturedEvidence.has(evidenceId),
        message: capturedEvidence.has(evidenceId)
          ? `captured evidence contains ${evidenceId}`
          : `captured observations do not contain ${evidenceId}`,
        expected: evidenceId,
      });
    }
  }
  for (const fieldCheck of verifierSpec.family_output_checks) {
    const actual = getPath(answer, fieldCheck.path);
    if ("equals" in fieldCheck) pushExact(checks, fieldCheck.path, actual, fieldCheck.equals);
    if ("contains_all" in fieldCheck) {
      for (const value of fieldCheck.contains_all) pushContains(checks, fieldCheck.path, actual, value);
    }
  }
  return {
    schema_version: "agent_native_seed_verifier_result.v0",
    task_id: verifierSpec.task_id,
    family: verifierSpec.family,
    answer_path: answerPath,
    passed: checks.every((check) => check.passed),
    checks,
  };
}

function schemaCheck(name, validate, value) {
  const passed = validate(value);
  return {
    name,
    passed,
    message: passed ? `${name} passed` : `${name} failed`,
    actual: passed ? undefined : validate.errors,
  };
}

function pushExact(checks, name, actual, expected) {
  const passed = stableJson(actual) === stableJson(expected);
  checks.push({
    name,
    passed,
    message: passed ? `${name} matched` : `${name} mismatch`,
    expected,
    actual,
  });
}

function pushContains(checks, name, actual, expected) {
  const passed = Array.isArray(actual) && actual.some((entry) => stableJson(entry) === stableJson(expected));
  checks.push({
    name,
    passed,
    message: passed ? `${name} contains ${String(expected)}` : `${name} missing ${String(expected)}`,
    expected,
    actual,
  });
}

function assertSchema(label, validate, value) {
  if (!validate(value)) throw new Error(`${label} failed schema validation: ${JSON.stringify(validate.errors)}`);
}

function getPath(value, dottedPath) {
  return dottedPath.split(".").reduce((current, key) => current?.[key], value);
}

function stableJson(value) {
  if (value === undefined) return "undefined";
  return JSON.stringify(value);
}

async function readObservations(taskDir) {
  const content = await fs.readFile(path.join(taskDir, "tools", "tool-observations.jsonl"), "utf8");
  return content.trim().split(/\r?\n/).filter(Boolean).map((line) => JSON.parse(line));
}

function expectationFor(taskId) {
  const expectation = EXPECTATIONS[taskId];
  if (!expectation) throw new Error(`No verifier expectation for ${taskId}`);
  return structuredClone(expectation);
}

function passSummary(taskId) {
  return `Verifier-passing structured decision for ${taskId}.`;
}

function nextActionSummary(nextActionType) {
  const labels = {
    submit_report: "Submit the verified report with cited evidence.",
    repair_report: "Repair the report by adding required evidence fields.",
    repair_revision: "Retry with the current workspace revision.",
    validate_workspace: "Validate the workspace after evidence-backed inspection.",
    annotate_feature: "Persist the feature annotation through the domain tool.",
    upsert_primer: "Persist the primer through the domain tool.",
    simulate_digest: "Use the digest simulation output as the decision source.",
    simulate_pcr: "Use the PCR simulation output as the decision source.",
    export_genbank: "Export the edited molecule workspace through the domain tool.",
    translate_region: "Use the ORF and translation tool outputs as evidence.",
    annotate_binding_site: "Annotate the ligand binding site through Protein MCP.",
    update_protein_view: "Apply the protein view edit with the current workspace revision.",
    inspect_scene_annotations: "Inspect the repaired scene annotations from Protein MCP.",
  };
  return labels[nextActionType] ?? nextActionType;
}

async function readJson(filePath) {
  return JSON.parse(await fs.readFile(filePath, "utf8"));
}

async function writeJson(filePath, value) {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.writeFile(filePath, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

export async function verifyTaskAnswer({ taskDir, answer, answerPath }) {
  const schemas = await loadSchemas();
  const task = { taskDir, spec: await readJson(path.join(taskDir, "task.spec.json")) };
  const verifierSpec = await readJson(path.join(taskDir, "verifier", "verifier.spec.json"));
  assertSchema(`${task.spec.task_id}/verifier.spec.json`, schemas.validateVerifierSpec, verifierSpec);
  const rows = await readObservations(task.taskDir);
  return verifyAnswer({
    answer,
    answerPath,
    verifierSpec,
    capturedEvidence: new Set(rows.flatMap((row) => row.evidence_ids)),
    schemas,
  });
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  main().catch((error) => {
    process.stderr.write(`${error.stack ?? error.message}\n`);
    process.exitCode = 1;
  });
}
