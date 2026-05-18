import { describe, expect, it } from "vitest";

import {
  getAgentTaskTrajectorySellableBlockers,
  isSellableAgentTaskTrajectoryRow,
  parseAgentTaskTrajectoryV1,
  serializeAgentTaskTrajectoryJsonlRow,
} from "../../../src/core/derivatives/trajectory/agentTaskTrajectorySchema.js";

function makeMixedRow(id = "agent-task-schema-row") {
  return {
    schema_version: "agent_task_trajectory.v1",
    id,
    created_at: "2026-05-07T00:00:00.000Z",
    task: {
      prompt: "Fix a runtime setting UI issue and verify the focused React test.",
      domains: ["coding", "ui"],
      workflows: ["runtime_settings"],
      environment: "React, TypeScript, Vitest",
    },
    context: {
      problem: "Saved runtime keys could appear cleared after a successful save.",
      source_paths: ["src/components/runtime/runtime-settings-section.tsx"],
    },
    trajectory: [
      {
        role: "user",
        content: "Asked to pick up a runtime API-key save UI-state sync fix.",
      },
      {
        role: "agent",
        content: "Inspected the runtime setup card and settings section state flow.",
      },
      {
        role: "tool",
        content: "Focused runtime setup card tests passed.",
        tool: "exec_command",
        command: "npx vitest run src/components/runtime/agent-runtime-setup-card.test.tsx",
        exit_code: 0,
      },
    ],
    evidence_blocks: [
      {
        type: "code_change",
        path: "src/components/runtime/runtime-settings-section.tsx",
        language: "tsx",
        before: "setFormState(agentRuntimeSetupFormFromView(updatedSetup));",
        after: "setFormState(agentRuntimeSetupStateAfterSave(updatedSetup, submittedApiKey));",
        reason: "Keep the submitted key in memory for the successful save round.",
      },
      {
        type: "command_result",
        command: "npx vitest run src/components/runtime/agent-runtime-setup-card.test.tsx",
        exit_code: 0,
        result_summary: "Runtime setup card test file passed: 9 tests, 0 failed.",
      },
    ],
    final: {
      summary: "Saved runtime API keys now remain visually saved after a successful submit.",
      changed_artifacts: [
        "src/components/runtime/runtime-settings-section.tsx",
        "src/components/runtime/agent-runtime-setup-card.test.tsx",
      ],
    },
    outcome: {
      label: "success",
      verification: "passed",
      command: "npx vitest run src/components/runtime/agent-runtime-setup-card.test.tsx",
      evidence: "Runtime setup card test file passed: 9 tests, 0 failed.",
    },
    export: {
      allowed: true,
      redaction: "none_needed",
    },
    curation: {
      quality: "use",
      tags: ["runtime-settings", "ui-state"],
    },
  };
}

function makeLabRow(id = "agent-task-lab-row") {
  return {
    ...makeMixedRow(id),
    task: {
      prompt: "Update a viability assay workflow using a cited source.",
      domains: ["biotech", "source_review"],
      workflows: ["lab_workflow_review"],
      environment: "protocol planning",
    },
    context: {
      problem: "The viability gate needed explicit replicate and threshold criteria.",
      source_paths: ["docs/viability-gate.md"],
    },
    evidence_blocks: [
      {
        type: "lab_workflow",
        workflow: "viability gate review",
        assay: "cell viability",
        measurement_context: "Triplicate plate-read measurements after compound exposure.",
        before: "Accept gate when a single viability measurement is above 70%.",
        after: "Accept gate when all triplicate wells remain above 70% viability and CV is below 15%.",
        criteria: "Triplicate wells, viability threshold, and coefficient of variation must all pass.",
      },
      {
        type: "source_reference",
        source_kind: "local_file",
        title: "Viability gate protocol note",
        source_path: "docs/viability-gate.md",
        excerpt: "Triplicate measurements reduce false acceptance when one well is an outlier.",
        relevance: "Grounds the added replicate and CV criteria.",
      },
    ],
    final: {
      summary: "The viability workflow now requires triplicate threshold and CV criteria.",
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

describe("agent_task_trajectory.v1 schema", () => {
  it("parses a mixed code_change and command_result row", () => {
    const parsed = parseAgentTaskTrajectoryV1(makeMixedRow());

    expect(parsed.schema_version).toBe("agent_task_trajectory.v1");
    expect(parsed.task.domains).toEqual(["coding", "ui"]);
    expect(parsed.evidence_blocks.map((block) => block.type)).toEqual(["code_change", "command_result"]);
    expect(isSellableAgentTaskTrajectoryRow(parsed)).toBe(true);
  });

  it("parses a non-code lab_workflow and source_reference row", () => {
    const parsed = parseAgentTaskTrajectoryV1(makeLabRow());

    expect(parsed.task.domains).toEqual(["biotech", "source_review"]);
    expect(parsed.evidence_blocks.map((block) => block.type)).toEqual(["lab_workflow", "source_reference"]);
    expect(parsed.final.changed_artifacts).toEqual(["docs/viability-gate.md"]);
  });

  it("accepts exact code_change patch evidence without before/after snippets", () => {
    const parsed = parseAgentTaskTrajectoryV1({
      ...makeMixedRow("patch-evidence"),
      evidence_blocks: [
        {
          type: "code_change",
          path: "PyMolAI/modules/protein_mcp/apply_plan.py",
          language: "python",
          symbol: "build_apply_plan",
          patch: [
            "+def build_apply_plan(workspace, previous_workspace, active_view_id):",
            "+    current_view = _active_view(workspace, active_view_id)",
            "+    previous_view = _active_view(previous_workspace, current_view.id if current_view else active_view_id)",
            "+    actions = []",
            "+    actions.extend(_object_actions(workspace, previous_workspace, current_view, previous_view))",
            "+    return {\"actions\": actions}",
          ].join("\n"),
          reason: "Add a pure entry point that compares workspace state and returns ordered scene actions.",
        },
        {
          type: "command_result",
          command: "pytest testing/protein_mcp/test_apply_plan.py -q",
          exit_code: 0,
          result_summary: "Focused apply-plan tests passed: 8 tests, 0 failed.",
        },
      ],
    });

    expect(parsed.evidence_blocks[0]).toMatchObject({
      type: "code_change",
      patch: expect.stringContaining("+def build_apply_plan"),
    });
    expect(isSellableAgentTaskTrajectoryRow(parsed)).toBe(true);
  });

  it("rejects empty evidence blocks", () => {
    expect(() => parseAgentTaskTrajectoryV1({
      ...makeMixedRow("empty-evidence"),
      evidence_blocks: [],
    })).toThrow(/evidence_blocks/);
  });

  it("rejects unknown evidence block types", () => {
    expect(() => parseAgentTaskTrajectoryV1({
      ...makeMixedRow("unknown-type"),
      evidence_blocks: [
        {
          type: "video_review",
          artifact: "screen-recording.mp4",
          summary: "Reviewed the recording.",
        },
      ],
    })).toThrow(/evidence_blocks/);
  });

  it("rejects unknown fields inside evidence blocks", () => {
    expect(() => parseAgentTaskTrajectoryV1({
      ...makeMixedRow("unknown-field"),
      evidence_blocks: [
        {
          type: "command_result",
          command: "npm test",
          exit_code: 0,
          result_summary: "npm test passed: 12 tests, 0 failed.",
          raw_output: "not allowed in the strict row",
        },
      ],
    })).toThrow(/Unrecognized key/);
  });

  it("keeps blocked export gates valid but unsellable", () => {
    const notAllowed = parseAgentTaskTrajectoryV1({
      ...makeMixedRow("not-allowed"),
      export: { allowed: false, redaction: "none_needed" },
    });
    const redactionBlocked = parseAgentTaskTrajectoryV1({
      ...makeMixedRow("redaction-blocked"),
      export: { allowed: true, redaction: "blocked" },
    });

    expect(isSellableAgentTaskTrajectoryRow(notAllowed)).toBe(false);
    expect(getAgentTaskTrajectorySellableBlockers(notAllowed)).toEqual(["export.allowed_false"]);
    expect(isSellableAgentTaskTrajectoryRow(redactionBlocked)).toBe(false);
    expect(getAgentTaskTrajectorySellableBlockers(redactionBlocked)).toEqual(["export.redaction_blocked"]);
  });

  it("formats one row as one JSONL object line", () => {
    const row = parseAgentTaskTrajectoryV1(makeMixedRow());
    const line = serializeAgentTaskTrajectoryJsonlRow(row);

    expect(line).not.toContain("\n");
    expect(JSON.parse(line)).toMatchObject({
      id: "agent-task-schema-row",
      schema_version: "agent_task_trajectory.v1",
    });
  });
});
