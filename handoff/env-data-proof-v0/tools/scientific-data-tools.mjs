#!/usr/bin/env node
import { createHash } from "node:crypto";
import http from "node:http";
import https from "node:https";
import { mkdir, readFile, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptPath = fileURLToPath(import.meta.url);
const root = path.resolve(path.dirname(scriptPath), "..");
const worldsRoot = path.join(root, "worlds");

const sharedOutputSchema = "../../schema/scientific-data-task-output.schema.json";

const toolDefinitions = {
  "workspace.list_files": "List fixture files available to the agent.",
  "artifact.read_text": "Read an approved fixture text artifact or excerpt.",
  "provenance.inspect": "Inspect public source provenance, pin, license review state, and publication policy.",
  "fastqc.parse_report": "Parse FastQC modules, statuses, basic statistics, and failed checks.",
  "single_cell.inspect_qc_table": "Inspect a locked single-cell QC summary table.",
  "flowcyto.parse_fcs_keywords": "Parse FCS keyword metadata, channels, event count, and marker labels.",
  "flowcyto.parse_compensation_matrix": "Parse flow cytometry compensation matrix channels and values.",
  "protein.parse_mmcif_metadata": "Parse structure id, method, resolution, polymer entities, nonpolymer ligands, and title.",
  "alignment.parse_qualimap": "Parse mapped reads, aligned bases, mapping quality, coverage, and relevant warnings.",
  "qc_policy.evaluate": "Apply a declared deterministic QC policy to parsed metrics.",
  "verifier.submit_answer": "Submit a structured scientific-data answer to the deterministic verifier."
};

const worlds = [
  {
    worldId: "fastq-qc-nanopore-fail-001",
    domain: "FASTQ sequencing QC",
    prompt: "Inspect the sequencing QC fixture workspace and produce a structured QC decision. Cite evidence ids for the sample, failed checks, and next action. Do not use live web access.",
    expectedClass: "fastq_qc_decision",
    expectedNextAction: "trim_or_filter_reads",
    severity: "fail",
    sourceId: "source:multiqc-fastqc-nan-reads",
    primaryUrl: "https://raw.githubusercontent.com/MultiQC/test-data/main/data/modules/fastqc/nan_reads/fastqc_data.txt",
    sources: [
      {
        source_id: "source:multiqc-fastqc-nan-reads",
        url: "https://raw.githubusercontent.com/MultiQC/test-data/main/data/modules/fastqc/nan_reads/fastqc_data.txt",
        kind: "fastqc_report",
        license_review: "pending",
        pin: {
          repo: "MultiQC/test-data",
          commit: "84dc905e6edb97668b87660896dfd78f175008ca",
          etag: "ab8d2041df37698afb21c147042360174aadbbe97e976c6cfbd677141bbb561f"
        }
      }
    ],
    allowedTools: [
      "workspace.list_files",
      "provenance.inspect",
      "artifact.read_text",
      "fastqc.parse_report",
      "qc_policy.evaluate",
      "verifier.submit_answer"
    ],
    forbiddenTools: [
      "web.open",
      "shell.live_download",
      "vision.inspect_image"
    ]
  },
  {
    worldId: "single-cell-pbmc3k-qc-summary-001",
    domain: "single-cell RNA-seq QC",
    prompt: "Inspect the single-cell QC fixture workspace and produce a structured QC decision. Cite evidence ids for the sample, QC thresholds, affected cells, and next action. Do not call live 10x or Scanpy services.",
    expectedClass: "single_cell_qc_decision",
    expectedNextAction: "exclude_sample",
    severity: "warning",
    sourceId: "source:multiqc-checkatlas-pbmc3k-scanpy-qc",
    primaryUrl: "https://cf.10xgenomics.com/samples/cell-exp/1.1.0/pbmc3k/pbmc3k_filtered_gene_bc_matrices.tar.gz",
    sources: [
      {
        source_id: "source:10x-pbmc3k-filtered-matrix",
        url: "https://cf.10xgenomics.com/samples/cell-exp/1.1.0/pbmc3k/pbmc3k_filtered_gene_bc_matrices.tar.gz",
        kind: "single_cell_count_matrix",
        license_review: "pending",
        pin: {
          provider: "10x Genomics",
          last_modified: "2017-06-02",
          content_length: "7621991"
        }
      },
      {
        source_id: "source:multiqc-checkatlas-pbmc3k-scanpy-qc",
        url: "https://raw.githubusercontent.com/MultiQC/test-data/main/data/modules/checkatlas/2023/qc/pbmc_3k_scanpy.tsv",
        kind: "derived_single_cell_qc_table",
        license_review: "pending",
        pin: {
          repo: "MultiQC/test-data",
          commit: "84dc905e6edb97668b87660896dfd78f175008ca"
        }
      },
      {
        source_id: "source:multiqc-checkatlas-pbmc3k-scanpy-summary",
        url: "https://raw.githubusercontent.com/MultiQC/test-data/main/data/modules/checkatlas/2023/summary/pbmc_3k_scanpy.tsv",
        kind: "derived_single_cell_summary",
        license_review: "pending",
        pin: {
          repo: "MultiQC/test-data",
          commit: "84dc905e6edb97668b87660896dfd78f175008ca"
        }
      }
    ],
    allowedTools: [
      "workspace.list_files",
      "provenance.inspect",
      "artifact.read_text",
      "single_cell.inspect_qc_table",
      "qc_policy.evaluate",
      "verifier.submit_answer"
    ],
    forbiddenTools: [
      "web.open",
      "shell.live_download",
      "vision.inspect_image"
    ]
  },
  {
    worldId: "flowcyto-fcs-compensation-metadata-001",
    domain: "flow cytometry metadata QC",
    prompt: "Inspect the flow cytometry metadata fixture workspace and produce a structured metadata QC decision. Cite evidence ids for channels, marker labels, compensation matrix coverage, and next action. Do not use plots or vision judgment.",
    expectedClass: "flowcyto_metadata_decision",
    expectedNextAction: "repair_metadata",
    severity: "warning",
    sourceId: "source:flowcore-fcs-e07",
    primaryUrl: "https://raw.githubusercontent.com/RGLab/flowCore/master/inst/extdata/0877408774.E07",
    sources: [
      {
        source_id: "source:flowcore-fcs-e07",
        url: "https://raw.githubusercontent.com/RGLab/flowCore/master/inst/extdata/0877408774.E07",
        kind: "fcs_file",
        license_review: "pending",
        pin: {
          repo: "RGLab/flowCore",
          commit: "4935c7bf318697b3128ee50dae81018a6b246ab8",
          etag: "9c15c60e305c825fca67aae73643cafedab83b1bcfcd4bbbdd0da865ce73ba9a"
        }
      },
      {
        source_id: "source:flowcore-compmatrix",
        url: "https://raw.githubusercontent.com/RGLab/flowCore/master/inst/extdata/compdata/compmatrix",
        kind: "compensation_matrix",
        license_review: "pending",
        pin: {
          repo: "RGLab/flowCore",
          commit: "4935c7bf318697b3128ee50dae81018a6b246ab8",
          etag: "01cab8ac508712ec0134b24a4f93ba54ea616c32c8457d09f420d2d52fc01e1d"
        }
      }
    ],
    allowedTools: [
      "workspace.list_files",
      "provenance.inspect",
      "artifact.read_text",
      "flowcyto.parse_fcs_keywords",
      "flowcyto.parse_compensation_matrix",
      "qc_policy.evaluate",
      "verifier.submit_answer"
    ],
    forbiddenTools: [
      "web.open",
      "shell.live_download",
      "vision.inspect_image"
    ]
  },
  {
    worldId: "protein-structure-ap5a-prep-001",
    domain: "protein structure preparation QC",
    prompt: "Inspect the protein structure fixture workspace and produce a structured preparation decision. Cite evidence ids for structure id, method, resolution, ligand, entities, and next action. Do not claim docking or design results.",
    expectedClass: "protein_structure_prep_decision",
    expectedNextAction: "prepare_structure",
    severity: "pass",
    sourceId: "source:rcsb-1ake-cif",
    primaryUrl: "https://files.rcsb.org/download/1AKE.cif",
    sources: [
      {
        source_id: "source:rcsb-1ake-cif",
        url: "https://files.rcsb.org/download/1AKE.cif",
        kind: "mmcif_structure",
        license_review: "pending",
        pin: {
          provider: "RCSB PDB",
          structure_id: "1AKE",
          verified_on: "2026-05-29"
        }
      },
      {
        source_id: "source:rcsb-1ake-entry-json",
        url: "https://data.rcsb.org/rest/v1/core/entry/1AKE",
        kind: "structure_entry_json",
        license_review: "pending",
        pin: {
          provider: "RCSB PDB",
          structure_id: "1AKE",
          verified_on: "2026-05-29"
        }
      }
    ],
    allowedTools: [
      "workspace.list_files",
      "provenance.inspect",
      "artifact.read_text",
      "protein.parse_mmcif_metadata",
      "qc_policy.evaluate",
      "verifier.submit_answer"
    ],
    forbiddenTools: [
      "web.open",
      "shell.live_download",
      "vision.inspect_image"
    ]
  },
  {
    worldId: "rnaseq-alignment-qualimap-low-mapq-001",
    domain: "RNA-seq alignment result QC",
    prompt: "Inspect the RNA-seq alignment QC fixture workspace and produce a structured workflow-result decision. Cite evidence ids for mapping rate, aligned bases, mapping quality, coverage, and next action. Do not treat a single favorable metric as sufficient.",
    expectedClass: "workflow_result_qc_decision",
    expectedNextAction: "rerun_analysis",
    severity: "fail",
    sourceId: "source:multiqc-qualimap-zero-aligned",
    primaryUrl: "https://raw.githubusercontent.com/MultiQC/test-data/main/data/modules/qualimap/bam_qc/issue_2199_zero_aligned/genome_results.txt",
    sources: [
      {
        source_id: "source:multiqc-qualimap-zero-aligned",
        url: "https://raw.githubusercontent.com/MultiQC/test-data/main/data/modules/qualimap/bam_qc/issue_2199_zero_aligned/genome_results.txt",
        kind: "qualimap_bamqc_report",
        license_review: "pending",
        pin: {
          repo: "MultiQC/test-data",
          commit: "84dc905e6edb97668b87660896dfd78f175008ca",
          etag: "de299db987e8c038368088c7584ef2fac900839e7353ebeb1a8c1a13b3bc647b"
        }
      }
    ],
    allowedTools: [
      "workspace.list_files",
      "provenance.inspect",
      "artifact.read_text",
      "alignment.parse_qualimap",
      "qc_policy.evaluate",
      "verifier.submit_answer"
    ],
    forbiddenTools: [
      "web.open",
      "shell.live_download",
      "vision.inspect_image"
    ]
  }
];

function worldDir(world) {
  return path.join(worldsRoot, world.worldId);
}

async function ensureDir(dir) {
  await mkdir(dir, { recursive: true });
}

async function writeJson(filePath, value) {
  await ensureDir(path.dirname(filePath));
  await writeFile(filePath, `${JSON.stringify(value, null, 2)}\n`);
}

function normalizedTextBytes(value) {
  const normalized = value
    .replace(/\r\n|\r/g, "\n")
    .split("\n")
    .map((line) => line.trimEnd())
    .join("\n");
  return Buffer.from(normalized.endsWith("\n") ? normalized : `${normalized}\n`);
}

async function writeText(filePath, value) {
  await ensureDir(path.dirname(filePath));
  await writeFile(filePath, normalizedTextBytes(value));
}

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

async function fetchBuffer(url, redirectCount = 0) {
  if (redirectCount > 3) {
    throw new Error(`fetch redirect limit exceeded ${url}`);
  }
  const parsedUrl = new URL(url);
  const client = parsedUrl.protocol === "https:" ? https : http;
  return await new Promise((resolve, reject) => {
    const request = client.get(parsedUrl, { headers: { "User-Agent": "datalox-env-data-proof-v0" } }, (response) => {
      const statusCode = response.statusCode ?? 0;
      if (statusCode >= 300 && statusCode < 400 && response.headers.location) {
        response.resume();
        fetchBuffer(new URL(response.headers.location, parsedUrl).toString(), redirectCount + 1).then(resolve, reject);
        return;
      }
      if (statusCode < 200 || statusCode >= 300) {
        response.resume();
        reject(new Error(`fetch failed ${statusCode} ${url}`));
        return;
      }
      const chunks = [];
      response.on("data", (chunk) => chunks.push(Buffer.from(chunk)));
      response.on("end", () => resolve(Buffer.concat(chunks)));
    });
    request.setTimeout(60000, () => request.destroy(new Error(`fetch timeout ${url}`)));
    request.on("error", reject);
  });
}

async function fetchText(url) {
  return (await fetchBuffer(url)).toString("utf8");
}

function parseFastqcReport(text) {
  const lines = text.split(/\r?\n/);
  const basic = {};
  const modules = [];
  let current = null;
  for (const line of lines) {
    const moduleMatch = /^>>(.+?)\t(\w+)/.exec(line);
    if (moduleMatch) {
      current = { name: moduleMatch[1], status: moduleMatch[2], rows: [] };
      modules.push(current);
      continue;
    }
    if (line === ">>END_MODULE") {
      current = null;
      continue;
    }
    if (current) {
      current.rows.push(line);
      if (current.name === "Basic Statistics" && line && !line.startsWith("#")) {
        const [key, value] = line.split("\t");
        if (key && value !== undefined) {
          basic[key] = value;
        }
      }
    }
  }
  return {
    evidence_id: "metric:fastqc.parsed_report",
    sample_id: basic.Filename,
    basic_statistics: basic,
    module_statuses: modules.map((module) => ({
      name: module.name,
      status: module.status
    })),
    failed_modules: modules.filter((module) => module.status === "fail").map((module) => module.name),
    warning_modules: modules.filter((module) => module.status === "warn").map((module) => module.name)
  };
}

function parseTsv(text) {
  const [headerLine, ...lines] = text.trim().split(/\r?\n/);
  const headers = headerLine.split("\t");
  return lines.filter(Boolean).map((line) => {
    const cells = line.split("\t");
    return Object.fromEntries(headers.map((header, index) => [header, cells[index] ?? ""]));
  });
}

function parseSingleCellQc(qcText, summaryText) {
  const qcRows = parseTsv(qcText).map((row) => ({
    n_genes_by_counts: Number(row.n_genes_by_counts),
    total_counts: Number(row.total_counts),
    cellrank_n_genes_by_counts: Number(row.cellrank_n_genes_by_counts),
    cellrank_total_counts: Number(row.cellrank_total_counts),
    cell_index: Number(row.cell_index)
  }));
  const summary = parseTsv(summaryText)[0];
  const highTotalCountCells = qcRows.filter((row) => row.total_counts > 500).map((row) => row.cell_index);
  const topCells = [...qcRows]
    .sort((a, b) => b.total_counts - a.total_counts)
    .slice(0, 10);
  return {
    evidence_id: "metric:single_cell.pbmc3k_qc_summary",
    dataset_id: "pbmc_3k_scanpy",
    summary: {
      cells: Number(summary.NbCells),
      genes: Number(summary.NbGenes),
      anndata_raw: summary["AnnData.raw"] === "True",
      anndata_x: summary["AnnData.X"] === "True"
    },
    policy_thresholds: {
      high_total_counts_gt: 500
    },
    high_total_count_cells: highTotalCountCells,
    top_total_count_cells: topCells
  };
}

function parseFcsKeywords(buffer) {
  const text = buffer.toString("latin1");
  const keyword = (key) => {
    const marker = `\\${key}\\`;
    const start = text.indexOf(marker);
    if (start === -1) {
      return null;
    }
    const valueStart = start + marker.length;
    const valueEnd = text.indexOf("\\", valueStart);
    return valueEnd === -1 ? text.slice(valueStart).trim() : text.slice(valueStart, valueEnd).trim();
  };
  const parameterCount = Number(keyword("$PAR"));
  const channels = [];
  for (let index = 1; index <= parameterCount; index += 1) {
    channels.push({
      index,
      name: keyword(`$P${index}N`),
      marker_label: keyword(`$P${index}S`) ?? ""
    });
  }
  return {
    evidence_id: "metric:flowcyto.fcs_keywords",
    file_id: "file:0877408774.E07",
    total_events: Number(keyword("$TOT")),
    parameter_count: parameterCount,
    cytometer: keyword("$CYT"),
    acquisition_start: keyword("$BTIM"),
    acquisition_end: keyword("$ETIM"),
    channels
  };
}

function parseCompensationMatrix(text) {
  const lines = text.trim().split(/\r\n|\n|\r/).map((line) => line.trim()).filter(Boolean);
  if (lines.length < 4) {
    throw new Error("compensation matrix source has too few rows");
  }
  const header = lines[2].split(/\t/);
  const rows = lines.slice(3).map((line, rowIndex) => {
    const values = line.split(/\t/).map(Number);
    return {
      channel: header[rowIndex],
      values: Object.fromEntries(header.map((channel, index) => [channel, values[index]]))
    };
  });
  return {
    evidence_id: "metric:flowcyto.compensation_matrix",
    matrix_id: lines[0],
    channels: header,
    rows
  };
}

function parseMmcifMetadata(cifText, entryJson) {
  const json = JSON.parse(entryJson);
  const ligandIds = [...new Set([...cifText.matchAll(/\b([A-Z0-9]{3})\s+non-polymer/g)].map((match) => match[1]))];
  if (/\bAP5\b/.test(cifText) && !ligandIds.includes("AP5")) {
    ligandIds.push("AP5");
  }
  return {
    evidence_id: "metric:protein.1ake_mmcif_metadata",
    structure_id: json.rcsb_id,
    title: json.struct?.title,
    experimental_method: json.exptl?.[0]?.method,
    resolution_angstrom: Number(json.rcsb_entry_info?.resolution_combined?.[0]),
    polymer_entity_count: Number(json.rcsb_entry_info?.polymer_entity_count),
    nonpolymer_entity_count: Number(json.rcsb_entry_info?.nonpolymer_entity_count),
    ligand_ids: ligandIds.sort()
  };
}

function parseQualimapReport(text) {
  const number = (regex) => {
    const match = regex.exec(text);
    return match ? Number(match[1].replace(/,/g, "")) : null;
  };
  const mappedMatch = /number of mapped reads = ([\d,]+) \(([\d.]+)%\)/.exec(text);
  return {
    evidence_id: "metric:qualimap.alignment_summary",
    read_count: number(/number of reads = ([\d,]+)/),
    mapped_reads: mappedMatch ? Number(mappedMatch[1].replace(/,/g, "")) : null,
    mapped_read_percentage: mappedMatch ? Number(mappedMatch[2]) : null,
    aligned_bases: number(/number of aligned bases = ([\d,]+) bp/),
    mean_mapping_quality: number(/mean mapping quality = ([\d.]+)/),
    mean_coverage: number(/mean coverageData = ([\d.]+)X/)
  };
}

function evaluatePolicy(world, metrics) {
  if (world.worldId === "fastq-qc-nanopore-fail-001") {
    return {
      evidence_id: "metric:fastq.policy_result",
      diagnosis_class: world.expectedClass,
      severity: "fail",
      next_action: "trim_or_filter_reads",
      checks: [
        {
          name: "per_base_sequence_quality",
          status: metrics.failed_modules.includes("Per base sequence quality") ? "fail" : "pass",
          observed: metrics.failed_modules.includes("Per base sequence quality") ? "module failed" : "module did not fail",
          evidence_id: "metric:fastqc.parsed_report"
        },
        {
          name: "adapter_content",
          status: metrics.failed_modules.includes("Adapter Content") ? "fail" : "pass",
          observed: metrics.failed_modules.includes("Adapter Content") ? "module failed" : "module did not fail",
          evidence_id: "metric:fastqc.parsed_report"
        }
      ]
    };
  }
  if (world.worldId === "single-cell-pbmc3k-qc-summary-001") {
    return {
      evidence_id: "metric:single_cell.policy_result",
      diagnosis_class: world.expectedClass,
      severity: metrics.high_total_count_cells.length > 0 ? "warning" : "pass",
      next_action: "exclude_sample",
      checks: [
        {
          name: "high_total_counts",
          status: metrics.high_total_count_cells.length > 0 ? "warning" : "pass",
          observed: `${metrics.high_total_count_cells.length} cells above total_counts > ${metrics.policy_thresholds.high_total_counts_gt}`,
          threshold: `total_counts > ${metrics.policy_thresholds.high_total_counts_gt}`,
          evidence_id: "metric:single_cell.pbmc3k_qc_summary"
        }
      ]
    };
  }
  if (world.worldId === "flowcyto-fcs-compensation-metadata-001") {
    const fluorescenceChannels = metrics.fcs.channels
      .map((channel) => channel.name)
      .filter((name) => /^FL\d-[HA]$/.test(name));
    const missingMarkerLabels = metrics.fcs.channels
      .filter((channel) => /^FL\d-H$/.test(channel.name) && !channel.marker_label)
      .map((channel) => channel.name);
    const uncoveredChannels = fluorescenceChannels.filter((channel) => channel.endsWith("-H") && !metrics.compensation.channels.includes(channel));
    return {
      evidence_id: "metric:flowcyto.policy_result",
      diagnosis_class: world.expectedClass,
      severity: missingMarkerLabels.length > 0 || uncoveredChannels.length > 0 ? "warning" : "pass",
      next_action: "repair_metadata",
      checks: [
        {
          name: "marker_label_coverage",
          status: missingMarkerLabels.length > 0 ? "warning" : "pass",
          observed: missingMarkerLabels.length > 0 ? `missing labels for ${missingMarkerLabels.join(", ")}` : "all fluorescence channels have marker labels",
          evidence_id: "metric:flowcyto.fcs_keywords"
        },
        {
          name: "compensation_channel_coverage",
          status: uncoveredChannels.length > 0 ? "warning" : "pass",
          observed: uncoveredChannels.length > 0 ? `uncovered channels ${uncoveredChannels.join(", ")}` : "height fluorescence channels covered by matrix",
          evidence_id: "metric:flowcyto.compensation_matrix"
        }
      ]
    };
  }
  if (world.worldId === "protein-structure-ap5a-prep-001") {
    return {
      evidence_id: "metric:protein.policy_result",
      diagnosis_class: world.expectedClass,
      severity: metrics.experimental_method === "X-RAY DIFFRACTION" && metrics.resolution_angstrom <= 2.5 && metrics.ligand_ids.includes("AP5") ? "pass" : "warning",
      next_action: "prepare_structure",
      checks: [
        {
          name: "resolution",
          status: metrics.resolution_angstrom <= 2.5 ? "pass" : "warning",
          observed: `${metrics.resolution_angstrom} A`,
          threshold: "<= 2.5 A for v0 structure-prep seed",
          evidence_id: "metric:protein.1ake_mmcif_metadata"
        },
        {
          name: "ligand_present",
          status: metrics.ligand_ids.includes("AP5") ? "pass" : "fail",
          observed: metrics.ligand_ids.join(", "),
          evidence_id: "metric:protein.1ake_mmcif_metadata"
        }
      ]
    };
  }
  if (world.worldId === "rnaseq-alignment-qualimap-low-mapq-001") {
    return {
      evidence_id: "metric:alignment.policy_result",
      diagnosis_class: world.expectedClass,
      severity: metrics.aligned_bases === 0 || metrics.mean_mapping_quality < 10 || metrics.mean_coverage < 1 ? "fail" : "pass",
      next_action: "rerun_analysis",
      checks: [
        {
          name: "aligned_bases",
          status: metrics.aligned_bases === 0 ? "fail" : "pass",
          observed: `${metrics.aligned_bases} bp`,
          threshold: "> 0 bp",
          evidence_id: "metric:qualimap.alignment_summary"
        },
        {
          name: "mean_mapping_quality",
          status: metrics.mean_mapping_quality < 10 ? "fail" : "pass",
          observed: String(metrics.mean_mapping_quality),
          threshold: ">= 10",
          evidence_id: "metric:qualimap.alignment_summary"
        },
        {
          name: "mean_coverage",
          status: metrics.mean_coverage < 1 ? "fail" : "pass",
          observed: `${metrics.mean_coverage}X`,
          threshold: ">= 1X",
          evidence_id: "metric:qualimap.alignment_summary"
        }
      ]
    };
  }
  throw new Error(`no policy for ${world.worldId}`);
}

function excerpt(text, patterns) {
  const lines = text.split(/\r?\n/);
  const keep = new Set();
  for (const [index, line] of lines.entries()) {
    if (patterns.some((pattern) => pattern.test(line))) {
      for (let offset = -2; offset <= 2; offset += 1) {
        const target = index + offset;
        if (target >= 0 && target < lines.length) {
          keep.add(target);
        }
      }
    }
  }
  return [...keep].sort((a, b) => a - b).map((index) => lines[index]).join("\n");
}

function qualimapExcerpt(text) {
  return excerpt(text, [/number of reads/, /number of mapped reads/, /number of aligned bases/, /mean mapping quality/, /mean coverageData/])
    .split("\n")
    .map((line) => line.replace(/^>>>>>>>[ \t]+(.+)$/, "section: $1"))
    .join("\n");
}

async function buildStep1() {
  for (const world of worlds) {
    const dir = worldDir(world);
    await ensureDir(dir);
    await writeJson(path.join(dir, "task.spec.json"), {
      schema_version: "scientific_data_task_spec.v0",
      world_id: world.worldId,
      split: "seed",
      task_family: "scientific-data-qc-basic",
      domain: world.domain,
      prompt: world.prompt,
      output_schema: sharedOutputSchema,
      allowed_tools: world.allowedTools,
      forbidden_tools: world.forbiddenTools,
      minimum_replayed_observations: 5,
      success_criteria: [
        "output validates against scientific-data-task-output.schema.json",
        "diagnosis.class matches the verifier spec",
        "required computed checks cite replay evidence ids",
        "next_action.type matches the verifier spec",
        "no forbidden action is claimed"
      ],
      publication_state: "draft_step_1_task_spec"
    });
  }
}

async function buildStep2() {
  for (const world of worlds) {
    await writeJson(path.join(worldDir(world), "provenance.json"), {
      schema_version: "scientific_data_provenance.v0",
      world_id: world.worldId,
      primary_source_id: world.sourceId,
      sources: world.sources,
      publication_policy: {
        copy_source_artifact: false,
        publish_derived_observations: true,
        reason: "Publish provenance URL, parser outputs, and evidence ids first; copy raw artifacts only after license review."
      }
    });
  }
}

async function buildStep3() {
  for (const world of worlds) {
    const dir = worldDir(world);
    const derivedDir = path.join(dir, "artifacts", "derived");
    await ensureDir(derivedDir);
    const artifacts = [];
    if (world.worldId === "fastq-qc-nanopore-fail-001") {
      const raw = await fetchText(world.primaryUrl);
      const metrics = parseFastqcReport(raw);
      const policy = evaluatePolicy(world, metrics);
      await addDerivedText(world, artifacts, "file:fastqc_excerpt", "fastqc_excerpt.txt", excerpt(raw, [/^Filename\t/, /^Total Sequences\t/, /^Sequence length\t/, /^>>.*\t(fail|warn)/]), "derived_excerpt", world.sourceId);
      await addDerivedJson(world, artifacts, "file:fastqc_metrics", "fastqc_metrics.json", metrics, "parser_output", world.sourceId);
      await addDerivedJson(world, artifacts, "file:fastqc_policy_result", "fastqc_policy_result.json", policy, "policy_output", world.sourceId);
    } else if (world.worldId === "single-cell-pbmc3k-qc-summary-001") {
      const qc = await fetchText("https://raw.githubusercontent.com/MultiQC/test-data/main/data/modules/checkatlas/2023/qc/pbmc_3k_scanpy.tsv");
      const summary = await fetchText("https://raw.githubusercontent.com/MultiQC/test-data/main/data/modules/checkatlas/2023/summary/pbmc_3k_scanpy.tsv");
      const metrics = parseSingleCellQc(qc, summary);
      const policy = evaluatePolicy(world, metrics);
      await addDerivedText(world, artifacts, "file:single_cell_qc_excerpt", "single_cell_qc_excerpt.tsv", qc.split(/\r?\n/).slice(0, 16).join("\n"), "derived_excerpt", world.sourceId);
      await addDerivedJson(world, artifacts, "file:single_cell_qc_metrics", "single_cell_qc_metrics.json", metrics, "parser_output", world.sourceId);
      await addDerivedJson(world, artifacts, "file:single_cell_policy_result", "single_cell_policy_result.json", policy, "policy_output", world.sourceId);
    } else if (world.worldId === "flowcyto-fcs-compensation-metadata-001") {
      const fcs = await fetchBuffer(world.primaryUrl);
      const comp = await fetchText("https://raw.githubusercontent.com/RGLab/flowCore/master/inst/extdata/compdata/compmatrix");
      const fcsMetrics = parseFcsKeywords(fcs);
      const compMetrics = parseCompensationMatrix(comp);
      const policy = evaluatePolicy(world, { fcs: fcsMetrics, compensation: compMetrics });
      await addDerivedText(world, artifacts, "file:compmatrix_excerpt", "compmatrix_excerpt.txt", comp, "derived_excerpt", "source:flowcore-compmatrix");
      await addDerivedJson(world, artifacts, "file:fcs_keyword_metrics", "fcs_keyword_metrics.json", fcsMetrics, "parser_output", "source:flowcore-fcs-e07");
      await addDerivedJson(world, artifacts, "file:compensation_metrics", "compensation_metrics.json", compMetrics, "parser_output", "source:flowcore-compmatrix");
      await addDerivedJson(world, artifacts, "file:flowcyto_policy_result", "flowcyto_policy_result.json", policy, "policy_output", world.sourceId);
    } else if (world.worldId === "protein-structure-ap5a-prep-001") {
      const cif = await fetchText(world.primaryUrl);
      const entry = await fetchText("https://data.rcsb.org/rest/v1/core/entry/1AKE");
      const metrics = parseMmcifMetadata(cif, entry);
      const policy = evaluatePolicy(world, metrics);
      await addDerivedText(world, artifacts, "file:1ake_mmcif_excerpt", "1ake_mmcif_excerpt.txt", excerpt(cif, [/_entry.id/, /_exptl.method/, /_refine.ls_d_res_high/, /AP5/, /_struct.title/]), "derived_excerpt", "source:rcsb-1ake-cif");
      await addDerivedJson(world, artifacts, "file:1ake_metadata", "1ake_metadata.json", metrics, "parser_output", world.sourceId);
      await addDerivedJson(world, artifacts, "file:protein_policy_result", "protein_policy_result.json", policy, "policy_output", world.sourceId);
    } else if (world.worldId === "rnaseq-alignment-qualimap-low-mapq-001") {
      const raw = await fetchText(world.primaryUrl);
      const metrics = parseQualimapReport(raw);
      const policy = evaluatePolicy(world, metrics);
      await addDerivedText(world, artifacts, "file:qualimap_excerpt", "qualimap_excerpt.txt", qualimapExcerpt(raw), "derived_excerpt", world.sourceId);
      await addDerivedJson(world, artifacts, "file:qualimap_metrics", "qualimap_metrics.json", metrics, "parser_output", world.sourceId);
      await addDerivedJson(world, artifacts, "file:alignment_policy_result", "alignment_policy_result.json", policy, "policy_output", world.sourceId);
    } else {
      throw new Error(`no build step 3 for ${world.worldId}`);
    }
    await writeJson(path.join(dir, "artifacts", "manifest.json"), {
      schema_version: "fixture_artifact_manifest.v0",
      world_id: world.worldId,
      artifacts
    });
  }
}

async function addDerivedText(world, artifacts, artifactId, relativeName, content, kind, sourceId) {
  const filePath = path.join(worldDir(world), "artifacts", "derived", relativeName);
  await writeText(filePath, content);
  artifacts.push({
    artifact_id: artifactId,
    path: `artifacts/derived/${relativeName}`,
    kind,
    source_id: sourceId,
    sha256: sha256(normalizedTextBytes(content)),
    publish: true
  });
}

async function addDerivedJson(world, artifacts, artifactId, relativeName, value, kind, sourceId) {
  const json = `${JSON.stringify(value, null, 2)}\n`;
  const filePath = path.join(worldDir(world), "artifacts", "derived", relativeName);
  await writeText(filePath, json);
  artifacts.push({
    artifact_id: artifactId,
    path: `artifacts/derived/${relativeName}`,
    kind,
    source_id: sourceId,
    sha256: sha256(Buffer.from(json)),
    publish: true
  });
}

async function buildStep4() {
  for (const world of worlds) {
    const dir = worldDir(world);
    const manifest = JSON.parse(await readFile(path.join(dir, "artifacts", "manifest.json"), "utf8"));
    const files = manifest.artifacts.map((artifact) => artifact.path);
    const catalog = {
      schema_version: "scientific_data_tool_catalog.v0",
      world_id: world.worldId,
      tools: world.allowedTools.map((name) => ({
        name,
        description: toolDefinitions[name]
      }))
    };
    await writeJson(path.join(dir, "tools", "tool-catalog.json"), catalog);

    const observations = [
      {
        schema_version: "scientific_data_tool_observation.v0",
        sequence_index: 0,
        tool_name: "workspace.list_files",
        arguments: {},
        evidence_id: `tool_io:${world.worldId}/workspace.list_files/0`,
        observation: { files }
      },
      {
        schema_version: "scientific_data_tool_observation.v0",
        sequence_index: 1,
        tool_name: "provenance.inspect",
        arguments: { source_id: world.sourceId },
        evidence_id: `source:${world.worldId}/primary`,
        observation: {
          primary_source_id: world.sourceId,
          primary_url: world.primaryUrl,
          publication_policy: "publish derived observations first"
        }
      }
    ];

    let sequence = 2;
    for (const artifact of manifest.artifacts) {
      if (artifact.kind === "derived_excerpt") {
        const content = await readFile(path.join(dir, artifact.path), "utf8");
        observations.push({
          schema_version: "scientific_data_tool_observation.v0",
          sequence_index: sequence,
          tool_name: "artifact.read_text",
          arguments: { artifact_id: artifact.artifact_id },
          evidence_id: artifact.artifact_id,
          observation: { path: artifact.path, excerpt: content.slice(0, 1200) }
        });
        sequence += 1;
      }
      if (artifact.kind === "parser_output") {
        const parsed = JSON.parse(await readFile(path.join(dir, artifact.path), "utf8"));
        observations.push({
          schema_version: "scientific_data_tool_observation.v0",
          sequence_index: sequence,
          tool_name: parserToolFor(world.worldId),
          arguments: { artifact_id: artifact.artifact_id },
          evidence_id: parsed.evidence_id ?? artifact.artifact_id,
          observation: parsed
        });
        sequence += 1;
      }
      if (artifact.kind === "policy_output") {
        const parsed = JSON.parse(await readFile(path.join(dir, artifact.path), "utf8"));
        observations.push({
          schema_version: "scientific_data_tool_observation.v0",
          sequence_index: sequence,
          tool_name: "qc_policy.evaluate",
          arguments: { artifact_id: artifact.artifact_id },
          evidence_id: parsed.evidence_id ?? artifact.artifact_id,
          observation: parsed
        });
        sequence += 1;
      }
    }
    await writeText(path.join(dir, "tools", "tool-observations.jsonl"), observations.map((observation) => JSON.stringify(observation)).join("\n"));
  }
}

function parserToolFor(worldId) {
  if (worldId.startsWith("fastq-")) return "fastqc.parse_report";
  if (worldId.startsWith("single-cell-")) return "single_cell.inspect_qc_table";
  if (worldId.startsWith("flowcyto-")) return "flowcyto.parse_fcs_keywords";
  if (worldId.startsWith("protein-")) return "protein.parse_mmcif_metadata";
  if (worldId.startsWith("rnaseq-")) return "alignment.parse_qualimap";
  return "artifact.read_text";
}

async function validateStep1() {
  for (const world of worlds) {
    const spec = JSON.parse(await readFile(path.join(worldDir(world), "task.spec.json"), "utf8"));
    assert(spec.schema_version === "scientific_data_task_spec.v0", `${world.worldId} bad task spec schema`);
    assert(spec.world_id === world.worldId, `${world.worldId} task spec world mismatch`);
    assert(spec.output_schema === sharedOutputSchema, `${world.worldId} task spec schema path mismatch`);
    assert(spec.allowed_tools.length >= 5, `${world.worldId} has too few allowed tools`);
    assert(!spec.prompt.includes(world.expectedNextAction), `${world.worldId} prompt leaks next action`);
  }
  console.log(`step1 passed: ${worlds.length} task specs`);
}

async function validateStep2() {
  for (const world of worlds) {
    const provenance = JSON.parse(await readFile(path.join(worldDir(world), "provenance.json"), "utf8"));
    assert(provenance.schema_version === "scientific_data_provenance.v0", `${world.worldId} bad provenance schema`);
    assert(provenance.sources.length >= 1, `${world.worldId} missing sources`);
    assert(provenance.sources.every((source) => /^https?:\/\//.test(source.url)), `${world.worldId} has non-url source`);
    assert(provenance.publication_policy.copy_source_artifact === false, `${world.worldId} should not copy raw source by default`);
  }
  console.log(`step2 passed: ${worlds.length} provenance records`);
}

async function validateStep3() {
  for (const world of worlds) {
    const manifest = JSON.parse(await readFile(path.join(worldDir(world), "artifacts", "manifest.json"), "utf8"));
    assert(manifest.artifacts.length >= 2, `${world.worldId} needs at least 2 artifacts`);
    for (const artifact of manifest.artifacts) {
      const filePath = path.join(worldDir(world), artifact.path);
      const content = await readFile(filePath);
      assert(artifact.sha256 === sha256(content), `${world.worldId} sha mismatch ${artifact.path}`);
      assert((await stat(filePath)).size > 0, `${world.worldId} empty artifact ${artifact.path}`);
    }
  }
  console.log(`step3 passed: derived artifacts and manifests`);
}

async function validateStep4() {
  for (const world of worlds) {
    const catalog = JSON.parse(await readFile(path.join(worldDir(world), "tools", "tool-catalog.json"), "utf8"));
    assert(catalog.tools.length >= 5, `${world.worldId} tool catalog too small`);
    assert(catalog.tools.every((tool) => tool.description), `${world.worldId} has tool without description`);
    const observations = (await readFile(path.join(worldDir(world), "tools", "tool-observations.jsonl"), "utf8"))
      .trim()
      .split(/\r?\n/)
      .filter(Boolean)
      .map((line) => JSON.parse(line));
    assert(observations.length >= 5, `${world.worldId} needs at least 5 tool observations`);
    assert(observations.some((obs) => obs.tool_name === "qc_policy.evaluate"), `${world.worldId} missing policy observation`);
    assert(new Set(observations.map((obs) => obs.evidence_id)).size === observations.length, `${world.worldId} duplicate evidence ids`);
  }
  console.log(`step4 passed: tool catalogs and observations`);
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

async function buildThrough(step) {
  if (step >= 1) await buildStep1();
  if (step >= 2) await buildStep2();
  if (step >= 3) await buildStep3();
  if (step >= 4) await buildStep4();
}

async function validateThrough(step) {
  if (step >= 1) await validateStep1();
  if (step >= 2) await validateStep2();
  if (step >= 3) await validateStep3();
  if (step >= 4) await validateStep4();
}

const command = process.argv[2] ?? "validate-all";
const stepMap = {
  "build-step1": 1,
  "build-step2": 2,
  "build-step3": 3,
  "build-step4": 4,
  "validate-step1": 1,
  "validate-step2": 2,
  "validate-step3": 3,
  "validate-step4": 4,
  "build-all": 4,
  "validate-all": 4
};

if (!(command in stepMap)) {
  throw new Error(`unknown command ${command}`);
}

if (command.startsWith("build")) {
  await buildThrough(stepMap[command]);
  await validateThrough(stepMap[command]);
} else {
  await validateThrough(stepMap[command]);
}
