#!/usr/bin/env node

import { appendFileSync } from "node:fs";

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

const logPath = process.env.DATALOX_VERIFIED_REPLAY_UPSTREAM_LOG;
let policyLookupCalls = 0;
let statusPingCalls = 0;

function logCall(payload) {
  if (!logPath) {
    return;
  }
  appendFileSync(logPath, `${JSON.stringify({
    at: new Date().toISOString(),
    ...payload,
  })}\n`);
}

const server = new McpServer({
  name: "datalox-verified-replay-fixture",
  version: "1.0.0",
});

server.registerTool(
  "policy_lookup",
  {
    description: "Return deterministic policy search results for the verified replay demo.",
    inputSchema: {
      query: z.string(),
      top_k: z.number().int().positive().optional(),
    },
    outputSchema: {
      query: z.string(),
      top_k: z.number(),
      call_index: z.number(),
      matches: z.array(z.object({
        id: z.string(),
        title: z.string(),
        excerpt: z.string(),
      })),
    },
    annotations: {
      readOnlyHint: true,
      destructiveHint: false,
      openWorldHint: false,
    },
  },
  async (input) => {
    const callIndex = policyLookupCalls;
    policyLookupCalls += 1;
    const topK = input.top_k ?? 2;
    logCall({
      tool: "policy_lookup",
      input,
      call_index: callIndex,
    });

    const payload = {
      query: input.query,
      top_k: topK,
      call_index: callIndex,
      matches: [
        {
          id: `verified-policy-${callIndex}-a`,
          title: "Taxi reimbursement policy",
          excerpt: `Deterministic match A for ${input.query}.`,
        },
        {
          id: `verified-policy-${callIndex}-b`,
          title: "Travel expense policy",
          excerpt: `Deterministic match B for ${input.query}.`,
        },
      ].slice(0, topK),
    };

    return {
      content: [{ type: "text", text: JSON.stringify(payload) }],
      structuredContent: payload,
    };
  },
);

server.registerTool(
  "status_ping",
  {
    description: "Return a deterministic status response without an output schema.",
    inputSchema: {
      label: z.string(),
    },
    annotations: {
      readOnlyHint: true,
      destructiveHint: false,
      openWorldHint: false,
    },
  },
  async (input) => {
    const callIndex = statusPingCalls;
    statusPingCalls += 1;
    logCall({
      tool: "status_ping",
      input,
      call_index: callIndex,
    });

    const payload = {
      ok: true,
      label: input.label,
      call_index: callIndex,
    };
    return {
      content: [{ type: "text", text: JSON.stringify(payload) }],
      structuredContent: payload,
    };
  },
);

await server.connect(new StdioServerTransport());
