import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import {
  autoBootstrapIfSafe,
  getDefaultPackUrl,
  probeBootstrapCandidate,
} from "../core/packCore.js";
import {
  disableHostIntegrations,
  inspectEnforcementStatus,
  installHostIntegrations,
  type InstallHost,
} from "../core/installCore.js";
import { packReplayBundle, verifyReplayBundle } from "../core/replayBundle.js";
import { readDataloxReplayProxyConfigFile } from "../core/mcpProxyConfig.js";
import { runReplayProxyServer } from "../mcp/replayProxyServer.js";
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
    if (isDataloxAgentReplayRoot(candidate)) {
      return candidate;
    }
  }

  return candidates[candidates.length - 1];
}

function isDataloxAgentReplayRoot(candidate: string): boolean {
  const packageJsonPath = path.join(candidate, "package.json");
  if (!existsSync(packageJsonPath) || !existsSync(path.join(candidate, "bin", "datalox.js"))) {
    return false;
  }
  try {
    const packageJson = JSON.parse(readFileSync(packageJsonPath, "utf8")) as { name?: unknown };
    return packageJson.name === "datalox-agent-replay";
  } catch {
    return false;
  }
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
    "  datalox bundle pack [--repo <path>] --bundle-id <id> [--json]",
    "  datalox bundle verify [--repo <path>] --bundle <bundle-path> [--json]",
    "  datalox proxy --mode <record|replay> [--repo <path>] [--config <json-path>] [--bundle <bundle-path>] [--json]",
    "  datalox wrap prompt [--repo <path>] [--task <task>] [--workflow <workflow>] [--step <step>] [--skill <skill-id>] [--prompt <text>] [--json]",
    "  datalox wrap command [--repo <path>] [--task <task>] [--workflow <workflow>] [--step <step>] [--skill <skill-id>] [--prompt <text>] [--summary <summary>] [--tag <tag>] [--event-kind <kind>] [--post-run-mode <off|replay>] [--json] -- <command> [args with __DATALOX_PROMPT__ placeholders]",
    "  datalox claude [--repo <path>] [--task <task>] [--workflow <workflow>] [--step <step>] [--skill <skill-id>] [--prompt <text>] [--summary <summary>] [--tag <tag>] [--event-kind <kind>] [--post-run-mode <off|replay>] [--review-model <model>] [--claude-bin <path>] [--json] [-- <claude args>]",
    "  datalox codex [--repo <path>] [--task <task>] [--workflow <workflow>] [--step <step>] [--skill <skill-id>] [--prompt <text>] [--summary <summary>] [--tag <tag>] [--event-kind <kind>] [--post-run-mode <off|replay>] [--review-model <model>] [--codex-bin <path>] [--json] [-- <codex exec args>]",
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
    case "replay":
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
    reason?: string;
    result?: {
      event?: { relativePath?: string };
      toolRecordCount?: number;
      decision?: { action?: string; reason?: string; occurrenceCount?: number };
    } | null;
  };
  const eventPath = typed.result?.event?.relativePath;
  const decision = typed.result?.decision;
  if (decision?.action) {
    process.stderr.write(
      `[${prefix}] ${decision.action} | ${decision.reason ?? "no reason"} | occurrences=${decision.occurrenceCount ?? "?"}${eventPath ? ` | ${eventPath}` : ""}\n`,
    );
    return;
  }
  process.stderr.write(
    `[${prefix}] ${typed.mode ?? "record"} | ${typed.trigger ?? "record_only"}${typed.reason ? ` | ${typed.reason}` : ""}${eventPath ? ` | ${eventPath}` : ""}\n`,
  );
}

async function main(): Promise<void> {
  const args = parseCliArgs(process.argv.slice(2));
  const [command, positional, ...rest] = args._;
  const asJson = args.json === true;
  if (args.help === true || command === "help" || command === "--help" || command === "-h" || command === undefined) {
    process.stdout.write(`${usage()}\n`);
    process.stdout.write(`Default pack URL: ${getDefaultPackUrl()}\n`);
    return;
  }
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
    case "bundle": {
      if (positional === "pack") {
        if (typeof args["bundle-id"] !== "string") {
          throw new Error("bundle pack requires --bundle-id");
        }
        const result = await packReplayBundle({
          repoPath: typeof args.repo === "string" ? args.repo : undefined,
          bundleId: args["bundle-id"],
        });
        writeResult(result, true);
        return;
      }
      if (positional === "verify") {
        if (typeof args.bundle !== "string") {
          throw new Error("bundle verify requires --bundle");
        }
        const result = await verifyReplayBundle({
          repoPath: typeof args.repo === "string" ? args.repo : undefined,
          bundlePath: args.bundle,
        });
        writeResult(result, true);
        return;
      }
      throw new Error("bundle requires subcommand pack or verify");
    }
    case "proxy": {
      const mode = typeof args.mode === "string" ? args.mode : undefined;
      const repoPath = typeof args.repo === "string" ? args.repo : undefined;
      if (mode === "record") {
        const configPath = typeof args.config === "string" ? args.config : "datalox.replay.json";
        await runReplayProxyServer({
          mode,
          repoPath,
          config: await readDataloxReplayProxyConfigFile({ repoPath, configPath }),
        });
        return;
      }
      if (mode === "replay") {
        if (typeof args.bundle !== "string") {
          throw new Error("proxy --mode replay requires --bundle");
        }
        await runReplayProxyServer({
          mode,
          repoPath,
          bundlePath: args.bundle,
        });
        return;
      }
      throw new Error("proxy requires --mode record or --mode replay");
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
