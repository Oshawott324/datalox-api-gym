import { describe, expect, it } from "vitest";

import { parseDataloxRunV1 } from "../src/core/run/runTranscriptSchema.js";

describe("datalox run transcript schema", () => {
  it("accepts a minimal model run transcript", () => {
    const run = parseDataloxRunV1({
      schema_version: "datalox_run.v1",
      id: "run_support_triage_qwen",
      created_at: "2026-05-23T00:00:00.000Z",
      task_ref: "support-triage@2026-05.0",
      fixture_refs: ["support-triage-basic@2026-05.0"],
      fixture_set_ref: "support-triage-basic@2026-05.0",
      model: {
        provider: "openai_compatible",
        model: "qwen2.5-7b-instruct",
        base_url: "http://localhost:8000/v1",
        sampling: {
          temperature: 0.2,
        },
      },
      messages: [
        {
          role: "user",
          content: "Summarize this support thread.",
        },
        {
          role: "assistant",
          content: "The issue is covered by the refund policy.",
        },
      ],
      steps: [
        {
          index: 0,
          assistant_message: {
            role: "assistant",
            content: "The issue is covered by the refund policy.",
          },
        },
      ],
      final_answer: "The issue is covered by the refund policy.",
      stop_reason: "final_answer",
      export: {
        allowed: true,
        redaction: "none_needed",
      },
    });

    expect(run.schema_version).toBe("datalox_run.v1");
  });

  it("rejects runs without fixture refs", () => {
    expect(() => parseDataloxRunV1({
      schema_version: "datalox_run.v1",
      id: "bad",
      created_at: "2026-05-23T00:00:00.000Z",
      fixture_refs: [],
      model: {
        provider: "openai_compatible",
        model: "qwen",
        base_url: "http://localhost:8000/v1",
      },
      messages: [],
      steps: [],
      stop_reason: "final_answer",
      export: {
        allowed: false,
        redaction: "blocked",
      },
    })).toThrow(/fixture_refs/);
  });
});
