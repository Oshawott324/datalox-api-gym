import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { afterEach, describe, expect, it } from "vitest";

import {
  AGENT_TASK_TRAJECTORY_EVENTS_RELATIVE_DIR,
  AgentTaskTrajectoryExportError,
  exportAgentTaskTrajectories,
  gradeAgentTaskTrajectoryRow,
  recordAgentTaskTrajectory,
} from "../src/core/agentTaskTrajectoryExport.js";
import { parseAgentTaskTrajectoryV1 } from "../src/core/agentTaskTrajectorySchema.js";

const repoRoot = process.cwd();
const builtCliPath = path.join(repoRoot, "dist", "src", "cli", "main.js");
const builtMcpPath = path.join(repoRoot, "dist", "src", "mcp", "trajectoryServer.js");

function makeRow(id: string) {
  return {
    schema_version: "agent_task_trajectory.v1",
    id,
    created_at: "2026-05-07T00:00:00.000Z",
    task: {
      prompt: `Resolve mixed task ${id}.`,
      domains: ["coding", "docs"],
      workflows: ["mixed_task_episode"],
      environment: "TypeScript and Markdown",
    },
    context: {
      problem: "The implementation and docs both needed a small coordinated update.",
      source_paths: ["src/example.ts", "docs/example.md"],
    },
    trajectory: [
      {
        role: "user",
        content: "Asked to make a small code and documentation update.",
      },
      {
        role: "agent",
        content: "Inspected the affected code and documentation surfaces.",
      },
      {
        role: "tool",
        content: "Focused verification passed.",
        tool: "exec_command",
        command: "npm test -- --runInBand",
        exit_code: 0,
      },
    ],
    evidence_blocks: [
      {
        type: "code_change",
        path: "src/example.ts",
        language: "typescript",
        before: "export const label = formatLabel(value);",
        after: "export const label = formatLabel(value.trim());",
        reason: "Normalize whitespace before formatting the label.",
      },
      {
        type: "command_result",
        command: "npm test -- --runInBand",
        exit_code: 0,
        result_summary: "Focused test command passed: 4 tests, 0 failed.",
      },
    ],
    final: {
      summary: "The task now normalizes label input and documents the behavior.",
      changed_artifacts: ["src/example.ts", "docs/example.md"],
    },
    outcome: {
      label: "success",
      verification: "passed",
      command: "npm test -- --runInBand",
      evidence: "Focused test command passed: 4 tests, 0 failed.",
    },
    export: {
      allowed: true,
      redaction: "none_needed",
    },
    curation: {
      quality: "use",
      tags: ["synthetic", "mixed-domain"],
    },
  };
}

function makeLabRow(id: string) {
  return {
    ...makeRow(id),
    task: {
      prompt: `Review viability gate ${id}.`,
      domains: ["biotech", "source_review"],
      workflows: ["lab_workflow_review"],
      environment: "Protocol review",
    },
    context: {
      problem: "A viability gate needed explicit replicate criteria.",
      source_paths: ["docs/viability-gate.md"],
    },
    evidence_blocks: [
      {
        type: "lab_workflow",
        workflow: "viability gate",
        assay: "cell viability",
        measurement_context: "Triplicate plate-read measurements after compound exposure.",
        before: "Accept when a single viability measurement is above 70%.",
        after: "Accept when all triplicate wells are above 70% viability and CV is below 15%.",
        criteria: "Triplicate wells, viability threshold, and CV must pass.",
      },
      {
        type: "source_reference",
        source_kind: "local_file",
        title: "Viability gate note",
        source_path: "docs/viability-gate.md",
        excerpt: "Triplicate measurements reduce false acceptance when one well is an outlier.",
        relevance: "Grounds the replicate and CV criteria.",
      },
    ],
    final: {
      summary: "The viability gate now uses triplicate and CV criteria.",
      changed_artifacts: ["docs/viability-gate.md"],
    },
    outcome: {
      label: "success",
      verification: "reviewed",
      evidence: "Reviewed against local protocol note.",
    },
    curation: {
      quality: "use",
      tags: ["biotech", "lab-workflow"],
    },
  };
}

function makeProseCodeRow(id: string) {
  return {
    ...makeRow(id),
    evidence_blocks: [
      {
        type: "code_change",
        path: "src/example.ts",
        before: "The previous code formatted the raw value.",
        after: "The new code trims the value before formatting it.",
      },
      {
        type: "command_result",
        command: "npm test -- --runInBand",
        exit_code: 0,
        result_summary: "Focused test command passed: 4 tests, 0 failed.",
      },
    ],
  };
}

function makeSourceOnlyRow(id: string) {
  return {
    ...makeLabRow(id),
    evidence_blocks: [
      {
        type: "source_reference",
        source_kind: "web",
        title: "Protocol source",
        url: "https://example.test/protocol",
      },
    ],
  };
}

function runBuiltCli(cwd: string, args: string[]) {
  return spawnSync("node", [builtCliPath, ...args], {
    cwd,
    encoding: "utf8",
    env: process.env,
  });
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

describe("agent_task_trajectory.v1 recording and export", () => {
  const tempDirs: string[] = [];

  afterEach(async () => {
    await Promise.all(tempDirs.splice(0).map((dir) => rm(dir, { recursive: true, force: true })));
  });

  it("records mixed-domain rows under .datalox and never writes agent-wiki events", async () => {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-agent-task-record-"));
    tempDirs.push(tempDir);

    const result = await recordAgentTaskTrajectory({
      repoPath: tempDir,
      agentTaskTrajectory: makeRow("record-one"),
      now: new Date("2026-05-07T10:00:00.000Z"),
    });
    const event = JSON.parse(await readFile(path.join(tempDir, result.eventPath), "utf8"));

    expect(result).toMatchObject({
      trajectoryId: "record-one",
      sellable: true,
      blockedReasons: [],
      readinessQuality: "use",
      deterministicPassed: true,
    });
    expect(result.eventPath).toContain(`${AGENT_TASK_TRAJECTORY_EVENTS_RELATIVE_DIR}/`);
    expect(event.eventKind).toBe("agent_task_trajectory");
    expect(event.agentTaskTrajectory.schema_version).toBe("agent_task_trajectory.v1");
    expect(event.agentTaskTrajectory.export.source_event_paths).toContain(result.eventPath);
    expect(existsSync(path.join(tempDir, "agent-wiki", "events"))).toBe(false);
  });

  it("exports sellable rows deterministically and reports blocked rows", async () => {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-agent-task-export-"));
    tempDirs.push(tempDir);

    await recordAgentTaskTrajectory({
      repoPath: tempDir,
      agentTaskTrajectory: makeRow("row-b"),
      now: new Date("2026-05-07T10:01:00.000Z"),
    });
    await recordAgentTaskTrajectory({
      repoPath: tempDir,
      agentTaskTrajectory: makeRow("row-a"),
      now: new Date("2026-05-07T10:00:00.000Z"),
    });
    await recordAgentTaskTrajectory({
      repoPath: tempDir,
      agentTaskTrajectory: {
        ...makeRow("not-allowed"),
        export: { allowed: false, redaction: "none_needed" },
      },
      now: new Date("2026-05-07T10:02:00.000Z"),
    });
    await recordAgentTaskTrajectory({
      repoPath: tempDir,
      agentTaskTrajectory: {
        ...makeRow("redaction-blocked"),
        export: { allowed: true, redaction: "blocked" },
      },
      now: new Date("2026-05-07T10:03:00.000Z"),
    });

    const firstReport = await exportAgentTaskTrajectories({
      repoPath: tempDir,
      outputPath: "out/rows.jsonl",
      blockedReportPath: "out/blocked.json",
      split: "eval",
    });
    const firstOutput = await readFile(path.join(tempDir, "out", "rows.jsonl"), "utf8");
    const secondReport = await exportAgentTaskTrajectories({
      repoPath: tempDir,
      outputPath: "out/rows-second.jsonl",
      split: "eval",
    });
    const secondOutput = await readFile(path.join(tempDir, "out", "rows-second.jsonl"), "utf8");
    const lines = firstOutput.trim().split("\n");
    const blockedReport = JSON.parse(await readFile(path.join(tempDir, "out", "blocked.json"), "utf8"));

    expect(firstReport).toMatchObject({
      candidateRows: 4,
      exportedRows: 2,
      blockedRows: 2,
      invalidRows: 0,
      duplicateRows: 0,
    });
    expect(secondReport.exportedRows).toBe(2);
    expect(firstOutput).toBe(secondOutput);
    expect(lines.map((line) => JSON.parse(line).id)).toEqual(["row-a", "row-b"]);
    expect(JSON.parse(lines[0]).curation.split).toBe("eval");
    expect(blockedReport.rejectedRows.map((row: { trajectoryId: string }) => row.trajectoryId)).toEqual([
      "not-allowed",
      "redaction-blocked",
    ]);
  });

  it("accepts non-code lab/source rows and exports them at quality use", async () => {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-agent-task-lab-"));
    tempDirs.push(tempDir);

    await recordAgentTaskTrajectory({
      repoPath: tempDir,
      agentTaskTrajectory: makeLabRow("lab-row"),
      now: new Date("2026-05-07T10:00:00.000Z"),
    });

    const report = await exportAgentTaskTrajectories({
      repoPath: tempDir,
      outputPath: "out/lab.jsonl",
      quality: "use",
    });
    const lines = (await readFile(path.join(tempDir, "out", "lab.jsonl"), "utf8")).trim().split("\n");

    expect(report.exportedRows).toBe(1);
    expect(JSON.parse(lines[0]).evidence_blocks.map((block: { type: string }) => block.type)).toEqual([
      "lab_workflow",
      "source_reference",
    ]);
  });

  it("grades source references with only URL/path as not buyer-ready", () => {
    const grade = gradeAgentTaskTrajectoryRow(parseAgentTaskTrajectoryV1(makeSourceOnlyRow("source-only")));

    expect(grade.quality).toBe("needs_review");
    expect(grade.deterministic_passed).toBe(false);
    expect(grade.blocking_issues.map((issue) => issue.code)).toEqual(
      expect.arrayContaining([
        "source_reference_missing_excerpt",
        "source_reference_missing_relevance",
      ]),
    );
  });

  it("excludes prose-only code evidence from quality-use export", async () => {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-agent-task-prose-"));
    tempDirs.push(tempDir);

    await recordAgentTaskTrajectory({
      repoPath: tempDir,
      agentTaskTrajectory: makeProseCodeRow("prose-code"),
      now: new Date("2026-05-07T10:00:00.000Z"),
    });

    const report = await exportAgentTaskTrajectories({
      repoPath: tempDir,
      outputPath: "out/use.jsonl",
      quality: "use",
    });
    const output = await readFile(path.join(tempDir, "out", "use.jsonl"), "utf8");

    expect(report.exportedRows).toBe(0);
    expect(report.rejectedRows).toEqual([
      expect.objectContaining({
        trajectoryId: "prose-code",
        reason: "readiness_filter",
        detail: expect.objectContaining({
          issue_codes: expect.arrayContaining(["prose_only_evidence_block"]),
        }),
      }),
    ]);
    expect(output).toBe("");
  });

  it("fails export on duplicate agent task trajectory ids", async () => {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-agent-task-duplicate-"));
    tempDirs.push(tempDir);

    await recordAgentTaskTrajectory({
      repoPath: tempDir,
      agentTaskTrajectory: makeRow("duplicate-id"),
      now: new Date("2026-05-07T10:00:00.000Z"),
    });
    await recordAgentTaskTrajectory({
      repoPath: tempDir,
      agentTaskTrajectory: makeLabRow("duplicate-id"),
      now: new Date("2026-05-07T10:01:00.000Z"),
    });

    await expect(exportAgentTaskTrajectories({ repoPath: tempDir, outputPath: "out/rows.jsonl" }))
      .rejects
      .toThrow(AgentTaskTrajectoryExportError);
  });

  it("records and exports through the built CLI", async () => {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-agent-task-cli-"));
    tempDirs.push(tempDir);
    const rowPath = path.join(tempDir, "row.json");
    await writeFile(rowPath, JSON.stringify(makeRow("cli-row"), null, 2), "utf8");

    const recordResult = runBuiltCli(repoRoot, [
      "record-agent-task-trajectory",
      "--repo",
      tempDir,
      "--agent-task-trajectory",
      rowPath,
      "--json",
    ]);
    expect(recordResult.status).toBe(0);
    expect(JSON.parse(recordResult.stdout)).toMatchObject({
      trajectoryId: "cli-row",
      sellable: true,
    });

    const exportResult = runBuiltCli(repoRoot, [
      "export-agent-task-trajectories",
      "--repo",
      tempDir,
      "--output",
      "out/cli.jsonl",
      "--quality",
      "use",
      "--json",
    ]);
    expect(exportResult.status).toBe(0);
    expect(JSON.parse(exportResult.stdout)).toMatchObject({ exportedRows: 1 });
  });

  it("exposes agent task trajectory tools through the lean MCP server", async () => {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-agent-task-mcp-"));
    tempDirs.push(tempDir);
    const transport = new StdioClientTransport({
      command: process.execPath,
      args: [builtMcpPath],
      cwd: repoRoot,
      stderr: "pipe",
    });
    const client = new Client({ name: "agent-task-trajectory-test-client", version: "1.0.0" }, { capabilities: {} });

    try {
      await client.connect(transport);
      const tools = await client.listTools();
      const toolNames = tools.tools.map((tool) => tool.name);
      expect(toolNames).toEqual([
        "record_trajectory",
        "export_trajectories",
        "record_agent_task_trajectory",
        "export_agent_task_trajectories",
        "grade_trajectories",
        "repair_trajectory",
      ]);

      const recordResult = await client.callTool({
        name: "record_agent_task_trajectory",
        arguments: {
          repo_path: tempDir,
          agent_task_trajectory: makeRow("mcp-agent-task-row"),
        },
      });
      expect(extractStructuredResult(recordResult)).toMatchObject({
        trajectoryId: "mcp-agent-task-row",
        sellable: true,
        readinessQuality: "use",
      });

      const exportResult = await client.callTool({
        name: "export_agent_task_trajectories",
        arguments: {
          repo_path: tempDir,
          output_path: "out/mcp.jsonl",
          quality: "use",
        },
      });
      expect(extractStructuredResult(exportResult)).toMatchObject({
        exportedRows: 1,
      });
    } finally {
      await client.close();
    }
  });
});
