import { mkdir, mkdtemp, readdir, readFile, rm, writeFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { tmpdir } from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";

import { afterEach, describe, expect, it } from "vitest";

const repoRoot = process.cwd();
const builtCliPath = path.join(repoRoot, "dist", "src", "cli", "main.js");
const legacyWikiDir = ["agent", "wiki"].join("-");

describe("wrapper surfaces", () => {
  const tempDirs: string[] = [];

  afterEach(async () => {
    await Promise.all(tempDirs.splice(0).map((dir) => rm(dir, { recursive: true, force: true })));
  });

  async function adoptHostRepo(): Promise<string> {
    const hostDir = await mkdtemp(path.join(tmpdir(), "datalox-wrapper-host-"));
    tempDirs.push(hostDir);
    const adopt = spawnSync("bash", [path.join(repoRoot, "bin", "adopt-host-repo.sh"), hostDir], {
      cwd: repoRoot,
      encoding: "utf8",
    });
    expect(adopt.status).toBe(0);
    return hostDir;
  }

  it("builds a replay-only wrapped prompt", async () => {
    const hostDir = await adoptHostRepo();
    const result = spawnSync(
      "node",
      [
        builtCliPath,
        "wrap",
        "prompt",
        "--repo",
        hostDir,
        "--task",
        "fix the failing wrapper smoke",
        "--workflow",
        "coding_debugging",
        "--prompt",
        "Fix the wrapper smoke.",
      ],
      {
        cwd: repoRoot,
        encoding: "utf8",
      },
    );

    expect(result.status).toBe(0);
    expect(result.stdout).toContain("# Datalox Agent Replay");
    expect(result.stdout).toContain("record_tool_io");
    expect(result.stdout).toContain("DATALOX_SESSION_ID");
    expect(result.stdout).toContain("# Original Prompt");
    expect(result.stdout).toContain("Fix the wrapper smoke.");
    expect(result.stdout).not.toContain("Reusable-Gap");
    expect(result.stdout).not.toContain("Candidate skills");
    expect(result.stdout).not.toContain("trajectory rows");
  });

  it("defaults wrapper post-run to empty replay capture without writing derivative rows when tool I/O is missing", async () => {
    const hostDir = await adoptHostRepo();
    const result = spawnSync(
      "node",
      [
        builtCliPath,
        "wrap",
        "command",
        "--repo",
        hostDir,
        "--task",
        "Fix wrapper replay capture.",
        "--workflow",
        "agent_replay",
        "--prompt",
        "Fix wrapper replay capture.",
        "--",
        "node",
        "-e",
        "process.stdout.write('completed without tool evidence')",
        "__DATALOX_PROMPT__",
      ],
      {
        cwd: repoRoot,
        encoding: "utf8",
      },
    );

    expect(result.status).toBe(0);
    expect(result.stderr).toContain("[datalox-wrap] replay | replay_capture_empty");
    expect(result.stderr).toContain("No explicit tool_io_record.v1 records were created during this wrapped run");
    expect(spawnSync("test", ["-e", path.join(hostDir, ".datalox", "events", "agent-turns")]).status).not.toBe(0);
    expect(spawnSync("test", ["-e", path.join(hostDir, ".datalox", "events", "trajectory-rows")]).status).not.toBe(0);
    expect(spawnSync("test", ["-e", path.join(hostDir, ".datalox", "derivatives", "trajectories")]).status).not.toBe(0);
    expect(spawnSync("test", ["-e", path.join(hostDir, legacyWikiDir, "events")]).status).not.toBe(0);
  });

  it("rejects an invalid CLI post-run mode before running the child command", async () => {
    const hostDir = await adoptHostRepo();
    const markerPath = path.join(hostDir, "child-ran-cli-mode");
    const result = spawnSync(
      "node",
      [
        builtCliPath,
        "wrap",
        "command",
        "--repo",
        hostDir,
        "--task",
        "Reject bad CLI mode.",
        "--post-run-mode",
        "invalid",
        "--",
        "node",
        "-e",
        `require('node:fs').writeFileSync(${JSON.stringify(markerPath)}, 'ran')`,
        "__DATALOX_PROMPT__",
      ],
      {
        cwd: repoRoot,
        encoding: "utf8",
      },
    );

    expect(result.status).toBe(1);
    expect(result.stderr).toContain("Invalid --post-run-mode");
    expect(result.stderr).toContain("Allowed values: off, replay");
    expect(spawnSync("test", ["-e", markerPath]).status).not.toBe(0);
  });

  it("rejects an invalid env post-run mode before running the child command", async () => {
    const hostDir = await adoptHostRepo();
    const markerPath = path.join(hostDir, "child-ran-env-mode");
    const result = spawnSync(
      "node",
      [
        builtCliPath,
        "wrap",
        "command",
        "--repo",
        hostDir,
        "--task",
        "Reject bad env mode.",
        "--",
        "node",
        "-e",
        `require('node:fs').writeFileSync(${JSON.stringify(markerPath)}, 'ran')`,
        "__DATALOX_PROMPT__",
      ],
      {
        cwd: repoRoot,
        encoding: "utf8",
        env: {
          ...process.env,
          DATALOX_DEFAULT_POST_RUN_MODE: "bogus",
        },
      },
    );

    expect(result.status).toBe(1);
    expect(result.stderr).toContain("Invalid DATALOX_DEFAULT_POST_RUN_MODE");
    expect(result.stderr).toContain("Allowed values: off, replay");
    expect(spawnSync("test", ["-e", markerPath]).status).not.toBe(0);
  });

  it("does not accept trajectory as a wrapper post-run mode", async () => {
    const hostDir = await adoptHostRepo();
    const markerPath = path.join(hostDir, "child-ran-trajectory-mode");
    const result = spawnSync(
      "node",
      [
        builtCliPath,
        "wrap",
        "command",
        "--repo",
        hostDir,
        "--task",
        "Reject trajectory mode.",
        "--post-run-mode",
        "trajectory",
        "--",
        "node",
        "-e",
        `require('node:fs').writeFileSync(${JSON.stringify(markerPath)}, 'ran')`,
        "__DATALOX_PROMPT__",
      ],
      {
        cwd: repoRoot,
        encoding: "utf8",
      },
    );

    expect(result.status).toBe(1);
    expect(result.stderr).toContain("Invalid --post-run-mode");
    expect(result.stderr).toContain("Allowed values: off, replay");
    expect(spawnSync("test", ["-e", markerPath]).status).not.toBe(0);
  });

  it("preserves explicit off post-run mode", async () => {
    const hostDir = await adoptHostRepo();
    const result = spawnSync(
      "node",
      [
        builtCliPath,
        "wrap",
        "command",
        "--repo",
        hostDir,
        "--task",
        "Run with post-run disabled.",
        "--post-run-mode",
        "off",
        "--",
        "node",
        "-e",
        "process.stdout.write('child still ran')",
        "__DATALOX_PROMPT__",
      ],
      {
        cwd: repoRoot,
        encoding: "utf8",
      },
    );

    expect(result.status).toBe(0);
    expect(result.stdout).toContain("child still ran");
    expect(result.stderr).toContain("[datalox-wrap] off | disabled");
    expect(result.stderr).toContain("Wrapper post-run recording is disabled");
    expect(spawnSync("test", ["-e", path.join(hostDir, ".datalox", "events", "agent-turns")]).status).not.toBe(0);
  });

  it("records an agent turn when a wrapped run creates explicit tool I/O evidence", async () => {
    const hostDir = await adoptHostRepo();
    const recordToolIoModuleUrl = pathToFileURL(path.join(repoRoot, "dist", "src", "core", "toolIoStore.js")).href;
    const recordScript = [
      `const { recordToolIo } = await import(${JSON.stringify(recordToolIoModuleUrl)});`,
      "await recordToolIo({",
      "  repoPath: process.env.DATALOX_REPO_PATH,",
      "  sessionId: process.env.DATALOX_SESSION_ID,",
      "  callId: 'call-1',",
      "  toolName: 'fake_tool',",
      "  arguments: { query: 'wrapper evidence' },",
      "  observation: { status: 'ok', content: { answer: 42 } },",
      "  source: { host: process.env.DATALOX_HOST_KIND, command: 'fake_tool wrapper evidence' },",
      "});",
      "process.stdout.write('recorded explicit tool io');",
    ].join("\n");

    const result = spawnSync(
      "node",
      [
        builtCliPath,
        "wrap",
        "command",
        "--repo",
        hostDir,
        "--task",
        "Record wrapper replay evidence.",
        "--workflow",
        "agent_replay",
        "--prompt",
        "Record wrapper replay evidence.",
        "--",
        "node",
        "--input-type=module",
        "-e",
        recordScript,
        "__DATALOX_PROMPT__",
      ],
      {
        cwd: repoRoot,
        encoding: "utf8",
      },
    );

    expect(result.status).toBe(0);
    expect(result.stdout).toContain("recorded explicit tool io");
    expect(result.stderr).toContain("[datalox-wrap] replay | replay_evidence_recorded");
    expect(result.stderr).toContain("Recorded agent_turn.v1 from 1 explicit tool_io_record.v1 record");

    const turnEventsRoot = path.join(hostDir, ".datalox", "events", "agent-turns");
    const turnEventNames = await readdir(turnEventsRoot);
    expect(turnEventNames).toHaveLength(1);
    const turnEvent = JSON.parse(await readFile(path.join(turnEventsRoot, turnEventNames[0]), "utf8"));
    expect(turnEvent.eventKind).toBe("agent_turn");
    expect(turnEvent.agentTurn.schema_version).toBe("agent_turn.v1");
    expect(turnEvent.agentTurn.session_id).toMatch(/^datalox-wrapper-/);
    expect(turnEvent.agentTurn.user_prompt).toBe("Record wrapper replay evidence.");
    expect(turnEvent.agentTurn.tool_calls).toHaveLength(1);
    expect(turnEvent.agentTurn.tool_calls[0]).toMatchObject({
      tool: "fake_tool",
      call_id: "call-1",
      command: "fake_tool wrapper evidence",
    });
    expect(turnEvent.agentTurn.tool_calls[0].tool_io_ref.record_id).toMatch(/^toolio-/);
    expect(spawnSync("test", ["-e", path.join(hostDir, ".datalox", "events", "trajectory-rows")]).status).not.toBe(0);
    expect(spawnSync("test", ["-e", path.join(hostDir, ".datalox", "derivatives", "trajectories")]).status).not.toBe(0);
  });

  it("does not create a legacy event from prose summaries", async () => {
    const hostDir = await adoptHostRepo();
    await mkdir(path.join(hostDir, legacyWikiDir), { recursive: true });
    await writeFile(path.join(hostDir, legacyWikiDir, "hot.md"), "# existing\n", "utf8");

    const result = spawnSync(
      "node",
      [
        builtCliPath,
        "wrap",
        "command",
        "--repo",
        hostDir,
        "--task",
        "Summarize without a row.",
        "--post-run-mode",
        "replay",
        "--",
        "node",
        "-e",
        "process.stdout.write('completed without row')",
        "__DATALOX_PROMPT__",
      ],
      {
        cwd: repoRoot,
        encoding: "utf8",
      },
    );

    expect(result.status).toBe(0);
    expect(result.stderr).toContain("[datalox-wrap] replay | replay_capture_empty");
    expect(await readFile(path.join(hostDir, legacyWikiDir, "hot.md"), "utf8")).toBe("# existing\n");
    expect(spawnSync("test", ["-e", path.join(hostDir, legacyWikiDir, "events")]).status).not.toBe(0);
  });
});
