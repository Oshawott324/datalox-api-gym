import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";

import {
  installFixturePack,
  type InstallFixtureInput,
  type InstallFixtureResult,
} from "../core/fixtures/installFixturePack.js";
import {
  installFixtureSet as installFixtureSetCore,
  type InstallFixtureSetInput,
  type InstallFixtureSetResult,
} from "../core/fixtures/installFixtureSet.js";
import {
  resolveFixtureRuntime,
  type FixtureRuntime,
  type ResolveFixtureRuntimeInput,
} from "../core/fixtures/resolveFixtureRuntime.js";
import {
  resolveFixtureSetRuntime,
  type FixtureSetRuntime,
  type ResolveFixtureSetRuntimeInput,
} from "../core/fixtures/resolveFixtureSetRuntime.js";
import { validateNoToolNameCollisions } from "../core/fixtures/validateToolCollisions.js";
import {
  runFixtureSetOpenAiCompatible,
  type RunFixtureSetOpenAiCompatibleInput,
  type RunFixtureSetOpenAiCompatibleResult,
} from "../core/run/openAiCompatibleFixtureRun.js";
import {
  exportSftFromRun,
  type ExportSftFromRunInput,
  type ExportSftFromRunResult,
} from "../core/exports/exportSftFromRun.js";
import {
  createReplayToolRuntime,
  type CreateReplayToolRuntimeInput,
  type ReplayToolRuntime,
} from "../core/run/replayToolRuntime.js";
import {
  runFixtureAgent,
  type RunFixtureAgentInput,
  type RunFixtureAgentResult,
} from "../core/run/runFixtureAgent.js";
import type { DataloxRunV1, RunMessage, RunStep } from "../core/run/runTranscriptSchema.js";
import type { SftFrameV1 } from "../core/exports/sftFrameSchema.js";
import { buildReplayProxyServer } from "../mcp/replayProxyServer.js";

export type {
  FixtureRuntime,
  FixtureSetRuntime,
  InstallFixtureInput,
  InstallFixtureResult,
  InstallFixtureSetInput,
  InstallFixtureSetResult,
  CreateReplayToolRuntimeInput,
  DataloxRunV1,
  ExportSftFromRunInput,
  ExportSftFromRunResult,
  ReplayToolRuntime,
  ResolveFixtureRuntimeInput,
  ResolveFixtureSetRuntimeInput,
  RunFixtureSetOpenAiCompatibleInput,
  RunFixtureSetOpenAiCompatibleResult,
  RunFixtureAgentInput,
  RunFixtureAgentResult,
  RunMessage,
  RunStep,
  SftFrameV1,
};

export async function installFixture(input: InstallFixtureInput): Promise<InstallFixtureResult> {
  return installFixturePack(input);
}

export async function resolveFixture(input: ResolveFixtureRuntimeInput): Promise<FixtureRuntime> {
  return resolveFixtureRuntime(input);
}

export async function installFixtureSet(input: InstallFixtureSetInput): Promise<InstallFixtureSetResult> {
  return installFixtureSetCore(input);
}

export async function resolveFixtureSet(input: ResolveFixtureSetRuntimeInput): Promise<FixtureSetRuntime> {
  return resolveFixtureSetRuntime(input);
}

export async function runFixtureSet(
  input: RunFixtureSetOpenAiCompatibleInput,
): Promise<RunFixtureSetOpenAiCompatibleResult> {
  return runFixtureSetOpenAiCompatible(input);
}

export async function createReplayRuntime(input: CreateReplayToolRuntimeInput): Promise<ReplayToolRuntime> {
  return createReplayToolRuntime(input);
}

export async function runFixture(input: RunFixtureAgentInput): Promise<RunFixtureAgentResult> {
  return runFixtureAgent(input);
}

export async function exportSft(input: ExportSftFromRunInput): Promise<ExportSftFromRunResult> {
  return exportSftFromRun(input);
}

export interface CreateReplayMcpServerInput {
  bundlePath?: string;
  fixtureRef?: string;
  fixtureRefs?: string[];
  fixtureSetRef?: string;
  cacheRoot?: string;
}

export async function createReplayMcpServer(input: CreateReplayMcpServerInput): Promise<McpServer> {
  const selectedModes = [
    input.bundlePath !== undefined,
    input.fixtureRef !== undefined,
    input.fixtureRefs !== undefined,
    input.fixtureSetRef !== undefined,
  ].filter(Boolean).length;
  if (selectedModes !== 1) {
    throw new Error("createReplayMcpServer requires exactly one of bundlePath, fixtureRef, fixtureRefs, or fixtureSetRef.");
  }

  if (input.bundlePath) {
    return buildReplayProxyServer({
      mode: "replay",
      bundlePath: input.bundlePath,
    });
  }

  if (input.fixtureRef) {
    const runtime = await resolveFixtureRuntime({
      ref: input.fixtureRef,
      cacheRoot: input.cacheRoot,
    });
    return buildReplayProxyServer({
      mode: "replay",
      bundlePath: runtime.bundlePath,
      activeFixtureRefs: [runtime.ref],
    });
  }

  if (input.fixtureSetRef) {
    const runtime = await resolveFixtureSetRuntime({
      ref: input.fixtureSetRef,
      cacheRoot: input.cacheRoot,
    });
    return buildReplayProxyServer({
      mode: "replay",
      bundlePaths: runtime.bundlePaths,
      activeFixtureRefs: runtime.activeFixtureRefs,
    });
  }

  const fixtureRefs = input.fixtureRefs ?? [];
  if (fixtureRefs.length === 0) {
    throw new Error("fixtureRefs must contain at least one fixture ref.");
  }
  const runtimes = [];
  for (const fixtureRef of fixtureRefs) {
    runtimes.push(await resolveFixtureRuntime({
      ref: fixtureRef,
      cacheRoot: input.cacheRoot,
    }));
  }
  await validateNoToolNameCollisions(runtimes);
  return buildReplayProxyServer({
    mode: "replay",
    bundlePaths: runtimes.map((runtime) => runtime.bundlePath),
    activeFixtureRefs: runtimes.map((runtime) => runtime.ref),
  });
}
