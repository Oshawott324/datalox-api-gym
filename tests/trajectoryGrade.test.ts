import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import {
  LEGACY_EVENTS_RELATIVE_DIR,
  PRODUCT_TRAJECTORY_EVENTS_RELATIVE_DIR,
  recordTrajectory,
} from "../src/core/trajectoryExport.js";
import { repairTrajectory } from "../src/core/trajectoryRepair.js";
import {
  gradeRecordedTrajectoryEvent,
  gradeTrajectories,
  gradeTrajectoryRow,
  TrajectoryGradeError,
} from "../src/core/trajectoryGrade.js";
import type { DebuggingTrajectoryV1 } from "../src/core/trajectorySchema.js";

const repoRoot = process.cwd();
const builtCliPath = path.join(repoRoot, "dist", "src", "cli", "main.js");

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

function runBuiltCli(cwd: string, args: string[]) {
  return spawnSync("node", [builtCliPath, ...args], {
    cwd,
    encoding: "utf8",
    env: process.env,
  });
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

  it("grades a dogfood-style receipt row as needs_review when snippets are prose", () => {
    const row = makeTrainingRow("dogfood-like-receipt");
    row.context.relevant_files = [
      {
        path: "src/adapters/shared.ts",
        before: "The wrapper used to write a legacy trace receipt after each run.",
        after: "The wrapper now records only explicit trajectory rows.",
      },
    ];
    delete row.final.patch;
    row.final.explanation = "Changed files are listed because the row was produced from a summarized wrapper capture.";

    const grade = gradeTrajectoryRow(row);

    expect(grade.quality).toBe("needs_review");
    expect(grade.exportable).toBe(true);
    expect(grade.deterministic_passed).toBe(false);
    expect(grade.blocking_issues).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          code: "prose_only_relevant_file",
          path: "context.relevant_files.0",
        }),
      ]),
    );
  });

  it("reports actionable diagnostics when a row has no patch and no explanation", () => {
    const row = makeTrainingRow("no-patch-no-explanation");
    delete row.final.patch;
    delete row.final.explanation;

    expect(issueCodes(row)).toContain("missing_patch_or_explanation");
    expect(gradeTrajectoryRow(row).blocking_issues).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          code: "missing_patch_or_explanation",
          repair_action: expect.stringContaining("final.patch"),
        }),
      ]),
    );
  });

  it("rejects placeholder patch and snippet evidence", () => {
    const row = makeTrainingRow("placeholder-evidence");
    row.final.patch = [
      "diff --git a/src/api.ts b/src/api.ts",
      "--- a/src/api.ts",
      "+++ b/src/api.ts",
      "@@",
      "-const data = fetchUser(id);",
      "+const data = await fetchUser(id);",
      "+  { cliCommand: \"grade-trajectories\", mcpTool: \"grade_trajectories\", ... },",
    ].join("\n");
    row.context.relevant_files = [
      {
        path: "src/api.ts",
        before: "function readUser(id) {\n  ...\n}",
        after: "async function readUser(id) {\n  ...\n}",
      },
    ];

    expect(issueCodes(row)).toEqual(
      expect.arrayContaining(["placeholder_patch", "placeholder_relevant_file"]),
    );
  });

  it("rejects rows that depend on external files instead of inline snippets", () => {
    const row = makeTrainingRow("external-reference-only");
    row.context.relevant_files = [
      {
        path: "src/api.ts",
        before: "See src/api.ts in the repo.\n",
        after: "Open agent-wiki/events/source.json for the fixed code.\n",
      },
    ];
    delete row.final.patch;
    row.final.explanation = "Refer to source_event_paths for the actual fix.";

    const grade = gradeTrajectoryRow(row);

    expect(grade.quality).toBe("needs_review");
    expect(grade.blocking_issues).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          code: "not_self_contained",
          path: "context.relevant_files",
        }),
        expect.objectContaining({
          code: "not_self_contained",
          path: "final.explanation",
        }),
      ]),
    );
  });

  it("allows source event paths when inline snippets carry the training payload", () => {
    const row = makeTrainingRow("source-paths-with-inline-evidence");
    row.export.source_event_paths = [
      "agent-wiki/events/source.json",
      ".datalox/events/trajectory-rows/source.json",
    ];

    expect(gradeTrajectoryRow(row)).toMatchObject({
      quality: "use",
      deterministic_passed: true,
      blocking_issues: [],
    });
  });

  it("allows no patch when the explanation is grounded in inline snippets", () => {
    const row = makeTrainingRow("concrete-explanation-without-patch");
    delete row.final.patch;
    row.final.explanation = [
      "The before snippet reads data.name from the unresolved fetchUser Promise.",
      "The after snippet awaits fetchUser(id) before reading data.name.",
    ].join(" ");

    expect(gradeTrajectoryRow(row)).toMatchObject({
      quality: "use",
      deterministic_passed: true,
      blocking_issues: [],
    });
  });

  it("rejects external-only explanations when no patch is available", () => {
    const row = makeTrainingRow("external-explanation-without-patch");
    delete row.final.patch;
    row.final.explanation = "See src/api.ts and source_event_paths for the actual patch.";

    expect(gradeTrajectoryRow(row).blocking_issues).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          code: "not_self_contained",
          path: "final.explanation",
        }),
      ]),
    );
  });

  it("returns null for non-trajectory event envelopes and grades trajectory envelopes", () => {
    expect(gradeRecordedTrajectoryEvent({ eventKind: "trace" })).toBeNull();
    expect(gradeRecordedTrajectoryEvent({ trajectoryRow: makeTrainingRow("enveloped-row") }))
      .toMatchObject({ trajectory_id: "enveloped-row", quality: "use" });
  });

  it("grades exactly one event path and does not mutate source events or write notes and skills", async () => {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-trajectory-grade-one-"));
    tempDirs.push(tempDir);
    const first = await recordTrajectory({
      repoPath: tempDir,
      trajectoryRow: makeTrainingRow("grade-one-a"),
      now: new Date("2026-05-04T01:00:00.000Z"),
    });
    await recordTrajectory({
      repoPath: tempDir,
      trajectoryRow: makeTrainingRow("grade-one-b"),
      now: new Date("2026-05-04T01:01:00.000Z"),
    });
    const absoluteEventPath = path.join(tempDir, first.eventPath);
    const before = await readFile(absoluteEventPath, "utf8");

    const report = await gradeTrajectories({
      repoPath: tempDir,
      eventPath: first.eventPath,
    });
    const after = await readFile(absoluteEventPath, "utf8");

    expect(report).toMatchObject({
      scannedEvents: 1,
      candidateRows: 1,
      useRows: 1,
      needsReviewRows: 0,
      discardRows: 0,
      invalidRows: 0,
    });
    expect(report.grades.map((entry) => entry.grade.trajectory_id)).toEqual(["grade-one-a"]);
    expect(after).toBe(before);
    expect(first.eventPath).toContain(`${PRODUCT_TRAJECTORY_EVENTS_RELATIVE_DIR}/`);
    expect(existsSync(path.join(tempDir, "agent-wiki", "notes"))).toBe(false);
    expect(existsSync(path.join(tempDir, "skills"))).toBe(false);
  });

  it("returns schema diagnostics with event path and field path for invalid trajectory rows", async () => {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-trajectory-grade-invalid-"));
    tempDirs.push(tempDir);
    await mkdir(path.join(tempDir, LEGACY_EVENTS_RELATIVE_DIR), { recursive: true });
    const eventPath = path.join(LEGACY_EVENTS_RELATIVE_DIR, "2026-05-04T01-00-00-000Z--invalid.json");
    const row = cloneRow(makeTrainingRow("invalid-row"));
    row.final = {} as DebuggingTrajectoryV1["final"];
    await writeFile(
      path.join(tempDir, eventPath),
      JSON.stringify({ timestamp: "2026-05-04T01:00:00.000Z", trajectoryRow: row }, null, 2),
    );

    try {
      await gradeTrajectories({ repoPath: tempDir });
      throw new Error("Expected invalid trajectory row");
    } catch (error) {
      expect(error).toBeInstanceOf(TrajectoryGradeError);
      const report = (error as TrajectoryGradeError).report;
      expect(report.invalidRows).toBe(1);
      expect(report.invalid[0]).toMatchObject({
        eventPath,
        reason: "invalid_schema",
      });
      expect(report.invalid[0].detail).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            path: ["final", "fix_summary"],
          }),
        ]),
      );
    }
  });

  it("fails grading on malformed event JSON", async () => {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-trajectory-grade-malformed-"));
    tempDirs.push(tempDir);
    await mkdir(path.join(tempDir, LEGACY_EVENTS_RELATIVE_DIR), { recursive: true });
    await writeFile(
      path.join(tempDir, LEGACY_EVENTS_RELATIVE_DIR, "2026-05-04T01-00-00-000Z--malformed.json"),
      "{ bad json",
    );

    await expect(gradeTrajectories({ repoPath: tempDir }))
      .rejects
      .toMatchObject({
        report: {
          invalidRows: 1,
          invalid: [
            expect.objectContaining({
              reason: "malformed_event",
            }),
          ],
        },
      });
  });

  it("flags oversized patch, snippets, and metadata independently", () => {
    const row = makeTrainingRow("over-budget-row");
    row.final.patch = `diff --git a/src/api.ts b/src/api.ts\n${"x".repeat(64)}`;
    row.context.relevant_files = [
      {
        path: "src/api.ts",
        before: `const before = "${"b".repeat(64)}";`,
        after: `const after = "${"a".repeat(64)}";`,
      },
    ];
    row.metadata = {
      source: "fixture",
      long: "m".repeat(64),
    };

    const grade = gradeTrajectoryRow(row, {
      maxRowChars: 100000,
      maxPatchChars: 20,
      maxSnippetChars: 20,
      maxMetadataChars: 20,
    });

    const overBudgetPaths = grade.blocking_issues
      .filter((issue) => issue.code === "row_over_token_budget")
      .map((issue) => issue.path);
    expect(overBudgetPaths).toEqual(
      expect.arrayContaining([
        "final.patch",
        "context.relevant_files.0.before",
        "context.relevant_files.0.after",
        "metadata",
      ]),
    );
  });

  it("repairs by writing a new linked event without mutating the original", async () => {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-trajectory-repair-"));
    tempDirs.push(tempDir);
    const originalRow = makeTrainingRow("repair-row");
    originalRow.context.relevant_files = [
      {
        path: "src/api.ts",
        before: "The API call was not awaited.",
        after: "The API call is awaited.",
      },
    ];
    originalRow.curation = { quality: "needs_review" };
    const original = await recordTrajectory({
      repoPath: tempDir,
      trajectoryRow: originalRow,
      now: new Date("2026-05-04T01:00:00.000Z"),
    });
    const originalAbsolutePath = path.join(tempDir, original.eventPath);
    const before = await readFile(originalAbsolutePath, "utf8");

    const correctedRow = makeTrainingRow("repair-row-corrected");
    const repair = await repairTrajectory({
      repoPath: tempDir,
      eventPath: original.eventPath,
      trajectoryRow: correctedRow,
      now: new Date("2026-05-04T01:01:00.000Z"),
    });
    const after = await readFile(originalAbsolutePath, "utf8");
    const repairedEvent = JSON.parse(await readFile(path.join(tempDir, repair.repairEventPath), "utf8"));

    expect(after).toBe(before);
    expect(repair).toMatchObject({
      originalEventPath: original.eventPath,
      trajectoryId: "repair-row-corrected",
      sellable: true,
    });
    expect(repairedEvent.trajectoryRow.export.source_event_paths).toEqual(
      expect.arrayContaining([original.eventPath, repair.repairEventPath]),
    );
    expect(repairedEvent.trajectoryRow.metadata.datalox_repaired_from_event_path).toBe(original.eventPath);
    expect(gradeTrajectoryRow(repairedEvent.trajectoryRow).quality).toBe("use");
  });

  it("repairs legacy trajectory events by writing the corrected row to .datalox", async () => {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-trajectory-repair-legacy-"));
    tempDirs.push(tempDir);
    await mkdir(path.join(tempDir, LEGACY_EVENTS_RELATIVE_DIR), { recursive: true });
    const legacyEventPath = path.join(
      LEGACY_EVENTS_RELATIVE_DIR,
      "2026-05-04T01-00-00-000Z--legacy-trajectory.json",
    );
    await writeFile(
      path.join(tempDir, legacyEventPath),
      JSON.stringify({
        timestamp: "2026-05-04T01:00:00.000Z",
        trajectoryRow: makeTrainingRow("legacy-repair-source"),
      }, null, 2),
    );

    const repair = await repairTrajectory({
      repoPath: tempDir,
      eventPath: legacyEventPath,
      trajectoryRow: makeTrainingRow("legacy-repair-corrected"),
      now: new Date("2026-05-04T01:01:00.000Z"),
    });

    expect(repair.originalEventPath).toBe(legacyEventPath);
    expect(repair.repairEventPath).toContain(`${PRODUCT_TRAJECTORY_EVENTS_RELATIVE_DIR}/`);
    const repairedEvent = JSON.parse(await readFile(path.join(tempDir, repair.repairEventPath), "utf8"));
    expect(repairedEvent.trajectoryRow.export.source_event_paths).toEqual(
      expect.arrayContaining([legacyEventPath, repair.repairEventPath]),
    );
  });

  it("prints deterministic grade counts through the built CLI", async () => {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-trajectory-grade-cli-"));
    tempDirs.push(tempDir);
    await recordTrajectory({
      repoPath: tempDir,
      trajectoryRow: makeTrainingRow("cli-grade-use"),
      now: new Date("2026-05-04T01:00:00.000Z"),
    });
    await recordTrajectory({
      repoPath: tempDir,
      trajectoryRow: {
        ...makeTrainingRow("cli-grade-review"),
        curation: { quality: "needs_review" },
      },
      now: new Date("2026-05-04T01:01:00.000Z"),
    });

    const result = runBuiltCli(repoRoot, [
      "grade-trajectories",
      "--repo",
      tempDir,
      "--json",
    ]);

    expect(result.status).toBe(0);
    expect(JSON.parse(result.stdout)).toMatchObject({
      scannedEvents: 2,
      candidateRows: 2,
      useRows: 1,
      needsReviewRows: 1,
      discardRows: 0,
      invalidRows: 0,
      issueCounts: {},
    });
  });
});
