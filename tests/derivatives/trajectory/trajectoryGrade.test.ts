import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import {
  DEBUGGING_TRAJECTORY_DERIVATIVES_RELATIVE_DIR,
  recordTrajectory,
} from "../../../src/core/derivatives/trajectory/trajectoryExport.js";
import { repairTrajectory } from "../../../src/core/derivatives/trajectory/trajectoryRepair.js";
import {
  gradeTrajectories,
  gradeTrajectoryRow,
  TrajectoryGradeError,
} from "../../../src/core/derivatives/trajectory/trajectoryGrade.js";
import type { DebuggingTrajectoryV1 } from "../../../src/core/derivatives/trajectory/trajectorySchema.js";

function makeTrainingRow(id: string): DebuggingTrajectoryV1 {
  return {
    schema_version: "debugging_trajectory.v1",
    id,
    created_at: "2026-05-04T00:00:00.000Z",
    task: {
      domain: "coding_debugging",
      prompt: "Fix the TypeError when reading an async API response.",
      language: "typescript",
      environment: "nodejs",
    },
    context: {
      error: "TypeError: Cannot read properties of undefined",
      relevant_files: [
        {
          path: "src/api.ts",
          before: "const data = fetchUser(id);\nreturn data.name;",
          after: "const data = await fetchUser(id);\nreturn data.name;",
        },
      ],
      notes: ["Failure came from reading data.name before the async response resolved."],
    },
    trajectory: [
      {
        role: "user",
        content: "The API response path fails with a TypeError.",
      },
      {
        role: "agent",
        content: "Inspected src/api.ts and found fetchUser(id) returns a Promise.",
      },
      {
        role: "agent",
        content: "Added await before fetchUser(id).",
        files_changed: ["src/api.ts"],
      },
      {
        role: "tool",
        content: "tests/api.test.ts passed: 8 tests, 0 failed.",
        tool: "shell",
        command: "npm test -- tests/api.test.ts",
        exit_code: 0,
      },
    ],
    final: {
      fix_summary: "Await the async API call before reading the response.",
      patch: [
        "diff --git a/src/api.ts b/src/api.ts",
        "--- a/src/api.ts",
        "+++ b/src/api.ts",
        "@@",
        "-const data = fetchUser(id);",
        "+const data = await fetchUser(id);",
        " return data.name;",
      ].join("\n"),
      changed_files: ["src/api.ts"],
    },
    outcome: {
      label: "success",
      verification: "passed",
      command: "npm test -- tests/api.test.ts",
      evidence: "tests/api.test.ts passed: 8 tests, 0 failed.",
    },
    export: {
      allowed: true,
      redaction: "none_needed",
    },
    curation: {
      quality: "use",
      tags: ["async", "missing-await"],
    },
    metadata: {
      verified_by: "deterministic-fixture",
    },
  };
}

function cloneRow(row: DebuggingTrajectoryV1): DebuggingTrajectoryV1 {
  return JSON.parse(JSON.stringify(row)) as DebuggingTrajectoryV1;
}

function issueCodes(row: DebuggingTrajectoryV1): string[] {
  return gradeTrajectoryRow(row).blocking_issues.map((issue) => issue.code);
}

describe("trajectory training-readiness grading", () => {
  const tempDirs: string[] = [];

  afterEach(async () => {
    await Promise.all(tempDirs.splice(0).map((dir) => rm(dir, { recursive: true, force: true })));
  });

  it("grades a training-ready row as use", () => {
    const grade = gradeTrajectoryRow(makeTrainingRow("ready-row"));

    expect(grade).toMatchObject({
      schema: "datalox.trajectory_grade.v1",
      trajectory_id: "ready-row",
      quality: "use",
      exportable: true,
      deterministic_passed: true,
      reviewer_required: false,
      blocking_issues: [],
      token_notes: {
        over_budget: false,
      },
    });
  });

  it("blocks rows whose snippets point outside the row instead of showing code", () => {
    const row = cloneRow(makeTrainingRow("external-reference"));
    row.context.relevant_files = [
      {
        path: "src/api.ts",
        before: "see src/api.ts before the change",
        after: "see .datalox/events/source.json for the fixed code",
      },
    ];

    expect(issueCodes(row)).toContain("relevant_file_snippet_external_reference");
  });

  it("grades recorded derivative events by event path", async () => {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-trajectory-grade-recorded-"));
    tempDirs.push(tempDir);

    const recorded = await recordTrajectory({
      repoPath: tempDir,
      trajectoryRow: makeTrainingRow("recorded-ready"),
      now: new Date("2026-05-04T01:00:00.000Z"),
    });
    const report = await gradeTrajectories({
      repoPath: tempDir,
      eventPath: recorded.eventPath,
    });
    const grade = report.grades[0].grade;

    expect(grade.trajectory_id).toBe("recorded-ready");
    expect(grade.quality).toBe("use");
  });

  it("rejects grading event paths outside the derivative trajectory root", async () => {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-trajectory-grade-invalid-path-"));
    tempDirs.push(tempDir);
    await writeFile(path.join(tempDir, "source.json"), JSON.stringify({ trajectoryRow: makeTrainingRow("bad") }));

    await expect(gradeTrajectories({
      repoPath: tempDir,
      eventPath: "source.json",
    })).rejects.toThrow("eventPath must point under .datalox/derivatives/trajectories/debugging.");
  });

  it("repairs derivative trajectory events by writing a corrected derivative event", async () => {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-trajectory-repair-"));
    tempDirs.push(tempDir);

    const source = await recordTrajectory({
      repoPath: tempDir,
      trajectoryRow: makeTrainingRow("repair-source"),
      now: new Date("2026-05-04T01:00:00.000Z"),
    });
    const repair = await repairTrajectory({
      repoPath: tempDir,
      eventPath: source.eventPath,
      trajectoryRow: makeTrainingRow("repair-corrected"),
      now: new Date("2026-05-04T01:01:00.000Z"),
    });

    expect(repair.originalEventPath).toBe(source.eventPath);
    expect(repair.repairEventPath).toContain(`${DEBUGGING_TRAJECTORY_DERIVATIVES_RELATIVE_DIR}/`);
    const repaired = JSON.parse(await readFile(path.join(tempDir, repair.repairEventPath), "utf8"));
    expect(repaired.trajectoryRow.id).toBe("repair-corrected");
  });
  it("throws a typed error for malformed recorded events", async () => {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-trajectory-grade-malformed-"));
    tempDirs.push(tempDir);

    await recordTrajectory({
      repoPath: tempDir,
      trajectoryRow: makeTrainingRow("valid"),
      now: new Date("2026-05-04T02:00:00.000Z"),
    });
    await writeFile(
      path.join(tempDir, DEBUGGING_TRAJECTORY_DERIVATIVES_RELATIVE_DIR, "malformed.json"),
      "{ not json",
    );

    await expect(gradeTrajectories({
      repoPath: tempDir,
    })).rejects.toBeInstanceOf(TrajectoryGradeError);
  });
});
