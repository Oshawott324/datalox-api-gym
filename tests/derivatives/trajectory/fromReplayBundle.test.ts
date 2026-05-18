import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { recordAgentTurn } from "../../../src/core/agentTurnStore.js";
import { AGENT_TURNS_RELATIVE_DIR } from "../../../src/core/agentTurnStore.js";
import {
  deriveAgentTaskTrajectoryFromReplayBundle,
} from "../../../src/core/derivatives/trajectory/fromReplayBundle.js";
import { packReplayBundle, ReplayBundleVerificationError } from "../../../src/core/replayBundle.js";
import { recordToolIo, TOOL_IO_RECORDS_RELATIVE_DIR } from "../../../src/core/toolIoStore.js";

describe("derive agent_task_trajectory.v1 from replay bundles", () => {
  const tempDirs: string[] = [];

  afterEach(async () => {
    await Promise.all(tempDirs.splice(0).map((dir) => rm(dir, { recursive: true, force: true })));
  });

  async function makeTempRepo(): Promise<string> {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-from-replay-bundle-"));
    tempDirs.push(tempDir);
    return tempDir;
  }

  async function seedCodeBundle(repoPath: string) {
    const patch = [
      "*** Begin Patch",
      "*** Add File: src/core/example.ts",
      "+export function answer(): number {",
      "+  return 42;",
      "+}",
      "*** End Patch",
      "",
    ].join("\n");
    const patchRecord = await recordToolIo({
      repoPath,
      sessionId: "session-1",
      turnId: "turn-1",
      callId: "patch-call",
      toolName: "apply_patch",
      arguments: { patch },
      observation: {
        status: "ok",
        content: { status: "applied" },
      },
      export: {
        allowed: true,
        redaction: "none_needed",
      },
      now: new Date("2026-05-18T00:00:00.000Z"),
    });
    const testRecord = await recordToolIo({
      repoPath,
      sessionId: "session-1",
      turnId: "turn-1",
      callId: "test-call",
      toolName: "exec_command",
      arguments: { command: "npm test" },
      observation: {
        status: "ok",
        content: {
          exit_code: 0,
          stdout: "2 tests passed in 120ms.",
        },
      },
      export: {
        allowed: true,
        redaction: "none_needed",
      },
      now: new Date("2026-05-18T00:00:01.000Z"),
    });

    await recordAgentTurn({
      repoPath,
      now: new Date("2026-05-18T00:00:02.000Z"),
      agentTurn: {
        schema_version: "agent_turn.v1",
        id: "turn-1",
        session_id: "session-1",
        turn_index: 0,
        created_at: "2026-05-18T00:00:02.000Z",
        user_prompt: "Add a small typed helper and verify it.",
        assistant_summary: "Added src/core/example.ts and ran the focused test command.",
        tool_calls: [
          {
            tool: "apply_patch",
            call_id: "patch-call",
            tool_io_ref: {
              record_id: patchRecord.record.id,
              request_hash: patchRecord.record.request_hash,
              sequence_index: patchRecord.record.sequence_index,
            },
            args_summary: "Add src/core/example.ts",
          },
          {
            tool: "exec_command",
            call_id: "test-call",
            tool_io_ref: {
              record_id: testRecord.record.id,
              request_hash: testRecord.record.request_hash,
              sequence_index: testRecord.record.sequence_index,
            },
            command: "npm test",
            exit_code: 0,
            output_summary: "2 tests passed in 120ms.",
          },
        ],
        file_changes: [
          {
            path: "src/core/example.ts",
            action: "created",
            diff_summary: "Added answer helper.",
          },
        ],
        verification: {
          command: "npm test",
          status: "passed",
          evidence: "2 tests passed in 120ms.",
        },
        export: {
          allowed: true,
          redaction: "none_needed",
        },
      },
    });

    return packReplayBundle({
      repoPath,
      bundleId: "verified-code-bundle",
      title: "Add typed helper",
      task: {
        prompt: "Add a small typed helper and verify it.",
        domains: ["typescript"],
        workflows: ["code_change"],
      },
      export: {
        allowed: true,
        redaction: "none_needed",
      },
      now: new Date("2026-05-18T00:00:03.000Z"),
    });
  }

  it("derives a standalone compact candidate from a verified replay bundle", async () => {
    const repoPath = await makeTempRepo();
    const bundle = await seedCodeBundle(repoPath);

    await rm(path.join(repoPath, TOOL_IO_RECORDS_RELATIVE_DIR), { recursive: true, force: true });
    await rm(path.join(repoPath, AGENT_TURNS_RELATIVE_DIR), { recursive: true, force: true });

    const result = await deriveAgentTaskTrajectoryFromReplayBundle({
      repoPath,
      bundlePath: bundle.bundlePath,
      quality: "use",
      now: new Date("2026-05-18T00:00:04.000Z"),
    });

    expect(result.verified).toBe(true);
    expect(result.replayBundle).toMatchObject({
      bundleId: "verified-code-bundle",
      bundlePath: ".datalox/replay-bundles/verified-code-bundle",
    });
    expect(result.row).toMatchObject({
      schema_version: "agent_task_trajectory.v1",
      id: "derived-verified-code-bundle",
      task: {
        prompt: "Add a small typed helper and verify it.",
        domains: ["typescript"],
      },
      replay_bundle_ref: {
        bundle_id: "verified-code-bundle",
        bundle_path: ".datalox/replay-bundles/verified-code-bundle",
      },
      outcome: {
        label: "success",
        verification: "passed",
        command: "npm test",
      },
      export: {
        allowed: true,
        redaction: "none_needed",
      },
      curation: {
        quality: "use",
      },
    });
    expect(result.row.export.source_event_paths).toBeUndefined();
    expect(result.row.evidence_blocks).toEqual(expect.arrayContaining([
      expect.objectContaining({
        type: "code_change",
        path: "src/core/example.ts",
        patch: expect.stringContaining("+export function answer"),
      }),
      expect.objectContaining({
        type: "command_result",
        command: "npm test",
        exit_code: 0,
        result_summary: expect.stringContaining("2 tests passed"),
      }),
    ]));
    expect(result.row.trajectory.map((step) => step.role)).toEqual([
      "user",
      "agent",
      "tool",
      "tool",
    ]);
    expect(result.readiness).toMatchObject({
      quality: "use",
      deterministic_passed: true,
      blocking_issues: [],
    });

    const jsonlRow = JSON.parse(result.jsonl);
    expect(jsonlRow.task.prompt).toBe("Add a small typed helper and verify it.");
    expect(jsonlRow.evidence_blocks[0].patch).toContain("+export function answer");
    expect(jsonlRow.replay_bundle_ref.bundle_id).toBe("verified-code-bundle");
  });

  it("blocks derivative export when the replay bundle is unverified", async () => {
    const repoPath = await makeTempRepo();
    const bundle = await seedCodeBundle(repoPath);
    const manifestPath = path.join(repoPath, bundle.bundlePath, "manifest.json");
    const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
    manifest.replay.tool_record_count = 999;
    await writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");

    await expect(deriveAgentTaskTrajectoryFromReplayBundle({
      repoPath,
      bundlePath: bundle.bundlePath,
    })).rejects.toBeInstanceOf(ReplayBundleVerificationError);
  });

  it("keeps replay bundles as source of truth for weak derivative candidates", async () => {
    const repoPath = await makeTempRepo();
    await mkdir(path.join(repoPath, AGENT_TURNS_RELATIVE_DIR), { recursive: true });
    await recordAgentTurn({
      repoPath,
      now: new Date("2026-05-18T01:00:00.000Z"),
      agentTurn: {
        schema_version: "agent_turn.v1",
        id: "review-turn",
        session_id: "session-review",
        turn_index: 0,
        created_at: "2026-05-18T01:00:00.000Z",
        user_prompt: "Review the bundle.",
        assistant_summary: "Reviewed the source material without running verification.",
        tool_calls: [],
        verification: {
          status: "not_run",
        },
        export: {
          allowed: false,
          redaction: "blocked",
        },
      },
    });
    const bundle = await packReplayBundle({
      repoPath,
      bundleId: "private-review-bundle",
      export: {
        allowed: false,
        redaction: "blocked",
      },
      now: new Date("2026-05-18T01:00:01.000Z"),
    });

    const result = await deriveAgentTaskTrajectoryFromReplayBundle({
      repoPath,
      bundlePath: bundle.bundlePath,
    });

    expect(result.row.export).toEqual({
      allowed: false,
      redaction: "blocked",
    });
    expect(result.row.replay_bundle_ref).toEqual({
      bundle_id: "private-review-bundle",
      bundle_path: ".datalox/replay-bundles/private-review-bundle",
    });
    expect(result.row.curation?.quality).toBe("needs_review");
    expect(result.readiness.exportable).toBe(false);
    expect(result.readiness.quality).toBe("discard");
    expect(result.row.evidence_blocks).toEqual([
      expect.objectContaining({
        type: "source_reference",
        source_path: ".datalox/replay-bundles/private-review-bundle/manifest.json",
      }),
    ]);
  });
});
