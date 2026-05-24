import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { runFixtureAgent } from "../src/core/run/runFixtureAgent.js";
import { parseDataloxRunV1 } from "../src/core/run/runTranscriptSchema.js";

const repoRoot = process.cwd();
const repeatedCallBundlePath = path.join(
  repoRoot,
  ".datalox",
  "replay-bundles",
  "ref-mcp-repeated-call",
);
const tempDirs: string[] = [];
const servers: Server[] = [];

afterEach(async () => {
  await Promise.all(servers.splice(0).map(closeServer));
  await Promise.all(tempDirs.splice(0).map((dir) => rm(dir, { recursive: true, force: true })));
});

describe("runFixtureAgent", () => {
  it("runs an OpenAI-compatible model against a replay bundle and writes a transcript", async () => {
    const requests: unknown[] = [];
    const { server, baseUrl } = await startServer(async (request, response) => {
      const body = await readJson(request);
      requests.push(body);
      const messages = (body as { messages: Array<{ role: string }> }).messages;
      response.writeHead(200, { "content-type": "application/json" });
      if (!messages.some((message) => message.role === "tool")) {
        response.end(JSON.stringify({
          choices: [
            {
              finish_reason: "tool_calls",
              message: {
                content: null,
                tool_calls: [
                  {
                    id: "call_policy_lookup",
                    type: "function",
                    function: {
                      name: "policy_lookup",
                      arguments: JSON.stringify({
                        query: "identical policy lookup",
                        top_k: 2,
                      }),
                    },
                  },
                ],
              },
            },
          ],
        }));
        return;
      }

      response.end(JSON.stringify({
        choices: [
          {
            finish_reason: "stop",
            message: {
              content: "Use the replayed policy evidence to answer the support question.",
            },
          },
        ],
      }));
    });
    servers.push(server);
    const outDir = await makeTempDir("datalox-run-fixture-agent-");

    const result = await runFixtureAgent({
      bundlePaths: [repeatedCallBundlePath],
      activeFixtureRefs: undefined,
      prompt: "Look up the relevant policy and answer.",
      model: {
        baseUrl,
        model: "local-qwen-test",
        apiKey: "test-key",
        timeoutMs: 5000,
        temperature: 0.2,
      },
      outDir,
      now: new Date("2026-05-23T00:00:00.000Z"),
    });

    expect(requests).toHaveLength(2);
    expect(result.run.stop_reason).toBe("final_answer");
    expect(result.run.steps).toHaveLength(2);
    expect(result.run.steps[0].tool_call).toMatchObject({
      id: "call_policy_lookup",
      name: "policy_lookup",
      arguments: {
        query: "identical policy lookup",
        top_k: 2,
      },
    });
    expect(result.run.steps[0].observation?.status).toBe("ok");
    expect(result.run.final_answer).toBe("Use the replayed policy evidence to answer the support question.");

    const savedRun = parseDataloxRunV1(JSON.parse(await readFile(result.runPath, "utf8")));
    expect(savedRun.id).toBe(result.run.id);
    expect(await readFile(result.transcriptPath, "utf8")).toContain("policy_lookup");
  });
});

async function makeTempDir(prefix: string): Promise<string> {
  const dir = await mkdtemp(path.join(tmpdir(), prefix));
  tempDirs.push(dir);
  return dir;
}

async function startServer(
  handler: (request: IncomingMessage, response: ServerResponse) => void | Promise<void>,
): Promise<{ server: Server; baseUrl: string }> {
  const server = createServer((request, response) => {
    void Promise.resolve(handler(request, response)).catch((error: unknown) => {
      response.writeHead(500, { "content-type": "text/plain" });
      response.end(error instanceof Error ? error.message : String(error));
    });
  });
  await new Promise<void>((resolve) => {
    server.listen(0, "127.0.0.1", resolve);
  });
  const address = server.address();
  if (address === null || typeof address === "string") {
    throw new Error("Expected TCP test server address");
  }
  return {
    server,
    baseUrl: `http://127.0.0.1:${address.port}`,
  };
}

async function readJson(request: IncomingMessage): Promise<unknown> {
  const chunks: Buffer[] = [];
  for await (const chunk of request) {
    chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
  }
  return JSON.parse(Buffer.concat(chunks).toString("utf8")) as unknown;
}

async function closeServer(server: Server): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    server.close((error) => {
      if (error) {
        reject(error);
        return;
      }
      resolve();
    });
  });
}
