import { existsSync } from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import {
  autoBootstrapIfSafe,
  getDefaultPackUrl,
  probeBootstrapCandidate,
  syncNoteRetrieval,
} from "../core/packCore.js";
import {
  disableHostIntegrations,
  inspectEnforcementStatus,
  installHostIntegrations,
  type InstallHost,
} from "../core/installCore.js";
import { runClaudeWrapper } from "../adapters/claude/run.js";
import { runCodexWrapper } from "../adapters/codex/run.js";
import { runGenericWrapper } from "../adapters/generic/run.js";
import type { WrapperPostRunMode } from "../adapters/shared.js";
import { getSharedCliCommand, parseSharedCliInput } from "../surface/sharedCommands.js";
import { parseCliArgs, toStringArray } from "./args.js";

function resolveCliPackRoot(): string {
  const candidates = [
    fileURLToPath(new URL("../../", import.meta.url)),
    fileURLToPath(new URL("../../../", import.meta.url)),
  ];

  for (const candidate of candidates) {
    if (
      existsSync(path.join(candidate, "package.json"))
      && existsSync(path.join(candidate, "scripts", "lib", "agent-pack.mjs"))
    ) {
      return candidate;
    }
  }

  return candidates[candidates.length - 1];
}

function usage(): string {
  return [
    "Usage:",
    "  datalox install [all|codex|claude] [--json]",
    "  datalox disable [all|codex|claude] [--json]",
    "  datalox status [--repo <path>] [--json]",
    "  datalox bootstrap [--repo <path>] [--pack-source <path-or-git-url>] [--json]",
    "  datalox setup [all|codex|claude] [--repo <path>] [--pack-source <path-or-git-url>] [--json]",
    "  datalox adopt <host-repo-path> [--pack-source <path-or-git-url>] [--json]",
    "  datalox probe-bootstrap [--repo <path>] [--json]",
    "  datalox auto-bootstrap [--repo <path>] [--pack-source <path-or-git-url>] [--json]",
    "  datalox capture-web [--repo <path>] --url <url> [--artifact <design-doc|design-tokens|css-variables|tailwind-theme|note|source-page>] [--title <title>] [--slug <slug>] [--output <path>] [--json]",
    "  datalox capture-design [--repo <path>] --url <url> [--title <title>] [--slug <slug>] [--output <path>] [--json]",
    "  datalox capture-pdf [--repo <path>] --path <pdf-path> [--title <title>] [--slug <slug>] [--source-url <url>] [--json]",
    "  datalox publish-web-capture [--repo <path>] --capture <slug> [--bucket <bucket>] [--prefix <prefix>] [--public-base-url <url>] [--json]",
    "  datalox resolve [--repo <path>] [--task <task>] [--workflow <workflow>] [--step <step>] [--skill <skill-id>] [--limit <n>] [--include-content] [--json]",
    "  datalox retrieval sync [--repo <path>] [--json]",
    "  datalox record-trajectory [--repo <path>] --trajectory-row <json-file> [--json]",
    "  datalox export-trajectories [--repo <path>] [--output <jsonl-path>] [--include-blocked-report <json-path>] [--split <train|validation|test|eval>] [--quality <use|needs-review|discard>] [--json]",
    "  datalox grade-trajectories [--repo <path>] [--event-path <event-json>] [--max-row-chars <n>] [--max-patch-chars <n>] [--max-snippet-chars <n>] [--max-metadata-chars <n>] [--json]",
    "  datalox repair-trajectory [--repo <path>] --event-path <event-json> --trajectory-row <json-file> [--json]",
    "  datalox record [--repo <path>] [--task <task>] [--workflow <workflow>] [--step <step>] [--skill <skill-id>] [--summary <summary>] [--observation <text>] [--changed-file <path>] [--transcript <text>] [--title <title>] [--signal <signal>] [--interpretation <text>] [--action <text>] [--outcome <text>] [--tag <tag>] [--event-kind <kind>] [--trajectory-row <json-file>] [--json]",
    "  datalox patch [--repo <path>] [--task <task>] [--workflow <workflow>] [--step <step>] [--skill <skill-id>] [--summary <summary>] [--observation <text>] [--transcript <text>] [--title <title>] [--signal <signal>] [--interpretation <text>] [--action <text>] [--event-path <path>] [--session-id <id>] [--host-kind <kind>] [--admin-override] [--tag <tag>] [--json]",
    "  datalox promote [--repo <path>] [--task <task>] [--workflow <workflow>] [--step <step>] [--skill <skill-id>] [--summary <summary>] [--observation <text>] [--changed-file <path>] [--transcript <text>] [--title <title>] [--signal <signal>] [--interpretation <text>] [--action <text>] [--outcome <text>] [--tag <tag>] [--event-kind <kind>] [--event-path <path>] [--session-id <id>] [--host-kind <kind>] [--admin-override] [--min-wiki-occurrences <n>] [--min-skill-occurrences <n>] [--json]",
    "  datalox maintain [--repo <path>] [--max-events <n>] [--include-covered] [--min-note-occurrences <n>] [--min-skill-occurrences <n>] [--synthesize-skills] [--json]",
    "  datalox lint [--repo <path>] [--json]",
    "  datalox wrap prompt [--repo <path>] [--task <task>] [--workflow <workflow>] [--step <step>] [--skill <skill-id>] [--prompt <text>] [--json]",
    "  datalox wrap command [--repo <path>] [--task <task>] [--workflow <workflow>] [--step <step>] [--skill <skill-id>] [--prompt <text>] [--summary <summary>] [--tag <tag>] [--event-kind <kind>] [--post-run-mode <off|trajectory|record|auto|promote|review>] [--json] -- <command> [args with __DATALOX_PROMPT__ placeholders]",
    "  datalox claude [--repo <path>] [--task <task>] [--workflow <workflow>] [--step <step>] [--skill <skill-id>] [--prompt <text>] [--summary <summary>] [--tag <tag>] [--event-kind <kind>] [--post-run-mode <off|trajectory|record|auto|promote|review>] [--review-model <model>] [--min-wiki-occurrences <n>] [--min-skill-occurrences <n>] [--claude-bin <path>] [--json] [-- <claude args>]",
    "  datalox codex [--repo <path>] [--task <task>] [--workflow <workflow>] [--step <step>] [--skill <skill-id>] [--prompt <text>] [--summary <summary>] [--tag <tag>] [--event-kind <kind>] [--post-run-mode <off|trajectory|record|auto|promote|review>] [--review-model <model>] [--min-wiki-occurrences <n>] [--min-skill-occurrences <n>] [--codex-bin <path>] [--json] [-- <codex exec args>]",
  ].join("\n");
}

function writeResult(result: unknown, asJson: boolean): void {
  if (asJson) {
    process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
    return;
  }
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
}

function parsePositiveInt(value: string | string[] | boolean | undefined): number | undefined {
  if (typeof value !== "string") {
    return undefined;
  }
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function parsePostRunMode(
  value: string | string[] | boolean | undefined,
): WrapperPostRunMode | undefined {
  const raw = typeof value === "string"
    ? value
    : typeof process.env.DATALOX_DEFAULT_POST_RUN_MODE === "string"
      ? process.env.DATALOX_DEFAULT_POST_RUN_MODE
      : undefined;

  switch (raw) {
    case "off":
    case "trajectory":
    case "record":
    case "auto":
    case "promote":
    case "review":
      return raw;
    default:
      return undefined;
  }
}

function parseOptionalString(
  value: string | string[] | boolean | undefined,
  envKey?: string,
): string | undefined {
  if (typeof value === "string") {
    return value;
  }
  if (envKey) {
    const envValue = process.env[envKey];
    if (typeof envValue === "string" && envValue.trim().length > 0) {
      return envValue.trim();
    }
  }
  return undefined;
}

function parseInstallHost(value: string | undefined): InstallHost {
  switch (value) {
    case "codex":
    case "claude":
      return value;
    default:
      return "all";
  }
}

async function bootstrapRepo(repoPath?: string, packSource?: string) {
  const probeBefore = await probeBootstrapCandidate(repoPath);
  if (probeBefore.status === "ready" || !probeBefore.canAutoBootstrap) {
    return {
      repoPath: probeBefore.repoPath,
      probeBefore,
      action: "none" as const,
      adoption: null,
      probeAfter: probeBefore,
    };
  }
  return autoBootstrapIfSafe({
    repoPath,
    packSource,
  });
}

function writePostRunSummary(prefix: string, postRun: unknown): void {
  if (!postRun || typeof postRun !== "object") {
    return;
  }
  const typed = postRun as {
    mode?: string;
    trigger?: string;
    result?: {
      event?: { relativePath?: string };
      decision?: { action?: string; reason?: string; occurrenceCount?: number };
    } | null;
    review?: {
      status?: string;
      decision?: { action?: string; reason?: string } | null;
      error?: string;
    } | null;
    maintenance?: {
      status?: string;
      skippedReason?: string | null;
      maintenance?: {
        scannedEvents?: number;
        noteActions?: unknown[];
        rollupActions?: unknown[];
        skillActions?: unknown[];
      } | null;
      afterBacklog?: {
        uncoveredEvents?: number;
        maintenanceRecommended?: boolean;
      } | null;
    } | null;
  };
  const eventPath = typed.result?.event?.relativePath;
  const decision = typed.result?.decision;
  const review = typed.review;
  const maintenance = typed.maintenance;
  const backlog = (typed as {
    backlog?: {
      maintenanceRecommended?: boolean;
      policy?: { level?: string };
      uncoveredEvents?: number;
      maintainableUnresolvedTraceGroupCount?: number;
      recommendedCommand?: string;
    } | null;
  }).backlog;
  if (maintenance?.status === "ran") {
    process.stderr.write(
      `[${prefix}] maintenance | ran | scanned=${maintenance.maintenance?.scannedEvents ?? "?"} | notes=${maintenance.maintenance?.noteActions?.length ?? 0} | rollups=${maintenance.maintenance?.rollupActions?.length ?? 0} | skills=${maintenance.maintenance?.skillActions?.length ?? 0} | uncovered=${maintenance.afterBacklog?.uncoveredEvents ?? "?"}\n`,
    );
  } else if (maintenance?.status === "skipped" && maintenance.skippedReason && maintenance.skippedReason !== "no_maintenance_backlog") {
    process.stderr.write(
      `[${prefix}] maintenance | skipped | ${maintenance.skippedReason}\n`,
    );
  }
  if (backlog?.maintenanceRecommended) {
    process.stderr.write(
      `[${prefix}] maintenance_backlog | ${backlog.policy?.level ?? "warn"} | uncovered=${backlog.uncoveredEvents ?? "?"} | maintainable_groups=${backlog.maintainableUnresolvedTraceGroupCount ?? "?"} | ${backlog.recommendedCommand ?? "datalox maintain --json"}\n`,
    );
  }
  if (typed.mode === "review") {
    if (review?.status === "completed" && review.decision) {
      process.stderr.write(
        `[${prefix}] review | ${review.decision.action} | ${review.decision.reason ?? "no reason"}${eventPath ? ` | ${eventPath}` : ""}\n`,
      );
      return;
    }
    process.stderr.write(
      `[${prefix}] review | ${review?.status ?? "failed"} | ${review?.error ?? "review unavailable"}${eventPath ? ` | ${eventPath}` : ""}\n`,
    );
    return;
  }
  if (decision?.action) {
    process.stderr.write(
      `[${prefix}] ${decision.action} | ${decision.reason ?? "no reason"} | occurrences=${decision.occurrenceCount ?? "?"}${eventPath ? ` | ${eventPath}` : ""}\n`,
    );
    return;
  }
  process.stderr.write(
    `[${prefix}] ${typed.mode ?? "record"} | ${typed.trigger ?? "record_only"}${eventPath ? ` | ${eventPath}` : ""}\n`,
  );
}

async function main(): Promise<void> {
  const args = parseCliArgs(process.argv.slice(2));
  const [command, positional, ...rest] = args._;
  const asJson = args.json === true;
  const sharedCommand = getSharedCliCommand(command);

  if (sharedCommand) {
    const result = await sharedCommand.run(parseSharedCliInput(sharedCommand, args));
    writeResult(result, true);
    return;
  }

  switch (command) {
    case "install": {
      const host = parseInstallHost(positional);
      const result = await installHostIntegrations({
        host,
        packRootPath: resolveCliPackRoot(),
      });
      writeResult(result, true);
      return;
    }
    case "disable": {
      const host = parseInstallHost(positional);
      const result = await disableHostIntegrations({
        host,
        packRootPath: resolveCliPackRoot(),
      });
      writeResult(result, true);
      return;
    }
    case "status": {
      const result = await inspectEnforcementStatus({
        packRootPath: resolveCliPackRoot(),
        repoPath: typeof args.repo === "string" ? args.repo : undefined,
      });
      writeResult(result, true);
      return;
    }
    case "bootstrap": {
      const result = await bootstrapRepo(
        typeof args.repo === "string" ? args.repo : undefined,
        typeof args["pack-source"] === "string" ? args["pack-source"] : undefined,
      );
      writeResult(result, true);
      return;
    }
    case "setup": {
      const host = parseInstallHost(positional);
      const install = await installHostIntegrations({
        host,
        packRootPath: resolveCliPackRoot(),
      });
      const bootstrap = await bootstrapRepo(
        typeof args.repo === "string" ? args.repo : undefined,
        typeof args["pack-source"] === "string" ? args["pack-source"] : undefined,
      );
      writeResult({ install, bootstrap }, true);
      return;
    }
    case "probe-bootstrap": {
      const result = await probeBootstrapCandidate(typeof args.repo === "string" ? args.repo : undefined);
      writeResult(result, true);
      return;
    }
    case "auto-bootstrap": {
      const result = await autoBootstrapIfSafe({
        repoPath: typeof args.repo === "string" ? args.repo : undefined,
        packSource: typeof args["pack-source"] === "string" ? args["pack-source"] : undefined,
      });
      writeResult(result, true);
      return;
    }
    case "retrieval": {
      if (positional !== "sync") {
        throw new Error("retrieval requires a subcommand; supported: sync");
      }
      const result = await syncNoteRetrieval({
        repoPath: typeof args.repo === "string" ? args.repo : undefined,
      });
      writeResult(result, true);
      return;
    }
    case "wrap": {
      const subcommand = positional;
      const wrapInput = {
        repoPath: typeof args.repo === "string" ? args.repo : undefined,
        task: typeof args.task === "string" ? args.task : undefined,
        workflow: typeof args.workflow === "string" ? args.workflow : undefined,
        step: typeof args.step === "string" ? args.step : undefined,
        skill: typeof args.skill === "string" ? args.skill : undefined,
        prompt: typeof args.prompt === "string" ? args.prompt : undefined,
        summary: typeof args.summary === "string" ? args.summary : undefined,
        tags: toStringArray(args.tag),
        eventKind: typeof args["event-kind"] === "string" ? args["event-kind"] : undefined,
        postRunMode: parsePostRunMode(args["post-run-mode"]),
        reviewModel: parseOptionalString(args["review-model"], "DATALOX_DEFAULT_REVIEW_MODEL"),
        minWikiOccurrences: parsePositiveInt(args["min-wiki-occurrences"]),
        minSkillOccurrences: parsePositiveInt(args["min-skill-occurrences"]),
      };

      if (subcommand === "prompt") {
        const result = await runGenericWrapper(wrapInput);
        if (asJson) {
          writeResult(result, true);
          return;
        }
        process.stdout.write(`${result.envelope.wrappedPrompt}\n`);
        return;
      }

      if (subcommand === "command") {
        if (rest.length === 0) {
          throw new Error("wrap command requires a command after --");
        }
        const [childCommand, ...childArgs] = rest;
        const result = await runGenericWrapper({
          ...wrapInput,
          command: childCommand,
          args: childArgs,
        });
        if (asJson) {
          writeResult(result, true);
          process.exitCode = result.child?.exitCode ?? 0;
          return;
        }
        if (result.child?.stdout) {
          process.stdout.write(result.child.stdout);
        }
        if (result.child?.stderr) {
          process.stderr.write(result.child.stderr);
        }
        writePostRunSummary("datalox-wrap", result.postRun);
        process.exitCode = result.child?.exitCode ?? 0;
        return;
      }

      throw new Error("wrap requires subcommand prompt or command");
    }
    case "codex": {
      const codexArgs = positional !== undefined ? [positional, ...rest] : rest;
      const result = await runCodexWrapper({
        repoPath: typeof args.repo === "string" ? args.repo : undefined,
        task: typeof args.task === "string" ? args.task : undefined,
        workflow: typeof args.workflow === "string" ? args.workflow : undefined,
        step: typeof args.step === "string" ? args.step : undefined,
        skill: typeof args.skill === "string" ? args.skill : undefined,
        prompt: typeof args.prompt === "string" ? args.prompt : undefined,
        summary: typeof args.summary === "string" ? args.summary : undefined,
        tags: toStringArray(args.tag),
        eventKind: typeof args["event-kind"] === "string" ? args["event-kind"] : undefined,
        postRunMode: parsePostRunMode(args["post-run-mode"]),
        reviewModel: parseOptionalString(args["review-model"], "DATALOX_DEFAULT_REVIEW_MODEL"),
        minWikiOccurrences: parsePositiveInt(args["min-wiki-occurrences"]),
        minSkillOccurrences: parsePositiveInt(args["min-skill-occurrences"]),
        codexBin: typeof args["codex-bin"] === "string" ? args["codex-bin"] : undefined,
        codexArgs,
      });
      if (asJson) {
        writeResult(result, true);
        process.exitCode = result.child.exitCode;
        return;
      }
      if (result.child.stdout) {
        process.stdout.write(result.child.stdout);
      }
      if (result.child.stderr) {
        process.stderr.write(result.child.stderr);
      }
      writePostRunSummary("datalox-codex", result.postRun);
      process.exitCode = result.child.exitCode;
      return;
    }
    case "claude": {
      const claudeArgs = positional !== undefined ? [positional, ...rest] : rest;
      const result = await runClaudeWrapper({
        repoPath: typeof args.repo === "string" ? args.repo : undefined,
        task: typeof args.task === "string" ? args.task : undefined,
        workflow: typeof args.workflow === "string" ? args.workflow : undefined,
        step: typeof args.step === "string" ? args.step : undefined,
        skill: typeof args.skill === "string" ? args.skill : undefined,
        prompt: typeof args.prompt === "string" ? args.prompt : undefined,
        summary: typeof args.summary === "string" ? args.summary : undefined,
        tags: toStringArray(args.tag),
        eventKind: typeof args["event-kind"] === "string" ? args["event-kind"] : undefined,
        postRunMode: parsePostRunMode(args["post-run-mode"]),
        reviewModel: parseOptionalString(args["review-model"], "DATALOX_DEFAULT_REVIEW_MODEL"),
        minWikiOccurrences: parsePositiveInt(args["min-wiki-occurrences"]),
        minSkillOccurrences: parsePositiveInt(args["min-skill-occurrences"]),
        claudeBin: typeof args["claude-bin"] === "string" ? args["claude-bin"] : undefined,
        claudeArgs,
      });
      if (asJson) {
        writeResult(result, true);
        process.exitCode = result.child.exitCode;
        return;
      }
      if (result.child.stdout) {
        process.stdout.write(result.child.stdout);
      }
      if (result.child.stderr) {
        process.stderr.write(result.child.stderr);
      }
      writePostRunSummary("datalox-claude", result.postRun);
      process.exitCode = result.child.exitCode;
      return;
    }
    case "help":
    case "--help":
    case "-h":
    case undefined:
      process.stdout.write(`${usage()}\n`);
      process.stdout.write(`Default pack URL: ${getDefaultPackUrl()}\n`);
      return;
    default:
      throw new Error(`Unknown command: ${command}`);
  }
}

main().catch((error: unknown) => {
  const message = error instanceof Error ? error.message : String(error);
  process.stderr.write(`${message}\n`);
  process.stderr.write(`${usage()}\n`);
  process.exit(1);
});
