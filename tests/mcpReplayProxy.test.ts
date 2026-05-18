import { existsSync } from "node:fs";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { afterEach, describe, expect, it } from "vitest";

import { packReplayBundle } from "../src/core/replayBundle.js";

const repoRoot = process.cwd();
const builtCliPath = path.join(repoRoot, "dist", "src", "cli", "main.js");

async function writeFakeUpstreamServer(tempDir: string, logPath: string): Promise<string> {
  const serverPath = path.join(tempDir, "fake-upstream.mjs");
  const mcpServerImport = pathToFileURL(
    path.join(repoRoot, "node_modules", "@modelcontextprotocol", "sdk", "dist", "esm", "server", "mcp.js"),
  ).href;
  const stdioImport = pathToFileURL(
    path.join(repoRoot, "node_modules", "@modelcontextprotocol", "sdk", "dist", "esm", "server", "stdio.js"),
  ).href;
  const zodImport = pathToFileURL(path.join(repoRoot, "node_modules", "zod", "index.js")).href;
  await writeFile(serverPath, [
    'import { appendFileSync } from "node:fs";',
    `import { McpServer } from ${JSON.stringify(mcpServerImport)};`,
    `import { StdioServerTransport } from ${JSON.stringify(stdioImport)};`,
    `import { z } from ${JSON.stringify(zodImport)};`,
    `const logPath = ${JSON.stringify(logPath)};`,
    'const server = new McpServer({ name: "fake-upstream", version: "1.0.0" });',
    'server.registerTool("search_policy", {',
    '  description: "Search fake policy docs.",',
    '  inputSchema: { query: z.string(), top_k: z.number().optional() },',
    '}, async (input) => {',
    '  appendFileSync(logPath, `${JSON.stringify({ tool: "search_policy", input })}\\n`);',
    '  const payload = { matches: ["policy-a", "policy-b"], input };',
    '  return {',
    '    content: [{ type: "text", text: JSON.stringify(payload) }],',
    '    structuredContent: payload,',
    '  };',
    '});',
    'await server.connect(new StdioServerTransport());',
    "",
  ].join("\n"), "utf8");
  return serverPath;
}

function makeProxyTransport(input: {
  repoPath: string;
  mode: "record" | "replay";
  config?: string;
  bundle?: string;
}) {
  const args = [
    builtCliPath,
    "proxy",
    "--mode",
    input.mode,
    "--repo",
    input.repoPath,
    "--json",
  ];
  if (input.config) {
    args.push("--config", input.config);
  }
  if (input.bundle) {
    args.push("--bundle", input.bundle);
  }
  return new StdioClientTransport({
    command: process.execPath,
    args,
    cwd: input.repoPath,
    stderr: "pipe",
  });
}

async function connectProxy(input: {
  repoPath: string;
  mode: "record" | "replay";
  config?: string;
  bundle?: string;
}): Promise<Client> {
  const client = new Client({ name: "mcp-replay-proxy-test-client", version: "1.0.0" }, { capabilities: {} });
  await client.connect(makeProxyTransport(input));
  return client;
}

async function readLogLines(logPath: string): Promise<string[]> {
  if (!existsSync(logPath)) {
    return [];
  }
  return (await readFile(logPath, "utf8")).trim().split("\n").filter(Boolean);
}

describe("MCP replay proxy", () => {
  const tempDirs: string[] = [];

  afterEach(async () => {
    await Promise.all(tempDirs.splice(0).map((dir) => rm(dir, { recursive: true, force: true })));
  });

  async function makeTempRepo(): Promise<string> {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-mcp-proxy-"));
    tempDirs.push(tempDir);
    return tempDir;
  }

  it("records upstream MCP tool results and replays them from a bundle without starting upstream", async () => {
    const repoPath = await makeTempRepo();
    const upstreamLog = path.join(repoPath, "upstream.log");
    const upstreamPath = await writeFakeUpstreamServer(repoPath, upstreamLog);
    const configPath = path.join(repoPath, "datalox.replay.json");
    await writeFile(configPath, `${JSON.stringify({
      schema_version: "datalox_replay_proxy_config.v1",
      upstream: {
        command: process.execPath,
        args: [upstreamPath],
      },
    }, null, 2)}\n`, "utf8");

    const recordClient = await connectProxy({
      repoPath,
      mode: "record",
      config: configPath,
    });
    let recordResult: unknown;
    try {
      const tools = await recordClient.listTools();
      expect(tools.tools.map((tool) => tool.name)).toEqual(["search_policy"]);
      recordResult = await recordClient.callTool({
        name: "search_policy",
        arguments: {
          query: "Beijing business-trip taxi reimbursement limit",
          top_k: 5,
        },
      });
    } finally {
      await recordClient.close();
    }

    expect(await readLogLines(upstreamLog)).toHaveLength(1);
    const packed = await packReplayBundle({
      repoPath,
      bundleId: "proxy-bundle",
      now: new Date("2026-05-18T00:00:00.000Z"),
    });
    await rm(path.join(repoPath, ".datalox", "tool-io"), { recursive: true, force: true });

    const replayClient = await connectProxy({
      repoPath,
      mode: "replay",
      bundle: packed.bundlePath,
    });
    try {
      const tools = await replayClient.listTools();
      expect(tools.tools.map((tool) => tool.name)).toEqual(["search_policy"]);
      const replayResult = await replayClient.callTool({
        name: "search_policy",
        arguments: {
          top_k: 5,
          query: "Beijing business-trip taxi reimbursement limit",
        },
      });
      expect(replayResult).toEqual(recordResult);
      expect(await readLogLines(upstreamLog)).toHaveLength(1);

      const missingResult = await replayClient.callTool({
        name: "search_policy",
        arguments: {
          query: "Shanghai business-trip taxi reimbursement limit",
          top_k: 5,
        },
      });
      expect(missingResult).toMatchObject({
        isError: true,
        structuredContent: {
          error: {
            code: "replay_miss",
          },
        },
      });
      expect(JSON.stringify(missingResult)).toContain("No tool_io_record.v1 replay record");
    } finally {
      await replayClient.close();
    }

    expect(await readLogLines(upstreamLog)).toHaveLength(1);
  }, 15000);

  it("rejects proxy configs that are not the declared schema", async () => {
    const repoPath = await makeTempRepo();
    const configPath = path.join(repoPath, "datalox.replay.json");
    await mkdir(path.dirname(configPath), { recursive: true });
    await writeFile(configPath, `${JSON.stringify({
      schema_version: "wrong",
      upstream: {
        command: process.execPath,
        args: [],
      },
    })}\n`, "utf8");

    const client = new Client({ name: "bad-config-client", version: "1.0.0" }, { capabilities: {} });
    await expect(client.connect(makeProxyTransport({
      repoPath,
      mode: "record",
      config: configPath,
    }))).rejects.toThrow();
  });
});
