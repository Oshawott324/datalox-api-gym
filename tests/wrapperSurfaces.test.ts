import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { tmpdir } from "node:os";
import path from "node:path";

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

  it("builds a product-only wrapped prompt", async () => {
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
    expect(result.stdout).toContain("# Original Prompt");
    expect(result.stdout).toContain("Fix the wrapper smoke.");
    expect(result.stdout).not.toContain("Reusable-Gap");
    expect(result.stdout).not.toContain("Candidate skills");
  });

  it("defaults wrapper post-run to replay capture without writing derivative rows", async () => {
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
    expect(result.stderr).toContain("[datalox-wrap] replay | replay_capture_pending");
    expect(spawnSync("test", ["-e", path.join(hostDir, ".datalox", "events", "trajectory-rows")]).status).not.toBe(0);
    expect(spawnSync("test", ["-e", path.join(hostDir, ".datalox", "derivatives", "trajectories")]).status).not.toBe(0);
    expect(spawnSync("test", ["-e", path.join(hostDir, legacyWikiDir, "events")]).status).not.toBe(0);
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
    expect(result.stderr).toContain("[datalox-wrap] replay | replay_capture_pending");
    expect(await readFile(path.join(hostDir, legacyWikiDir, "hot.md"), "utf8")).toBe("# existing\n");
    expect(spawnSync("test", ["-e", path.join(hostDir, legacyWikiDir, "events")]).status).not.toBe(0);
  });
});
