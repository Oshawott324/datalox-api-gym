import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { afterEach, describe, expect, it } from "vitest";

import {
  exportTrajectories,
  LEGACY_EVENTS_RELATIVE_DIR,
  PRODUCT_TRAJECTORY_EVENTS_RELATIVE_DIR,
  recordTrajectory,
  TrajectoryExportError,
} from "../src/core/trajectoryExport.js";
import { repairTrajectory } from "../src/core/trajectoryRepair.js";

const repoRoot = process.cwd();
const builtCliPath = path.join(repoRoot, "dist", "src", "cli", "main.js");
const builtMcpPath = path.join(repoRoot, "dist", "src", "mcp", "trajectoryServer.js");
const dataloxMcpBinPath = path.join(repoRoot, "bin", "datalox-mcp.js");

function makeRow(id: string) {
  return {
    schema_version: "debugging_trajectory.v1",
    id,
    created_at: "2026-05-03T00:00:00.000Z",
    task: {
      domain: "coding_debugging",
      prompt: `Fix ${id}`,
      language: "typescript",
      environment: "nodejs",
    },
    context: {
      error: "TypeError: undefined is not a function",
      relevant_files: [
        {
          path: "src/example.ts",
          before: "value();",
          after: "if (value) value();",
        },
      ],
      notes: ["Test command: npm test"],
    },
    trajectory: [
      {
        role: "user",
        content: "The failing test reports a TypeError.",
      },
      {
        role: "agent",
        content: "Inspected the failing call site and found an unchecked optional value.",
      },
      {
        role: "agent",
        content: "Added an explicit guard before invoking the value.",
        files_changed: ["src/example.ts"],
      },
      {
        role: "tool",
        content: "npm test passed: 3 tests, 0 failed.",
        tool: "shell",
        command: "npm test",
        exit_code: 0,
      },
    ],
    final: {
      fix_summary: "Added a guard before invoking the optional value.",
      changed_files: ["src/example.ts"],
      explanation: "The guard makes the call site handle the missing value explicitly.",
    },
    outcome: {
      label: "success",
      verification: "passed",
      command: "npm test",
      evidence: "npm test passed: 3 tests, 0 failed.",
    },
    export: {
      allowed: true,
      redaction: "none_needed",
    },
    curation: {
      quality: "use",
      tags: ["synthetic"],
    },
    metadata: {
      verified_by: "agent",
    },
  };
}

function makeProseSnippetUseRow(id: string) {
  return {
    ...makeRow(id),
    context: {
      error: "TypeError: undefined is not a function",
      relevant_files: [
        {
          path: "src/example.ts",
          before: "The previous code called the value directly.",
          after: "The new code guards the optional value before calling it.",
        },
      ],
    },
    curation: {
      quality: "use",
      tags: ["synthetic"],
    },
  };
}

function makePlaceholderSnippetUseRow(id: string) {
  return {
    ...makeRow(id),
    context: {
      error: "TypeError: undefined is not a function",
      relevant_files: [
        {
          path: "src/example.ts",
          before: "function run(value) {\n  value();\n}",
          after: "function run(value) {\n  ...\n  if (value) value();\n}",
        },
      ],
    },
    curation: {
      quality: "use",
      tags: ["synthetic"],
    },
  };
}

function runBuiltCli(cwd: string, args: string[]) {
  return spawnSync("node", [builtCliPath, ...args], {
    cwd,
    encoding: "utf8",
    env: process.env,
  });
}

async function writeMinimalDataloxConfig(repoPath: string) {
  await mkdir(path.join(repoPath, ".datalox"), { recursive: true });
  await writeFile(
    path.join(repoPath, ".datalox", "config.json"),
    JSON.stringify({
      version: 1,
      mode: "repo_only",
      project: {
        id: "trajectory-test",
        name: "Trajectory Test",
      },
      sources: [
        {
          kind: "local_repo",
          name: "trajectory-test",
          enabled: true,
          root: ".datalox",
        },
      ],
      agent: {
        profile: "local_first",
        nativeSkillPolicy: "preserve",
        detectOnEveryLoop: true,
        configReadOrder: [".datalox/config.json"],
        interfaceOrder: ["skill_loop", "runtime_compile"],
      },
      paths: {
        seedSkillsDir: "skills",
        seedNotesDir: "agent-wiki/notes",
        hostSkillsDir: "skills",
        hostNotesDir: "agent-wiki/notes",
      },
      runtime: {
        enabled: false,
        baseUrl: "http://localhost:3000",
        defaultWorkflow: "coding_debugging",
        requestTimeoutMs: 10000,
        endpoints: {
          compile: "/v1/runtime/compile",
          guidance: "/v1/runtime/guidance",
          publish: "/v1/runtime/publish",
          search: "/v1/runtime/search",
          install: "/v1/runtime/install",
          ingest: "/v1/runtime/ingest",
          register: "/v1/runtime/register",
        },
      },
      auth: {
        apiKeyEnv: "DATALOX_API_KEY",
        contributorKeyEnv: "DATALOX_CONTRIBUTOR_KEY",
      },
    }, null, 2),
  );
}

function extractStructuredResult(result: unknown) {
  const resolved = (typeof result === "object" && result !== null && "toolResult" in result)
    ? (result as { toolResult: unknown }).toolResult
    : result;

  if (
    resolved
    && typeof resolved === "object"
    && "structuredContent" in resolved
    && (resolved as { structuredContent?: unknown }).structuredContent
    && typeof (resolved as { structuredContent?: unknown }).structuredContent === "object"
  ) {
    return (resolved as { structuredContent: { result: unknown } }).structuredContent.result;
  }

  const content = (resolved as { content?: Array<{ type: string; text?: string }> }).content;
  const text = content?.find((item) => item.type === "text")?.text;
  if (!text) {
    throw new Error("No structured MCP result found");
  }
  return JSON.parse(text) as unknown;
}

describe("trajectory recording and export", () => {
  const tempDirs: string[] = [];

  afterEach(async () => {
    await Promise.all(tempDirs.splice(0).map((dir) => rm(dir, { recursive: true, force: true })));
  });

  it("records a trajectory row without creating note or skill product state", async () => {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-trajectory-record-"));
    tempDirs.push(tempDir);

    const result = await recordTrajectory({
      repoPath: tempDir,
      trajectoryRow: makeRow("record-one"),
      now: new Date("2026-05-03T10:00:00.000Z"),
    });
    const event = JSON.parse(await readFile(path.join(tempDir, result.eventPath), "utf8"));

    expect(result).toMatchObject({
      trajectoryId: "record-one",
      sellable: true,
      blockedReasons: [],
      quality: "use",
      deterministicPassed: true,
      qualityDowngraded: false,
      qualityDowngradeIssueCodes: [],
    });
    expect(event.eventKind).toBe("trajectory_row");
    expect(event.trajectoryRow.schema_version).toBe("debugging_trajectory.v1");
    expect(event.trajectoryRow.export.source_event_paths).toContain(result.eventPath);
    expect(event.trajectoryRow.metadata.datalox_quality_downgraded_from).toBeUndefined();
    expect(result.eventPath).toContain(`${PRODUCT_TRAJECTORY_EVENTS_RELATIVE_DIR}/`);
    expect(existsSync(path.join(tempDir, "agent-wiki", "events"))).toBe(false);
    expect(existsSync(path.join(tempDir, "agent-wiki", "notes"))).toBe(false);
    expect(existsSync(path.join(tempDir, "skills"))).toBe(false);
  });

  it("downgrades weak use rows at record time without dropping evidence", async () => {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-trajectory-record-downgrade-"));
    tempDirs.push(tempDir);

    const result = await recordTrajectory({
      repoPath: tempDir,
      trajectoryRow: makeProseSnippetUseRow("record-downgraded"),
      now: new Date("2026-05-03T10:00:00.000Z"),
    });
    const event = JSON.parse(await readFile(path.join(tempDir, result.eventPath), "utf8"));

    expect(result).toMatchObject({
      trajectoryId: "record-downgraded",
      sellable: true,
      quality: "needs_review",
      deterministicPassed: false,
      qualityDowngraded: true,
      qualityDowngradeIssueCodes: expect.arrayContaining([
        "prose_only_relevant_file",
        "not_self_contained",
      ]),
    });
    expect(event.trajectoryRow.curation.quality).toBe("needs_review");
    expect(event.trajectoryRow.metadata).toMatchObject({
      datalox_quality_downgraded_from: "use",
      datalox_quality_downgrade_issue_codes: expect.arrayContaining([
        "prose_only_relevant_file",
        "not_self_contained",
      ]),
      datalox_quality_downgraded_at: "2026-05-03T10:00:00.000Z",
    });
    expect(event.trajectoryRow.context.relevant_files[0].before).toBe(
      "The previous code called the value directly.",
    );
  });

  it("rejects invalid rows before writing event files", async () => {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-trajectory-invalid-"));
    tempDirs.push(tempDir);
    const invalidRow = {
      ...makeRow("invalid-one"),
      final: { fix_summary: "" },
    };

    await expect(recordTrajectory({ repoPath: tempDir, trajectoryRow: invalidRow }))
      .rejects
      .toThrow(/final\.fix_summary/);
    expect(existsSync(path.join(tempDir, "agent-wiki", "events"))).toBe(false);
    expect(existsSync(path.join(tempDir, PRODUCT_TRAJECTORY_EVENTS_RELATIVE_DIR))).toBe(false);
  });

  it("exports only sellable rows as deterministic JSONL and reports blocked rows", async () => {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-trajectory-export-"));
    tempDirs.push(tempDir);

    await recordTrajectory({
      repoPath: tempDir,
      trajectoryRow: makeRow("row-a"),
      now: new Date("2026-05-03T10:00:00.000Z"),
    });
    await recordTrajectory({
      repoPath: tempDir,
      trajectoryRow: makeRow("row-b"),
      now: new Date("2026-05-03T10:01:00.000Z"),
    });
    await recordTrajectory({
      repoPath: tempDir,
      trajectoryRow: {
        ...makeRow("row-not-allowed"),
        export: { allowed: false, redaction: "none_needed" },
      },
      now: new Date("2026-05-03T10:02:00.000Z"),
    });
    await recordTrajectory({
      repoPath: tempDir,
      trajectoryRow: {
        ...makeRow("row-redaction-blocked"),
        export: { allowed: true, redaction: "blocked" },
      },
      now: new Date("2026-05-03T10:03:00.000Z"),
    });

    const report = await exportTrajectories({
      repoPath: tempDir,
      outputPath: "out/rows.jsonl",
      blockedReportPath: "out/blocked.json",
      split: "eval",
    });
    const lines = (await readFile(path.join(tempDir, "out", "rows.jsonl"), "utf8"))
      .trim()
      .split("\n");
    const blockedReport = JSON.parse(await readFile(path.join(tempDir, "out", "blocked.json"), "utf8"));

    expect(report).toMatchObject({
      candidateRows: 4,
      exportedRows: 2,
      blockedRows: 2,
      invalidRows: 0,
      duplicateRows: 0,
    });
    expect(lines.map((line) => JSON.parse(line).id)).toEqual(["row-a", "row-b"]);
    expect(JSON.parse(lines[0]).curation.split).toBe("eval");
    expect(blockedReport.rejectedRows.map((row: { trajectoryId: string }) => row.trajectoryId)).toEqual([
      "row-not-allowed",
      "row-redaction-blocked",
    ]);
  });

  it("filters export rows by curation quality", async () => {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-trajectory-export-quality-"));
    tempDirs.push(tempDir);

    await recordTrajectory({
      repoPath: tempDir,
      trajectoryRow: makeRow("quality-use"),
      now: new Date("2026-05-03T10:00:00.000Z"),
    });
    await recordTrajectory({
      repoPath: tempDir,
      trajectoryRow: {
        ...makeRow("quality-review"),
        curation: { quality: "needs_review", tags: ["synthetic"] },
      },
      now: new Date("2026-05-03T10:01:00.000Z"),
    });

    const report = await exportTrajectories({
      repoPath: tempDir,
      outputPath: "out/use-rows.jsonl",
      quality: "use",
    });
    const lines = (await readFile(path.join(tempDir, "out", "use-rows.jsonl"), "utf8"))
      .trim()
      .split("\n");

    expect(report).toMatchObject({
      candidateRows: 2,
      exportedRows: 1,
      blockedRows: 1,
      rejectedRows: [
        expect.objectContaining({
          trajectoryId: "quality-review",
          reason: "quality_filter",
          detail: {
            required_quality: "use",
            row_quality: "needs_review",
          },
        }),
      ],
    });
    expect(lines.map((line) => JSON.parse(line).id)).toEqual(["quality-use"]);
  });

  it("exports only accepted standalone rows in buyer-facing quality-use fixtures", async () => {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-trajectory-export-standalone-"));
    tempDirs.push(tempDir);

    await recordTrajectory({
      repoPath: tempDir,
      trajectoryRow: {
        ...makeRow("standalone-use"),
        export: {
          allowed: true,
          redaction: "none_needed",
          source_event_paths: ["agent-wiki/events/source.json"],
        },
      },
      now: new Date("2026-05-03T10:00:00.000Z"),
    });
    await recordTrajectory({
      repoPath: tempDir,
      trajectoryRow: {
        ...makeProseSnippetUseRow("external-reference-review"),
        final: {
          fix_summary: "Added a guard before invoking the optional value.",
          changed_files: ["src/example.ts"],
          explanation: "The row is a repair candidate because snippets are prose.",
        },
      },
      now: new Date("2026-05-03T10:01:00.000Z"),
    });
    await mkdir(path.join(tempDir, LEGACY_EVENTS_RELATIVE_DIR), { recursive: true });
    await writeFile(
      path.join(tempDir, LEGACY_EVENTS_RELATIVE_DIR, "2026-05-03T10-02-00-000Z--stale-use.json"),
      JSON.stringify({
        timestamp: "2026-05-03T10:02:00.000Z",
        trajectoryRow: {
          ...makeProseSnippetUseRow("stale-quality-use"),
          final: {
            fix_summary: "Added a guard before invoking the optional value.",
            changed_files: ["src/example.ts"],
            explanation: "See src/example.ts and source_event_paths for the actual patch.",
          },
        },
      }, null, 2),
    );

    const report = await exportTrajectories({
      repoPath: tempDir,
      outputPath: "out/use-standalone.jsonl",
      quality: "use",
    });
    const rows = (await readFile(path.join(tempDir, "out", "use-standalone.jsonl"), "utf8"))
      .trim()
      .split("\n")
      .map((line) => JSON.parse(line));

    expect(report).toMatchObject({
      candidateRows: 3,
      exportedRows: 1,
      blockedRows: 2,
      rejectedRows: [
        expect.objectContaining({
          trajectoryId: "external-reference-review",
          reason: "quality_filter",
          detail: expect.objectContaining({
            required_quality: "use",
            row_quality: "needs_review",
          }),
        }),
        expect.objectContaining({
          trajectoryId: "stale-quality-use",
          reason: "training_grade_filter",
          detail: expect.objectContaining({
            issue_codes: expect.arrayContaining(["not_self_contained"]),
          }),
        }),
      ],
    });
    expect(rows.map((row) => row.id)).toEqual(["standalone-use"]);
    expect(rows[0].context.relevant_files[0]).toMatchObject({
      path: "src/example.ts",
      before: "value();",
      after: "if (value) value();",
    });
    expect(rows[0].export.source_event_paths).toEqual(
      expect.arrayContaining(["agent-wiki/events/source.json"]),
    );
  });

  it("fails export on invalid trajectory candidates", async () => {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-trajectory-export-invalid-"));
    tempDirs.push(tempDir);
    await mkdir(path.join(tempDir, LEGACY_EVENTS_RELATIVE_DIR), { recursive: true });
    await writeFile(
      path.join(tempDir, LEGACY_EVENTS_RELATIVE_DIR, "2026-05-03T10-00-00-000Z--bad.json"),
      JSON.stringify({
        timestamp: "2026-05-03T10:00:00.000Z",
        trajectoryRow: {
          ...makeRow("invalid-export"),
          final: { fix_summary: "" },
        },
      }),
    );

    await expect(exportTrajectories({ repoPath: tempDir, outputPath: "out/rows.jsonl" }))
      .rejects
      .toMatchObject({
        report: {
          candidateRows: 1,
          invalidRows: 1,
          exportedRows: 0,
        },
      });
  });

  it("exports legacy trajectory rows from agent-wiki/events while new writes use .datalox", async () => {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-trajectory-export-legacy-"));
    tempDirs.push(tempDir);
    await mkdir(path.join(tempDir, LEGACY_EVENTS_RELATIVE_DIR), { recursive: true });
    await writeFile(
      path.join(tempDir, LEGACY_EVENTS_RELATIVE_DIR, "2026-05-03T09-00-00-000Z--legacy.json"),
      JSON.stringify({
        timestamp: "2026-05-03T09:00:00.000Z",
        trajectoryRow: makeRow("legacy-row"),
      }, null, 2),
    );
    await recordTrajectory({
      repoPath: tempDir,
      trajectoryRow: makeRow("new-row"),
      now: new Date("2026-05-03T10:00:00.000Z"),
    });

    const report = await exportTrajectories({
      repoPath: tempDir,
      outputPath: "out/rows.jsonl",
    });
    const lines = (await readFile(path.join(tempDir, "out", "rows.jsonl"), "utf8"))
      .trim()
      .split("\n");

    expect(report).toMatchObject({
      scannedEvents: 2,
      candidateRows: 2,
      exportedRows: 2,
    });
    expect(lines.map((line) => JSON.parse(line).id)).toEqual(["legacy-row", "new-row"]);
  });

  it("fails export on duplicate trajectory ids with source paths", async () => {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-trajectory-export-duplicates-"));
    tempDirs.push(tempDir);

    await recordTrajectory({
      repoPath: tempDir,
      trajectoryRow: makeRow("duplicate-id"),
      now: new Date("2026-05-03T10:00:00.000Z"),
    });
    await recordTrajectory({
      repoPath: tempDir,
      trajectoryRow: makeRow("duplicate-id"),
      now: new Date("2026-05-03T10:01:00.000Z"),
    });

    await expect(exportTrajectories({ repoPath: tempDir, outputPath: "out/rows.jsonl", quality: "use" }))
      .rejects
      .toBeInstanceOf(TrajectoryExportError);
    try {
      await exportTrajectories({ repoPath: tempDir, outputPath: "out/rows.jsonl", quality: "use" });
      throw new Error("Expected duplicate export failure");
    } catch (error) {
      expect(error).toBeInstanceOf(TrajectoryExportError);
      const report = (error as TrajectoryExportError).report;
      expect(report.duplicateRows).toBe(2);
      expect(report.rejectedRows).toHaveLength(2);
      expect(report.rejectedRows[0].detail).toMatchObject({
        duplicate_event_paths: expect.arrayContaining([
          ".datalox/events/trajectory-rows/2026-05-03T10-00-00-000Z--trajectory-duplicate-id.json",
          ".datalox/events/trajectory-rows/2026-05-03T10-01-00-000Z--trajectory-duplicate-id.json",
        ]),
      });
    }
  });

  it("exports only the final use row from a repair chain", async () => {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-trajectory-export-repair-chain-"));
    tempDirs.push(tempDir);

    const original = await recordTrajectory({
      repoPath: tempDir,
      trajectoryRow: makeProseSnippetUseRow("repair-chain"),
      now: new Date("2026-05-03T10:00:00.000Z"),
    });
    const firstRepair = await repairTrajectory({
      repoPath: tempDir,
      eventPath: original.eventPath,
      trajectoryRow: makePlaceholderSnippetUseRow("repair-chain"),
      now: new Date("2026-05-03T10:01:00.000Z"),
    });
    const secondRepair = await repairTrajectory({
      repoPath: tempDir,
      eventPath: firstRepair.repairEventPath,
      trajectoryRow: makePlaceholderSnippetUseRow("repair-chain"),
      now: new Date("2026-05-03T10:02:00.000Z"),
    });
    const finalRepair = await repairTrajectory({
      repoPath: tempDir,
      eventPath: secondRepair.repairEventPath,
      trajectoryRow: makeRow("repair-chain"),
      now: new Date("2026-05-03T10:03:00.000Z"),
    });

    const report = await exportTrajectories({
      repoPath: tempDir,
      outputPath: "out/use-repaired.jsonl",
      blockedReportPath: "out/use-repaired-report.json",
      quality: "use",
    });
    const rows = (await readFile(path.join(tempDir, "out", "use-repaired.jsonl"), "utf8"))
      .trim()
      .split("\n")
      .map((line) => JSON.parse(line));
    const blockedReport = JSON.parse(await readFile(path.join(tempDir, "out", "use-repaired-report.json"), "utf8"));

    expect(report).toMatchObject({
      candidateRows: 4,
      exportedRows: 1,
      blockedRows: 3,
      duplicateRows: 0,
    });
    expect(rows.map((row) => row.id)).toEqual(["repair-chain"]);
    expect(rows[0].export.source_event_paths).toContain(finalRepair.repairEventPath);
    expect(rows[0].metadata.datalox_repaired_from_event_path).toBe(secondRepair.repairEventPath);
    expect(blockedReport.rejectedRows).toEqual([
      expect.objectContaining({
        eventPath: original.eventPath,
        trajectoryId: "repair-chain",
        reason: "superseded_by_repair",
        detail: { repaired_by_event_path: firstRepair.repairEventPath },
      }),
      expect.objectContaining({
        eventPath: firstRepair.repairEventPath,
        trajectoryId: "repair-chain",
        reason: "superseded_by_repair",
        detail: { repaired_by_event_path: secondRepair.repairEventPath },
      }),
      expect.objectContaining({
        eventPath: secondRepair.repairEventPath,
        trajectoryId: "repair-chain",
        reason: "superseded_by_repair",
        detail: { repaired_by_event_path: finalRepair.repairEventPath },
      }),
    ]);
  });

  it("does not let a missing repair pointer mask unrelated duplicate ids", async () => {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-trajectory-export-missing-repair-"));
    tempDirs.push(tempDir);

    await recordTrajectory({
      repoPath: tempDir,
      trajectoryRow: makeRow("missing-repair-duplicate"),
      now: new Date("2026-05-03T10:00:00.000Z"),
    });
    await recordTrajectory({
      repoPath: tempDir,
      trajectoryRow: {
        ...makeRow("missing-repair-duplicate"),
        metadata: {
          datalox_repaired_from_event_path: ".datalox/events/trajectory-rows/missing.json",
        },
      },
      now: new Date("2026-05-03T10:01:00.000Z"),
    });

    try {
      await exportTrajectories({ repoPath: tempDir, outputPath: "out/rows.jsonl", quality: "use" });
      throw new Error("Expected duplicate export failure");
    } catch (error) {
      expect(error).toBeInstanceOf(TrajectoryExportError);
      const report = (error as TrajectoryExportError).report;
      expect(report.duplicateRows).toBe(2);
      expect(report.rejectedRows).toEqual([
        expect.objectContaining({
          trajectoryId: "missing-repair-duplicate",
          reason: "duplicate_id",
        }),
        expect.objectContaining({
          trajectoryId: "missing-repair-duplicate",
          reason: "duplicate_id",
        }),
      ]);
    }
  });

  it("exports a .datalox repair instead of the superseded legacy source row", async () => {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-trajectory-export-legacy-repair-"));
    tempDirs.push(tempDir);
    const legacyRelativePath = path.join(
      LEGACY_EVENTS_RELATIVE_DIR,
      "2026-05-03T10-00-00-000Z--legacy-repair.json",
    );
    await mkdir(path.join(tempDir, LEGACY_EVENTS_RELATIVE_DIR), { recursive: true });
    await writeFile(
      path.join(tempDir, legacyRelativePath),
      JSON.stringify({
        timestamp: "2026-05-03T10:00:00.000Z",
        trajectoryRow: makeRow("legacy-repair"),
      }, null, 2),
    );
    const repair = await repairTrajectory({
      repoPath: tempDir,
      eventPath: legacyRelativePath,
      trajectoryRow: makeRow("legacy-repair"),
      now: new Date("2026-05-03T10:01:00.000Z"),
    });

    const report = await exportTrajectories({
      repoPath: tempDir,
      outputPath: "out/use-legacy-repair.jsonl",
      quality: "use",
    });
    const rows = (await readFile(path.join(tempDir, "out", "use-legacy-repair.jsonl"), "utf8"))
      .trim()
      .split("\n")
      .map((line) => JSON.parse(line));

    expect(report).toMatchObject({
      candidateRows: 2,
      exportedRows: 1,
      blockedRows: 1,
      duplicateRows: 0,
      rejectedRows: [
        expect.objectContaining({
          eventPath: legacyRelativePath,
          trajectoryId: "legacy-repair",
          reason: "superseded_by_repair",
          detail: { repaired_by_event_path: repair.repairEventPath },
        }),
      ],
    });
    expect(repair.repairEventPath).toContain(`${PRODUCT_TRAJECTORY_EVENTS_RELATIVE_DIR}/`);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      id: "legacy-repair",
      metadata: {
        datalox_repaired_from_event_path: legacyRelativePath,
      },
    });
  });

  it("records rows through the built CLI and exports them", async () => {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-trajectory-cli-"));
    tempDirs.push(tempDir);
    const rowPath = path.join(tempDir, "row.json");
    await writeFile(rowPath, JSON.stringify(makeRow("cli-row"), null, 2));

    const recordResult = runBuiltCli(repoRoot, [
      "record-trajectory",
      "--repo",
      tempDir,
      "--trajectory-row",
      rowPath,
      "--json",
    ]);
    expect(recordResult.status).toBe(0);
    expect(JSON.parse(recordResult.stdout)).toMatchObject({
      trajectoryId: "cli-row",
      sellable: true,
      quality: "use",
      deterministicPassed: true,
      qualityDowngraded: false,
    });

    const exportResult = runBuiltCli(repoRoot, [
      "export-trajectories",
      "--repo",
      tempDir,
      "--output",
      "rows.jsonl",
      "--json",
    ]);
    expect(exportResult.status).toBe(0);
    expect(JSON.parse(exportResult.stdout)).toMatchObject({ exportedRows: 1 });
    const lines = (await readFile(path.join(tempDir, "rows.jsonl"), "utf8")).trim().split("\n");
    expect(JSON.parse(lines[0]).id).toBe("cli-row");
  });

  it("prints downgrade feedback when the built CLI records a weak use row", async () => {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-trajectory-cli-downgrade-"));
    tempDirs.push(tempDir);
    const rowPath = path.join(tempDir, "row.json");
    await writeFile(rowPath, JSON.stringify(makeProseSnippetUseRow("cli-downgrade-row"), null, 2));

    const recordResult = runBuiltCli(repoRoot, [
      "record-trajectory",
      "--repo",
      tempDir,
      "--trajectory-row",
      rowPath,
      "--json",
    ]);

    expect(recordResult.status).toBe(0);
    const result = JSON.parse(recordResult.stdout);
    expect(result).toMatchObject({
      trajectoryId: "cli-downgrade-row",
      quality: "needs_review",
      deterministicPassed: false,
      qualityDowngraded: true,
      qualityDowngradeIssueCodes: expect.arrayContaining(["not_self_contained"]),
    });
    const event = JSON.parse(await readFile(path.join(tempDir, result.eventPath), "utf8"));
    expect(event.trajectoryRow.curation.quality).toBe("needs_review");
  });

  it("records legacy record events and writes explicit trajectory rows to .datalox through the built CLI", async () => {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-trajectory-cli-record-"));
    tempDirs.push(tempDir);
    await writeMinimalDataloxConfig(tempDir);
    const rowPath = path.join(tempDir, "row.json");
    await writeFile(rowPath, JSON.stringify(makeRow("record-cli-row"), null, 2));

    const recordResult = runBuiltCli(repoRoot, [
      "record",
      "--repo",
      tempDir,
      "--summary",
      "recorded a trajectory row",
      "--trajectory-row",
      rowPath,
      "--json",
    ]);

    expect(recordResult.status).toBe(0);
    const result = JSON.parse(recordResult.stdout);
    const payload = result.event.payload;
    expect(payload.trajectoryRow).toBeUndefined();
    expect(payload.trajectoryId).toBe("record-cli-row");
    expect(payload.trajectoryEventPath).toContain(`${PRODUCT_TRAJECTORY_EVENTS_RELATIVE_DIR}/`);
    expect(result.trajectoryEvent.relativePath).toBe(payload.trajectoryEventPath);
    expect(result.trajectoryEvent.payload.trajectoryRow.id).toBe("record-cli-row");
    expect(result.trajectoryEvent.payload.trajectoryRow.export.source_event_paths).toEqual(
      expect.arrayContaining([
        result.event.relativePath,
        result.trajectoryEvent.relativePath,
      ]),
    );
  });

  it("rejects invalid trajectory rows in existing record events before writing", async () => {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-trajectory-cli-record-invalid-"));
    tempDirs.push(tempDir);
    await writeMinimalDataloxConfig(tempDir);
    const rowPath = path.join(tempDir, "row.json");
    await writeFile(rowPath, JSON.stringify({
      ...makeRow("invalid-record-cli-row"),
      final: { fix_summary: "" },
    }, null, 2));

    const recordResult = runBuiltCli(repoRoot, [
      "record",
      "--repo",
      tempDir,
      "--summary",
      "invalid trajectory row",
      "--trajectory-row",
      rowPath,
      "--json",
    ]);

    expect(recordResult.status).toBe(1);
    expect(recordResult.stderr).toContain("final.fix_summary");
    expect(existsSync(path.join(tempDir, "agent-wiki", "events"))).toBe(false);
  });

  it("records three rows through MCP and exports them through the CLI", async () => {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-trajectory-mcp-"));
    tempDirs.push(tempDir);
    const transport = new StdioClientTransport({
      command: process.execPath,
      args: [builtMcpPath],
      cwd: repoRoot,
      stderr: "pipe",
    });
    const client = new Client({ name: "trajectory-export-test-client", version: "1.0.0" }, { capabilities: {} });

    try {
      await client.connect(transport);
      const tools = await client.listTools();
      const toolNames = tools.tools.map((tool) => tool.name);
      expect(toolNames).toEqual([
        "record_trajectory",
        "export_trajectories",
        "grade_trajectories",
        "repair_trajectory",
      ]);
      expect(toolNames).not.toEqual(
        expect.arrayContaining(["promote_gap", "patch_knowledge", "lint_pack", "capture_web_artifact", "adopt_pack"]),
      );

      for (const id of ["mcp-row-a", "mcp-row-b", "mcp-row-c"]) {
        const result = await client.callTool({
          name: "record_trajectory",
          arguments: {
            repo_path: tempDir,
            trajectory_row: makeRow(id),
          },
        });
        expect(extractStructuredResult(result)).toMatchObject({
          trajectoryId: id,
          sellable: true,
          blockedReasons: [],
          quality: "use",
          deterministicPassed: true,
          qualityDowngraded: false,
        });
      }
      const gradeResult = await client.callTool({
        name: "grade_trajectories",
        arguments: {
          repo_path: tempDir,
        },
      });
      expect(extractStructuredResult(gradeResult)).toMatchObject({
        scannedEvents: 3,
        candidateRows: 3,
      });
    } finally {
      await client.close();
    }

    const exportResult = runBuiltCli(repoRoot, [
      "export-trajectories",
      "--repo",
      tempDir,
      "--output",
      "mcp-rows.jsonl",
      "--json",
    ]);
    expect(exportResult.status).toBe(0);
    expect(JSON.parse(exportResult.stdout)).toMatchObject({ exportedRows: 3 });
    const lines = (await readFile(path.join(tempDir, "mcp-rows.jsonl"), "utf8")).trim().split("\n");
    expect(lines.map((line) => JSON.parse(line).id)).toEqual(["mcp-row-a", "mcp-row-b", "mcp-row-c"]);
  });

  it("reports downgrade feedback through the MCP record_trajectory tool", async () => {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-trajectory-mcp-downgrade-"));
    tempDirs.push(tempDir);
    const transport = new StdioClientTransport({
      command: process.execPath,
      args: [builtMcpPath],
      cwd: repoRoot,
      stderr: "pipe",
    });
    const client = new Client({ name: "trajectory-downgrade-test-client", version: "1.0.0" }, { capabilities: {} });

    try {
      await client.connect(transport);
      const result = await client.callTool({
        name: "record_trajectory",
        arguments: {
          repo_path: tempDir,
          trajectory_row: makeProseSnippetUseRow("mcp-downgrade-row"),
        },
      });

      expect(extractStructuredResult(result)).toMatchObject({
        trajectoryId: "mcp-downgrade-row",
        quality: "needs_review",
        deterministicPassed: false,
        qualityDowngraded: true,
        qualityDowngradeIssueCodes: expect.arrayContaining(["not_self_contained"]),
      });
    } finally {
      await client.close();
    }
  });

  it("launches the install-facing datalox-mcp bin as the lean trajectory server", async () => {
    const transport = new StdioClientTransport({
      command: process.execPath,
      args: [dataloxMcpBinPath],
      cwd: repoRoot,
      stderr: "pipe",
    });
    const client = new Client({ name: "trajectory-bin-test-client", version: "1.0.0" }, { capabilities: {} });

    try {
      await client.connect(transport);
      const tools = await client.listTools();
      expect(tools.tools.map((tool) => tool.name)).toEqual([
        "record_trajectory",
        "export_trajectories",
        "grade_trajectories",
        "repair_trajectory",
      ]);
    } finally {
      await client.close();
    }
  });
});
