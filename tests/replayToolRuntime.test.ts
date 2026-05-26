import path from "node:path";

import { describe, expect, it } from "vitest";

import { createReplayToolRuntime } from "../src/core/run/replayToolRuntime.js";

const repoRoot = process.cwd();
const repeatedCallBundlePath = path.join(
  repoRoot,
  ".datalox",
  "replay-bundles",
  "ref-mcp-repeated-call",
);

describe("replay tool runtime", () => {
  it("lists catalog tools and replays repeated identical calls in sequence", async () => {
    const runtime = await createReplayToolRuntime({
      bundlePaths: [repeatedCallBundlePath],
      activeFixtureRefs: ["ref-mcp-repeated-call@local"],
    });

    const tools = await runtime.listTools();
    expect(tools.map((tool) => tool.name)).toContain("policy_lookup");

    const first = await runtime.callTool({
      name: "policy_lookup",
      arguments: {
        query: "identical policy lookup",
        top_k: 2,
      },
    });
    const second = await runtime.callTool({
      name: "policy_lookup",
      arguments: {
        query: "identical policy lookup",
        top_k: 2,
      },
    });
    const third = await runtime.callTool({
      name: "policy_lookup",
      arguments: {
        query: "identical policy lookup",
        top_k: 2,
      },
    });

    expect(first.observation.status).toBe("ok");
    expect(second.observation.status).toBe("ok");
    expect(first.record?.sequence_index).toBe(0);
    expect(second.record?.sequence_index).toBe(1);
    expect(third.observation.status).toBe("error");
    expect(third.replayMiss).toMatchObject({
      code: "replay_miss",
      sequence_index: 2,
      tool_name: "policy_lookup",
      active_fixture_refs: ["ref-mcp-repeated-call@local"],
      liveFallback: false,
    });
  });
});
