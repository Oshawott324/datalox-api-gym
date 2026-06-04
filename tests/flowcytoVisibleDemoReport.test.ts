import path from "node:path";
import { pathToFileURL } from "node:url";

import { describe, expect, it } from "vitest";

describe("FlowCyto visible demo report", () => {
  it("renders proof cards and a domain tool timeline from run artifacts", async () => {
    const reportModuleUrl = pathToFileURL(path.join(
      process.cwd(),
      "examples",
      "flowcyto-gating-qc-demo",
      "report.mjs",
    )).href;
    const { renderDemoReport } = await import(reportModuleUrl) as {
      renderDemoReport: (input: Record<string, unknown>) => string;
    };

    const html = renderDemoReport({
      fixtureSetRef: "flowcyto-gating-qc-basic@2026-06.0",
      installResult: {
        ref: "flowcyto-gating-qc-basic@2026-06.0",
        installed: true,
      },
      runResult: {
        stopReason: "final_answer",
        stepCount: 7,
      },
      run: {
        schema_version: "datalox_run.v1",
        fixture_set_ref: "flowcyto-gating-qc-basic@2026-06.0",
        stop_reason: "final_answer",
        final_answer: "Completed with QC evidence.",
        steps: [
          {
            index: 0,
            tool_call: {
              name: "open_fcs",
              arguments: { path: "fixture://flowcyto-gating-qc-basic/testdata/CFP_Well_A4.fcs" },
            },
            observation: { status: "ok" },
          },
          {
            index: 1,
            tool_call: {
              name: "compute_gate_stats",
              arguments: { gate_id: "lymphocytes" },
            },
            observation: { status: "ok", content: { percentOfParent: 0.31 } },
          },
        ],
      },
      exportResult: {
        frameCount: 1,
      },
      replayMissProof: {
        replayMiss: {
          code: "replay_miss",
          tool_name: "compute_gate_stats",
          liveFallback: false,
        },
      },
      artifactPaths: {
        runPath: "run/run.json",
        transcriptPath: "run/transcript.jsonl",
        sftPath: "flowcyto-qc.sft.jsonl",
        replayMissPath: "replay-miss-proof.json",
      },
    });

    expect(html).toContain("Fixture Installed");
    expect(html).toContain("Agent Used FlowCyto Tools");
    expect(html).toContain("Replay World Only");
    expect(html).toContain("Run Artifact");
    expect(html).toContain("SFT Export");
    expect(html).toContain("flowcyto-gating-qc-basic@2026-06.0");
    expect(html).toContain("open_fcs");
    expect(html).toContain("compute_gate_stats");
    expect(html).toContain("liveFallback");
    expect(html).toContain("run/run.json");
    expect(html).toContain("flowcyto-qc.sft.jsonl");
  });
});
