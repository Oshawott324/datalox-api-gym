import { spawnSync } from "node:child_process";
import path from "node:path";

import { describe, expect, it } from "vitest";

const repoRoot = process.cwd();
const demoScript = path.join(repoRoot, "examples", "verified-replay-quickstart", "run-demo.mjs");

describe("verified replay quickstart", () => {
  it("records, packs, verifies, replays with upstream off, misses unseen calls, and catches tampering", () => {
    const result = spawnSync(process.execPath, [demoScript, "--json"], {
      cwd: repoRoot,
      encoding: "utf8",
      maxBuffer: 10 * 1024 * 1024,
    });

    expect(result.stderr).toBe("");
    expect(result.status).toBe(0);

    const summary = JSON.parse(result.stdout) as {
      status: string;
      bundle_id: string;
      tool_record_count: number;
      mcp_tool_catalog_count: number;
      replay_hit_count: number;
      replay_miss_count: number;
      upstream_calls_during_replay: number;
      replay_miss: {
        code: string;
        request_hash: string;
        sequence_index: number;
      };
      tamper_detected: boolean;
      elapsed_ms: number;
    };

    expect(summary.status).toBe("passed");
    expect(summary.bundle_id).toBe("verified-replay-demo");
    expect(summary.tool_record_count).toBe(3);
    expect(summary.mcp_tool_catalog_count).toBe(1);
    expect(summary.replay_hit_count).toBe(3);
    expect(summary.replay_miss_count).toBe(1);
    expect(summary.upstream_calls_during_replay).toBe(0);
    expect(summary.replay_miss.code).toBe("replay_miss");
    expect(summary.replay_miss.request_hash).toMatch(/^[a-f0-9]{64}$/);
    expect(summary.replay_miss.sequence_index).toBe(0);
    expect(summary.tamper_detected).toBe(true);
    expect(summary.elapsed_ms).toBeGreaterThan(0);
  });
});
