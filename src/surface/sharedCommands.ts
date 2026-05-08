import { readFile } from "node:fs/promises";
import path from "node:path";

import { z } from "zod";

import {
  adoptPack,
  lintLocalPack,
  maintainKnowledge,
  patchKnowledge,
  promoteGap,
  recordTurnResult,
  resolveLoop,
} from "../core/packCore.js";
import {
  exportAgentTaskTrajectories,
  recordAgentTaskTrajectory,
} from "../core/agentTaskTrajectoryExport.js";
import { exportTrajectories, recordTrajectory } from "../core/trajectoryExport.js";
import { gradeTrajectories } from "../core/trajectoryGrade.js";
import { repairTrajectory } from "../core/trajectoryRepair.js";
import { capturePdfArtifact } from "../core/pdfCapture.js";
import { publishWebCapture } from "../core/publishWebCapture.js";
import { captureDesignFromUrl, captureWebArtifact } from "../core/webCapture.js";

type CliArgsLike = Record<string, string | string[] | boolean> & { _: string[] };

type SharedArgKind = "string" | "boolean" | "string[]" | "int" | "enum" | "json";

interface SharedArgOption {
  canonical: string;
  cli?: string;
}

interface SharedArgSpec {
  key: string;
  description: string;
  kind: SharedArgKind;
  cliFlag?: string;
  cliPositionalIndex?: number;
  cliPositionalLabel?: string;
  mcpKey?: string;
  cliRequired?: boolean;
  mcpRequired?: boolean;
  positive?: boolean;
  options?: readonly SharedArgOption[];
}

export interface SharedCommandSpec {
  cliCommand?: string;
  mcpTool: string;
  description: string;
  args: readonly SharedArgSpec[];
  run(input: Record<string, unknown>): Promise<unknown>;
}

const artifactTypeOptions = [
  { canonical: "design_doc", cli: "design-doc" },
  { canonical: "design_tokens", cli: "design-tokens" },
  { canonical: "css_variables", cli: "css-variables" },
  { canonical: "tailwind_theme", cli: "tailwind-theme" },
  { canonical: "note", cli: "note" },
  { canonical: "source_page", cli: "source-page" },
] as const;

const repoPathArg: SharedArgSpec = {
  key: "repoPath",
  description: "Absolute or relative path to the host repo.",
  kind: "string",
  cliFlag: "repo",
  mcpKey: "repo_path",
  mcpRequired: true,
};

const taskArg: SharedArgSpec = {
  key: "task",
  description: "Current task text.",
  kind: "string",
  cliFlag: "task",
  mcpKey: "task",
};

const workflowArg: SharedArgSpec = {
  key: "workflow",
  description: "Workflow identifier.",
  kind: "string",
  cliFlag: "workflow",
  mcpKey: "workflow",
};

const stepArg: SharedArgSpec = {
  key: "step",
  description: "Current workflow step.",
  kind: "string",
  cliFlag: "step",
  mcpKey: "step",
};

const summaryArg: SharedArgSpec = {
  key: "summary",
  description: "Summary of the interaction or gap.",
  kind: "string",
  cliFlag: "summary",
  mcpKey: "summary",
};

const observationsArg: SharedArgSpec = {
  key: "observations",
  description: "Concrete observations from the current interaction.",
  kind: "string[]",
  cliFlag: "observation",
  mcpKey: "observations",
};

const changedFilesArg: SharedArgSpec = {
  key: "changedFiles",
  description: "Changed file paths relevant to the event.",
  kind: "string[]",
  cliFlag: "changed-file",
  mcpKey: "changed_files",
};

const transcriptArg: SharedArgSpec = {
  key: "transcript",
  description: "Optional transcript snippet for evidence.",
  kind: "string",
  cliFlag: "transcript",
  mcpKey: "transcript",
};

const tagsArg: SharedArgSpec = {
  key: "tags",
  description: "Tags attached to the command result.",
  kind: "string[]",
  cliFlag: "tag",
  mcpKey: "tags",
};

const titleArg: SharedArgSpec = {
  key: "title",
  description: "Human-readable title.",
  kind: "string",
  cliFlag: "title",
  mcpKey: "title",
};

const signalArg: SharedArgSpec = {
  key: "signal",
  description: "Recurring signal that triggered the work.",
  kind: "string",
  cliFlag: "signal",
  mcpKey: "signal",
};

const interpretationArg: SharedArgSpec = {
  key: "interpretation",
  description: "Interpretation of the signal.",
  kind: "string",
  cliFlag: "interpretation",
  mcpKey: "interpretation",
};

const recommendedActionArg: SharedArgSpec = {
  key: "recommendedAction",
  description: "Recommended next action.",
  kind: "string",
  cliFlag: "action",
  mcpKey: "recommended_action",
};

const outcomeArg: SharedArgSpec = {
  key: "outcome",
  description: "Observed outcome.",
  kind: "string",
  cliFlag: "outcome",
  mcpKey: "outcome",
};

const eventKindArg: SharedArgSpec = {
  key: "eventKind",
  description: "Event kind for the recorded interaction.",
  kind: "string",
  cliFlag: "event-kind",
  mcpKey: "event_kind",
};

const eventPathArg: SharedArgSpec = {
  key: "eventPath",
  description: "Relative or absolute path to a previously recorded event that provides durable-write provenance.",
  kind: "string",
  cliFlag: "event-path",
  mcpKey: "event_path",
};

const requiredEventPathArg: SharedArgSpec = {
  ...eventPathArg,
  cliRequired: true,
  mcpRequired: true,
};

const sessionIdArg: SharedArgSpec = {
  key: "sessionId",
  description: "Session identifier that can be paired with hostKind for durable-write provenance.",
  kind: "string",
  cliFlag: "session-id",
  mcpKey: "session_id",
};

const hostKindArg: SharedArgSpec = {
  key: "hostKind",
  description: "Host kind that can be paired with sessionId for durable-write provenance.",
  kind: "string",
  cliFlag: "host-kind",
  mcpKey: "host_kind",
};

const adminOverrideArg: SharedArgSpec = {
  key: "adminOverride",
  description: "Allow a manual durable write without event provenance.",
  kind: "boolean",
  cliFlag: "admin-override",
  mcpKey: "admin_override",
};
const eventClassOptions = [
  { canonical: "trace", cli: "trace" },
  { canonical: "candidate", cli: "candidate" },
] as const;

const eventClassArg: SharedArgSpec = {
  key: "eventClass",
  description: "Event class: trace for grounded history, candidate for promotable reusable gaps.",
  kind: "enum",
  cliFlag: "event-class",
  mcpKey: "event_class",
  options: eventClassOptions,
};

const adjudicationDecisionArg: SharedArgSpec = {
  key: "adjudicationDecision",
  description: "Structured promotion decision: record_trace, create_operational_note, patch_existing_skill, create_new_skill, or needs_more_evidence.",
  kind: "string",
  cliFlag: "decision",
  mcpKey: "adjudication_decision",
};

const adjudicationSkillIdArg: SharedArgSpec = {
  key: "adjudicationSkillId",
  description: "Optional skill id selected by the agent when the adjudication decision is patch_existing_skill.",
  kind: "string",
  cliFlag: "decision-skill",
  mcpKey: "adjudication_skill_id",
};

const skillArg: SharedArgSpec = {
  key: "skill",
  description: "Skill identifier to resolve directly.",
  kind: "string",
  cliFlag: "skill",
  mcpKey: "skill",
};

const skillIdArg: SharedArgSpec = {
  key: "skillId",
  description: "Skill identifier for the recorded or promoted interaction.",
  kind: "string",
  cliFlag: "skill",
  mcpKey: "skill_id",
};

const limitArg: SharedArgSpec = {
  key: "limit",
  description: "Maximum number of matches to return.",
  kind: "int",
  cliFlag: "limit",
  mcpKey: "limit",
  positive: true,
};

const includeContentArg: SharedArgSpec = {
  key: "includeContent",
  description: "Include note contents in the resolution output.",
  kind: "boolean",
  cliFlag: "include-content",
  mcpKey: "include_content",
};

const minWikiOccurrencesArg: SharedArgSpec = {
  key: "minWikiOccurrences",
  description: "Override the note promotion threshold.",
  kind: "int",
  cliFlag: "min-wiki-occurrences",
  mcpKey: "min_wiki_occurrences",
  positive: true,
};

const minSkillOccurrencesArg: SharedArgSpec = {
  key: "minSkillOccurrences",
  description: "Override the skill promotion threshold.",
  kind: "int",
  cliFlag: "min-skill-occurrences",
  mcpKey: "min_skill_occurrences",
  positive: true,
};

const maxEventsArg: SharedArgSpec = {
  key: "maxEvents",
  description: "Maximum number of recent events to scan during maintenance.",
  kind: "int",
  cliFlag: "max-events",
  mcpKey: "max_events",
  positive: true,
};

const includeCoveredArg: SharedArgSpec = {
  key: "includeCovered",
  description: "Include already covered traces in the maintenance scan.",
  kind: "boolean",
  cliFlag: "include-covered",
  mcpKey: "include_covered",
};

const minNoteOccurrencesArg: SharedArgSpec = {
  key: "minNoteOccurrences",
  description: "Minimum repeated trace count before maintenance compacts a group into a note.",
  kind: "int",
  cliFlag: "min-note-occurrences",
  mcpKey: "min_note_occurrences",
  positive: true,
};

const synthesizeSkillsArg: SharedArgSpec = {
  key: "synthesizeSkills",
  description: "Explicitly synthesize note-backed skills after note maintenance.",
  kind: "boolean",
  cliFlag: "synthesize-skills",
  mcpKey: "synthesize_skills",
};

const packSourceArg: SharedArgSpec = {
  key: "packSource",
  description: "Optional local path or git URL for the source pack.",
  kind: "string",
  cliFlag: "pack-source",
  mcpKey: "pack_source",
};

const hostRepoPathArg: SharedArgSpec = {
  key: "hostRepoPath",
  description: "Absolute or relative path to the host repo.",
  kind: "string",
  cliPositionalIndex: 0,
  cliPositionalLabel: "<host-repo-path>",
  mcpKey: "host_repo_path",
  cliRequired: true,
  mcpRequired: true,
};

const urlArg: SharedArgSpec = {
  key: "url",
  description: "Website URL to capture.",
  kind: "string",
  cliFlag: "url",
  mcpKey: "url",
  cliRequired: true,
  mcpRequired: true,
};

const pathArg: SharedArgSpec = {
  key: "path",
  description: "Absolute or relative path to the PDF file.",
  kind: "string",
  cliFlag: "path",
  mcpKey: "path",
  cliRequired: true,
  mcpRequired: true,
};

const captureArg: SharedArgSpec = {
  key: "capture",
  description: "Capture slug under agent-wiki/notes/web/<slug>.capture.json.",
  kind: "string",
  cliFlag: "capture",
  mcpKey: "capture",
  cliRequired: true,
  mcpRequired: true,
};

const slugArg: SharedArgSpec = {
  key: "slug",
  description: "Optional stable slug.",
  kind: "string",
  cliFlag: "slug",
  mcpKey: "slug",
};

const outputPathArg: SharedArgSpec = {
  key: "outputPath",
  description: "Optional output path for the derived artifact.",
  kind: "string",
  cliFlag: "output",
  mcpKey: "output_path",
};

const trajectoryOutputPathArg: SharedArgSpec = {
  key: "outputPath",
  description: "Optional output path for the JSONL trajectory export.",
  kind: "string",
  cliFlag: "output",
  mcpKey: "output_path",
};

const trajectoryRowFileArg: SharedArgSpec = {
  key: "trajectoryRowFile",
  description: "Path to a JSON file containing one debugging_trajectory.v1 row.",
  kind: "string",
  cliFlag: "trajectory-row",
};

const requiredTrajectoryRowFileArg: SharedArgSpec = {
  ...trajectoryRowFileArg,
  cliRequired: true,
};

const trajectoryRowArg: SharedArgSpec = {
  key: "trajectoryRow",
  description: "One debugging_trajectory.v1 row object.",
  kind: "json",
  mcpKey: "trajectory_row",
};

const requiredTrajectoryRowArg: SharedArgSpec = {
  ...trajectoryRowArg,
  mcpRequired: true,
};

const agentTaskTrajectoryOutputPathArg: SharedArgSpec = {
  key: "outputPath",
  description: "Optional output path for the JSONL agent_task_trajectory.v1 export.",
  kind: "string",
  cliFlag: "output",
  mcpKey: "output_path",
};

const agentTaskTrajectoryRowFileArg: SharedArgSpec = {
  key: "agentTaskTrajectoryFile",
  description: "Path to a JSON file containing one agent_task_trajectory.v1 row.",
  kind: "string",
  cliFlag: "agent-task-trajectory",
};

const requiredAgentTaskTrajectoryRowFileArg: SharedArgSpec = {
  ...agentTaskTrajectoryRowFileArg,
  cliRequired: true,
};

const agentTaskTrajectoryArg: SharedArgSpec = {
  key: "agentTaskTrajectory",
  description: "One agent_task_trajectory.v1 row object.",
  kind: "json",
  mcpKey: "agent_task_trajectory",
};

const requiredAgentTaskTrajectoryArg: SharedArgSpec = {
  ...agentTaskTrajectoryArg,
  mcpRequired: true,
};

const blockedReportPathArg: SharedArgSpec = {
  key: "blockedReportPath",
  description: "Optional path for an export report that includes blocked trajectory rows.",
  kind: "string",
  cliFlag: "include-blocked-report",
  mcpKey: "include_blocked_report",
};

const splitOptions = [
  { canonical: "train", cli: "train" },
  { canonical: "validation", cli: "validation" },
  { canonical: "test", cli: "test" },
  { canonical: "eval", cli: "eval" },
] as const;

const splitArg: SharedArgSpec = {
  key: "split",
  description: "Optional export-time curation split override.",
  kind: "enum",
  cliFlag: "split",
  mcpKey: "split",
  options: splitOptions,
};

const qualityOptions = [
  { canonical: "use", cli: "use" },
  { canonical: "needs_review", cli: "needs-review" },
  { canonical: "discard", cli: "discard" },
] as const;

const qualityArg: SharedArgSpec = {
  key: "quality",
  description: "Optional curation quality filter.",
  kind: "enum",
  cliFlag: "quality",
  mcpKey: "quality",
  options: qualityOptions,
};

const maxRowCharsArg: SharedArgSpec = {
  key: "maxRowChars",
  description: "Maximum estimated JSON row chars before training readiness fails.",
  kind: "int",
  cliFlag: "max-row-chars",
  mcpKey: "max_row_chars",
  positive: true,
};

const maxPatchCharsArg: SharedArgSpec = {
  key: "maxPatchChars",
  description: "Maximum inline final.patch chars before training readiness fails.",
  kind: "int",
  cliFlag: "max-patch-chars",
  mcpKey: "max_patch_chars",
  positive: true,
};

const maxSnippetCharsArg: SharedArgSpec = {
  key: "maxSnippetChars",
  description: "Maximum inline relevant file snippet chars before training readiness fails.",
  kind: "int",
  cliFlag: "max-snippet-chars",
  mcpKey: "max_snippet_chars",
  positive: true,
};

const maxMetadataCharsArg: SharedArgSpec = {
  key: "maxMetadataChars",
  description: "Maximum inline metadata chars before training readiness fails.",
  kind: "int",
  cliFlag: "max-metadata-chars",
  mcpKey: "max_metadata_chars",
  positive: true,
};

const bucketArg: SharedArgSpec = {
  key: "bucket",
  description: "Optional target bucket.",
  kind: "string",
  cliFlag: "bucket",
  mcpKey: "bucket",
};

const prefixArg: SharedArgSpec = {
  key: "prefix",
  description: "Optional object prefix inside the target bucket.",
  kind: "string",
  cliFlag: "prefix",
  mcpKey: "prefix",
};

const publicBaseUrlArg: SharedArgSpec = {
  key: "publicBaseUrl",
  description: "Optional public base URL for published assets.",
  kind: "string",
  cliFlag: "public-base-url",
  mcpKey: "public_base_url",
};

const sourceUrlArg: SharedArgSpec = {
  key: "sourceUrl",
  description: "Optional source URL for the captured PDF.",
  kind: "string",
  cliFlag: "source-url",
  mcpKey: "source_url",
};

const artifactTypeArg: SharedArgSpec = {
  key: "artifactType",
  description: "Derived artifact type to write.",
  kind: "enum",
  cliFlag: "artifact",
  mcpKey: "artifact_type",
  options: artifactTypeOptions,
};

function maybeString(value: unknown): string | undefined {
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

function maybeStringArray(value: unknown): string[] | undefined {
  return Array.isArray(value) ? value.map(String) : undefined;
}

function maybeBoolean(value: unknown): boolean | undefined {
  return typeof value === "boolean" ? value : undefined;
}

function maybeNumber(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function maybeUnknownObject(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : undefined;
}

function lastScalar(value: string | string[] | boolean | undefined): string | undefined {
  if (Array.isArray(value)) {
    for (let index = value.length - 1; index >= 0; index -= 1) {
      if (typeof value[index] === "string") {
        return value[index];
      }
    }
    return undefined;
  }
  return typeof value === "string" ? value : undefined;
}

function parseCliBoolean(value: string | string[] | boolean | undefined): boolean | undefined {
  if (typeof value === "boolean") {
    return value;
  }
  const raw = lastScalar(value);
  if (raw === undefined) {
    return undefined;
  }
  const normalized = raw.trim().toLowerCase();
  if (["1", "true", "yes", "on"].includes(normalized)) {
    return true;
  }
  if (["0", "false", "no", "off"].includes(normalized)) {
    return false;
  }
  return true;
}

function parseCliInt(spec: SharedArgSpec, value: string | string[] | boolean | undefined): number | undefined {
  const raw = lastScalar(value);
  if (raw === undefined) {
    return undefined;
  }
  const parsed = Number.parseInt(raw, 10);
  if (!Number.isFinite(parsed)) {
    throw new Error(`--${spec.cliFlag} must be an integer`);
  }
  if (spec.positive && parsed <= 0) {
    throw new Error(`--${spec.cliFlag} must be a positive integer`);
  }
  return parsed;
}

function parseCliEnum(spec: SharedArgSpec, value: string | string[] | boolean | undefined): string | undefined {
  const raw = lastScalar(value);
  if (raw === undefined) {
    return undefined;
  }
  const option = spec.options?.find((candidate) => candidate.cli === raw || candidate.canonical === raw);
  if (!option) {
    throw new Error(`--${spec.cliFlag} has unsupported value ${raw}`);
  }
  return option.canonical;
}

function parseCliValue(spec: SharedArgSpec, value: string | string[] | boolean | undefined): unknown {
  switch (spec.kind) {
    case "string":
      return lastScalar(value);
    case "string[]":
      if (value === undefined || value === false || value === true) {
        return [];
      }
      return Array.isArray(value) ? value : [value];
    case "boolean":
      return parseCliBoolean(value);
    case "int":
      return parseCliInt(spec, value);
    case "enum":
      return parseCliEnum(spec, value);
    case "json":
      return undefined;
    default:
      return undefined;
  }
}

function isMissingCliValue(value: unknown): boolean {
  return value === undefined;
}

function mcpArgIsRequired(spec: SharedArgSpec): boolean {
  return spec.mcpRequired ?? false;
}

function buildMcpArgSchema(spec: SharedArgSpec): z.ZodTypeAny {
  let schema: z.ZodTypeAny;
  switch (spec.kind) {
    case "string":
      schema = z.string();
      break;
    case "string[]":
      schema = z.array(z.string());
      break;
    case "boolean":
      schema = z.boolean();
      break;
    case "int":
      schema = spec.positive ? z.number().int().positive() : z.number().int();
      break;
    case "enum": {
      const options = (spec.options ?? []).map((option) => option.canonical);
      schema = z.enum(options as [string, ...string[]]);
      break;
    }
    case "json":
      schema = z.record(z.string(), z.unknown());
      break;
    default:
      schema = z.unknown();
      break;
  }
  if (!mcpArgIsRequired(spec)) {
    schema = schema.optional();
  }
  return schema.describe(spec.description);
}

async function loadJsonRowInput(
  input: Record<string, unknown>,
  directRowKey: string,
  rowFileKey: string,
  required: boolean,
  errorMessage: string,
): Promise<unknown | undefined> {
  const directRow = maybeUnknownObject(input[directRowKey]);
  if (directRow !== undefined) {
    return directRow;
  }
  const rowFile = maybeString(input[rowFileKey]);
  if (rowFile !== undefined) {
    const repoPath = maybeString(input.repoPath);
    const basePath = repoPath ? path.resolve(repoPath) : process.cwd();
    const resolvedPath = path.isAbsolute(rowFile)
      ? rowFile
      : path.join(basePath, rowFile);
    return JSON.parse(await readFile(resolvedPath, "utf8"));
  }
  if (required) {
    throw new Error(errorMessage);
  }
  return undefined;
}

async function loadTrajectoryRowInput(input: Record<string, unknown>, required: boolean): Promise<unknown | undefined> {
  return loadJsonRowInput(
    input,
    "trajectoryRow",
    "trajectoryRowFile",
    required,
    "A debugging_trajectory.v1 row is required.",
  );
}

async function loadAgentTaskTrajectoryInput(
  input: Record<string, unknown>,
  required: boolean,
): Promise<unknown | undefined> {
  return loadJsonRowInput(
    input,
    "agentTaskTrajectory",
    "agentTaskTrajectoryFile",
    required,
    "An agent_task_trajectory.v1 row is required.",
  );
}

const sharedCommandsInternal: SharedCommandSpec[] = [
  {
    cliCommand: "adopt",
    mcpTool: "adopt_pack",
    description: "Copy the Datalox pack into a host repo from the current repo or a git URL.",
    args: [hostRepoPathArg, packSourceArg],
    async run(input) {
      return adoptPack({
        hostRepoPath: maybeString(input.hostRepoPath) ?? "",
        packSource: maybeString(input.packSource),
      });
    },
  },
  {
    cliCommand: "capture-web",
    mcpTool: "capture_web_artifact",
    description: "Capture a live website into a repo-local note plus an optional reusable artifact such as a design brief, CSS variable sheet, tokens, or Tailwind theme.",
    args: [repoPathArg, urlArg, artifactTypeArg, titleArg, slugArg, outputPathArg],
    async run(input) {
      return captureWebArtifact({
        repoPath: maybeString(input.repoPath),
        url: maybeString(input.url) ?? "",
        artifactType: (maybeString(input.artifactType) as "design_doc" | "design_tokens" | "css_variables" | "tailwind_theme" | "note" | "source_page" | undefined),
        title: maybeString(input.title),
        slug: maybeString(input.slug),
        outputPath: maybeString(input.outputPath),
      });
    },
  },
  {
    cliCommand: "capture-design",
    mcpTool: "capture_design_source",
    description: "Compatibility alias: capture a live website into a design brief plus a reusable note and screenshots in the host repo.",
    args: [repoPathArg, urlArg, titleArg, slugArg, outputPathArg],
    async run(input) {
      return captureDesignFromUrl({
        repoPath: maybeString(input.repoPath),
        url: maybeString(input.url) ?? "",
        title: maybeString(input.title),
        slug: maybeString(input.slug),
        outputPath: maybeString(input.outputPath),
      });
    },
  },
  {
    cliCommand: "capture-pdf",
    mcpTool: "capture_pdf_artifact",
    description: "Capture a PDF into a repo-local note so agents can act from extracted evidence instead of reopening the file.",
    args: [repoPathArg, pathArg, titleArg, slugArg, sourceUrlArg],
    async run(input) {
      return capturePdfArtifact({
        repoPath: maybeString(input.repoPath),
        path: maybeString(input.path) ?? "",
        title: maybeString(input.title),
        slug: maybeString(input.slug),
        sourceUrl: maybeString(input.sourceUrl),
      });
    },
  },
  {
    cliCommand: "publish-web-capture",
    mcpTool: "publish_web_capture",
    description: "Publish one captured web instance to R2, write its manifest.json, and regenerate indexes/latest.json.",
    args: [repoPathArg, captureArg, bucketArg, prefixArg, publicBaseUrlArg],
    async run(input) {
      return publishWebCapture({
        repoPath: maybeString(input.repoPath),
        capture: maybeString(input.capture) ?? "",
        bucket: maybeString(input.bucket),
        prefix: maybeString(input.prefix),
        publicBaseUrl: maybeString(input.publicBaseUrl),
      });
    },
  },
  {
    cliCommand: "resolve",
    mcpTool: "resolve_loop",
    description: "Resolve the best matching Datalox skill for the current loop and return actionable guidance.",
    args: [repoPathArg, taskArg, workflowArg, stepArg, skillArg, limitArg, includeContentArg],
    async run(input) {
      return resolveLoop({
        repoPath: maybeString(input.repoPath),
        task: maybeString(input.task),
        workflow: maybeString(input.workflow),
        step: maybeString(input.step),
        skill: maybeString(input.skill),
        limit: maybeNumber(input.limit),
        includeContent: maybeBoolean(input.includeContent),
      });
    },
  },
  {
    cliCommand: "record-trajectory",
    mcpTool: "record_trajectory",
    description: "Record one validated debugging_trajectory.v1 row as a dataset candidate event without note or skill promotion.",
    args: [repoPathArg, requiredTrajectoryRowFileArg, requiredTrajectoryRowArg],
    async run(input) {
      return recordTrajectory({
        repoPath: maybeString(input.repoPath),
        trajectoryRow: await loadTrajectoryRowInput(input, true),
      });
    },
  },
  {
    cliCommand: "export-trajectories",
    mcpTool: "export_trajectories",
    description: "Export sellable debugging_trajectory.v1 rows from recorded events into deterministic JSONL.",
    args: [repoPathArg, trajectoryOutputPathArg, blockedReportPathArg, splitArg, qualityArg],
    async run(input) {
      return exportTrajectories({
        repoPath: maybeString(input.repoPath),
        outputPath: maybeString(input.outputPath),
        blockedReportPath: maybeString(input.blockedReportPath),
        split: maybeString(input.split) as "train" | "validation" | "test" | "eval" | undefined,
        quality: maybeString(input.quality) as "use" | "needs_review" | "discard" | undefined,
      });
    },
  },
  {
    cliCommand: "record-agent-task-trajectory",
    mcpTool: "record_agent_task_trajectory",
    description: "Record one validated agent_task_trajectory.v1 row as a mixed-domain dataset candidate event.",
    args: [repoPathArg, requiredAgentTaskTrajectoryRowFileArg, requiredAgentTaskTrajectoryArg],
    async run(input) {
      return recordAgentTaskTrajectory({
        repoPath: maybeString(input.repoPath),
        agentTaskTrajectory: await loadAgentTaskTrajectoryInput(input, true),
      });
    },
  },
  {
    cliCommand: "export-agent-task-trajectories",
    mcpTool: "export_agent_task_trajectories",
    description: "Export sellable agent_task_trajectory.v1 rows from recorded events into deterministic JSONL.",
    args: [repoPathArg, agentTaskTrajectoryOutputPathArg, blockedReportPathArg, splitArg, qualityArg],
    async run(input) {
      return exportAgentTaskTrajectories({
        repoPath: maybeString(input.repoPath),
        outputPath: maybeString(input.outputPath),
        blockedReportPath: maybeString(input.blockedReportPath),
        split: maybeString(input.split) as "train" | "validation" | "test" | "eval" | undefined,
        quality: maybeString(input.quality) as "use" | "needs_review" | "discard" | undefined,
      });
    },
  },
  {
    cliCommand: "grade-trajectories",
    mcpTool: "grade_trajectories",
    description: "Grade recorded debugging_trajectory.v1 rows for training readiness without mutating events.",
    args: [
      repoPathArg,
      eventPathArg,
      maxRowCharsArg,
      maxPatchCharsArg,
      maxSnippetCharsArg,
      maxMetadataCharsArg,
    ],
    async run(input) {
      return gradeTrajectories({
        repoPath: maybeString(input.repoPath),
        eventPath: maybeString(input.eventPath),
        maxRowChars: maybeNumber(input.maxRowChars),
        maxPatchChars: maybeNumber(input.maxPatchChars),
        maxSnippetChars: maybeNumber(input.maxSnippetChars),
        maxMetadataChars: maybeNumber(input.maxMetadataChars),
      });
    },
  },
  {
    cliCommand: "repair-trajectory",
    mcpTool: "repair_trajectory",
    description: "Record a corrected debugging_trajectory.v1 row as a new event linked to the original row event.",
    args: [repoPathArg, requiredEventPathArg, requiredTrajectoryRowFileArg, requiredTrajectoryRowArg],
    async run(input) {
      return repairTrajectory({
        repoPath: maybeString(input.repoPath),
        eventPath: maybeString(input.eventPath) ?? "",
        trajectoryRow: await loadTrajectoryRowInput(input, true),
      });
    },
  },
  {
    cliCommand: "record",
    mcpTool: "record_turn_result",
    description: "Record a grounded loop event before promoting it into wiki pages or skills.",
    args: [
      repoPathArg,
      taskArg,
      workflowArg,
      stepArg,
      skillIdArg,
      summaryArg,
      observationsArg,
      changedFilesArg,
      transcriptArg,
      tagsArg,
      titleArg,
      signalArg,
      interpretationArg,
      recommendedActionArg,
      outcomeArg,
      eventKindArg,
      eventClassArg,
      adjudicationDecisionArg,
      adjudicationSkillIdArg,
      trajectoryRowFileArg,
      trajectoryRowArg,
    ],
    async run(input) {
      return recordTurnResult({
        repoPath: maybeString(input.repoPath),
        task: maybeString(input.task),
        workflow: maybeString(input.workflow),
        step: maybeString(input.step),
        skillId: maybeString(input.skillId),
        summary: maybeString(input.summary),
        observations: maybeStringArray(input.observations),
        changedFiles: maybeStringArray(input.changedFiles),
        transcript: maybeString(input.transcript),
        tags: maybeStringArray(input.tags),
        title: maybeString(input.title),
        signal: maybeString(input.signal),
        interpretation: maybeString(input.interpretation),
        recommendedAction: maybeString(input.recommendedAction),
        outcome: maybeString(input.outcome),
        eventKind: maybeString(input.eventKind),
        eventClass: maybeString(input.eventClass) as "trace" | "candidate" | undefined,
        adjudicationDecision: maybeString(input.adjudicationDecision),
        adjudicationSkillId: maybeString(input.adjudicationSkillId),
        trajectoryRow: await loadTrajectoryRowInput(input, false),
      });
    },
  },
  {
    cliCommand: "patch",
    mcpTool: "patch_knowledge",
    description: "Write a reusable note, create or update a skill, and refresh the visible pack artifacts.",
    args: [
      repoPathArg,
      taskArg,
      workflowArg,
      stepArg,
      skillIdArg,
      summaryArg,
      observationsArg,
      transcriptArg,
      tagsArg,
      titleArg,
      signalArg,
      interpretationArg,
      recommendedActionArg,
      eventPathArg,
      sessionIdArg,
      hostKindArg,
      adminOverrideArg,
    ],
    async run(input) {
      return patchKnowledge({
        repoPath: maybeString(input.repoPath),
        task: maybeString(input.task),
        workflow: maybeString(input.workflow),
        step: maybeString(input.step),
        skillId: maybeString(input.skillId),
        summary: maybeString(input.summary),
        observations: maybeStringArray(input.observations),
        transcript: maybeString(input.transcript),
        tags: maybeStringArray(input.tags),
        title: maybeString(input.title),
        signal: maybeString(input.signal),
        interpretation: maybeString(input.interpretation),
        recommendedAction: maybeString(input.recommendedAction),
        eventPath: maybeString(input.eventPath),
        sessionId: maybeString(input.sessionId),
        hostKind: maybeString(input.hostKind),
        adminOverride: maybeBoolean(input.adminOverride),
      });
    },
  },
  {
    cliCommand: "promote",
    mcpTool: "promote_gap",
    description: "Promote repeated grounded events into reusable notes or new or updated skills using conservative thresholds.",
    args: [
      repoPathArg,
      taskArg,
      workflowArg,
      stepArg,
      skillIdArg,
      summaryArg,
      observationsArg,
      changedFilesArg,
      transcriptArg,
      tagsArg,
      titleArg,
      signalArg,
      interpretationArg,
      recommendedActionArg,
      outcomeArg,
      eventKindArg,
      eventPathArg,
      sessionIdArg,
      hostKindArg,
      adminOverrideArg,
      minWikiOccurrencesArg,
      minSkillOccurrencesArg,
      adjudicationDecisionArg,
      adjudicationSkillIdArg,
    ],
    async run(input) {
      return promoteGap({
        repoPath: maybeString(input.repoPath),
        task: maybeString(input.task),
        workflow: maybeString(input.workflow),
        step: maybeString(input.step),
        skillId: maybeString(input.skillId),
        summary: maybeString(input.summary),
        observations: maybeStringArray(input.observations),
        changedFiles: maybeStringArray(input.changedFiles),
        transcript: maybeString(input.transcript),
        tags: maybeStringArray(input.tags),
        title: maybeString(input.title),
        signal: maybeString(input.signal),
        interpretation: maybeString(input.interpretation),
        recommendedAction: maybeString(input.recommendedAction),
        outcome: maybeString(input.outcome),
        eventKind: maybeString(input.eventKind),
        eventPath: maybeString(input.eventPath),
        sessionId: maybeString(input.sessionId),
        hostKind: maybeString(input.hostKind),
        adminOverride: maybeBoolean(input.adminOverride),
        minWikiOccurrences: maybeNumber(input.minWikiOccurrences),
        minSkillOccurrences: maybeNumber(input.minSkillOccurrences),
        adjudicationDecision: maybeString(input.adjudicationDecision),
        adjudicationSkillId: maybeString(input.adjudicationSkillId),
      });
    },
  },
  {
    cliCommand: "maintain",
    mcpTool: "maintain_knowledge",
    description: "Run a bounded maintenance pass over recent repo-local traces and compact repeated groups into notes.",
    args: [
      repoPathArg,
      maxEventsArg,
      includeCoveredArg,
      minNoteOccurrencesArg,
      minSkillOccurrencesArg,
      synthesizeSkillsArg,
    ],
    async run(input) {
      return maintainKnowledge({
        repoPath: maybeString(input.repoPath),
        maxEvents: maybeNumber(input.maxEvents),
        includeCovered: maybeBoolean(input.includeCovered),
        minNoteOccurrences: maybeNumber(input.minNoteOccurrences),
        minSkillOccurrences: maybeNumber(input.minSkillOccurrences),
        synthesizeSkills: maybeBoolean(input.synthesizeSkills),
      });
    },
  },
  {
    cliCommand: "lint",
    mcpTool: "lint_pack",
    description: "Lint the local Datalox pack and refresh agent-wiki/lint.md.",
    args: [repoPathArg],
    async run(input) {
      return lintLocalPack({
        repoPath: maybeString(input.repoPath),
      });
    },
  },
];

export const SHARED_COMMANDS: readonly SharedCommandSpec[] = sharedCommandsInternal;

export function getSharedCliCommand(commandName: string | undefined): SharedCommandSpec | undefined {
  if (!commandName) {
    return undefined;
  }
  return SHARED_COMMANDS.find((spec) => spec.cliCommand === commandName);
}

export function getSharedMcpCommands(): readonly SharedCommandSpec[] {
  return SHARED_COMMANDS;
}

export function parseSharedCliInput(spec: SharedCommandSpec, args: CliArgsLike): Record<string, unknown> {
  const input: Record<string, unknown> = {};
  const positionals = args._.slice(1);
  for (const arg of spec.args) {
    const raw = arg.cliPositionalIndex !== undefined
      ? positionals[arg.cliPositionalIndex]
      : arg.cliFlag
        ? args[arg.cliFlag]
        : undefined;
    const parsed = parseCliValue(arg, raw);
    if (arg.cliRequired && isMissingCliValue(parsed)) {
      if (arg.cliPositionalLabel) {
        throw new Error(`${spec.cliCommand} requires ${arg.cliPositionalLabel}`);
      }
      throw new Error(`${spec.cliCommand} requires --${arg.cliFlag}`);
    }
    if (!isMissingCliValue(parsed)) {
      input[arg.key] = parsed;
    }
  }
  return input;
}

export function buildSharedMcpInputSchema(spec: SharedCommandSpec): Record<string, z.ZodTypeAny> {
  const schema: Record<string, z.ZodTypeAny> = {};
  for (const arg of spec.args) {
    if (!arg.mcpKey) {
      continue;
    }
    schema[arg.mcpKey] = buildMcpArgSchema(arg);
  }
  return schema;
}

export function parseSharedMcpInput(spec: SharedCommandSpec, input: Record<string, unknown>): Record<string, unknown> {
  const normalized: Record<string, unknown> = {};
  for (const arg of spec.args) {
    if (!arg.mcpKey) {
      continue;
    }
    if (input[arg.mcpKey] !== undefined) {
      normalized[arg.key] = input[arg.mcpKey];
    }
  }
  return normalized;
}
