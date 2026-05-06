import { spawnSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import path from "node:path";

import {
  autoBootstrapIfSafe,
  compileRecordedEvent,
  getEventBacklogStatus,
  patchKnowledge,
  recordLoopApplication,
  recordTurnResult,
  resolveLoop,
  runAutomaticMaintenance,
  type AutoBootstrapResult,
  type RecordTurnResultInput,
  type ResolveLoopInput,
} from "../core/packCore.js";
import { recordTrajectory } from "../core/trajectoryExport.js";
import { resolveSourceRoute } from "./sourceRoutes.js";

export type WrapperPostRunMode = "off" | "trajectory" | "record" | "auto" | "promote" | "review";

export interface LoopEnvelopeInput extends ResolveLoopInput {
  prompt?: string;
  sessionId?: string;
  matcher?: WrapperMatchRunner | null;
}

export interface LoopEnvelope {
  repoPath: string;
  sessionId: string | null;
  active: boolean;
  originalPrompt: string;
  wrappedPrompt: string;
  resolution: Awaited<ReturnType<typeof resolveLoop>> | null;
  bootstrap: AutoBootstrapResult;
  guidance: {
    workflow: string;
    selectionBasis: string;
    matchedSkillId: string | null;
    candidateSkills: Array<{
      skillId: string;
      displayName: string;
      workflow: string | null;
      supportingNotes: Array<{
        path: string;
        title: string;
      }>;
      whyMatched: string[];
    }>;
    whyMatched: string[];
    whatToDoNow: string[];
    watchFor: string[];
    nextReads: string[];
    supportingNotes: Array<{
      path: string;
      title: string;
      whenToUse: string | null;
      signal: string | null;
      interpretation: string | null;
      action: string | null;
      examples: string[];
    }>;
  };
}

export interface WrappedCommandResult {
  command: string;
  args: string[];
  exitCode: number;
  stdout: string;
  stderr: string;
}

export interface WrapperPostRunInput {
  task?: string;
  workflow?: string;
  step?: string;
  skillId?: string;
  summary?: string;
  tags?: string[];
  eventKind?: string;
  postRunMode?: WrapperPostRunMode;
  minWikiOccurrences?: number;
  minSkillOccurrences?: number;
  sessionId?: string;
  reviewModel?: string;
}

export interface WrapperReviewDecision {
  action: "noop" | "persist";
  reason: string;
  summary?: string;
  title?: string;
  signal?: string;
  interpretation?: string;
  recommendedAction?: string;
  observations: string[];
  tags: string[];
}

export interface WrapperMatchDecision {
  matchedSkillId: string | null;
  noMatch: boolean;
  alternatives: string[];
  reason: string;
}

export interface WrapperMatchRunner {
  kind: string;
  model: string | null;
  run(prompt: string, envelope: LoopEnvelope): WrappedCommandResult;
}

export interface WrapperReviewResult {
  status: "skipped" | "completed" | "failed";
  model: string | null;
  decision: WrapperReviewDecision | null;
  persisted: Awaited<ReturnType<typeof patchKnowledge>> | null;
  error?: string;
}

export interface WrapperPostRunResult {
  mode: "off" | "trajectory" | "record" | "promote" | "review";
  trigger: "disabled" | "missing_trajectory_row" | "trajectory_row" | "record_only" | "explicit_signal" | "failure_exit";
  result:
    | Awaited<ReturnType<typeof recordTrajectory>>
    | Awaited<ReturnType<typeof recordTurnResult>>
    | Awaited<ReturnType<typeof compileRecordedEvent>>
    | null;
  review: WrapperReviewResult | null;
  backlog: Awaited<ReturnType<typeof getEventBacklogStatus>> | null;
  maintenance: Awaited<ReturnType<typeof runAutomaticMaintenance>> | null;
}

export interface WrappedLoopResult {
  envelope: LoopEnvelope;
  child: WrappedCommandResult | null;
  postRun: WrapperPostRunResult | null;
}

export interface ObservedTurnInput {
  hostKind: string;
  sourceKind?: "trace" | "web" | "pdf";
  eventClass?: "trace" | "candidate";
  task?: string;
  workflow?: string;
  step?: string;
  skillId?: string | null;
  matchedSkillIdHint?: string | null;
  adjudicationDecision?: string;
  adjudicationSkillId?: string | null;
  summary?: string;
  observations?: string[];
  transcript?: string;
  changedFiles?: string[];
  matchedNotePaths?: string[];
  tags?: string[];
  title?: string;
  signal?: string;
  interpretation?: string;
  recommendedAction?: string;
  eventKind?: string;
}

interface ParsedMarkers {
  cleanedText: string;
  adjudicationDecision?: string;
  adjudicationSkillId?: string;
  summary?: string;
  title?: string;
  signal?: string;
  interpretation?: string;
  recommendedAction?: string;
  eventKind?: string;
  trajectoryRow?: unknown;
  trajectoryRowFile?: string;
  observations: string[];
  tags: string[];
}

export interface WrapperReviewRunner {
  kind: string;
  model: string | null;
  run(prompt: string, envelope: LoopEnvelope): WrappedCommandResult;
}

const CONTROL_TEXT_PATTERN = /[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/g;
const STORED_TRANSCRIPT_LIMITS = {
  wrappedPrompt: 6000,
  command: 3000,
  stdout: 12000,
  stderr: 12000,
} as const;
const REVIEW_TRANSCRIPT_LIMITS = {
  wrappedPrompt: 4000,
  command: 2000,
  stdout: 6000,
  stderr: 6000,
} as const;
const UNKNOWN_WORKFLOW = "unknown";
const TRANSPORT_NOISE_LINE_PATTERNS = [
  /^Reading additional input from stdin\.\.\.$/i,
  /^OpenAI Codex v.*$/i,
  /^--------$/i,
  /^reasoning summaries:\s*/i,
  /^user$/i,
  /^codex$/i,
  /^exec$/i,
  /^tokens used$/i,
  /^succeeded in \d+ms:?\s*$/i,
  /^exited \d+ in \d+ms:?\s*$/i,
  /^workdir:\s*/i,
  /^model:\s*/i,
  /^provider:\s*/i,
  /^approval:\s*/i,
  /^sandbox:\s*/i,
  /^reasoning effort:\s*/i,
  /^session id:\s*/i,
  /^cwd:\s*/i,
] as const;
const TRANSPORT_NOISE_BLOCK_PATTERNS = [
  /codex_core::plugins::manager: failed to warm featured plugin ids cache/i,
  /remote plugin sync request to https:\/\/chatgpt\.com\/backend-api\/plugins\/featured failed/i,
  /codex_analytics::client: events failed with status 403 Forbidden/i,
  /window\._cf_chl_opt/i,
  /Enable JavaScript and cookies to continue/i,
] as const;
const TRANSPORT_NOISE_WARNING_PATTERNS = [
  /codex_core_plugins::manifest: ignoring interface\.defaultPrompt/i,
  /codex_rmcp_client::stdio_server_launcher: Failed to terminate MCP process group/i,
  /codex_core::shell_snapshot: Failed to delete shell snapshot/i,
] as const;
const TRANSPORT_HTML_LINE_PATTERNS = [
  /^\s*<(?:!doctype|html|head|body|meta|style|div|script|noscript|svg|path)\b/i,
  /^\s*<\/(?:html|head|body|div|script|noscript|svg)\b/i,
] as const;
const TRANSPORT_NOISE_BLOCK_END_PATTERNS = [
  /^\d{4}-\d{2}-\d{2}T/,
  /^(?:codex|exec|tokens used|user)$/i,
  /^succeeded in \d+ms:?\s*$/i,
  /^exited \d+ in \d+ms:?\s*$/i,
] as const;
const EXPLICIT_PLACEHOLDER_VALUES = {
  __DATALOX_PROMPT__: (envelope: LoopEnvelope) => envelope.wrappedPrompt,
  __DATALOX_ORIGINAL_PROMPT__: (envelope: LoopEnvelope) => envelope.originalPrompt,
  __DATALOX_GUIDANCE_JSON__: (envelope: LoopEnvelope) => JSON.stringify(envelope.guidance),
  __DATALOX_REPO_PATH__: (envelope: LoopEnvelope) => envelope.repoPath,
  __DATALOX_MATCHED_SKILL__: (envelope: LoopEnvelope) => envelope.guidance.matchedSkillId ?? "",
  __DATALOX_WORKFLOW__: (envelope: LoopEnvelope) => envelope.guidance.workflow === UNKNOWN_WORKFLOW ? "" : envelope.guidance.workflow,
} as const;
const EXPLICIT_PLACEHOLDER_KEYS = Object.keys(EXPLICIT_PLACEHOLDER_VALUES) as Array<keyof typeof EXPLICIT_PLACEHOLDER_VALUES>;

function sanitizeWrappedText(text: string): string {
  return text.replace(/\r\n/g, "\n").replace(CONTROL_TEXT_PATTERN, "");
}

function stripTransportNoise(text: string): string {
  const keptLines: string[] = [];
  let droppingHtmlNoise = false;

  for (const rawLine of text.split("\n")) {
    const line = rawLine.trim();
    const isTransportLine = TRANSPORT_NOISE_LINE_PATTERNS.some((pattern) => pattern.test(line));
    const isTransportBlock = TRANSPORT_NOISE_BLOCK_PATTERNS.some((pattern) => pattern.test(line));
    const isTransportWarning = TRANSPORT_NOISE_WARNING_PATTERNS.some((pattern) => pattern.test(line));
    const isHtmlNoiseLine = TRANSPORT_HTML_LINE_PATTERNS.some((pattern) => pattern.test(line));
    const isNoiseBlockEnd = TRANSPORT_NOISE_BLOCK_END_PATTERNS.some((pattern) => pattern.test(line));

    if (isTransportLine || isTransportWarning || isTransportBlock || isHtmlNoiseLine) {
      if (isTransportBlock || /<html\b/i.test(line)) {
        droppingHtmlNoise = true;
      }
      if (/<\/html>/i.test(line) || /<\/body>/i.test(line)) {
        droppingHtmlNoise = false;
      }
      continue;
    }

    if (droppingHtmlNoise) {
      if (isNoiseBlockEnd) {
        droppingHtmlNoise = false;
      } else if (/<\/html>/i.test(line) || /<\/body>/i.test(line)) {
        droppingHtmlNoise = false;
        continue;
      } else {
        continue;
      }
    }

    if (isTransportLine || isTransportWarning) {
      continue;
    }

    if (isTransportBlock || isHtmlNoiseLine) {
      if (/<\/html>/i.test(line) || /<\/body>/i.test(line)) {
        droppingHtmlNoise = false;
      }
      continue;
    }

    keptLines.push(rawLine);
  }

  return keptLines.join("\n").trim();
}

export function stripDataloxMarkers(text: string): string {
  return extractMarkers(sanitizeWrappedText(text)).cleanedText;
}

function toPrompt(input: LoopEnvelopeInput): string {
  if (typeof input.prompt === "string" && input.prompt.trim().length > 0) {
    return input.prompt;
  }
  if (typeof input.task === "string" && input.task.trim().length > 0) {
    return input.task;
  }
  return "";
}

function toSupportingNotes(noteDocs: Array<{
  path: string;
  title: string;
  whenToUse?: string | null;
  signal?: string | null;
  interpretation?: string | null;
  action?: string | null;
  examples?: string[] | null;
}> = []): LoopEnvelope["guidance"]["supportingNotes"] {
  return noteDocs.map((noteDoc) => ({
    path: noteDoc.path,
    title: noteDoc.title,
    whenToUse: noteDoc.whenToUse ?? null,
    signal: noteDoc.signal ?? null,
    interpretation: noteDoc.interpretation ?? null,
    action: noteDoc.action ?? null,
    examples: Array.isArray(noteDoc.examples) ? noteDoc.examples.filter(Boolean) : [],
  }));
}

function toCandidateSkills(
  matches: Array<{
    skill: {
      id: string;
      displayName?: string | null;
      name?: string | null;
      workflow?: string | null;
    };
    linkedNotes?: Array<{
      path: string;
      title: string;
    }>;
    loopGuidance?: {
      whyMatched?: string[];
    } | null;
  }> = [],
): LoopEnvelope["guidance"]["candidateSkills"] {
  return matches.slice(0, 3).map((match) => ({
    skillId: match.skill.id,
    displayName: match.skill.displayName ?? match.skill.name ?? match.skill.id,
    workflow: match.skill.workflow ?? null,
    supportingNotes: (match.linkedNotes ?? []).slice(0, 2).map((noteDoc) => ({
      path: noteDoc.path,
      title: noteDoc.title,
    })),
    whyMatched: match.loopGuidance?.whyMatched ?? [],
  }));
}

function toGuidanceFromSelectedMatch(
  resolution: Awaited<ReturnType<typeof resolveLoop>>,
  match: {
    skill: {
      id: string;
    };
    linkedNotes?: Array<{
      path: string;
      title: string;
      whenToUse?: string | null;
      signal?: string | null;
      interpretation?: string | null;
      action?: string | null;
      examples?: string[] | null;
    }>;
    loopGuidance?: {
      whyMatched?: string[];
      whatToDoNow?: string[];
      watchFor?: string[];
      nextReads?: string[];
    } | null;
  },
  reason: string[] = [],
): LoopEnvelope["guidance"] {
  const supportingNotes = toSupportingNotes(match.linkedNotes ?? []);
  const whyMatched = [...new Set([...(match.loopGuidance?.whyMatched ?? []), ...reason].filter(Boolean))];

  return {
    workflow: resolution.workflow,
    selectionBasis: resolution.selectionBasis,
    matchedSkillId: match.skill.id,
    candidateSkills: toCandidateSkills((resolution.matches ?? []) as Array<{
      skill: {
        id: string;
        displayName?: string | null;
        name?: string | null;
        workflow?: string | null;
      };
      linkedNotes?: Array<{
        path: string;
        title: string;
      }>;
      loopGuidance?: {
        whyMatched?: string[];
      } | null;
    }>),
    whyMatched,
    whatToDoNow: (match.loopGuidance?.whatToDoNow?.length ?? 0) > 0
      ? (match.loopGuidance?.whatToDoNow ?? [])
      : supportingNotes
        .map((note) => note.action)
        .filter((value: string | null): value is string => Boolean(value)),
    watchFor: (match.loopGuidance?.watchFor?.length ?? 0) > 0
      ? (match.loopGuidance?.watchFor ?? [])
      : supportingNotes
        .map((note) => note.signal)
        .filter((value: string | null): value is string => Boolean(value)),
    nextReads: match.loopGuidance?.nextReads ?? [],
    supportingNotes,
  };
}

function summarizeResolution(
  resolution: Awaited<ReturnType<typeof resolveLoop>> | null,
  workflowHint?: string,
): LoopEnvelope["guidance"] {
  if (!resolution) {
    return {
      workflow: workflowHint ?? "unknown",
      selectionBasis: "bootstrap_unavailable",
      matchedSkillId: null,
      candidateSkills: [],
      whyMatched: [],
      whatToDoNow: [],
      watchFor: [],
      nextReads: [],
      supportingNotes: [],
    };
  }
  const directNotes = Array.isArray((resolution as { directNoteMatches?: Array<{ note?: unknown }> }).directNoteMatches)
    ? ((resolution as { directNoteMatches?: Array<{ note?: {
      path: string;
      title: string;
      whenToUse?: string | null;
      signal?: string | null;
      interpretation?: string | null;
      action?: string | null;
      examples?: string[] | null;
    } }> }).directNoteMatches ?? []).map((entry) => entry.note).filter(Boolean)
    : [];
  const matchedSkillId = typeof (resolution as { matchedSkillId?: unknown }).matchedSkillId === "string"
    ? (resolution as { matchedSkillId: string }).matchedSkillId
    : null;
  const authoritativeMatch = matchedSkillId
    ? resolution.matches.find((match: { skill: { id: string } }) => match.skill.id === matchedSkillId) ?? null
    : null;

  if (authoritativeMatch) {
    return toGuidanceFromSelectedMatch(
      resolution,
      authoritativeMatch as {
        skill: {
          id: string;
        };
        linkedNotes?: Array<{
          path: string;
          title: string;
          whenToUse?: string | null;
          signal?: string | null;
          interpretation?: string | null;
          action?: string | null;
          examples?: string[] | null;
        }>;
        loopGuidance?: {
          whyMatched?: string[];
          whatToDoNow?: string[];
          watchFor?: string[];
          nextReads?: string[];
        } | null;
      },
    );
  }

  const supportingNotes = toSupportingNotes(directNotes as Array<{
    path: string;
    title: string;
    whenToUse?: string | null;
    signal?: string | null;
    interpretation?: string | null;
    action?: string | null;
    examples?: string[] | null;
  }>);
  const candidateSkills = toCandidateSkills((resolution.matches ?? []) as Array<{
    skill: {
      id: string;
      displayName?: string | null;
      name?: string | null;
      workflow?: string | null;
    };
    linkedNotes?: Array<{
      path: string;
      title: string;
    }>;
    loopGuidance?: {
      whyMatched?: string[];
    } | null;
  }>);
  const loopGuidance = (resolution as { loopGuidance?: {
    whyMatched?: string[];
    whatToDoNow?: string[];
    watchFor?: string[];
    nextReads?: string[];
  } | null }).loopGuidance ?? null;
  return {
    workflow: resolution.workflow,
    selectionBasis: resolution.selectionBasis,
    matchedSkillId: null,
    candidateSkills,
    whyMatched: loopGuidance?.whyMatched ?? [],
    whatToDoNow: (loopGuidance?.whatToDoNow?.length ?? 0) > 0
      ? (loopGuidance?.whatToDoNow ?? [])
      : supportingNotes
        .map((note: LoopEnvelope["guidance"]["supportingNotes"][number]) => note.action)
        .filter((value: string | null): value is string => Boolean(value)),
    watchFor: (loopGuidance?.watchFor?.length ?? 0) > 0
      ? (loopGuidance?.watchFor ?? [])
      : supportingNotes
        .map((note: LoopEnvelope["guidance"]["supportingNotes"][number]) => note.signal)
        .filter((value: string | null): value is string => Boolean(value)),
    nextReads: loopGuidance?.nextReads ?? [],
    supportingNotes,
  };
}

function buildMatchCandidateCards(
  resolution: Awaited<ReturnType<typeof resolveLoop>>,
) {
  return resolution.matches.slice(0, 5).map((match: {
    skill: {
      id: string;
      displayName?: string | null;
      name?: string | null;
      workflow?: string | null;
      trigger?: string | null;
      description?: string | null;
    };
    linkedNotes?: Array<{
      title: string;
      whenToUse?: string | null;
      signal?: string | null;
      action?: string | null;
    }>;
    loopGuidance?: {
      whyMatched?: string[];
    } | null;
  }) => ({
    skillId: match.skill.id,
    displayName: match.skill.displayName ?? match.skill.name ?? match.skill.id,
    workflow: match.skill.workflow ?? null,
    trigger: match.skill.trigger ?? null,
    description: match.skill.description ?? null,
    whyMatched: match.loopGuidance?.whyMatched ?? [],
    supportingNotes: (match.linkedNotes ?? []).slice(0, 2).map((note) => ({
      title: note.title,
      whenToUse: note.whenToUse ?? null,
      signal: note.signal ?? null,
      action: note.action ?? null,
    })),
  }));
}

function shouldRunMatchAdjudicator(
  resolution: Awaited<ReturnType<typeof resolveLoop>> | null,
  input: LoopEnvelopeInput,
): boolean {
  if (!resolution || !input.matcher) {
    return false;
  }
  if (input.skill) {
    return false;
  }
  if (resolution.selectionBasis !== "task_query") {
    return false;
  }
  if (resolution.matchedSkillId) {
    return false;
  }
  if (!(input.task || input.step || input.prompt)) {
    return false;
  }
  return (resolution.matches?.length ?? 0) > 0;
}

function buildMatchAdjudicationPrompt(
  input: LoopEnvelopeInput,
  resolution: Awaited<ReturnType<typeof resolveLoop>>,
): string {
  const candidateCards = buildMatchCandidateCards(resolution);
  const payload = {
    task: input.task ?? input.prompt ?? null,
    workflow: input.workflow ?? resolution.workflow ?? null,
    step: input.step ?? null,
    candidates: candidateCards,
  };

  return [
    "Decide whether the current task semantically matches one of the provided skills.",
    "Token overlap alone is not enough.",
    "Only select a skill if it is the same reusable workflow boundary.",
    "Return JSON only with this shape:",
    "{\"matchedSkillId\": string | null, \"noMatch\": boolean, \"alternatives\": string[], \"reason\": string}",
    "Rules:",
    "- choose only from the provided candidates",
    "- set noMatch=true when none of the candidates is actually the right workflow",
    "- keep alternatives short and limited to provided candidate ids",
    "",
    JSON.stringify(payload, null, 2),
  ].join("\n");
}

function parseMatchDecision(
  raw: unknown,
  candidateSkillIds: string[],
): WrapperMatchDecision {
  if (!raw || typeof raw !== "object") {
    throw new Error("Match adjudicator JSON must be an object.");
  }

  const reason = maybeNonEmptyString((raw as { reason?: unknown }).reason);
  if (!reason) {
    throw new Error("Match adjudicator reason is required.");
  }

  const matchedSkillId = maybeNonEmptyString((raw as { matchedSkillId?: unknown }).matchedSkillId) ?? null;
  const noMatch = Boolean((raw as { noMatch?: unknown }).noMatch);
  const alternatives = maybeStringArray((raw as { alternatives?: unknown }).alternatives)
    .filter((skillId) => candidateSkillIds.includes(skillId))
    .slice(0, 5);

  if (matchedSkillId && !candidateSkillIds.includes(matchedSkillId)) {
    throw new Error("Match adjudicator selected a skill outside the provided candidate set.");
  }
  if (noMatch && matchedSkillId) {
    throw new Error("Match adjudicator cannot set both noMatch=true and matchedSkillId.");
  }

  return {
    matchedSkillId,
    noMatch: noMatch || !matchedSkillId,
    alternatives,
    reason,
  };
}

async function maybeAdjudicateGuidance(
  resolution: Awaited<ReturnType<typeof resolveLoop>>,
  input: LoopEnvelopeInput,
  guidance: LoopEnvelope["guidance"],
  baseEnvelope: Pick<LoopEnvelope, "repoPath" | "sessionId" | "active" | "originalPrompt" | "wrappedPrompt" | "resolution" | "bootstrap" | "guidance">,
): Promise<LoopEnvelope["guidance"]> {
  if (!shouldRunMatchAdjudicator(resolution, input)) {
    return guidance;
  }

  const candidateSkillIds = guidance.candidateSkills.map((candidate) => candidate.skillId);
  if (candidateSkillIds.length === 0) {
    return guidance;
  }

  const prompt = buildMatchAdjudicationPrompt(input, resolution);
  const reviewEnvelope = {
    ...baseEnvelope,
    guidance,
    wrappedPrompt: prompt,
  } as LoopEnvelope;
  const run = input.matcher?.run(prompt, reviewEnvelope);
  if (!run || run.exitCode !== 0) {
    return guidance;
  }

  try {
    const decision = parseMatchDecision(tryParseJsonBlock(run.stdout), candidateSkillIds);
    if (!decision.matchedSkillId || decision.noMatch) {
      return guidance;
    }
    const selected = resolution.matches.find((match: { skill: { id: string } }) => match.skill.id === decision.matchedSkillId);
    if (!selected) {
      return guidance;
    }
    return toGuidanceFromSelectedMatch(
      resolution,
      selected as {
        skill: {
          id: string;
        };
        linkedNotes?: Array<{
          path: string;
          title: string;
          whenToUse?: string | null;
          signal?: string | null;
          interpretation?: string | null;
          action?: string | null;
          examples?: string[] | null;
        }>;
        loopGuidance?: {
          whyMatched?: string[];
          whatToDoNow?: string[];
          watchFor?: string[];
          nextReads?: string[];
        } | null;
      },
      ["agent_adjudicated_match"],
    );
  } catch {
    return guidance;
  }
}

function renderBulletSection(title: string, lines: string[]): string[] {
  if (lines.length === 0) {
    return [];
  }
  return [
    `${title}:`,
    ...lines.map((line) => `- ${line}`),
    "",
  ];
}

function renderSupportingNotes(notes: LoopEnvelope["guidance"]["supportingNotes"]): string[] {
  if (notes.length === 0) {
    return [];
  }

  const rendered: string[] = ["Supporting notes:"];
  for (const note of notes) {
    rendered.push(`- ${note.title} | ${note.path}`);
    if (note.whenToUse) {
      rendered.push(`  When to use: ${note.whenToUse}`);
    }
    if (note.signal) {
      rendered.push(`  Signal: ${note.signal}`);
    }
    if (note.interpretation) {
      rendered.push(`  Interpretation: ${note.interpretation}`);
    }
    if (note.action) {
      rendered.push(`  Action: ${note.action}`);
    }
    if (note.examples.length > 0) {
      rendered.push(`  Example: ${note.examples[0]}`);
    }
  }
  rendered.push("");
  return rendered;
}

function renderCandidateSkills(candidateSkills: LoopEnvelope["guidance"]["candidateSkills"]): string[] {
  if (candidateSkills.length === 0) {
    return [];
  }

  const rendered: string[] = ["Candidate skills:"];
  for (const candidate of candidateSkills) {
    rendered.push(`- ${candidate.displayName} | ${candidate.skillId}`);
    if (candidate.workflow) {
      rendered.push(`  Workflow: ${candidate.workflow}`);
    }
    if (candidate.supportingNotes.length > 0) {
      rendered.push(`  Notes: ${candidate.supportingNotes.map((note) => note.title).join(" | ")}`);
    }
    if (candidate.whyMatched.length > 0) {
      rendered.push(`  Why matched: ${candidate.whyMatched[0]}`);
    }
  }
  rendered.push("");
  return rendered;
}

export function renderWrappedPrompt(envelope: LoopEnvelope): string {
  if (!envelope.active) {
    return envelope.originalPrompt;
  }
  const shouldPreferNewSkill = envelope.guidance.supportingNotes.length > 0
    && !envelope.guidance.matchedSkillId
    && envelope.guidance.workflow !== UNKNOWN_WORKFLOW;
  const guidanceLines = [
    "# Datalox Loop Guidance",
    `Selection basis: ${envelope.guidance.selectionBasis}`,
    `Workflow: ${envelope.guidance.workflow}`,
    `Matched skill: ${envelope.guidance.matchedSkillId ?? "none"}`,
    "",
    ...renderBulletSection("Why matched", envelope.guidance.whyMatched),
    ...renderBulletSection("What to do now", envelope.guidance.whatToDoNow),
    ...renderBulletSection("Watch for", envelope.guidance.watchFor),
    ...renderCandidateSkills(envelope.guidance.candidateSkills),
    ...renderSupportingNotes(envelope.guidance.supportingNotes),
    ...renderBulletSection("Next reads", envelope.guidance.nextReads),
    "# Datalox Trajectory Capture",
    "For coding-debugging work, write one explicit `debugging_trajectory.v1` JSON row to a repo-local file after the fix or investigation is complete.",
    "Use observed facts only: task prompt, minimal context, concise user/agent/tool steps, final fix, verification status, outcome label, and export gate.",
    "Set `curation.quality` to `needs_review` by default; use `use` only when a reviewer has already accepted the row.",
    "Do not infer a row from prose, hidden reasoning, or missing facts. If a row is not justified for this run, omit the marker.",
    "When a row file exists, append this marker at the very end of your response:",
    "- DATALOX_TRAJECTORY_ROW_FILE: .datalox/trajectory-rows/<stable-id>.json",
    "",
    ...(shouldPreferNewSkill
      ? [
        "Promotion state:",
        "- Supporting notes already cover this gap, but there is still no matched skill.",
        "- If this run confirms the same recurring workflow, prefer DATALOX_DECISION: create_new_skill over create_operational_note.",
        "",
      ]
      : []),
    "# Datalox Reusable-Gap Protocol",
    "Only if you discover a reusable gap, recurring workflow, or repeated failure worth remembering, append plain text marker lines at the very end of your response:",
    "- DATALOX_SUMMARY: one-line summary of the reusable gap",
    "- DATALOX_TITLE: short title for the future page or skill",
    "- DATALOX_SIGNAL: concrete signal or failure symptom",
    "- DATALOX_INTERPRETATION: why this gap is reusable",
    "- DATALOX_ACTION: what the next agent should do",
    "- DATALOX_OBSERVATION: optional repeated observations (repeatable)",
    "- DATALOX_TAG: optional tags (repeatable)",
    "- DATALOX_DECISION: one of record_trace | create_operational_note | patch_existing_skill | create_new_skill | needs_more_evidence",
    "- DATALOX_SKILL: required skill id to patch when DATALOX_DECISION is patch_existing_skill unless the wrapper invocation already pins an explicit skill",
    "Decision rules:",
    "- use record_trace when the run is one-off or not yet reusable enough",
    "- use create_operational_note when you found the first durable reusable local pattern for this gap",
    "- use create_new_skill when supporting notes already cover the same gap and the correction now reads like a reusable workflow with no matched skill yet",
    "- use patch_existing_skill when a matched skill already exists and this gap belongs inside that workflow",
    "- use needs_more_evidence when you cannot justify a durable write yet",
    "If there is no reusable gap, do not emit any DATALOX_* lines.",
    "",
    "# Original Prompt",
    envelope.originalPrompt,
  ];

  return guidanceLines.join("\n").trim();
}

export async function buildLoopEnvelope(input: LoopEnvelopeInput): Promise<LoopEnvelope> {
  const repoPath = path.resolve(input.repoPath ?? process.cwd());
  const originalPrompt = toPrompt(input);
  const retrievalTask = input.task ?? (originalPrompt.trim().length > 0 ? originalPrompt : undefined);
  const bootstrap = await autoBootstrapIfSafe({ repoPath });
  const sourceRoute = bootstrap.probeAfter.status === "ready"
    && !input.skill
    && originalPrompt.trim().length > 0
    ? await resolveSourceRoute({
      repoPath,
      prompt: originalPrompt,
    })
    : null;
  const resolution = bootstrap.probeAfter.status === "ready"
    && !sourceRoute
    ? await resolveLoop({
      repoPath,
      task: retrievalTask,
      workflow: input.workflow,
      step: input.step,
      skill: input.skill,
      limit: input.limit,
      includeContent: input.includeContent,
    })
    : null;
  let guidance = sourceRoute?.guidance ?? summarizeResolution(resolution, input.workflow);
  const baseEnvelope = {
    repoPath,
    sessionId: input.sessionId ?? null,
    active: sourceRoute !== null || resolution !== null,
    originalPrompt,
    resolution,
    bootstrap,
    guidance,
    wrappedPrompt: "",
  };

  if (resolution && !sourceRoute) {
    guidance = await maybeAdjudicateGuidance(resolution, input, guidance, baseEnvelope);
    baseEnvelope.guidance = guidance;
  }

  return {
    ...baseEnvelope,
    wrappedPrompt: renderWrappedPrompt(baseEnvelope),
  };
}

export function buildWrapperEnv(envelope: LoopEnvelope, hostKind?: string): NodeJS.ProcessEnv {
  return {
    DATALOX_REPO_PATH: envelope.repoPath,
    DATALOX_SESSION_ID: envelope.sessionId ?? "",
    DATALOX_ORIGINAL_PROMPT: envelope.originalPrompt,
    DATALOX_PROMPT: envelope.wrappedPrompt,
    DATALOX_GUIDANCE_JSON: JSON.stringify(envelope.guidance),
    DATALOX_SELECTION_BASIS: envelope.guidance.selectionBasis,
    DATALOX_WORKFLOW: envelope.guidance.workflow === UNKNOWN_WORKFLOW ? "" : envelope.guidance.workflow,
    DATALOX_MATCHED_SKILL: envelope.guidance.matchedSkillId ?? "",
    ...(hostKind
      ? {
          DATALOX_ACTIVE_WRAPPER: hostKind,
          DATALOX_HOST_KIND: hostKind,
          DATALOX_ENFORCEMENT: "wrapper",
        }
      : {}),
  };
}

function replaceExplicitPlaceholder(
  input: string,
  key: keyof typeof EXPLICIT_PLACEHOLDER_VALUES,
  value: string,
): string {
  if (input === key) {
    return value;
  }

  const assignmentSuffix = `=${key}`;
  if (input.endsWith(assignmentSuffix)) {
    return `${input.slice(0, -assignmentSuffix.length)}=${value}`;
  }

  return input;
}

export function hasExplicitPromptPlaceholder(input: string): boolean {
  return input === "__DATALOX_PROMPT__" || input.endsWith("=__DATALOX_PROMPT__");
}

export function replacePromptPlaceholders(input: string, envelope: LoopEnvelope): string {
  if (input === envelope.wrappedPrompt || input === envelope.originalPrompt) {
    return input;
  }

  return EXPLICIT_PLACEHOLDER_KEYS.reduce(
    (current, key) => replaceExplicitPlaceholder(current, key, EXPLICIT_PLACEHOLDER_VALUES[key](envelope)),
    input,
  );
}

export function runWrappedCommand(
  command: string,
  args: string[],
  envelope: LoopEnvelope,
  options: {
    cwd?: string;
    env?: NodeJS.ProcessEnv;
    hostKind?: string;
  } = {},
): WrappedCommandResult {
  const result = spawnSync(
    command,
    args.map((arg) => replacePromptPlaceholders(arg, envelope)),
    {
      cwd: options.cwd ?? envelope.repoPath,
      env: {
        ...process.env,
        ...buildWrapperEnv(envelope, options.hostKind),
        ...options.env,
      },
      encoding: "utf8",
    },
  );

  return {
    command,
    args: args.map((arg) => replacePromptPlaceholders(arg, envelope)),
    exitCode: result.status ?? 1,
    stdout: result.stdout ?? "",
    stderr: result.stderr ?? "",
  };
}

function firstNonEmpty(lines: Array<string | undefined | null>): string | undefined {
  for (const value of lines) {
    if (typeof value === "string") {
      const trimmed = value.trim();
      if (trimmed.length > 0) {
        return trimmed;
      }
    }
  }
  return undefined;
}

function firstNonEmptyLine(text: string): string | undefined {
  return firstNonEmpty(text.split(/\r?\n/));
}

function extractChildSummary(child: WrappedCommandResult): string | undefined {
  const streams = child.exitCode === 0
    ? [child.stdout, child.stderr]
    : [child.stderr, child.stdout];
  for (const stream of streams) {
    const firstLine = firstNonEmptyLine(stripTransportNoise(stream));
    if (firstLine) {
      return firstLine;
    }
  }
  return undefined;
}

function parseMarkerLine(line: string, parsed: ParsedMarkers): boolean {
  const match = line.match(/^DATALOX_([A-Z_]+):\s*(.+)$/);
  if (!match) {
    return false;
  }
  const [, rawKey, rawValue] = match;
  const value = rawValue.trim();
  switch (rawKey) {
    case "SUMMARY":
      parsed.summary = value;
      return true;
    case "TITLE":
      parsed.title = value;
      return true;
    case "SIGNAL":
      parsed.signal = value;
      return true;
    case "INTERPRETATION":
      parsed.interpretation = value;
      return true;
    case "ACTION":
    case "RECOMMENDED_ACTION":
      parsed.recommendedAction = value;
      return true;
    case "EVENT_KIND":
      parsed.eventKind = value;
      return true;
    case "TRAJECTORY_ROW":
      parsed.trajectoryRow = JSON.parse(value);
      return true;
    case "TRAJECTORY_ROW_FILE":
      parsed.trajectoryRowFile = value;
      return true;
    case "OBSERVATION":
      parsed.observations.push(value);
      return true;
    case "TAG":
      parsed.tags.push(value);
      return true;
    case "DECISION":
      parsed.adjudicationDecision = value;
      return true;
    case "SKILL":
      parsed.adjudicationSkillId = value;
      return true;
    default:
      return false;
  }
}

function extractMarkers(text: string): ParsedMarkers {
  const parsed: ParsedMarkers = {
    cleanedText: "",
    observations: [],
    tags: [],
  };
  const keptLines: string[] = [];
  for (const line of text.split(/\r?\n/)) {
    if (!parseMarkerLine(line, parsed)) {
      keptLines.push(line);
    }
  }
  parsed.cleanedText = keptLines.join("\n").trim();
  return parsed;
}

function mergeMarkers(left: ParsedMarkers, right: ParsedMarkers): ParsedMarkers {
  return {
    cleanedText: "",
    adjudicationDecision: left.adjudicationDecision ?? right.adjudicationDecision,
    adjudicationSkillId: left.adjudicationSkillId ?? right.adjudicationSkillId,
    summary: left.summary ?? right.summary,
    title: left.title ?? right.title,
    signal: left.signal ?? right.signal,
    interpretation: left.interpretation ?? right.interpretation,
    recommendedAction: left.recommendedAction ?? right.recommendedAction,
    eventKind: left.eventKind ?? right.eventKind,
    trajectoryRow: left.trajectoryRow ?? right.trajectoryRow,
    trajectoryRowFile: left.trajectoryRowFile ?? right.trajectoryRowFile,
    observations: [...left.observations, ...right.observations],
    tags: [...left.tags, ...right.tags],
  };
}

export function sanitizeWrappedCommandResult(result: WrappedCommandResult): {
  child: WrappedCommandResult;
  markers: ParsedMarkers;
} {
  const stdoutMarkers = extractMarkers(sanitizeWrappedText(result.stdout));
  const stderrMarkers = extractMarkers(sanitizeWrappedText(result.stderr));
  return {
    child: {
      ...result,
      stdout: stripTransportNoise(stdoutMarkers.cleanedText),
      stderr: stripTransportNoise(stderrMarkers.cleanedText),
    },
    markers: mergeMarkers(stdoutMarkers, stderrMarkers),
  };
}

function truncateTranscriptSection(text: string, maxChars?: number): string {
  const sanitized = sanitizeWrappedText(text).trim();
  if (!sanitized) {
    return "(empty)";
  }
  if (!maxChars || sanitized.length <= maxChars) {
    return sanitized;
  }
  const remaining = sanitized.length - maxChars;
  return `${sanitized.slice(0, maxChars).trimEnd()}\n[truncated ${remaining} chars]`;
}

function buildTranscript(
  envelope: LoopEnvelope,
  child: WrappedCommandResult | null,
  options: {
    wrappedPrompt?: number;
    command?: number;
    stdout?: number;
    stderr?: number;
  } = {},
): string | undefined {
  if (!child) {
    const wrappedPrompt = truncateTranscriptSection(envelope.wrappedPrompt, options.wrappedPrompt);
    return wrappedPrompt === "(empty)" ? undefined : wrappedPrompt;
  }

  const parts = [
    "# Wrapped Prompt",
    truncateTranscriptSection(envelope.wrappedPrompt, options.wrappedPrompt),
    "",
    "# Child Command",
    truncateTranscriptSection([child.command, ...child.args].join(" "), options.command),
    "",
    "# Exit Code",
    String(child.exitCode),
    "",
    "# Stdout",
    truncateTranscriptSection(child.stdout, options.stdout),
    "",
    "# Stderr",
    truncateTranscriptSection(child.stderr, options.stderr),
  ];
  return parts.join("\n").trim();
}

function buildFailureObservation(child: WrappedCommandResult): string | undefined {
  const firstLine = extractChildSummary(child);
  if (!firstLine) {
    return `Wrapped host command exited with code ${child.exitCode}.`;
  }
  return `Wrapped host command exited with code ${child.exitCode}: ${firstLine}`;
}

function hasExplicitPromotionSignal(markers: ParsedMarkers): boolean {
  return Boolean(
    markers.title
      || markers.signal
      || markers.interpretation
      || markers.recommendedAction
      || markers.eventKind
      || markers.observations.length > 0,
  );
}

function collectChangedFiles(repoPath: string): string[] {
  const status = spawnSync("git", ["status", "--short"], {
    cwd: repoPath,
    encoding: "utf8",
  });
  if (status.status !== 0) {
    return [];
  }

  return status.stdout
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => line.slice(3).trim())
    .filter(Boolean)
    .slice(0, 25);
}

export function buildObservedTurnPayload(
  envelope: Pick<LoopEnvelope, "repoPath" | "sessionId" | "guidance" | "originalPrompt">,
  input: ObservedTurnInput,
): RecordTurnResultInput {
  const transcript = typeof input.transcript === "string"
    ? truncateTranscriptSection(input.transcript, STORED_TRANSCRIPT_LIMITS.stdout)
    : undefined;
  const changedFiles = Array.isArray(input.changedFiles)
    ? input.changedFiles.filter(Boolean).slice(0, 25)
    : [];
  const inheritedWorkflow = envelope.guidance.workflow !== UNKNOWN_WORKFLOW
    && (Boolean(envelope.guidance.matchedSkillId) || envelope.guidance.selectionBasis !== "task_query")
      ? envelope.guidance.workflow
      : undefined;
  const matchedNotePaths = Array.isArray(input.matchedNotePaths) && input.matchedNotePaths.length > 0
    ? input.matchedNotePaths.filter(Boolean)
    : envelope.guidance.supportingNotes.map((note) => note.path);

  return {
    repoPath: envelope.repoPath,
    sourceKind: input.sourceKind ?? "trace",
    eventClass: input.eventClass,
    task: input.task ?? (envelope.originalPrompt || undefined),
    workflow: input.workflow ?? inheritedWorkflow,
    step: input.step,
    skillId: input.skillId ?? undefined,
    matchedSkillIdHint: input.matchedSkillIdHint ?? (input.skillId ? undefined : (envelope.guidance.matchedSkillId ?? undefined)),
    adjudicationDecision: input.adjudicationDecision,
    adjudicationSkillId: input.adjudicationSkillId ?? undefined,
    candidateSkills: envelope.guidance.candidateSkills,
    summary: input.summary ?? firstNonEmptyLine(transcript ?? ""),
    observations: Array.isArray(input.observations) ? [...input.observations] : [],
    transcript,
    changedFiles,
    matchedNotePaths,
    tags: Array.isArray(input.tags) ? [...input.tags] : [],
    title: input.title,
    signal: input.signal,
    interpretation: input.interpretation,
    recommendedAction: input.recommendedAction,
    eventKind: input.eventKind,
    sessionId: envelope.sessionId ?? undefined,
    hostKind: input.hostKind,
  };
}

export async function recordObservedTurnPayload(
  envelope: Pick<LoopEnvelope, "repoPath" | "guidance">,
  payloadBase: RecordTurnResultInput,
  options: {
    applyMatchedNotes?: boolean;
  } = {},
) {
  const recorded = await recordTurnResult(payloadBase);
  const matchedNotePaths = Array.isArray(payloadBase.matchedNotePaths)
    ? payloadBase.matchedNotePaths.filter(Boolean)
    : [];

  if (options.applyMatchedNotes && matchedNotePaths.length > 0) {
    await recordLoopApplication({
      repoPath: envelope.repoPath,
      notePaths: matchedNotePaths,
    });
  }

  return recorded;
}

async function loadTrajectoryRowMarker(
  repoPath: string,
  markers: ParsedMarkers,
): Promise<unknown | null> {
  if (markers.trajectoryRow !== undefined && markers.trajectoryRowFile !== undefined) {
    throw new Error("Use either DATALOX_TRAJECTORY_ROW or DATALOX_TRAJECTORY_ROW_FILE, not both.");
  }
  if (markers.trajectoryRow !== undefined) {
    return markers.trajectoryRow;
  }
  if (markers.trajectoryRowFile === undefined) {
    return null;
  }

  const resolvedPath = path.isAbsolute(markers.trajectoryRowFile)
    ? path.resolve(markers.trajectoryRowFile)
    : path.resolve(repoPath, markers.trajectoryRowFile);
  const relativePath = path.relative(repoPath, resolvedPath);
  if (relativePath.startsWith("..") || path.isAbsolute(relativePath)) {
    throw new Error("DATALOX_TRAJECTORY_ROW_FILE must point inside the repo.");
  }
  return JSON.parse(await readFile(resolvedPath, "utf8"));
}

function renderReviewNotes(notes: LoopEnvelope["guidance"]["supportingNotes"]): string {
  if (notes.length === 0) {
    return "- none";
  }

  return notes.map((note) => {
    const parts = [`- ${note.title} (${note.path})`];
    if (note.action) {
      parts.push(`  action: ${note.action}`);
    }
    if (note.signal) {
      parts.push(`  signal: ${note.signal}`);
    }
    return parts.join("\n");
  }).join("\n");
}

function buildReviewPrompt(
  envelope: LoopEnvelope,
  child: WrappedCommandResult,
  payloadBase: RecordTurnResultInput,
  changedFiles: string[],
): string {
  const transcript = buildTranscript(envelope, child, REVIEW_TRANSCRIPT_LIMITS) ?? "(empty)";
  const observations = payloadBase.observations?.length
    ? payloadBase.observations.map((item) => `- ${item}`).join("\n")
    : "- none";
  const tags = payloadBase.tags?.length
    ? payloadBase.tags.map((item) => `- ${item}`).join("\n")
    : "- none";
  const changed = changedFiles.length > 0
    ? changedFiles.map((item) => `- ${item}`).join("\n")
    : "- none";

  return [
    "# Datalox Post-Run Review",
    "You are a second-pass reviewer deciding whether this wrapped run produced reusable repo-local knowledge.",
    "Persist only when the run revealed a grounded, reusable workflow, correction, or pitfall that future agents should follow.",
    "Return action=\"noop\" for one-off work, generic success/failure logging, or guidance already covered by the matched skill/notes.",
    "Prefer caution. Bad saves are worse than missed saves.",
    "",
    "Return JSON only. No markdown fences.",
    "",
    "{",
    "  \"action\": \"noop\" | \"persist\",",
    "  \"reason\": \"short reason\",",
    "  \"summary\": \"required when action=persist\",",
    "  \"title\": \"required when action=persist\",",
    "  \"signal\": \"required when action=persist\",",
    "  \"interpretation\": \"required when action=persist\",",
    "  \"recommendedAction\": \"required when action=persist\",",
    "  \"observations\": [\"optional concrete observations\"],",
    "  \"tags\": [\"optional tags\"]",
    "}",
    "",
    "## Current Loop Context",
    `Task: ${payloadBase.task ?? "(missing)"}`,
    `Workflow: ${payloadBase.workflow ?? "(missing)"}`,
    `Matched skill: ${payloadBase.skillId ?? "none"}`,
    `Trigger: ${child.exitCode === 0 ? "success" : "failure"}`,
    `Exit code: ${child.exitCode}`,
    `Selection basis: ${envelope.guidance.selectionBasis}`,
    "",
    "## Existing Guidance",
    `What to do now: ${envelope.guidance.whatToDoNow.join(" | ") || "none"}`,
    `Watch for: ${envelope.guidance.watchFor.join(" | ") || "none"}`,
    "Supporting notes:",
    renderReviewNotes(envelope.guidance.supportingNotes),
    "",
    "## Grounded Evidence",
    "Observations:",
    observations,
    "Tags:",
    tags,
    "Changed files:",
    changed,
    "",
    "## Wrapped Transcript",
    transcript,
  ].join("\n");
}

function tryParseJsonBlock(text: string): unknown {
  const trimmed = text.trim();
  if (trimmed.length === 0) {
    throw new Error("Reviewer returned empty output.");
  }

  try {
    return JSON.parse(trimmed);
  } catch {
    // fall through
  }

  const fenced = trimmed.match(/```(?:json)?\s*([\s\S]*?)```/i);
  if (fenced?.[1]) {
    return JSON.parse(fenced[1].trim());
  }

  const start = trimmed.indexOf("{");
  const end = trimmed.lastIndexOf("}");
  if (start !== -1 && end !== -1 && end > start) {
    return JSON.parse(trimmed.slice(start, end + 1));
  }

  throw new Error("Reviewer output did not contain a JSON object.");
}

function maybeNonEmptyString(value: unknown): string | undefined {
  return typeof value === "string" && value.trim().length > 0 ? value.trim() : undefined;
}

function maybeStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .filter((item): item is string => typeof item === "string")
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, 8);
}

function parseReviewDecision(raw: unknown): WrapperReviewDecision {
  if (!raw || typeof raw !== "object") {
    throw new Error("Reviewer JSON must be an object.");
  }

  const action = (raw as { action?: unknown }).action;
  if (action !== "noop" && action !== "persist") {
    throw new Error("Reviewer action must be 'noop' or 'persist'.");
  }

  const reason = maybeNonEmptyString((raw as { reason?: unknown }).reason);
  if (!reason) {
    throw new Error("Reviewer reason is required.");
  }

  const decision: WrapperReviewDecision = {
    action,
    reason,
    summary: maybeNonEmptyString((raw as { summary?: unknown }).summary),
    title: maybeNonEmptyString((raw as { title?: unknown }).title),
    signal: maybeNonEmptyString((raw as { signal?: unknown }).signal),
    interpretation: maybeNonEmptyString((raw as { interpretation?: unknown }).interpretation),
    recommendedAction: maybeNonEmptyString((raw as { recommendedAction?: unknown }).recommendedAction),
    observations: maybeStringArray((raw as { observations?: unknown }).observations),
    tags: maybeStringArray((raw as { tags?: unknown }).tags),
  };

  if (decision.action === "persist") {
    if (!decision.summary || !decision.title || !decision.signal || !decision.interpretation || !decision.recommendedAction) {
      throw new Error("Persist decisions must include summary, title, signal, interpretation, and recommendedAction.");
    }
  }

  return decision;
}

async function runSecondPassReview(
  envelope: LoopEnvelope,
  child: WrappedCommandResult,
  payloadBase: RecordTurnResultInput,
  reviewer: WrapperReviewRunner | null | undefined,
  changedFiles: string[],
  eventPath: string,
): Promise<WrapperReviewResult> {
  if (!reviewer) {
    return {
      status: "skipped",
      model: null,
      decision: null,
      persisted: null,
      error: "No autonomous reviewer is configured for this wrapper path.",
    };
  }

  try {
    const prompt = buildReviewPrompt(envelope, child, payloadBase, changedFiles);
    const reviewRun = reviewer.run(prompt, envelope);
    if (reviewRun.exitCode !== 0) {
      return {
        status: "failed",
        model: reviewer.model,
        decision: null,
        persisted: null,
        error: reviewRun.stderr.trim() || `Reviewer exited with code ${reviewRun.exitCode}.`,
      };
    }

    const decision = parseReviewDecision(tryParseJsonBlock(reviewRun.stdout));
    const persisted = decision.action === "persist"
      ? await patchKnowledge({
        repoPath: envelope.repoPath,
        task: payloadBase.task,
        workflow: payloadBase.workflow,
        step: payloadBase.step,
        skillId: payloadBase.skillId,
        summary: decision.summary,
        observations: decision.observations,
        transcript: payloadBase.transcript,
        tags: [...(payloadBase.tags ?? []), ...decision.tags],
        title: decision.title,
        signal: decision.signal,
        interpretation: decision.interpretation,
        recommendedAction: decision.recommendedAction,
        eventPath,
        sessionId: payloadBase.sessionId,
        hostKind: payloadBase.hostKind,
      })
      : null;

    return {
      status: "completed",
      model: reviewer.model,
      decision,
      persisted,
    };
  } catch (error) {
    return {
      status: "failed",
      model: reviewer.model,
      decision: null,
      persisted: null,
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

export async function finalizeWrappedRun(
  envelope: LoopEnvelope,
  child: WrappedCommandResult | null,
  input: WrapperPostRunInput & { hostKind: string; reviewer?: WrapperReviewRunner | null },
): Promise<WrapperPostRunResult> {
  const postRunMode = input.postRunMode ?? "trajectory";
  if (!child || !envelope.active) {
    return {
      mode: "off",
      trigger: "disabled",
      result: null,
      review: null,
      backlog: null,
      maintenance: null,
    };
  }

  if (postRunMode === "off") {
    return {
      mode: "off",
      trigger: "disabled",
      result: null,
      review: null,
      backlog: null,
      maintenance: null,
    };
  }
  const sanitized = sanitizeWrappedCommandResult(child);
  const markers = sanitized.markers;
  const changedFiles = collectChangedFiles(envelope.repoPath);
  if (postRunMode === "trajectory") {
    const trajectoryRow = await loadTrajectoryRowMarker(envelope.repoPath, markers);
    if (trajectoryRow === null) {
      return {
        mode: "trajectory",
        trigger: "missing_trajectory_row",
        result: null,
        review: null,
        backlog: null,
        maintenance: null,
      };
    }
    const recordedTrajectory = await recordTrajectory({
      repoPath: envelope.repoPath,
      trajectoryRow,
    });
    return {
      mode: "trajectory",
      trigger: "trajectory_row",
      result: recordedTrajectory,
      review: null,
      backlog: null,
      maintenance: null,
    };
  }

  const trigger = hasExplicitPromotionSignal(markers)
    ? "explicit_signal"
    : sanitized.child.exitCode !== 0
      ? "failure_exit"
      : "record_only";

  const observations = markers.observations.length > 0
    ? [...markers.observations]
    : sanitized.child.exitCode !== 0
      ? [buildFailureObservation(sanitized.child)].filter((value): value is string => Boolean(value))
      : [];
  const eventClass = hasExplicitPromotionSignal(markers) ? "candidate" : "trace";

  const payloadBase = buildObservedTurnPayload(envelope, {
    hostKind: input.hostKind,
    sourceKind: "trace",
    eventClass,
    task: input.task ?? (envelope.originalPrompt || undefined),
    workflow: input.workflow,
    step: input.step,
    skillId: input.skillId,
    adjudicationDecision: markers.adjudicationDecision,
    adjudicationSkillId: markers.adjudicationSkillId,
    summary: input.summary
      ?? markers.summary
      ?? extractChildSummary(sanitized.child),
    observations,
    transcript: buildTranscript(envelope, sanitized.child, STORED_TRANSCRIPT_LIMITS),
    changedFiles,
    tags: [
      ...(input.tags ?? []),
      ...markers.tags,
      `wrapper:${input.hostKind}`,
      sanitized.child.exitCode === 0 ? "success" : "failure",
    ],
    title: markers.title,
    signal: markers.signal,
    interpretation: markers.interpretation,
    recommendedAction: markers.recommendedAction,
    eventKind: input.eventKind ?? markers.eventKind ?? `wrapper:${input.hostKind}:${sanitized.child.exitCode === 0 ? "success" : "failure"}`,
  });

  const recorded = await recordObservedTurnPayload(envelope, payloadBase, {
    applyMatchedNotes: sanitized.child.exitCode === 0,
  });

  if (postRunMode === "review" && !input.reviewer) {
    throw new Error(`Autonomous review is not configured for the ${input.hostKind} wrapper path.`);
  }

  if (postRunMode === "review") {
    const review = await runSecondPassReview(
      envelope,
      sanitized.child,
      payloadBase,
      input.reviewer,
      changedFiles,
      recorded.event.relativePath,
    );
    const maintenance = await runAutomaticMaintenance({
      repoPath: envelope.repoPath,
      reason: `wrapper:${input.hostKind}:review`,
    });
    return {
      mode: "review",
      trigger,
      result: recorded,
      review,
      backlog: maintenance.afterBacklog ?? maintenance.beforeBacklog,
      maintenance,
    };
  }

  const shouldCompile = postRunMode !== "record";
  const result = shouldCompile
    ? await compileRecordedEvent({
      repoPath: envelope.repoPath,
      eventPath: recorded.event.relativePath,
      minWikiOccurrences: input.minWikiOccurrences,
      minSkillOccurrences: input.minSkillOccurrences,
    })
    : recorded;

  const maintenance = await runAutomaticMaintenance({
    repoPath: envelope.repoPath,
    reason: `wrapper:${input.hostKind}:${shouldCompile ? "promote" : "record"}`,
  });

  return {
    mode: shouldCompile ? "promote" : "record",
    trigger,
    result,
    review: null,
    backlog: maintenance.afterBacklog ?? maintenance.beforeBacklog,
    maintenance,
  };
}
