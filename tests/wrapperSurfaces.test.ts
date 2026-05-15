import { mkdir, mkdtemp, readFile, readdir, rm, writeFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { PRODUCT_TRAJECTORY_EVENTS_RELATIVE_DIR } from "../src/core/trajectoryExport.js";

const repoRoot = process.cwd();
const builtCliPath = path.join(repoRoot, "dist", "src", "cli", "main.js");
const legacyWikiDir = ["agent", "wiki"].join("-");

function makeRowSource(id: string): string {
  return JSON.stringify({
    schema_version: "debugging_trajectory.v1",
    id,
    created_at: "2026-05-04T00:00:00.000Z",
    task: {
      domain: "coding_debugging",
      prompt: "Fix wrapper trajectory capture.",
      language: "javascript",
      environment: "nodejs",
    },
    context: {
      error: "Wrapper should record explicit rows only.",
      relevant_files: [
        {
          path: "src/wrapper.js",
          before: "recordProse(summary);",
          after: "recordExplicitRow(row);",
        },
      ],
    },
    trajectory: [
      {
        role: "user",
        content: "Requested wrapper trajectory capture.",
      },
      {
        role: "agent",
        content: "Wrote an explicit debugging_trajectory.v1 row file.",
      },
      {
        role: "tool",
        content: "Smoke command completed.",
        tool: "exec_command",
        command: "node -e <script>",
        exit_code: 0,
      },
    ],
    final: {
      fix_summary: "Record the explicit trajectory row supplied by the wrapped agent.",
      changed_files: ["src/wrapper.js"],
    },
    outcome: {
      label: "success",
      verification: "passed",
      command: "node -e <script>",
      evidence: "Smoke command completed.",
    },
    export: {
      allowed: true,
      redaction: "none_needed",
    },
    curation: {
      quality: "use",
      tags: ["wrapper"],
    },
  });
}

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
    expect(result.stdout).toContain("# Datalox Trajectory Capture");
    expect(result.stdout).toContain("# Original Prompt");
    expect(result.stdout).toContain("Fix the wrapper smoke.");
    expect(result.stdout).not.toContain("Reusable-Gap");
    expect(result.stdout).not.toContain("Candidate skills");
  });

  it("records an explicit trajectory row from the default wrapper post-run path", async () => {
    const hostDir = await adoptHostRepo();
    const script = [
      "const fs = require('node:fs');",
      "const path = require('node:path');",
      "const repo = process.env.DATALOX_REPO_PATH;",
      "const rowPath = path.join(repo, '.datalox/trajectory-rows/default-wrapper-row.json');",
      "fs.mkdirSync(path.dirname(rowPath), { recursive: true });",
      `fs.writeFileSync(rowPath, ${JSON.stringify(makeRowSource("traj_wrapper_default"))});`,
      "process.stdout.write('DATALOX_TRAJECTORY_ROW_FILE: .datalox/trajectory-rows/default-wrapper-row.json\\n');",
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
        "Fix wrapper trajectory capture.",
        "--workflow",
        "coding_debugging",
        "--prompt",
        "Fix wrapper trajectory capture.",
        "--",
        "node",
        "-e",
        script,
        "__DATALOX_PROMPT__",
      ],
      {
        cwd: repoRoot,
        encoding: "utf8",
      },
    );

    expect(result.status).toBe(0);
    expect(result.stderr).toContain("[datalox-wrap] trajectory | trajectory_row");
    const eventFiles = await readdir(path.join(hostDir, PRODUCT_TRAJECTORY_EVENTS_RELATIVE_DIR));
    expect(eventFiles).toHaveLength(1);
    const event = JSON.parse(await readFile(path.join(hostDir, PRODUCT_TRAJECTORY_EVENTS_RELATIVE_DIR, eventFiles[0]), "utf8"));
    expect(event.trajectoryRow.id).toBe("traj_wrapper_default");
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
        "trajectory",
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
    expect(result.stderr).toContain("[datalox-wrap] trajectory | missing_trajectory_row");
    expect(await readFile(path.join(hostDir, legacyWikiDir, "hot.md"), "utf8")).toBe("# existing\n");
    expect(spawnSync("test", ["-e", path.join(hostDir, legacyWikiDir, "events")]).status).not.toBe(0);
  });
});
