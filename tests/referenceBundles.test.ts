import path from "node:path";

import { describe, expect, it } from "vitest";

import {
  readReplayBundleMcpToolCatalogs,
  readReplayBundleToolIoRecords,
  verifyReplayBundle,
} from "../src/core/replayBundle.js";

const repoRoot = process.cwd();

const referenceBundles = [
  {
    id: "ref-mcp-success",
    expectedToolRecords: 1,
    expectedToolName: "policy_lookup",
  },
  {
    id: "ref-mcp-repeated-call",
    expectedToolRecords: 2,
    expectedToolName: "policy_lookup",
  },
  {
    id: "ref-mcp-error-observation",
    expectedToolRecords: 1,
    expectedToolName: "validation_error",
  },
];

function bundlePath(bundleId: string): string {
  return path.join(".datalox", "replay-bundles", bundleId);
}

describe("reference replay bundles", () => {
  it("verify as sealed replay_bundle.v1 artifacts", async () => {
    for (const bundle of referenceBundles) {
      await expect(verifyReplayBundle({
        repoPath: repoRoot,
        bundlePath: bundlePath(bundle.id),
      })).resolves.toMatchObject({
        verified: true,
        manifest: {
          id: bundle.id,
          source: {
            repo_path: ".",
            turn_event_paths: [],
          },
          replay: {
            tool_record_count: bundle.expectedToolRecords,
            turn_count: 0,
            deterministic: true,
          },
          export: {
            allowed: true,
            redaction: "none_needed",
            approval_id: "reference-public",
          },
        },
      });
    }
  });

  it("include exact tool I/O and MCP tool catalogs", async () => {
    for (const bundle of referenceBundles) {
      const records = await readReplayBundleToolIoRecords({
        repoPath: repoRoot,
        bundlePath: bundlePath(bundle.id),
      });
      const catalogs = await readReplayBundleMcpToolCatalogs({
        repoPath: repoRoot,
        bundlePath: bundlePath(bundle.id),
      });

      expect(records).toHaveLength(bundle.expectedToolRecords);
      expect(records.map((record) => record.tool_name)).toEqual(
        Array.from({ length: bundle.expectedToolRecords }, () => bundle.expectedToolName),
      );
      expect(records.every((record) => record.export.allowed)).toBe(true);
      expect(catalogs).toHaveLength(1);
      expect(catalogs[0].tools.map((tool) => tool.name)).toEqual([
        "policy_lookup",
        "validation_error",
      ]);
      expect(JSON.stringify({ records, catalogs })).not.toContain(repoRoot);
    }
  });

  it("preserve repeated-call replay ordering by sequence index", async () => {
    const records = await readReplayBundleToolIoRecords({
      repoPath: repoRoot,
      bundlePath: bundlePath("ref-mcp-repeated-call"),
    });

    expect(new Set(records.map((record) => record.request_hash)).size).toBe(1);
    expect(records.map((record) => record.sequence_index)).toEqual([0, 1]);
    expect(records.map((record) => (
      record.observation.content as { structuredContent: { call_index: number } }
    ).structuredContent.call_index)).toEqual([0, 1]);
  });

  it("preserves an agent-visible MCP error observation exactly", async () => {
    const [record] = await readReplayBundleToolIoRecords({
      repoPath: repoRoot,
      bundlePath: bundlePath("ref-mcp-error-observation"),
    });

    expect(record.observation.status).toBe("ok");
    expect(record.observation.content).toMatchObject({
      isError: true,
      structuredContent: {
        reference_error: true,
        code: "reference_validation_failed",
        reason: "visible upstream validation",
      },
    });
  });
});
