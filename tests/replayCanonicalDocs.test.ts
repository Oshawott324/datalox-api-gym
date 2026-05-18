import { readFile } from "node:fs/promises";
import path from "node:path";

import { describe, expect, it } from "vitest";

const repoRoot = process.cwd();
const actionPipeline = "messy agent traces -> validated action/observation records -> replay bundle -> approval/export -> optional derivatives";

async function read(relativePath: string): Promise<string> {
  return readFile(path.join(repoRoot, relativePath), "utf8");
}

describe("replay canonical schema docs", () => {
  it("defines the replay source schemas and canonical paths", async () => {
    const [actionObservationSchema, toolIoSchema, replayBundleSchema] = await Promise.all([
      read("docs/action-observation-schema.md"),
      read("docs/tool-io-store-schema.md"),
      read("docs/replay-bundle-schema.md"),
    ]);

    expect(actionObservationSchema).toContain('schema_version: "action_observation.v1"');
    expect(actionObservationSchema).toContain("messy agent traces -> validated action/observation records -> replay bundle");
    expect(actionObservationSchema).toContain(".datalox/tool-io/records/");

    expect(toolIoSchema).toContain('schema_version: "tool_io_record.v1"');
    expect(toolIoSchema).toContain(".datalox/tool-io/records/");
    expect(toolIoSchema).toContain("request_hash + sequence_index");
    expect(toolIoSchema).toContain(actionPipeline);

    expect(replayBundleSchema).toContain('schema_version: "replay_bundle.v1"');
    expect(replayBundleSchema).toContain(".datalox/replay-bundles/");
    expect(replayBundleSchema).toContain("checksums.json");
    expect(replayBundleSchema).toContain(actionPipeline);
  });

  it("keeps action/observation docs aligned with strict TypeScript validators", async () => {
    const [schemaDoc, schemaSource, normalizeSource] = await Promise.all([
      read("docs/action-observation-schema.md"),
      read("src/core/actionObservationSchema.ts"),
      read("src/core/actionObservationNormalize.ts"),
    ]);
    const requiredActionFields = [
      'schema_version: "action_observation.v1"',
      'type: "tool_call"',
      "name: string",
      "version?: string",
      "arguments: unknown",
      "argument_schema_ref?: string",
      "request_hash: string",
      "sequence_index: number",
    ];
    const requiredObservationFields = [
      'status: "ok" | "error"',
      "content?: unknown",
      "error_code?: string",
      "error_message?: string",
      "observation_schema_ref?: string",
    ];
    const requiredProvenanceFields = [
      'source_kind: "mcp" | "wrapper" | "raw_trace"',
      "source_path?: string",
      "host?: string",
      "session_id?: string",
      "turn_id?: string",
      "call_id: string",
    ];

    for (const field of [...requiredActionFields, ...requiredObservationFields, ...requiredProvenanceFields]) {
      expect(schemaDoc).toContain(field);
    }
    for (const schemaToken of [
      'schema_version: z.literal("action_observation.v1")',
      'type: z.literal("tool_call")',
      'source_kind: z.enum(["mcp", "wrapper", "raw_trace"])',
      ".strict()",
      "canonicalJson(row.action.arguments)",
      "buildToolIoRequestHash(row.action.name, row.action.arguments)",
      "canonicalJson(row.observation)",
    ]) {
      expect(schemaSource).toContain(schemaToken);
    }
    for (const normalizeToken of [
      "actionObservationFromToolIoRecord",
      "actionObservationFromRawTrace",
      "rawActionObservationTraceInputSchema",
      "observation: toolIoObservationV1Schema",
      "tool_version",
      "argument_schema_ref",
      "observation_schema_ref",
      "sequence_index",
    ]) {
      expect(normalizeSource).toContain(normalizeToken);
    }
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
      if (!content.includes(actionPipeline)) {
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
      capturePrimitives: ["action_observation.v1", "tool_io_record.v1", "agent_turn.v1"],
      bundleSchema: "replay_bundle.v1",
      derivatives: ["debugging_trajectory.v1", "agent_task_trajectory.v1"],
    });
  });
});
