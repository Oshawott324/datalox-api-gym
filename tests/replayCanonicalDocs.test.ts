import { readFile } from "node:fs/promises";
import path from "node:path";

import { describe, expect, it } from "vitest";

const repoRoot = process.cwd();
const replayPipeline = "agent run -> tool I/O records -> replay bundle -> approval/export -> optional derivatives";

async function read(relativePath: string): Promise<string> {
  return readFile(path.join(repoRoot, relativePath), "utf8");
}

describe("replay canonical schema docs", () => {
  it("defines the replay source schemas and canonical paths", async () => {
    const [toolIoSchema, replayBundleSchema] = await Promise.all([
      read("docs/tool-io-store-schema.md"),
      read("docs/replay-bundle-schema.md"),
    ]);

    expect(toolIoSchema).toContain('schema_version: "tool_io_record.v1"');
    expect(toolIoSchema).toContain(".datalox/tool-io/records/");
    expect(toolIoSchema).toContain("request_hash + sequence_index");
    expect(toolIoSchema).toContain(replayPipeline);

    expect(replayBundleSchema).toContain('schema_version: "replay_bundle.v1"');
    expect(replayBundleSchema).toContain(".datalox/replay-bundles/");
    expect(replayBundleSchema).toContain("checksums.json");
    expect(replayBundleSchema).toContain(replayPipeline);
  });

  it("keeps first-read docs replay-first", async () => {
    const firstReadDocs = [
      "README.md",
      "START_HERE.md",
      "DATALOX.md",
      "AGENTS.md",
      "CLAUDE.md",
      "GEMINI.md",
      "WIKI.md",
      "docs/product-definition.md",
      "docs/agent-turn-schema.md",
      "docs/agent-configuration.md",
      "docs/project-overview.md",
    ];

    const missing = [];
    for (const relativePath of firstReadDocs) {
      const content = await read(relativePath);
      if (!content.includes(replayPipeline)) {
        missing.push(relativePath);
      }
    }

    expect(missing).toEqual([]);
  });

  it("does not teach trajectory rows as normal product capture", async () => {
    const checkedDocs = [
      "README.md",
      "START_HERE.md",
      "DATALOX.md",
      "AGENTS.md",
      "CLAUDE.md",
      "GEMINI.md",
      "docs/product-definition.md",
      "docs/agent-configuration.md",
    ];
    const forbiddenPhrases = [
      "generate trajectory rows",
      "default to `trajectory`",
      "DATALOX_TRAJECTORY",
      "Then call MCP tool `record_trajectory`",
      "After a coding-debugging run, the agent should build",
    ];
    const violations = [];

    for (const relativePath of checkedDocs) {
      const content = await read(relativePath);
      for (const phrase of forbiddenPhrases) {
        if (content.includes(phrase)) {
          violations.push(`${relativePath} contains ${phrase}`);
        }
      }
    }

    expect(violations).toEqual([]);
  });

  it("declares replay stores in the manifest", async () => {
    const manifest = JSON.parse(await read(".datalox/manifest.json")) as {
      eventStores?: Record<string, string>;
      productModel?: {
        sourceAsset?: string;
        capturePrimitives?: string[];
        bundleSchema?: string;
        derivatives?: string[];
      };
    };

    expect(manifest.eventStores).toMatchObject({
      agentTurns: ".datalox/events/agent-turns",
      toolIoRecords: ".datalox/tool-io/records",
      replayBundles: ".datalox/replay-bundles",
      approvals: ".datalox/approvals",
      trajectoryDerivatives: ".datalox/derivatives/trajectories",
    });
    expect(manifest.productModel).toMatchObject({
      sourceAsset: "approved_anonymized_replay_bundle",
      capturePrimitives: ["tool_io_record.v1", "agent_turn.v1"],
      bundleSchema: "replay_bundle.v1",
      derivatives: ["debugging_trajectory.v1", "agent_task_trajectory.v1"],
    });
  });
});
