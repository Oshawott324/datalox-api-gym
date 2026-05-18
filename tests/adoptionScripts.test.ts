import { chmod, mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

const repoRoot = process.cwd();
const legacyWikiDir = ["agent", "wiki"].join("-");

describe("product adoption scripts", () => {
  const tempDirs: string[] = [];

  afterEach(async () => {
    await Promise.all(tempDirs.splice(0).map((dir) => rm(dir, { recursive: true, force: true })));
  });

  it("adopts product surfaces without creating the removed wiki store", async () => {
    const hostDir = await mkdtemp(path.join(tmpdir(), "datalox-host-adopt-"));
    tempDirs.push(hostDir);

    const result = spawnSync("bash", [path.join(repoRoot, "bin/adopt-host-repo.sh"), hostDir], {
      cwd: repoRoot,
      encoding: "utf8",
    });

    expect(result.status).toBe(0);
    expect(await readFile(path.join(hostDir, "DATALOX.md"), "utf8")).toContain("source kinds: `trace`, `web`, `pdf`");
    expect(await readFile(path.join(hostDir, "AGENTS.md"), "utf8")).toContain(".datalox/manifest.json");
    expect(await readFile(path.join(hostDir, ".datalox/install.json"), "utf8")).toContain("\"installMode\": \"manual\"");
    expect(await readFile(path.join(hostDir, "bin/datalox.js"), "utf8")).toContain("Unable to resolve Datalox Agent Replay runtime root for datalox.js");
    expect(await readFile(path.join(hostDir, "bin/datalox-mcp.js"), "utf8")).toContain("replayServer.js");
    expect(await readFile(path.join(hostDir, "bin/datalox-agent-replay-mcp.js"), "utf8")).toContain("replayServer.js");
    expect(spawnSync("test", ["-e", path.join(hostDir, legacyWikiDir)]).status).not.toBe(0);
    expect(spawnSync("test", ["-e", path.join(hostDir, "skills")]).status).not.toBe(0);
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
