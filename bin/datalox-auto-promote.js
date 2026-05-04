#!/usr/bin/env node

import { existsSync, readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { fileURLToPath, pathToFileURL } from "node:url";

function parseArgs(argv) {
  const parsed = { _: [] };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (!arg.startsWith("--")) {
      parsed._.push(arg);
      continue;
    }

    const key = arg.slice(2);
    const next = argv[index + 1];
    const hasValue = next !== undefined && !next.startsWith("--");
    parsed[key] = hasValue ? next : true;
    if (hasValue) {
      index += 1;
    }
  }

  return parsed;
}

function parseOptionalPositiveInt(value) {
  if (value === undefined || value === null || value === "") {
    return undefined;
  }

  const parsed = Number.parseInt(String(value), 10);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : undefined;
}

function parseEventClass(value, fallback = "trace") {
  if (value === "trace" || value === "candidate") {
    return value;
  }
  return fallback;
}

async function readStdin() {
  if (process.stdin.isTTY) {
    return "";
  }

  const chunks = [];
  for await (const chunk of process.stdin) {
    chunks.push(chunk);
  }
  return Buffer.concat(chunks).toString("utf8");
}

function parseJson(value) {
  if (!value || !value.trim()) {
    return null;
  }

  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

function truncate(value, maxLength = 240) {
  const normalized = String(value ?? "").replace(/\s+/g, " ").trim();
  if (normalized.length <= maxLength) {
    return normalized;
  }
  return `${normalized.slice(0, maxLength - 1).trim()}…`;
}

function parseDataloxMarkers(text) {
  const normalizedText = typeof text === "string"
    ? text.replaceAll("\\r\\n", "\n").replaceAll("\\n", "\n")
    : "";
  const parsed = {
    cleanedText: normalizedText,
    adjudicationDecision: undefined,
    adjudicationSkillId: undefined,
    title: undefined,
    signal: undefined,
    interpretation: undefined,
    recommendedAction: undefined,
    observations: [],
  };

  if (normalizedText.trim().length === 0) {
    return parsed;
  }

  const keptLines = [];
  for (const rawLine of normalizedText.split(/\r?\n/)) {
    const line = rawLine.trim();
    const match = line.match(/^DATALOX_([A-Z_]+):\s*(.+)$/);
    if (!match) {
      keptLines.push(rawLine);
      continue;
    }

    const [, key, rawValue] = match;
    const value = rawValue.trim();
    switch (key) {
      case "DECISION":
        parsed.adjudicationDecision = value;
        break;
      case "SKILL":
        parsed.adjudicationSkillId = value;
        break;
      case "TITLE":
        parsed.title = value;
        break;
      case "SIGNAL":
        parsed.signal = value;
        break;
      case "INTERPRETATION":
        parsed.interpretation = value;
        break;
      case "ACTION":
      case "RECOMMENDED_ACTION":
        parsed.recommendedAction = value;
        break;
      case "OBSERVATION":
        parsed.observations.push(value);
        break;
      default:
        break;
    }
  }

  parsed.cleanedText = keptLines.join("\n").trim();
  return parsed;
}

function firstTextContent(message) {
  const content = message?.message?.content;
  if (!Array.isArray(content)) {
    return null;
  }

  const texts = content
    .filter((item) => item?.type === "text" && typeof item.text === "string")
    .map((item) => item.text.trim())
    .filter(Boolean);

  return texts.length > 0 ? texts.join("\n") : null;
}

function parseTranscript(transcriptPath) {
  if (!transcriptPath || !existsSync(transcriptPath)) {
    return {
      task: null,
      summary: null,
      transcript: null,
    };
  }

  const raw = readFileSync(transcriptPath, "utf8")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

  const entries = raw.map((line) => {
    try {
      return JSON.parse(line);
    } catch {
      return null;
    }
  }).filter(Boolean);

  const lastUser = [...entries]
    .reverse()
    .find((entry) => entry.type === "user" && firstTextContent(entry));
  const lastAssistant = [...entries]
    .reverse()
    .find((entry) =>
      entry.type === "assistant"
      && firstTextContent(entry)
      && entry.isApiErrorMessage !== true
    );

  const task = firstTextContent(lastUser);
  const assistantText = firstTextContent(lastAssistant);
  const markers = parseDataloxMarkers(assistantText);
  const summary = markers.cleanedText || assistantText;
  const transcript = [
    task ? `User: ${task}` : null,
    summary ? `Assistant: ${summary}` : null,
  ]
    .filter(Boolean)
    .join("\n\n");

  return {
    task: task ? truncate(task, 400) : null,
    summary: summary ? truncate(summary, 400) : null,
    transcript: transcript || null,
    markers,
  };
}

function parseGitChangedPaths(repoPath) {
  const result = spawnSync("git", ["status", "--short"], {
    cwd: repoPath,
    encoding: "utf8",
  });

  if (result.status !== 0) {
    return [];
  }

  return result.stdout
    .split("\n")
    .map((line) => line.trimEnd())
    .filter(Boolean)
    .map((line) => line.slice(3).trim())
    .filter(Boolean)
    .map((line) => line.includes(" -> ") ? line.split(" -> ").at(-1) : line);
}

function resolvePackRoot(args) {
  const candidates = [
    typeof args["pack-root"] === "string" ? args["pack-root"] : null,
    process.env.DATALOX_PACK_ROOT,
    path.resolve(path.dirname(fileURLToPath(import.meta.url)), ".."),
    path.join(os.homedir(), ".datalox", "cache", "datalox-trajectory-mcp"),
  ].filter(Boolean);

  for (const candidate of candidates) {
    const normalized = path.resolve(candidate);
    if (existsSync(path.join(normalized, "scripts", "lib", "agent-pack.mjs"))) {
      return normalized;
    }
  }

  throw new Error("Unable to resolve Datalox pack root for auto-promote hook");
}

function resolvePackDistModuleUrl(packRoot, ...relativeParts) {
  const modulePath = path.join(packRoot, "dist", ...relativeParts);
  if (!existsSync(modulePath)) {
    throw new Error(`Missing built Datalox module: ${path.relative(packRoot, modulePath)}`);
  }
  return pathToFileURL(modulePath).href;
}

function resolveRepoPath(args, payload) {
  const candidate = typeof args.repo === "string"
    ? args.repo
    : payload?.cwd
      ?? payload?.repo_path
      ?? payload?.project_path
      ?? payload?.workspace_path
      ?? process.env.CLAUDE_PROJECT_DIR
      ?? process.cwd();
  return path.resolve(candidate);
}

function runAutoBootstrap(packRoot, repoPath) {
  const entrypoint = path.join(packRoot, "dist", "src", "cli", "main.js");
  if (!existsSync(entrypoint)) {
    return null;
  }

  const result = spawnSync(process.execPath, [entrypoint, "auto-bootstrap", "--repo", repoPath, "--json"], {
    cwd: repoPath,
    encoding: "utf8",
  });

  if (result.status !== 0) {
    throw new Error(result.stderr.trim() || result.stdout.trim() || "auto-bootstrap failed");
  }

  return parseJson(result.stdout);
}

function buildObservations(changedPaths, payload) {
  const observations = [];
  if (changedPaths.length > 0) {
    observations.push(`Changed files: ${changedPaths.slice(0, 8).join(", ")}`);
  }
  if (payload?.hook_event_name) {
    observations.push(`Hook event: ${payload.hook_event_name}`);
  }
  if (payload?.stop_hook_active === true) {
    observations.push("Stop hook resumed the agent previously.");
  }
  return observations;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const payload = parseJson(await readStdin()) ?? {};

  if (payload?.stop_hook_active === true) {
    return;
  }

  const repoPath = resolveRepoPath(args, payload);
  const packRoot = resolvePackRoot(args);
  const configPath = path.join(repoPath, ".datalox", "config.json");
  if (!existsSync(configPath)) {
    runAutoBootstrap(packRoot, repoPath);
    if (!existsSync(configPath)) {
      return;
    }
  }

  const transcriptPath = typeof args["transcript-path"] === "string"
    ? args["transcript-path"]
    : payload?.transcript_path ?? payload?.transcriptPath;
  const transcript = parseTranscript(transcriptPath ? path.resolve(transcriptPath) : null);
  const changedPaths = parseGitChangedPaths(repoPath);
  const observations = buildObservations(changedPaths, payload);
  const task = typeof args.task === "string" ? args.task : transcript.task;
  const summary = typeof args.summary === "string" ? args.summary : transcript.summary;
  const workflow = typeof args.workflow === "string"
    ? args.workflow
    : typeof payload?.workflow === "string"
      ? payload.workflow
      : process.env.DATALOX_DEFAULT_WORKFLOW;
  const eventClass = parseEventClass(
    typeof args["event-class"] === "string"
      ? args["event-class"]
      : process.env.DATALOX_HOOK_EVENT_CLASS,
    "trace",
  );
  const interpretation = typeof args.interpretation === "string"
    ? args.interpretation
    : eventClass === "candidate"
      ? `Automatic post-turn promotion from ${payload?.hook_event_name ?? "host-hook"}.`
      : undefined;
  const recommendedAction = typeof args.action === "string"
    ? args.action
    : eventClass === "candidate"
      ? "Promote only if this gap repeats enough to justify a wiki page or skill."
      : undefined;

  if (!task && !summary && observations.length === 0) {
    return;
  }

  const sharedModuleUrl = resolvePackDistModuleUrl(packRoot, "src", "adapters", "shared.js");
  const coreModuleUrl = resolvePackDistModuleUrl(packRoot, "src", "core", "packCore.js");
  const {
    buildLoopEnvelope,
    buildObservedTurnPayload,
    recordObservedTurnPayload,
  } = await import(sharedModuleUrl);
  const { compileRecordedEvent, runAutomaticMaintenance } = await import(coreModuleUrl);

  const normalizedTask = task ?? summary ?? "auto-promote-hook";
  const envelope = await buildLoopEnvelope({
    repoPath,
    task: normalizedTask,
    workflow,
    prompt: task ?? summary ?? undefined,
    sessionId: typeof payload?.session_id === "string"
      ? payload.session_id
      : typeof payload?.sessionId === "string"
        ? payload.sessionId
        : undefined,
  });
  const recordPayload = buildObservedTurnPayload(envelope, {
    hostKind: "hook",
    eventClass,
    task: normalizedTask,
    workflow,
    step: typeof args.step === "string" ? args.step : undefined,
    summary: summary ?? undefined,
    observations: [...observations, ...(transcript.markers?.observations ?? [])],
    transcript: transcript.transcript ?? undefined,
    changedFiles: changedPaths,
    tags: [
      "auto_hook",
      payload?.hook_event_name ? `hook:${String(payload.hook_event_name).toLowerCase()}` : null,
    ].filter(Boolean),
    title: typeof args.title === "string" ? args.title : transcript.markers?.title,
    signal: typeof args.signal === "string" ? args.signal : transcript.markers?.signal,
    interpretation: typeof args.interpretation === "string"
      ? args.interpretation
      : transcript.markers?.interpretation ?? interpretation,
    recommendedAction: typeof args.action === "string"
      ? args.action
      : transcript.markers?.recommendedAction ?? recommendedAction,
    adjudicationDecision: transcript.markers?.adjudicationDecision,
    adjudicationSkillId: transcript.markers?.adjudicationSkillId,
    eventKind: typeof args["event-kind"] === "string"
      ? args["event-kind"]
      : payload?.hook_event_name
        ? `hook:${payload.hook_event_name}`
        : "hook:auto-promote",
  });
  const recorded = await recordObservedTurnPayload(envelope, recordPayload, {
    applyMatchedNotes: true,
  });
  const result = await compileRecordedEvent(
    {
      eventPath: recorded.event.relativePath,
      minWikiOccurrences: parseOptionalPositiveInt(args["min-wiki-occurrences"])
        ?? parseOptionalPositiveInt(process.env.DATALOX_AUTO_PROMOTE_MIN_WIKI),
      minSkillOccurrences: parseOptionalPositiveInt(args["min-skill-occurrences"])
        ?? parseOptionalPositiveInt(process.env.DATALOX_AUTO_PROMOTE_MIN_SKILL),
    },
    repoPath,
  );

  process.stderr.write(
    `[datalox-auto-promote] ${result.decision.action} | ${result.decision.reason} | occurrences=${result.decision.occurrenceCount}\n`,
  );
  const maintenance = await runAutomaticMaintenance({
    repoPath,
    reason: "hook:auto-promote",
  });
  if (maintenance.status === "ran") {
    process.stderr.write(
      `[datalox-auto-promote] maintenance | ran | scanned=${maintenance.maintenance?.scannedEvents ?? "?"} | notes=${maintenance.maintenance?.noteActions?.length ?? 0} | rollups=${maintenance.maintenance?.rollupActions?.length ?? 0} | skills=${maintenance.maintenance?.skillActions?.length ?? 0} | uncovered=${maintenance.afterBacklog?.uncoveredEvents ?? "?"}\n`,
    );
  } else if (maintenance.beforeBacklog?.maintenanceRecommended) {
    process.stderr.write(
      `[datalox-auto-promote] maintenance_backlog | ${maintenance.beforeBacklog.policy.level} | uncovered=${maintenance.beforeBacklog.uncoveredEvents} | maintainable_groups=${maintenance.beforeBacklog.maintainableUnresolvedTraceGroupCount} | ${maintenance.beforeBacklog.recommendedCommand} | skipped=${maintenance.skippedReason ?? "unknown"}\n`,
    );
  }
}

main().catch((error) => {
  process.stderr.write(`[datalox-auto-promote] ${error instanceof Error ? error.message : String(error)}\n`);
  process.exit(1);
});
