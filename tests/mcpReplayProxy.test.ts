import { existsSync } from "node:fs";
import { mkdir, mkdtemp, readFile, realpath, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { afterEach, describe, expect, it } from "vitest";

import { packReplayBundle } from "../src/core/replayBundle.js";
import { buildToolIoRequestHash } from "../src/core/toolIoSchema.js";
import { readToolIoRecords } from "../src/core/toolIoStore.js";

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
    'let searchPolicyCallCount = 0;',
    'const server = new McpServer({ name: "fake-upstream", version: "1.0.0" });',
    'server.registerTool("search_policy", {',
    '  description: "Search fake policy docs.",',
    '  inputSchema: { query: z.string(), top_k: z.number().optional() },',
    '  outputSchema: {',
    '    matches: z.array(z.string()),',
    '    input: z.object({ query: z.string(), top_k: z.number().optional() }),',
    '    call_index: z.number(),',
    '  },',
    '  annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: false },',
    '  _meta: { "datalox.test/catalog": "policy-search" },',
    '}, async (input) => {',
    '  const call_index = searchPolicyCallCount;',
    '  searchPolicyCallCount += 1;',
    '  appendFileSync(logPath, `${JSON.stringify({ tool: "search_policy", input, call_index, cwd: process.cwd(), env: process.env.DATALOX_TEST_UPSTREAM_ENV ?? null })}\\n`);',
    '  const payload = { matches: [`policy-a-${call_index}`, `policy-b-${call_index}`], input, call_index };',
    '  return {',
    '    content: [{ type: "text", text: JSON.stringify(payload) }],',
    '    structuredContent: payload,',
    '  };',
    '});',
    'server.registerTool("returned_is_error", {',
    '  description: "Return an upstream MCP isError result.",',
    '  inputSchema: { reason: z.string() },',
    '}, async (input) => {',
    '  appendFileSync(logPath, `${JSON.stringify({ tool: "returned_is_error", input })}\\n`);',
    '  return {',
    '    isError: true,',
    '    content: [{ type: "text", text: `upstream returned isError: ${input.reason}` }],',
    '    structuredContent: { upstream_error: true, reason: input.reason },',
    '  };',
    '});',
    'server.registerTool("throws_exception", {',
    '  description: "Throw an upstream exception.",',
    '  inputSchema: { reason: z.string() },',
    '}, async (input) => {',
    '  appendFileSync(logPath, `${JSON.stringify({ tool: "throws_exception", input })}\\n`);',
    '  queueMicrotask(() => { throw new Error(`intentional upstream failure: ${input.reason}`); });',
    '  await new Promise(() => {});',
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
    const configDir = path.join(repoPath, "configs");
    const upstreamCwd = path.join(repoPath, "upstream-workdir");
    await mkdir(configDir, { recursive: true });
    await mkdir(upstreamCwd, { recursive: true });
    const configPath = path.join(configDir, "datalox.replay.json");
    await writeFile(configPath, `${JSON.stringify({
      schema_version: "datalox_replay_proxy_config.v1",
      upstream: {
        command: process.execPath,
        args: [upstreamPath],
        cwd: "../upstream-workdir",
        env: {
          DATALOX_TEST_UPSTREAM_ENV: "configured-env",
        },
      },
      record: {
        session_id: "proxy-session-1",
        turn_id: "proxy-turn-1",
        export: {
          allowed: true,
          redaction: "none_needed",
          approval_id: "approval-1",
        },
      },
    }, null, 2)}\n`, "utf8");

    const recordClient = await connectProxy({
      repoPath,
      mode: "record",
      config: configPath,
    });
    let recordResult: unknown;
    let recordSearchPolicyTool: unknown;
    try {
      const tools = await recordClient.listTools();
      expect(tools.tools.map((tool) => tool.name)).toEqual([
        "search_policy",
        "returned_is_error",
        "throws_exception",
      ]);
      const searchPolicyTool = tools.tools.find((tool) => tool.name === "search_policy");
      expect(searchPolicyTool?.inputSchema).toMatchObject({
        type: "object",
        properties: {
          query: {
            type: "string",
          },
          top_k: {
            type: "number",
          },
        },
        required: ["query"],
      });
      expect(searchPolicyTool?.inputSchema).not.toEqual({
        type: "object",
        additionalProperties: true,
      });
      expect(searchPolicyTool?.outputSchema).toMatchObject({
        type: "object",
        properties: {
          matches: {
            type: "array",
          },
          call_index: {
            type: "number",
          },
        },
        required: expect.arrayContaining(["matches", "input", "call_index"]),
      });
      expect(searchPolicyTool?.annotations).toMatchObject({
        readOnlyHint: true,
        destructiveHint: false,
        openWorldHint: false,
      });
      expect(searchPolicyTool?._meta).toEqual({
        "datalox.test/catalog": "policy-search",
      });
      recordSearchPolicyTool = searchPolicyTool;
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
    const upstreamCall = JSON.parse((await readLogLines(upstreamLog))[0]) as {
      cwd: string;
      env: string;
    };
    expect(await realpath(upstreamCall.cwd)).toBe(await realpath(upstreamCwd));
    expect(upstreamCall.env).toBe("configured-env");
    const records = await readToolIoRecords(repoPath);
    expect(records).toHaveLength(1);
    expect(records[0]).toMatchObject({
      session_id: "proxy-session-1",
      turn_id: "proxy-turn-1",
      export: {
        allowed: true,
        redaction: "none_needed",
        approval_id: "approval-1",
      },
    });
    const packed = await packReplayBundle({
      repoPath,
      bundleId: "proxy-bundle",
      now: new Date("2026-05-18T00:00:00.000Z"),
    });
    expect(packed.manifest.source.mcp_tool_catalog_paths).toHaveLength(1);
    await rm(path.join(repoPath, ".datalox", "tool-io"), { recursive: true, force: true });
    await rm(path.join(repoPath, ".datalox", "mcp-tool-catalogs"), { recursive: true, force: true });

    const replayClient = await connectProxy({
      repoPath,
      mode: "replay",
      bundle: packed.bundlePath,
    });
    try {
      const tools = await replayClient.listTools();
      expect(tools.tools.map((tool) => tool.name)).toEqual([
        "search_policy",
        "returned_is_error",
        "throws_exception",
      ]);
      expect(tools.tools.find((tool) => tool.name === "search_policy")).toEqual(recordSearchPolicyTool);
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
      });
      expect(JSON.stringify(missingResult)).toContain("replay_miss");
      expect(JSON.stringify(missingResult)).toContain("No tool_io_record.v1 replay record");
    } finally {
      await replayClient.close();
    }

    expect(await readLogLines(upstreamLog)).toHaveLength(1);
  }, 15000);

  it("records repeated identical proxy calls with sequence indexes and replays them in order", async () => {
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
    const toolArguments = {
      query: "identical policy lookup",
      top_k: 2,
    };

    const recordClient = await connectProxy({
      repoPath,
      mode: "record",
      config: configPath,
    });
    let firstRecordResult: unknown;
    let secondRecordResult: unknown;
    try {
      firstRecordResult = await recordClient.callTool({
        name: "search_policy",
        arguments: toolArguments,
      });
      secondRecordResult = await recordClient.callTool({
        name: "search_policy",
        arguments: toolArguments,
      });
    } finally {
      await recordClient.close();
    }

    expect(firstRecordResult).not.toEqual(secondRecordResult);
    const upstreamCalls = (await readLogLines(upstreamLog)).map((line) => JSON.parse(line) as {
      call_index: number;
      input: unknown;
    });
    expect(upstreamCalls.map((call) => call.call_index)).toEqual([0, 1]);
    expect(upstreamCalls.map((call) => call.input)).toEqual([toolArguments, toolArguments]);

    const records = await readToolIoRecords(repoPath);
    expect(records).toHaveLength(2);
    expect(new Set(records.map((record) => record.request_hash)).size).toBe(1);
    expect(records.map((record) => record.sequence_index)).toEqual([0, 1]);
    expect(records[0].observation).toEqual({
      status: "ok",
      content: firstRecordResult,
    });
    expect(records[1].observation).toEqual({
      status: "ok",
      content: secondRecordResult,
    });

    const packed = await packReplayBundle({
      repoPath,
      bundleId: "repeated-identical-proxy-bundle",
      now: new Date("2026-05-18T00:00:00.000Z"),
    });
    await rm(path.join(repoPath, ".datalox", "tool-io"), { recursive: true, force: true });
    await rm(path.join(repoPath, ".datalox", "mcp-tool-catalogs"), { recursive: true, force: true });

    const replayClient = await connectProxy({
      repoPath,
      mode: "replay",
      bundle: packed.bundlePath,
    });
    try {
      const firstReplayResult = await replayClient.callTool({
        name: "search_policy",
        arguments: toolArguments,
      });
      const secondReplayResult = await replayClient.callTool({
        name: "search_policy",
        arguments: toolArguments,
      });
      expect(firstReplayResult).toEqual(firstRecordResult);
      expect(secondReplayResult).toEqual(secondRecordResult);
    } finally {
      await replayClient.close();
    }

    expect(await readLogLines(upstreamLog)).toHaveLength(2);
  }, 15000);

  it("records upstream returned isError results as ok observations and returns them unchanged", async () => {
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
    let result: unknown;
    try {
      result = await recordClient.callTool({
        name: "returned_is_error",
        arguments: {
          reason: "visible upstream validation",
        },
      });
    } finally {
      await recordClient.close();
    }

    expect(result).toEqual({
      isError: true,
      content: [{ type: "text", text: "upstream returned isError: visible upstream validation" }],
      structuredContent: { upstream_error: true, reason: "visible upstream validation" },
    });
    const records = await readToolIoRecords(repoPath);
    expect(records).toHaveLength(1);
    expect(records[0].observation).toEqual({
      status: "ok",
      content: result,
    });

    const packed = await packReplayBundle({
      repoPath,
      bundleId: "returned-is-error-proxy-bundle",
      now: new Date("2026-05-18T00:00:00.000Z"),
    });
    await rm(path.join(repoPath, ".datalox", "tool-io"), { recursive: true, force: true });
    await rm(path.join(repoPath, ".datalox", "mcp-tool-catalogs"), { recursive: true, force: true });

    const replayClient = await connectProxy({
      repoPath,
      mode: "replay",
      bundle: packed.bundlePath,
    });
    try {
      const replayResult = await replayClient.callTool({
        name: "returned_is_error",
        arguments: {
          reason: "visible upstream validation",
        },
      });
      expect(JSON.stringify(replayResult)).toBe(JSON.stringify(result));
      expect(replayResult).toEqual(result);
    } finally {
      await replayClient.close();
    }

    expect(await readLogLines(upstreamLog)).toHaveLength(1);
  }, 15000);

  it("returns replay miss structuredContent with request hash and sequence index for no-output-schema tools", async () => {
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
    try {
      await recordClient.callTool({
        name: "returned_is_error",
        arguments: {
          reason: "recorded reason",
        },
      });
    } finally {
      await recordClient.close();
    }

    const packed = await packReplayBundle({
      repoPath,
      bundleId: "no-output-schema-replay-miss-bundle",
      now: new Date("2026-05-18T00:00:00.000Z"),
    });
    await rm(path.join(repoPath, ".datalox", "tool-io"), { recursive: true, force: true });
    await rm(path.join(repoPath, ".datalox", "mcp-tool-catalogs"), { recursive: true, force: true });

    const missingArguments = {
      reason: "unrecorded reason",
    };
    const expectedRequestHash = buildToolIoRequestHash("returned_is_error", missingArguments);
    const replayClient = await connectProxy({
      repoPath,
      mode: "replay",
      bundle: packed.bundlePath,
    });
    try {
      const missingResult = await replayClient.callTool({
        name: "returned_is_error",
        arguments: missingArguments,
      });
      expect(missingResult).toMatchObject({
        isError: true,
        structuredContent: {
          error: {
            code: "replay_miss",
            request_hash: expectedRequestHash,
            sequence_index: 0,
          },
        },
      });
    } finally {
      await replayClient.close();
    }

    expect(await readLogLines(upstreamLog)).toHaveLength(1);
  }, 15000);

  it("records thrown upstream exceptions as upstream_tool_error observations", async () => {
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
    let result: unknown;
    try {
      result = await recordClient.callTool({
        name: "throws_exception",
        arguments: {
          reason: "network timeout",
        },
      });
    } finally {
      await recordClient.close();
    }

    expect(result).toMatchObject({
      isError: true,
      structuredContent: {
        error: {
          code: "upstream_tool_error",
        },
      },
    });
    const records = await readToolIoRecords(repoPath);
    expect(records).toHaveLength(1);
    expect(records[0].observation).toMatchObject({
      status: "error",
      error_code: "upstream_tool_error",
    });
    expect(records[0].observation.error_message).toBeTruthy();

    const packed = await packReplayBundle({
      repoPath,
      bundleId: "thrown-exception-proxy-bundle",
      now: new Date("2026-05-18T00:00:00.000Z"),
    });
    await rm(path.join(repoPath, ".datalox", "tool-io"), { recursive: true, force: true });
    await rm(path.join(repoPath, ".datalox", "mcp-tool-catalogs"), { recursive: true, force: true });

    const replayClient = await connectProxy({
      repoPath,
      mode: "replay",
      bundle: packed.bundlePath,
    });
    try {
      const replayResult = await replayClient.callTool({
        name: "throws_exception",
        arguments: {
          reason: "network timeout",
        },
      });
      expect(replayResult).toEqual(result);
      expect(replayResult).toMatchObject({
        isError: true,
        structuredContent: {
          error: {
            code: "upstream_tool_error",
          },
        },
      });
    } finally {
      await replayClient.close();
    }

    expect(await readLogLines(upstreamLog)).toHaveLength(1);
  }, 15000);

  it("returns a proxy record error when Datalox cannot persist after upstream success", async () => {
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
    await mkdir(path.join(repoPath, ".datalox", "tool-io"), { recursive: true });
    await writeFile(path.join(repoPath, ".datalox", "tool-io", "records"), "not a directory\n", "utf8");

    const recordClient = await connectProxy({
      repoPath,
      mode: "record",
      config: configPath,
    });
    let result: unknown;
    try {
      result = await recordClient.callTool({
        name: "search_policy",
        arguments: {
          query: "record write failure",
        },
      });
    } finally {
      await recordClient.close();
    }

    expect(await readLogLines(upstreamLog)).toHaveLength(1);
    expect(result).toMatchObject({
      isError: true,
    });
    expect(JSON.stringify(result)).toContain("datalox_record_error");
    expect(JSON.stringify(result)).not.toContain("upstream_tool_error");
    expect(JSON.stringify(result)).toContain("Datalox record write failed");
  }, 15000);

  it("refuses to start replay mode when bundled records no longer match checksums", async () => {
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
    try {
      await recordClient.callTool({
        name: "search_policy",
        arguments: {
          query: "record before checksum mutation",
        },
      });
    } finally {
      await recordClient.close();
    }

    const packed = await packReplayBundle({
      repoPath,
      bundleId: "invalid-proxy-bundle",
      now: new Date("2026-05-18T00:00:00.000Z"),
    });
    const bundledRecordPath = path.join(
      repoPath,
      packed.bundlePath,
      packed.manifest.source.tool_io_record_paths[0],
    );
    const bundledRecord = JSON.parse(await readFile(bundledRecordPath, "utf8")) as {
      observation: { content?: unknown };
    };
    bundledRecord.observation.content = {
      mutated_after_checksum: true,
    };
    await writeFile(bundledRecordPath, `${JSON.stringify(bundledRecord, null, 2)}\n`, "utf8");
    await rm(path.join(repoPath, ".datalox", "tool-io"), { recursive: true, force: true });

    const client = new Client({ name: "invalid-bundle-client", version: "1.0.0" }, { capabilities: {} });
    await expect(client.connect(makeProxyTransport({
      repoPath,
      mode: "replay",
      bundle: packed.bundlePath,
    }))).rejects.toThrow();
    expect(await readLogLines(upstreamLog)).toHaveLength(1);
  }, 15000);

  it("refuses to start replay mode when a bundled MCP tool catalog is mutated", async () => {
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
    try {
      await recordClient.callTool({
        name: "search_policy",
        arguments: {
          query: "record before catalog mutation",
        },
      });
    } finally {
      await recordClient.close();
    }

    const packed = await packReplayBundle({
      repoPath,
      bundleId: "invalid-catalog-proxy-bundle",
      now: new Date("2026-05-18T00:00:00.000Z"),
    });
    const bundledCatalogPath = path.join(
      repoPath,
      packed.bundlePath,
      packed.manifest.source.mcp_tool_catalog_paths?.[0] ?? "",
    );
    const bundledCatalog = JSON.parse(await readFile(bundledCatalogPath, "utf8")) as {
      tools: Array<{ input_schema?: unknown }>;
    };
    bundledCatalog.tools[0].input_schema = {
      type: "object",
      properties: {
        mutated_after_checksum: {
          type: "boolean",
        },
      },
    };
    await writeFile(bundledCatalogPath, `${JSON.stringify(bundledCatalog, null, 2)}\n`, "utf8");
    await rm(path.join(repoPath, ".datalox", "tool-io"), { recursive: true, force: true });
    await rm(path.join(repoPath, ".datalox", "mcp-tool-catalogs"), { recursive: true, force: true });

    const client = new Client({ name: "invalid-catalog-bundle-client", version: "1.0.0" }, { capabilities: {} });
    await expect(client.connect(makeProxyTransport({
      repoPath,
      mode: "replay",
      bundle: packed.bundlePath,
    }))).rejects.toThrow();
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

  it("rejects proxy configs with unknown fields", async () => {
    const repoPath = await makeTempRepo();
    const configPath = path.join(repoPath, "datalox.replay.json");
    await writeFile(configPath, `${JSON.stringify({
      schema_version: "datalox_replay_proxy_config.v1",
      upstream: {
        command: process.execPath,
        args: [],
        unexpected: true,
      },
    })}\n`, "utf8");

    const client = new Client({ name: "unknown-config-client", version: "1.0.0" }, { capabilities: {} });
    await expect(client.connect(makeProxyTransport({
      repoPath,
      mode: "record",
      config: configPath,
    }))).rejects.toThrow();
  });
});
