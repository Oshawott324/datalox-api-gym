import { describe, expect, it } from "vitest";

import {
  getTrajectorySellableBlockers,
  isSellableTrajectoryRow,
  parseDebuggingTrajectoryV1,
  serializeTrajectoryJsonlRow,
} from "../src/core/trajectorySchema.js";

function makeRow(id = "schema-row") {
  return {
    schema_version: "debugging_trajectory.v1",
    id,
    created_at: "2026-05-03T00:00:00.000Z",
    task: {
      domain: "coding_debugging",
      prompt: "Fix a TypeScript test failure",
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
        content: "The test suite fails with a TypeError.",
      },
      {
        role: "agent",
        content: "Inspected the failing call site and found an unchecked optional value.",
        tool: "shell",
        command: "npm test",
        exit_code: 1,
      },
      {
        role: "agent",
        content: "Added an explicit guard before invoking the value.",
        files_changed: ["src/example.ts"],
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
      evidence: "Tests passed.",
    },
    export: {
      allowed: true,
      redaction: "none_needed",
    },
    metadata: {
      verified_by: "agent",
    },
  };
}

function makeSchemaDocExample() {
  return {
    schema_version: "debugging_trajectory.v1",
    id: "traj_01hxyz",
    created_at: "2026-05-03T00:00:00.000Z",
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
          before: "const data = fetchUser(id); return data.name;",
          after: "const data = await fetchUser(id); return data.name;",
        },
      ],
    },
    trajectory: [
      {
        role: "agent",
        content: "Observed that the failing line reads a property from the API response.",
      },
      {
        role: "agent",
        content: "Identified that fetchUser returns a Promise and the call was not awaited.",
      },
      {
        role: "agent",
        content: "Added await before fetchUser(id).",
        files_changed: ["src/api.ts"],
      },
      {
        role: "tool",
        content: "Tests passed.",
        command: "npm test",
        exit_code: 0,
      },
    ],
    final: {
      fix_summary: "Await the async API call before reading the response.",
      changed_files: ["src/api.ts"],
      explanation: "The resolved object is available before property access.",
    },
    outcome: {
      label: "success",
      verification: "passed",
      command: "npm test",
      evidence: "Tests passed.",
    },
    export: {
      allowed: true,
      redaction: "none_needed",
      source_event_paths: ["agent-wiki/events/example.json"],
    },
    curation: {
      quality: "use",
      tags: ["async", "missing-await"],
    },
  };
}

describe("debugging_trajectory.v1 schema", () => {
  it("parses the lean training row shape", () => {
    const parsed = parseDebuggingTrajectoryV1(makeRow());

    expect(parsed.schema_version).toBe("debugging_trajectory.v1");
    expect(parsed.task.domain).toBe("coding_debugging");
    expect(parsed.trajectory).toHaveLength(3);
    expect(isSellableTrajectoryRow(parsed)).toBe(true);
  });

  it("parses the minimal valid example from the schema doc", () => {
    const parsed = parseDebuggingTrajectoryV1(makeSchemaDocExample());

    expect(parsed.id).toBe("traj_01hxyz");
    expect(parsed.context.relevant_files?.[0]?.path).toBe("src/api.ts");
    expect(parsed.curation?.quality).toBe("use");
  });

  it("rejects missing required fields with field-level errors", () => {
    expect(() => parseDebuggingTrajectoryV1({ ...makeRow(), task: { domain: "coding_debugging", prompt: "" } }))
      .toThrow(/task\.prompt/);
    expect(() => parseDebuggingTrajectoryV1({ ...makeRow(), trajectory: [] }))
      .toThrow(/trajectory/);
    expect(() => parseDebuggingTrajectoryV1({ ...makeRow(), final: { fix_summary: "" } }))
      .toThrow(/final\.fix_summary/);

    const { outcome: _outcome, ...missingOutcome } = makeRow();
    expect(() => parseDebuggingTrajectoryV1(missingOutcome)).toThrow(/outcome/);

    const { export: _export, ...missingExport } = makeRow();
    expect(() => parseDebuggingTrajectoryV1(missingExport)).toThrow(/export/);
  });

  it("accepts explicit non-command verification states", () => {
    const notRun = parseDebuggingTrajectoryV1({
      ...makeRow("not-run"),
      outcome: { label: "partial", verification: "not_run" },
    });
    const reviewed = parseDebuggingTrajectoryV1({
      ...makeRow("reviewed"),
      outcome: { label: "success", verification: "reviewed" },
    });

    expect(notRun.outcome.verification).toBe("not_run");
    expect(reviewed.outcome.verification).toBe("reviewed");
  });

  it("keeps blocked export gates valid but unsellable", () => {
    const notAllowed = parseDebuggingTrajectoryV1({
      ...makeRow("not-allowed"),
      export: { allowed: false, redaction: "none_needed" },
    });
    const redactionBlocked = parseDebuggingTrajectoryV1({
      ...makeRow("redaction-blocked"),
      export: { allowed: true, redaction: "blocked" },
    });

    expect(isSellableTrajectoryRow(notAllowed)).toBe(false);
    expect(getTrajectorySellableBlockers(notAllowed)).toEqual(["export.allowed_false"]);
    expect(isSellableTrajectoryRow(redactionBlocked)).toBe(false);
    expect(getTrajectorySellableBlockers(redactionBlocked)).toEqual(["export.redaction_blocked"]);
  });

  it("formats one row as one JSONL object line", () => {
    const row = parseDebuggingTrajectoryV1(makeRow());
    const line = serializeTrajectoryJsonlRow(row);

    expect(line).not.toContain("\n");
    expect(JSON.parse(line)).toMatchObject({ id: "schema-row", schema_version: "debugging_trajectory.v1" });
  });
});
