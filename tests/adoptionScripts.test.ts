import { chmod, mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

const repoRoot = process.cwd();
const legacyWikiDir = ["agent", "wiki"].join("-");
const legacyPackToken = `DATALOX_${"PACK"}`;

describe("replay adoption scripts", () => {
  const tempDirs: string[] = [];

  afterEach(async () => {
    await Promise.all(tempDirs.splice(0).map((dir) => rm(dir, { recursive: true, force: true })));
  });

  it("adopts replay surfaces without creating the removed wiki store", async () => {
    const hostDir = await mkdtemp(path.join(tmpdir(), "datalox-host-adopt-"));
    tempDirs.push(hostDir);

    const result = spawnSync("bash", [path.join(repoRoot, "bin/adopt-host-repo.sh"), hostDir], {
      cwd: repoRoot,
      encoding: "utf8",
    });

    expect(result.status).toBe(0);
    expect(await readFile(path.join(hostDir, "DATALOX.md"), "utf8")).toContain("agent tool call -> tool_io_record.v1 -> replay_bundle.v1 -> deterministic replay -> optional derivatives");
    expect(await readFile(path.join(hostDir, "AGENTS.md"), "utf8")).toContain(".datalox/manifest.json");
    expect(await readFile(path.join(hostDir, "AGENTS.md"), "utf8")).toContain(".datalox/tool-io/records/");
    expect(await readFile(path.join(hostDir, "AGENTS.md"), "utf8")).toContain(".datalox/events/agent-turns/");
    expect(await readFile(path.join(hostDir, "AGENTS.md"), "utf8")).toContain(".datalox/replay-bundles/");
    expect(await readFile(path.join(hostDir, ".datalox/install.json"), "utf8")).toContain("\"installMode\": \"manual\"");
    expect(await readFile(path.join(hostDir, "bin/datalox.js"), "utf8")).toContain("Unable to resolve Datalox Agent Replay runtime root for datalox.js");
    expect(await readFile(path.join(hostDir, "bin/datalox-mcp.js"), "utf8")).toContain("replayServer.js");
    expect(await readFile(path.join(hostDir, "bin/datalox-agent-replay-mcp.js"), "utf8")).toContain("replayServer.js");
    expect(spawnSync("test", ["-e", path.join(hostDir, legacyWikiDir)]).status).not.toBe(0);
    expect(spawnSync("test", ["-e", path.join(hostDir, "skills")]).status).not.toBe(0);
    expect(spawnSync("test", ["-e", path.join(hostDir, ".datalox", "derivatives", "trajectories")]).status).not.toBe(0);
  }, 30000);

  it("injects replay-only instructions into existing host instruction files", async () => {
    const hostDir = await mkdtemp(path.join(tmpdir(), "datalox-host-existing-instructions-"));
    tempDirs.push(hostDir);
    await mkdir(path.join(hostDir, ".github"), { recursive: true });
    await writeFile(path.join(hostDir, "AGENTS.md"), [
      "# Existing Agent Instructions",
      "",
      `<!-- ${legacyPackToken}:BEGIN -->`,
      `Use ${legacyWikiDir}/events for legacy pack events.`,
      `<!-- ${legacyPackToken}:END -->`,
      "",
      "Keep this project-specific instruction.",
      "",
    ].join("\n"), "utf8");
    await writeFile(path.join(hostDir, ".github", "copilot-instructions.md"), [
      "# Existing Copilot Instructions",
      "",
      "Keep Copilot local instruction.",
      "",
    ].join("\n"), "utf8");

    const result = spawnSync("bash", [path.join(repoRoot, "bin/adopt-host-repo.sh"), hostDir], {
      cwd: repoRoot,
      encoding: "utf8",
    });

    expect(result.status).toBe(0);
    for (const relativePath of ["AGENTS.md", ".github/copilot-instructions.md"]) {
      const content = await readFile(path.join(hostDir, relativePath), "utf8");
      expect(content).toContain("DATALOX_AGENT_REPLAY:BEGIN");
      expect(content).toContain(".datalox/tool-io/records/");
      expect(content).toContain(".datalox/events/agent-turns/");
      expect(content).toContain(".datalox/replay-bundles/");
      expect(content).not.toContain(legacyPackToken);
      expect(content).not.toContain(legacyWikiDir);
    }
    expect(await readFile(path.join(hostDir, "AGENTS.md"), "utf8")).toContain("Keep this project-specific instruction.");
    expect(await readFile(path.join(hostDir, ".github", "copilot-instructions.md"), "utf8")).toContain("Keep Copilot local instruction.");
    expect(spawnSync("test", ["-e", path.join(hostDir, legacyWikiDir)]).status).not.toBe(0);
  }, 30000);

  it("preserves an existing user-owned legacy wiki directory without adopting into it", async () => {
    const hostDir = await mkdtemp(path.join(tmpdir(), "datalox-host-existing-wiki-"));
    tempDirs.push(hostDir);
    await mkdir(path.join(hostDir, legacyWikiDir), { recursive: true });
    await writeFile(path.join(hostDir, legacyWikiDir, "hot.md"), "# existing\n", "utf8");

    const result = spawnSync("bash", [path.join(repoRoot, "bin/adopt-host-repo.sh"), hostDir], {
      cwd: repoRoot,
      encoding: "utf8",
    });

    expect(result.status).toBe(0);
    expect(await readFile(path.join(hostDir, legacyWikiDir, "hot.md"), "utf8")).toBe("# existing\n");
    expect(spawnSync("test", ["-e", path.join(hostDir, legacyWikiDir, "events")]).status).not.toBe(0);
  }, 30000);

  it("installs host shims without linking legacy native skills", async () => {
    const hostDir = await mkdtemp(path.join(tmpdir(), "datalox-host-self-install-"));
    const homeDir = await mkdtemp(path.join(tmpdir(), "datalox-home-"));
    tempDirs.push(hostDir, homeDir);

    const adopt = spawnSync("bash", [path.join(repoRoot, "bin/adopt-host-repo.sh"), hostDir], {
      cwd: repoRoot,
      encoding: "utf8",
    });
    expect(adopt.status).toBe(0);

    const fakeCodex = path.join(homeDir, "fake-codex");
    const fakeClaude = path.join(homeDir, "fake-claude");
    await writeFile(fakeCodex, "#!/usr/bin/env bash\nexit 0\n", "utf8");
    await writeFile(fakeClaude, "#!/usr/bin/env bash\nexit 0\n", "utf8");
    await chmod(fakeCodex, 0o755);
    await chmod(fakeClaude, 0o755);

    const install = spawnSync("bash", [path.join(hostDir, "bin/install-default-host-integrations.sh")], {
      cwd: hostDir,
      encoding: "utf8",
      env: {
        ...process.env,
        HOME: homeDir,
        DATALOX_REAL_CODEX_BIN: fakeCodex,
        DATALOX_REAL_CLAUDE_BIN: fakeClaude,
      },
    });

    expect(install.status).toBe(0);
    expect(await readFile(path.join(homeDir, ".local/bin/codex"), "utf8")).toContain(`PACK_ROOT="${repoRoot}"`);
    expect(await readFile(path.join(homeDir, ".local/bin/claude"), "utf8")).toContain(`PACK_ROOT="${repoRoot}"`);
    expect(await readFile(path.join(homeDir, ".local/bin/codex"), "utf8")).toContain("DATALOX_DEFAULT_POST_RUN_MODE:=replay");
    expect(await readFile(path.join(homeDir, ".local/bin/claude"), "utf8")).toContain("DATALOX_DEFAULT_POST_RUN_MODE:=replay");
    expect(await readFile(path.join(repoRoot, "bin", "datalox-codex.js"), "utf8")).toContain("DATALOX_DEFAULT_POST_RUN_MODE: process.env.DATALOX_DEFAULT_POST_RUN_MODE ?? \"replay\"");
    expect(await readFile(path.join(repoRoot, "bin", "datalox-claude.js"), "utf8")).toContain("DATALOX_DEFAULT_POST_RUN_MODE: process.env.DATALOX_DEFAULT_POST_RUN_MODE ?? \"replay\"");
    expect(spawnSync("test", ["-e", path.join(homeDir, ".claude/skills/maintain-datalox-agent-replay")]).status).not.toBe(0);
    expect(spawnSync("test", ["-e", path.join(homeDir, ".codex/skills/datalox-agent-replay")]).status).not.toBe(0);
  }, 15000);

  it("does not expose removed legacy or derivative write commands in help", () => {
    const result = spawnSync("node", [path.join(repoRoot, "bin/datalox.js"), "--help"], {
      cwd: repoRoot,
      encoding: "utf8",
    });

    expect(result.status).toBe(0);
    expect(result.stdout).not.toContain("record-trajectory");
    expect(result.stdout).not.toContain("export-trajectories");
    expect(result.stdout).not.toContain("grade-trajectories");
    expect(result.stdout).not.toContain("repair-trajectory");
    expect(result.stdout).not.toContain(" datalox record ");
    expect(result.stdout).not.toContain(" datalox promote ");
    expect(result.stdout).not.toContain(" datalox maintain ");
  }, 30000);
});
