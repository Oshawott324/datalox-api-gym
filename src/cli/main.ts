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
import { exportSftFromRun } from "../core/exports/exportSftFromRun.js";
import { listInstalledFixtures } from "../core/fixtures/fixtureCache.js";
import { installFixturePack } from "../core/fixtures/installFixturePack.js";
import { installFixtureSet } from "../core/fixtures/installFixtureSet.js";
import { readFixtureCatalog } from "../core/fixtures/readFixtureCatalog.js";
import { resolveFixtureRuntime } from "../core/fixtures/resolveFixtureRuntime.js";
import { resolveFixtureSetRuntime } from "../core/fixtures/resolveFixtureSetRuntime.js";
import { validateNoToolNameCollisions } from "../core/fixtures/validateToolCollisions.js";
import { evalFixtureSetOpenAiCompatible } from "../core/run/openAiCompatibleFixtureEval.js";
import { runFixtureAgent } from "../core/run/runFixtureAgent.js";
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
    if (isDataloxApiGymRoot(candidate)) {
      return candidate;
    }
  }

  return candidates[candidates.length - 1];
}

function isDataloxApiGymRoot(candidate: string): boolean {
  const packageJsonPath = path.join(candidate, "package.json");
  if (!existsSync(packageJsonPath) || !existsSync(path.join(candidate, "bin", "datalox.js"))) {
    return false;
  }
  try {
    const packageJson = JSON.parse(readFileSync(packageJsonPath, "utf8")) as { name?: unknown };
    return packageJson.name === "datalox-api-gym";
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
    "  datalox fixtures list [--catalog <catalog.json>] [--cache-root <path>] [--json]",
    "  datalox fixtures install <fixture-ref|fixture-dir> [--catalog <catalog.json>] [--cache-root <path>] [--force] [--json]",
    "  datalox fixture-sets list --catalog <catalog.json> [--json]",
    "  datalox fixture-sets install <fixture-set-ref> --catalog <catalog.json> [--cache-root <path>] [--force] [--json]",
    "  datalox replay --fixture <fixture-ref> [--cache-root <path>]",
    "  datalox replay --fixture-set <fixture-set-ref> [--cache-root <path>]",
    "  datalox replay --fixtures <fixture-ref>... [--cache-root <path>]",
    "  datalox run --fixture <fixture-ref>|--fixture-set <fixture-set-ref>|--fixtures <fixture-ref>...|--bundle <bundle-path> --base-url <url> --model <model> --prompt <text> --out <run-dir> [--api-key <key>|--api-key-env <env>] [--max-steps <n>] [--json]",
    "  datalox world run --fixture <fixture-ref>|--fixture-set <fixture-set-ref>|--fixtures <fixture-ref>...|--bundle <bundle-path> --base-url <url> --model <model> --prompt <text> --out <run-dir> [--api-key <key>|--api-key-env <env>] [--max-steps <n>] [--json]",
    "  datalox eval --fixture-set <fixture-set-ref> --catalog <catalog.json> --model <model> [--base-url <url>] [--api-key <key>] [--cache-root <path>] [--split <train|dev|test>] [--max-tasks <n>] [--max-turns <n>] [--out <jsonl>] [--json]",
    "  datalox export sft --run <run-dir>|--run-path <run.json> --out <frames.jsonl> [--json]",
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
  if (value === undefined) {
    return undefined;
  }
  if (typeof value !== "string") {
    throw new Error(`Expected a positive integer, got ${JSON.stringify(value)}.`);
  }
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed < 1 || String(parsed) !== value) {
    throw new Error(`Expected a positive integer, got ${JSON.stringify(value)}.`);
  }
  return parsed;
}

function parseOptionalNumber(value: string | string[] | boolean | undefined): number | undefined {
  if (typeof value !== "string") {
    return undefined;
  }
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function requireStringArg(args: ReturnType<typeof parseCliArgs>, key: string): string {
  const value = args[key];
  if (typeof value !== "string" || value.trim().length === 0) {
    throw new Error(`--${key} is required`);
  }
  return value;
}

function parsePostRunMode(
  value: string | string[] | boolean | undefined,
): WrapperPostRunMode | undefined {
  if (value !== undefined) {
    if (value === "off" || value === "replay") {
      return value;
    }
    throw new Error(`Invalid --post-run-mode ${JSON.stringify(value)}. Allowed values: off, replay.`);
  }

  const envValue = process.env.DATALOX_DEFAULT_POST_RUN_MODE;
  if (envValue === undefined) {
    return undefined;
  }
  if (envValue === "off" || envValue === "replay") {
    return envValue;
  }
  throw new Error(`Invalid DATALOX_DEFAULT_POST_RUN_MODE ${JSON.stringify(envValue)}. Allowed values: off, replay.`);
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

function requireCliString(
  value: string | string[] | boolean | undefined,
  name: string,
  envKey?: string,
): string {
  const parsed = parseOptionalString(value, envKey);
  if (!parsed) {
    throw new Error(`${name} is required${envKey ? `; set --${name} or ${envKey}` : ""}.`);
  }
  return parsed;
}

function parseRunSplit(value: string | string[] | boolean | undefined): "train" | "dev" | "test" | undefined {
  if (value === undefined) {
    return undefined;
  }
  if (value === "train" || value === "dev" || value === "test") {
    return value;
  }
  throw new Error(`Invalid --split ${JSON.stringify(value)}. Allowed values: train, dev, test.`);
}

async function runReplayWorldFromCli(args: ReturnType<typeof parseCliArgs>, commandLabel: string) {
  if (typeof args.catalog === "string" || args.split !== undefined || args["max-tasks"] !== undefined || args["max-turns"] !== undefined) {
    throw new Error(`${commandLabel} no longer accepts --catalog, --split, --max-tasks, or --max-turns; use datalox eval for fixture-set batch evaluation.`);
  }

  const fixtureRefs = toStringArray(args.fixtures);
  const bundlePaths = toStringArray(args.bundle);
  const hasFixture = typeof args.fixture === "string";
  const hasFixtureSet = typeof args["fixture-set"] === "string";
  const envModeCount = [
    hasFixture,
    hasFixtureSet,
    fixtureRefs.length > 0,
    bundlePaths.length > 0,
  ].filter(Boolean).length;
  if (envModeCount !== 1) {
    throw new Error(`${commandLabel} requires exactly one replay world: --fixture, --fixture-set, --fixtures, or --bundle`);
  }

  return runFixtureAgent({
    repoPath: typeof args.repo === "string" ? args.repo : undefined,
    cacheRoot: typeof args["cache-root"] === "string" ? args["cache-root"] : undefined,
    fixtureRef: hasFixture ? args.fixture as string : undefined,
    fixtureRefs: fixtureRefs.length > 0 ? fixtureRefs : undefined,
    fixtureSetRef: hasFixtureSet ? args["fixture-set"] as string : undefined,
    bundlePaths: bundlePaths.length > 0 ? bundlePaths : undefined,
    activeFixtureRefs: toStringArray(args["active-fixture-ref"]),
    prompt: requireStringArg(args, "prompt"),
    systemPrompt: typeof args["system-prompt"] === "string" ? args["system-prompt"] : undefined,
    taskRef: typeof args["task-ref"] === "string" ? args["task-ref"] : undefined,
    model: {
      baseUrl: requireStringArg(args, "base-url"),
      model: requireStringArg(args, "model"),
      apiKey: typeof args["api-key"] === "string" ? args["api-key"] : undefined,
      apiKeyEnv: typeof args["api-key-env"] === "string" ? args["api-key-env"] : undefined,
      timeoutMs: parsePositiveInt(args["timeout-ms"]),
      temperature: parseOptionalNumber(args.temperature),
      topP: parseOptionalNumber(args["top-p"]),
      maxTokens: parsePositiveInt(args["max-tokens"]),
    },
    outDir: requireStringArg(args, "out"),
    maxSteps: parsePositiveInt(args["max-steps"]),
  });
}

function summarizeReplayWorldRun(result: Awaited<ReturnType<typeof runFixtureAgent>>): Record<string, unknown> {
  return {
    runDir: result.runDir,
    runPath: result.runPath,
    transcriptPath: result.transcriptPath,
    stopReason: result.run.stop_reason,
    finalAnswer: result.run.final_answer,
    stepCount: result.run.steps.length,
  };
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
    case "fixtures": {
      if (positional === "list") {
        if (typeof args.catalog === "string") {
          const catalog = await readFixtureCatalog(args.catalog);
          writeResult({
            source: "catalog",
            catalogPath: catalog.catalogPath,
            fixtures: catalog.catalog.fixtures.map((fixture) => ({
              ref: fixture.ref,
              status: fixture.status,
              tools: fixture.tools.map((tool) => `${tool.surface}:${tool.server}`),
            })),
          }, true);
        } else {
          const fixtures = await listInstalledFixtures({
            cacheRoot: typeof args["cache-root"] === "string" ? args["cache-root"] : undefined,
          });
          writeResult({
            source: "cache",
            cacheRoot: typeof args["cache-root"] === "string" ? args["cache-root"] : undefined,
            fixtures: fixtures.map((fixture) => ({
              ref: fixture.ref,
              status: fixture.status,
              tools: fixture.tools.map((tool) => `${tool.surface}:${tool.server}`),
              bundleSha256: fixture.bundleSha256,
            })),
          }, true);
        }
        return;
      }
      if (positional === "install") {
        const fixtureRefOrPath = rest[0];
        if (!fixtureRefOrPath) {
          throw new Error("fixtures install requires <fixture-ref|fixture-dir>");
        }
        const result = await installFixturePack({
          ...(typeof args.catalog === "string"
            ? { ref: fixtureRefOrPath, catalogPath: args.catalog }
            : { sourcePath: fixtureRefOrPath }),
          cacheRoot: typeof args["cache-root"] === "string" ? args["cache-root"] : undefined,
          force: args.force === true,
        });
        writeResult(result, true);
        return;
      }
      throw new Error("fixtures requires subcommand list or install");
    }
    case "fixture-sets": {
      if (positional === "list") {
        if (typeof args.catalog !== "string") {
          throw new Error("fixture-sets list requires --catalog");
        }
        const catalog = await readFixtureCatalog(args.catalog);
        writeResult({
          catalogPath: catalog.catalogPath,
          fixtureSets: catalog.catalog.fixture_sets.map((fixtureSet) => ({
            ref: fixtureSet.ref,
            status: fixtureSet.status,
            fixtures: fixtureSet.fixtures,
          })),
        }, true);
        return;
      }
      if (positional === "install") {
        const fixtureSetRef = rest[0];
        if (!fixtureSetRef) {
          throw new Error("fixture-sets install requires <fixture-set-ref>");
        }
        if (typeof args.catalog !== "string") {
          throw new Error("fixture-sets install requires --catalog");
        }
        const result = await installFixtureSet({
          ref: fixtureSetRef,
          catalogPath: args.catalog,
          cacheRoot: typeof args["cache-root"] === "string" ? args["cache-root"] : undefined,
          force: args.force === true,
        });
        writeResult(result, true);
        return;
      }
      throw new Error("fixture-sets requires subcommand list or install");
    }
    case "replay": {
      if (typeof args.fixture === "string") {
        const runtime = await resolveFixtureRuntime({
          ref: args.fixture,
          cacheRoot: typeof args["cache-root"] === "string" ? args["cache-root"] : undefined,
        });
        process.stderr.write(`${JSON.stringify({
          event: "datalox_replay_fixture_start",
          fixtureRef: runtime.ref,
          bundleId: runtime.bundleId,
          bundleSha256: runtime.bundleSha256,
          export: runtime.export,
          toolCatalogPaths: runtime.toolCatalogPaths,
          toolCatalogAbsolutePaths: runtime.toolCatalogAbsolutePaths,
          toolCatalogCount: runtime.toolCatalogCount,
          specs: runtime.specs,
          liveFallback: false,
        }, null, 2)}\n`);
        await runReplayProxyServer({
          mode: "replay",
          bundlePath: runtime.bundlePath,
          activeFixtureRefs: [runtime.ref],
        });
        return;
      }
      if (typeof args["fixture-set"] === "string") {
        const runtime = await resolveFixtureSetRuntime({
          ref: args["fixture-set"],
          cacheRoot: typeof args["cache-root"] === "string" ? args["cache-root"] : undefined,
        });
        process.stderr.write(`${JSON.stringify({
          event: "datalox_replay_fixture_set_start",
          fixtureSetRef: runtime.ref,
          activeFixtureRefs: runtime.activeFixtureRefs,
          bundleIds: runtime.fixtures.map((fixture) => fixture.bundleId),
          bundleSha256s: Object.fromEntries(runtime.fixtures.map((fixture) => [fixture.ref, fixture.bundleSha256])),
          toolCatalogPaths: Object.fromEntries(runtime.fixtures.map((fixture) => [fixture.ref, fixture.toolCatalogPaths])),
          toolCatalogAbsolutePaths: Object.fromEntries(runtime.fixtures.map((fixture) => [fixture.ref, fixture.toolCatalogAbsolutePaths])),
          specs: runtime.specs,
          fixtureSpecs: Object.fromEntries(runtime.fixtures.map((fixture) => [fixture.ref, fixture.specs])),
          liveFallback: false,
        }, null, 2)}\n`);
        await runReplayProxyServer({
          mode: "replay",
          bundlePaths: runtime.bundlePaths,
          activeFixtureRefs: runtime.activeFixtureRefs,
        });
        return;
      }
      const fixtureRefs = [
        ...toStringArray(args.fixtures),
        ...(positional !== undefined ? [positional, ...rest] : []),
      ];
      if (fixtureRefs.length > 0) {
        const runtimes = [];
        for (const fixtureRef of fixtureRefs) {
          runtimes.push(await resolveFixtureRuntime({
            ref: fixtureRef,
            cacheRoot: typeof args["cache-root"] === "string" ? args["cache-root"] : undefined,
          }));
        }
        await validateNoToolNameCollisions(runtimes);
        process.stderr.write(`${JSON.stringify({
          event: "datalox_replay_fixtures_start",
          activeFixtureRefs: runtimes.map((runtime) => runtime.ref),
          bundleIds: runtimes.map((runtime) => runtime.bundleId),
          bundleSha256s: Object.fromEntries(runtimes.map((runtime) => [runtime.ref, runtime.bundleSha256])),
          toolCatalogPaths: Object.fromEntries(runtimes.map((runtime) => [runtime.ref, runtime.toolCatalogPaths])),
          toolCatalogAbsolutePaths: Object.fromEntries(runtimes.map((runtime) => [runtime.ref, runtime.toolCatalogAbsolutePaths])),
          fixtureSpecs: Object.fromEntries(runtimes.map((runtime) => [runtime.ref, runtime.specs])),
          liveFallback: false,
        }, null, 2)}\n`);
        await runReplayProxyServer({
          mode: "replay",
          bundlePaths: runtimes.map((runtime) => runtime.bundlePath),
          activeFixtureRefs: runtimes.map((runtime) => runtime.ref),
        });
        return;
      }
      throw new Error("replay requires --fixture, --fixture-set, or --fixtures");
    }
    case "run": {
      const result = await runReplayWorldFromCli(args, "datalox run");
      writeResult(summarizeReplayWorldRun(result), true);
      return;
    }
    case "world": {
      if (positional !== "run") {
        throw new Error("world requires subcommand run");
      }
      const result = await runReplayWorldFromCli(args, "datalox world run");
      writeResult(summarizeReplayWorldRun(result), true);
      return;
    }
    case "eval": {
      if (typeof args["fixture-set"] !== "string") {
        throw new Error("eval requires --fixture-set");
      }
      if (typeof args.catalog !== "string") {
        throw new Error("eval requires --catalog");
      }
      const result = await evalFixtureSetOpenAiCompatible({
        fixtureSetRef: args["fixture-set"],
        catalogPath: args.catalog,
        cacheRoot: typeof args["cache-root"] === "string" ? args["cache-root"] : undefined,
        outputPath: typeof args.out === "string" ? args.out : undefined,
        split: parseRunSplit(args.split),
        maxTasks: parsePositiveInt(args["max-tasks"]),
        maxTurns: parsePositiveInt(args["max-turns"]),
        model: requireCliString(args.model, "model", "DATALOX_MODEL"),
        baseUrl: requireCliString(args["base-url"], "base-url", "OPENAI_BASE_URL"),
        apiKey: requireCliString(args["api-key"], "api-key", "OPENAI_API_KEY"),
      });
      writeResult(result, true);
      return;
    }
    case "export": {
      if (positional === "sft") {
        const result = await exportSftFromRun({
          runDir: typeof args.run === "string" ? args.run : undefined,
          runPath: typeof args["run-path"] === "string" ? args["run-path"] : undefined,
          outPath: requireStringArg(args, "out"),
        });
        writeResult({
          outPath: result.outPath,
          frameCount: result.frameCount,
        }, true);
        return;
      }
      throw new Error("export requires subcommand sft");
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
