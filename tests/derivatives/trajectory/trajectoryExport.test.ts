import { existsSync } from "node:fs";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import {
  DEBUGGING_TRAJECTORY_DERIVATIVES_RELATIVE_DIR,
  exportTrajectories,
  recordTrajectory,
  TrajectoryExportError,
} from "../../../src/core/derivatives/trajectory/trajectoryExport.js";
import { repairTrajectory } from "../../../src/core/derivatives/trajectory/trajectoryRepair.js";

const legacyWikiDir = ["agent", "wiki"].join("-");

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

function makeWeakUseRow(id: string) {
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

describe("trajectory recording and export", () => {
  const tempDirs: string[] = [];

  afterEach(async () => {
    await Promise.all(tempDirs.splice(0).map((dir) => rm(dir, { recursive: true, force: true })));
  });

  it("records a trajectory row only under the product event root", async () => {
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
    });
    expect(event.eventKind).toBe("trajectory_row");
    expect(event.trajectoryRow.schema_version).toBe("debugging_trajectory.v1");
    expect(event.trajectoryRow.export.source_event_paths).toContain(result.eventPath);
    expect(result.eventPath).toContain(`${DEBUGGING_TRAJECTORY_DERIVATIVES_RELATIVE_DIR}/`);
    expect(existsSync(path.join(tempDir, legacyWikiDir))).toBe(false);
    expect(existsSync(path.join(tempDir, "skills"))).toBe(false);
  });

  it("downgrades weak use rows at record time without dropping evidence", async () => {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-trajectory-record-downgrade-"));
    tempDirs.push(tempDir);

    const result = await recordTrajectory({
      repoPath: tempDir,
      trajectoryRow: makeWeakUseRow("record-downgraded"),
      now: new Date("2026-05-03T11:00:00.000Z"),
    });
    const event = JSON.parse(await readFile(path.join(tempDir, result.eventPath), "utf8"));

    expect(result.quality).toBe("needs_review");
    expect(result.qualityDowngraded).toBe(true);
    expect(result.qualityDowngradeIssueCodes).toContain("relevant_file_snippet_not_code_like");
    expect(event.trajectoryRow.curation.quality).toBe("needs_review");
    expect(event.trajectoryRow.metadata.datalox_quality_downgraded_from).toBe("use");
  });

  it("exports only .datalox trajectory rows", async () => {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-trajectory-export-"));
    tempDirs.push(tempDir);

    await mkdir(path.join(tempDir, legacyWikiDir, "events"), { recursive: true });
    await writeFile(
      path.join(tempDir, legacyWikiDir, "events", "ignored.json"),
      JSON.stringify({ trajectoryRow: makeRow("ignored-row") }, null, 2),
    );
    await recordTrajectory({
      repoPath: tempDir,
      trajectoryRow: makeRow("new-row"),
      now: new Date("2026-05-03T10:00:00.000Z"),
    });

    const report = await exportTrajectories({
      repoPath: tempDir,
      outputPath: "out/use.jsonl",
      quality: "use",
    });
    const lines = (await readFile(path.join(tempDir, "out", "use.jsonl"), "utf8"))
      .trim()
      .split("\n");

    expect(report.scannedEvents).toBe(1);
    expect(lines.map((line) => JSON.parse(line).id)).toEqual(["new-row"]);
  });

  it("repairs only product trajectory event paths", async () => {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-trajectory-repair-"));
    tempDirs.push(tempDir);

    const recorded = await recordTrajectory({
      repoPath: tempDir,
      trajectoryRow: makeWeakUseRow("repair-row"),
      now: new Date("2026-05-03T10:00:00.000Z"),
    });
    const repair = await repairTrajectory({
      repoPath: tempDir,
      eventPath: recorded.eventPath,
      trajectoryRow: makeRow("repair-row"),
      now: new Date("2026-05-03T10:01:00.000Z"),
    });

    expect(repair.originalEventPath).toBe(recorded.eventPath);
    expect(repair.repairEventPath).toContain(`${DEBUGGING_TRAJECTORY_DERIVATIVES_RELATIVE_DIR}/`);
    expect(repair.trajectoryId).toBe("repair-row");
  });

  it("fails export when use rows are blocked", async () => {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-trajectory-export-blocked-"));
    tempDirs.push(tempDir);

    const blocked = {
      ...makeRow("blocked-row"),
      export: {
        allowed: false,
        redaction: "blocked",
      },
    };
    await recordTrajectory({
      repoPath: tempDir,
      trajectoryRow: blocked,
      now: new Date("2026-05-03T12:00:00.000Z"),
    });

    await expect(exportTrajectories({
      repoPath: tempDir,
      outputPath: "out/use.jsonl",
      quality: "use",
    })).rejects.toBeInstanceOf(TrajectoryExportError);
  });
});
