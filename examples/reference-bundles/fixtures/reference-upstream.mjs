#!/usr/bin/env node

import { appendFileSync } from "node:fs";

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

const logPath = process.env.DATALOX_REFERENCE_UPSTREAM_LOG;
const bundleId = process.env.DATALOX_REFERENCE_BUNDLE_ID ?? "unknown-reference-bundle";
let policyLookupCallCount = 0;

function logCall(payload) {
  if (!logPath) {
    return;
  }
  appendFileSync(logPath, `${JSON.stringify({
    bundle_id: bundleId,
    ...payload,
  })}\n`);
}

const server = new McpServer({
  name: "datalox-reference-upstream",
  version: "1.0.0",
});

server.registerTool(
  "policy_lookup",
  {
    description: "Look up a deterministic reference policy result.",
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
    _meta: {
      "datalox.reference/fixture": "policy_lookup",
    },
  },
  async (input) => {
    const callIndex = policyLookupCallCount;
    policyLookupCallCount += 1;
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
          id: `policy-${callIndex}-a`,
          title: "Reference taxi reimbursement policy",
          excerpt: `Deterministic policy match A for ${input.query}.`,
        },
        {
          id: `policy-${callIndex}-b`,
          title: "Reference travel expense policy",
          excerpt: `Deterministic policy match B for ${input.query}.`,
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
  "validation_error",
  {
    description: "Return a deterministic agent-visible validation error.",
    inputSchema: {
      reason: z.string(),
    },
    annotations: {
      readOnlyHint: true,
      destructiveHint: false,
      openWorldHint: false,
    },
    _meta: {
      "datalox.reference/fixture": "validation_error",
    },
  },
  async (input) => {
    logCall({
      tool: "validation_error",
      input,
    });
    return {
      isError: true,
      content: [{
        type: "text",
        text: `reference validation failed: ${input.reason}`,
      }],
      structuredContent: {
        reference_error: true,
        code: "reference_validation_failed",
        reason: input.reason,
      },
    };
  },
);

await server.connect(new StdioServerTransport());
