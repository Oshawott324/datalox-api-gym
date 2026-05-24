import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";

import { afterEach, describe, expect, it } from "vitest";

import { OpenAiCompatibleClient } from "../src/core/model/openAiCompatibleClient.js";
import { parseOpenAiCompatibleModelConfig } from "../src/core/model/modelConfig.js";

interface RequestRecord {
  method: string | undefined;
  url: string | undefined;
  headers: IncomingMessage["headers"];
  body: unknown;
}

const servers: Server[] = [];

afterEach(async () => {
  await Promise.all(servers.splice(0).map((server) => closeServer(server)));
});

describe("parseOpenAiCompatibleModelConfig", () => {
  it("normalizes baseUrl and reads apiKey from env", () => {
    process.env.DATALOX_TEST_MODEL_KEY = "secret-key";

    try {
      const config = parseOpenAiCompatibleModelConfig({
        baseUrl: "http://localhost:1234/",
        model: "cheap-live-test",
        apiKeyEnv: "DATALOX_TEST_MODEL_KEY",
        timeoutMs: 5000,
        temperature: 0.2,
        topP: 0.9,
        maxTokens: 128,
      });

      expect(config).toEqual({
        baseUrl: "http://localhost:1234",
        model: "cheap-live-test",
        apiKey: "secret-key",
        timeoutMs: 5000,
        temperature: 0.2,
        topP: 0.9,
        maxTokens: 128,
      });
    } finally {
      delete process.env.DATALOX_TEST_MODEL_KEY;
    }
  });

  it("rejects missing required fields", () => {
    expect(() => parseOpenAiCompatibleModelConfig({ baseUrl: "http://localhost:1" }))
      .toThrow("model");
  });
});

describe("OpenAiCompatibleClient", () => {
  it("posts chat completions with OpenAI-compatible fields and parses assistant output", async () => {
    const requests: RequestRecord[] = [];
    const { server, baseUrl } = await startServer(async (request, response) => {
      const body = await readJson(request);
      requests.push({
        method: request.method,
        url: request.url,
        headers: request.headers,
        body,
      });

      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify({
        choices: [
          {
            finish_reason: "tool_calls",
            message: {
              content: "Need a tool.",
              tool_calls: [
                {
                  id: "call_1",
                  type: "function",
                  function: {
                    name: "lookup_fixture",
                    arguments: "{\"fixture\":\"demo\"}",
                  },
                },
              ],
            },
          },
        ],
      }));
    });
    servers.push(server);

    const client = new OpenAiCompatibleClient(parseOpenAiCompatibleModelConfig({
      baseUrl,
      model: "openai-compatible-small",
      apiKey: "local-test-key",
      timeoutMs: 5000,
      temperature: 0.1,
      topP: 0.8,
      maxTokens: 64,
    }));

    const result = await client.createChatCompletion({
      messages: [
        { role: "system", content: "Use tools when needed." },
        { role: "user", content: "Find fixture." },
      ],
      tools: [
        {
          type: "function",
          function: {
            name: "lookup_fixture",
            parameters: {
              type: "object",
              properties: {
                fixture: { type: "string" },
              },
            },
          },
        },
      ],
      toolChoice: "auto",
    });

    expect(requests).toHaveLength(1);
    expect(requests[0]).toMatchObject({
      method: "POST",
      url: "/chat/completions",
    });
    expect(requests[0].headers.authorization).toBe("Bearer local-test-key");
    expect(requests[0].body).toEqual({
      model: "openai-compatible-small",
      messages: [
        { role: "system", content: "Use tools when needed." },
        { role: "user", content: "Find fixture." },
      ],
      tools: [
        {
          type: "function",
          function: {
            name: "lookup_fixture",
            parameters: {
              type: "object",
              properties: {
                fixture: { type: "string" },
              },
            },
          },
        },
      ],
      temperature: 0.1,
      top_p: 0.8,
      max_tokens: 64,
      tool_choice: "auto",
      parallel_tool_calls: false,
    });
    expect(result).toEqual({
      content: "Need a tool.",
      finishReason: "tool_calls",
      toolCalls: [
        {
          id: "call_1",
          name: "lookup_fixture",
          argumentsJson: "{\"fixture\":\"demo\"}",
        },
      ],
    });
  });

  it("allows callers to override default sampling fields and parallel tool calls", async () => {
    const requests: RequestRecord[] = [];
    const { server, baseUrl } = await startServer(async (request, response) => {
      requests.push({
        method: request.method,
        url: request.url,
        headers: request.headers,
        body: await readJson(request),
      });
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify({
        choices: [
          {
            finish_reason: "stop",
            message: {
              content: null,
            },
          },
        ],
      }));
    });
    servers.push(server);

    const client = new OpenAiCompatibleClient(parseOpenAiCompatibleModelConfig({
      baseUrl,
      model: "openai-compatible-small",
      timeoutMs: 5000,
      temperature: 0.1,
      topP: 0.8,
      maxTokens: 64,
    }));

    const result = await client.createChatCompletion({
      messages: [{ role: "user", content: "Answer directly." }],
      temperature: 0.3,
      topP: 0.7,
      maxTokens: 12,
      parallelToolCalls: true,
    });

    expect(requests[0].body).toMatchObject({
      temperature: 0.3,
      top_p: 0.7,
      max_tokens: 12,
      parallel_tool_calls: true,
    });
    expect(result).toEqual({
      content: null,
      finishReason: "stop",
      toolCalls: [],
    });
  });
});

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
