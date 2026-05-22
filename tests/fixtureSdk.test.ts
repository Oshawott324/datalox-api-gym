import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { createReplayMcpServer } from "../src/sdk/index.js";
import { packReplayBundle } from "../src/core/replayBundle.js";
import { recordToolIo } from "../src/core/toolIoStore.js";

const tempDirs: string[] = [];

afterEach(async () => {
  await Promise.all(tempDirs.splice(0).map((dir) => rm(dir, { recursive: true, force: true })));
});

async function makeTempRepo(): Promise<string> {
  const dir = await mkdtemp(path.join(tmpdir(), "datalox-fixture-sdk-"));
  tempDirs.push(dir);
  return dir;
}

describe("fixture SDK facade", () => {
  it("creates a replay MCP server from a verified bundle path", async () => {
    const repoPath = await makeTempRepo();
    await recordToolIo({
      repoPath,
      callId: "call-1",
      toolName: "search_query",
      arguments: {
        query: "policy",
      },
      observation: {
        status: "ok",
        content: {
          hits: [],
        },
      },
      export: {
        allowed: true,
        redaction: "none_needed",
      },
      now: new Date("2026-05-20T00:00:00.000Z"),
    });
    const bundle = await packReplayBundle({
      repoPath,
      sourceRepoPath: ".",
      bundleId: "sdk-bundle",
      export: {
        allowed: true,
        redaction: "none_needed",
      },
      now: new Date("2026-05-20T01:00:00.000Z"),
    });

    await expect(createReplayMcpServer({
      bundlePath: path.join(repoPath, bundle.bundlePath),
    })).resolves.toBeTruthy();
  });

  it("requires exactly one replay source selector", async () => {
    await expect(createReplayMcpServer({})).rejects.toThrow(/exactly one/);
    await expect(createReplayMcpServer({
      bundlePath: "/tmp/a",
      fixtureRef: "github-pr-review-basic@2026-05.0",
    })).rejects.toThrow(/exactly one/);
  });
});
