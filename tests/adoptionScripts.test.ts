import { chmod, cp, mkdir, mkdtemp, readFile, readdir, readlink, realpath, rm, symlink, writeFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

const repoRoot = process.cwd();

async function copyPackSnapshot(sourceRoot: string, destinationRoot: string): Promise<void> {
  const entries = await readdir(sourceRoot);
  for (const entry of entries) {
    if (entry === ".git" || entry === "node_modules" || entry === "dist") {
      continue;
    }
    await cp(path.join(sourceRoot, entry), path.join(destinationRoot, entry), {
      recursive: true,
      filter: (sourcePath) => {
        const relativePath = path.relative(sourceRoot, sourcePath);
        const segments = relativePath.split(path.sep);
        return !segments.includes(".git") && !segments.includes("node_modules") && !segments.includes("dist");
      },
    });
  }
}

function parseLastJsonObject(stdout: string): any {
  const trimmed = stdout.trim();
  const objectStart = trimmed.lastIndexOf("\n{");
  return JSON.parse(objectStart >= 0 ? trimmed.slice(objectStart + 1) : trimmed.slice(trimmed.indexOf("{")));
}

describe("adoption scripts", () => {
  const tempDirs: string[] = [];

  afterEach(async () => {
    await Promise.all(tempDirs.splice(0).map((dir) => rm(dir, { recursive: true, force: true })));
  });

  it("adopts the pack into a host repo with one command", async () => {
    const hostDir = await mkdtemp(path.join(tmpdir(), "datalox-host-adopt-"));
    tempDirs.push(hostDir);

    const result = spawnSync("bash", [path.join(repoRoot, "bin/adopt-host-repo.sh"), hostDir], {
      cwd: repoRoot,
      encoding: "utf8",
    });

    expect(result.status).toBe(0);
    expect(await readFile(path.join(hostDir, "DATALOX.md"), "utf8")).toContain("source kinds: `trace`, `web`, `pdf`");
    expect(await readFile(path.join(hostDir, "WIKI.md"), "utf8")).toContain("agent-wiki/notes/");
    expect(await readFile(path.join(hostDir, ".claude/settings.json"), "utf8")).toContain("\"Stop\"");
    expect(await readFile(path.join(hostDir, ".claude/hooks/auto-promote.sh"), "utf8")).toContain("datalox-auto-promote.js");
    expect(await readFile(path.join(hostDir, "bin/datalox-auto-promote.js"), "utf8")).toContain("compileRecordedEvent");
    expect(await readFile(path.join(hostDir, "bin/claude-global-auto-promote.sh"), "utf8")).toContain("datalox-auto-promote.js");
    expect(await readFile(path.join(hostDir, "bin/datalox-claude.js"), "utf8")).toContain("\"claude\"");
    expect(await readFile(path.join(hostDir, "bin/datalox-codex.js"), "utf8")).toContain("\"codex\"");
    expect(await readFile(path.join(hostDir, "bin/datalox.js"), "utf8")).toContain("Unable to resolve Datalox Trajectory MCP runtime root for datalox.js");
    expect(await readFile(path.join(hostDir, "bin/datalox-wrap.js"), "utf8")).toContain("\"wrap\"");
    expect(await readFile(path.join(hostDir, "bin/disable-default-host-integrations.sh"), "utf8")).toContain("CLI-first disable flow");
    expect(await readFile(path.join(hostDir, "bin/install-default-host-integrations.sh"), "utf8")).toContain("Compatibility shim for the CLI-first install flow.");
    expect(await readFile(path.join(hostDir, "bin/setup-multi-agent.sh"), "utf8")).toContain("Datalox Trajectory MCP multi-agent setup");
    expect(await readFile(path.join(hostDir, ".github/copilot-instructions.md"), "utf8")).toContain("repo-local implementation package for Datalox MCP");
    expect(await readFile(path.join(hostDir, "skills/maintain-datalox-pack/SKILL.md"), "utf8")).toContain("Maintain Datalox Pack");
    expect(await readFile(path.join(hostDir, "skills/use-datalox-through-host-cli/SKILL.md"), "utf8")).toContain("Use Datalox Through Host CLI");
    expect(await readFile(path.join(hostDir, "agent-wiki/note.schema.md"), "utf8")).toContain("Action");
    expect(await readFile(path.join(hostDir, "agent-wiki/notes/use-datalox-through-host-cli.md"), "utf8")).toContain("thin wrapper");
    expect(await readFile(path.join(hostDir, ".datalox/install.json"), "utf8")).toContain("\"installMode\": \"manual\"");
    expect(spawnSync("test", ["-e", path.join(hostDir, "skills/github")]).status).not.toBe(0);
    expect(spawnSync("test", ["-e", path.join(hostDir, "skills/ordercli")]).status).not.toBe(0);
    expect(spawnSync("test", ["-e", path.join(hostDir, "skills/review-ambiguous-viability-gate")]).status).not.toBe(0);
    expect(spawnSync("test", ["-e", path.join(hostDir, "skills/capture-web-knowledge")]).status).not.toBe(0);
    expect(spawnSync("test", ["-e", path.join(hostDir, "agent-wiki/notes/pdf")]).status).not.toBe(0);
    expect(spawnSync("test", ["-e", path.join(hostDir, "agent-wiki/notes/web")]).status).not.toBe(0);
  }, 30000);

  it("lets an agent run host-local install-default-host-integrations.sh from an adopted repo", async () => {
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
    expect(await readFile(path.join(homeDir, ".local/bin/codex"), "utf8")).toContain("DATALOX_DEFAULT_POST_RUN_MODE:=review");
    expect(await readFile(path.join(homeDir, ".local/bin/codex"), "utf8")).toContain("DATALOX_DEFAULT_REVIEW_MODEL:=gpt-5.4-mini");
    expect(await readFile(path.join(homeDir, ".local/bin/claude"), "utf8")).toContain("DATALOX_DEFAULT_POST_RUN_MODE:=review");
    expect(await readFile(path.join(homeDir, ".local/bin/claude"), "utf8")).toContain("DATALOX_DEFAULT_REVIEW_MODEL:=gpt-5.4-mini");
    expect(await readFile(path.join(homeDir, ".claude/hooks/datalox-auto-promote.sh"), "utf8")).toContain("datalox-auto-promote.js");
    expect(await readlink(path.join(homeDir, ".claude/skills/maintain-datalox-pack"))).toBe(path.join(repoRoot, "skills/maintain-datalox-pack"));
    expect(await readFile(path.join(homeDir, ".claude/skills/maintain-datalox-pack/SKILL.md"), "utf8")).toContain("Maintain Datalox Pack");
    expect(spawnSync("test", ["-e", path.join(homeDir, ".claude/skills/datalox-pack")]).status).not.toBe(0);
    expect(await readlink(path.join(homeDir, ".datalox/cache/datalox-trajectory-mcp"))).toBe(repoRoot);
  }, 15000);

  it("lets an agent stop host integrations from an adopted repo", async () => {
    const hostDir = await mkdtemp(path.join(tmpdir(), "datalox-host-self-disable-"));
    const homeDir = await mkdtemp(path.join(tmpdir(), "datalox-disable-home-"));
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

    const disable = spawnSync("bash", [path.join(hostDir, "bin/disable-default-host-integrations.sh")], {
      cwd: hostDir,
      encoding: "utf8",
      env: {
        ...process.env,
        HOME: homeDir,
      },
    });

    expect(disable.status).toBe(0);
    expect(spawnSync("test", ["-e", path.join(homeDir, ".local/bin/codex")]).status).not.toBe(0);
    expect(spawnSync("test", ["-e", path.join(homeDir, ".local/bin/claude")]).status).not.toBe(0);
    expect(spawnSync("test", ["-e", path.join(homeDir, ".claude/hooks/datalox-auto-promote.sh")]).status).not.toBe(0);
    expect(spawnSync("test", ["-e", path.join(homeDir, ".claude/skills/maintain-datalox-pack")]).status).not.toBe(0);
    expect(spawnSync("test", ["-e", path.join(homeDir, ".codex/skills/datalox-trajectory-mcp")]).status).not.toBe(0);
    expect(await readFile(path.join(homeDir, ".claude/settings.json"), "utf8")).not.toContain("datalox-auto-promote.sh");
  }, 20000);

  it("runs setup-multi-agent.sh from a fresh pack copy without requiring exec permissions on nested scripts", async () => {
    const packDir = await mkdtemp(path.join(tmpdir(), "datalox-pack-copy-"));
    const homeDir = await mkdtemp(path.join(tmpdir(), "datalox-setup-home-"));
    tempDirs.push(packDir, homeDir);

    await copyPackSnapshot(repoRoot, packDir);

    const fakeCodex = path.join(homeDir, "fake-codex");
    const fakeClaude = path.join(homeDir, "fake-claude");
    await writeFile(fakeCodex, "#!/usr/bin/env bash\nexit 0\n", "utf8");
    await writeFile(fakeClaude, "#!/usr/bin/env bash\nexit 0\n", "utf8");
    await chmod(fakeCodex, 0o755);
    await chmod(fakeClaude, 0o755);

    const setup = spawnSync("bash", [path.join(packDir, "bin/setup-multi-agent.sh")], {
      cwd: packDir,
      encoding: "utf8",
      env: {
        ...process.env,
        HOME: homeDir,
        DATALOX_REAL_CODEX_BIN: fakeCodex,
        DATALOX_REAL_CLAUDE_BIN: fakeClaude,
      },
    });

    expect(setup.status).toBe(0);
    const resolvedPackDir = await realpath(packDir);
    expect(await readFile(path.join(homeDir, ".local/bin/codex"), "utf8")).toContain(`PACK_ROOT="${resolvedPackDir}"`);
    expect(await readFile(path.join(homeDir, ".local/bin/claude"), "utf8")).toContain(`PACK_ROOT="${resolvedPackDir}"`);
    expect(await readlink(path.join(homeDir, ".codex/skills/datalox-trajectory-mcp"))).toBe(path.join(resolvedPackDir, "skills"));
    expect(await readlink(path.join(homeDir, ".claude/skills/maintain-datalox-pack"))).toBe(path.join(resolvedPackDir, "skills/maintain-datalox-pack"));
    expect(spawnSync("test", ["-e", path.join(homeDir, ".claude/skills/datalox-pack")]).status).not.toBe(0);
    expect(await readFile(path.join(homeDir, ".claude/hooks/datalox-auto-promote.sh"), "utf8")).toContain("datalox-auto-promote.js");
  }, 60000);

  it("installs Claude native skills at canonical paths and safely cleans managed links", async () => {
    const packDir = await mkdtemp(path.join(tmpdir(), "datalox-claude-skills-pack-"));
    const homeDir = await mkdtemp(path.join(tmpdir(), "datalox-claude-skills-home-"));
    tempDirs.push(packDir, homeDir);

    await copyPackSnapshot(repoRoot, packDir);

    const fakeClaude = path.join(homeDir, "fake-claude");
    await writeFile(fakeClaude, "#!/usr/bin/env bash\nexit 0\n", "utf8");
    await chmod(fakeClaude, 0o755);

    const userSkillDir = path.join(homeDir, ".claude", "skills", "user-owned-skill");
    await mkdir(userSkillDir, { recursive: true });
    await writeFile(path.join(userSkillDir, "SKILL.md"), "# User-owned skill\n", "utf8");

    await symlink(path.join(packDir, "skills"), path.join(homeDir, ".claude", "skills", "datalox-pack"), "dir");

    const install = spawnSync("node", [path.join(packDir, "bin/datalox.js"), "install", "claude", "--json"], {
      cwd: packDir,
      encoding: "utf8",
      env: {
        ...process.env,
        HOME: homeDir,
        DATALOX_REAL_CLAUDE_BIN: fakeClaude,
      },
    });
    expect(install.status).toBe(0);
    const installed = parseLastJsonObject(install.stdout);
    expect(installed.status.adapters.claude.nativeSkillLinks.canonical).toBe(true);
    expect(installed.status.adapters.claude.nativeSkillLinks.linked).toContain(path.join(homeDir, ".claude/skills/maintain-datalox-pack"));
    expect(installed.status.adapters.claude.nativeSkillLinks.missing).toEqual([]);

    const resolvedPackDir = await realpath(packDir);
    expect(await readlink(path.join(homeDir, ".claude/skills/maintain-datalox-pack"))).toBe(path.join(resolvedPackDir, "skills/maintain-datalox-pack"));
    expect(await readFile(path.join(homeDir, ".claude/skills/maintain-datalox-pack/SKILL.md"), "utf8")).toContain("Maintain Datalox Pack");
    expect(spawnSync("test", ["-e", path.join(homeDir, ".claude/skills/datalox-pack")]).status).not.toBe(0);
    expect(await readFile(path.join(userSkillDir, "SKILL.md"), "utf8")).toContain("User-owned skill");

    const status = spawnSync("node", [path.join(packDir, "bin/datalox.js"), "status", "--repo", packDir, "--json"], {
      cwd: packDir,
      encoding: "utf8",
      env: {
        ...process.env,
        HOME: homeDir,
      },
    });
    expect(status.status).toBe(0);
    const parsedStatus = JSON.parse(status.stdout);
    expect(parsedStatus.adapters.claude.nativeSkillLinks.installed).toBe(true);
    expect(parsedStatus.adapters.claude.nativeSkillLinks.canonical).toBe(true);
    expect(parsedStatus.adapters.claude.hookInstalled).toBe(true);

    await symlink(path.join(packDir, "skills"), path.join(homeDir, ".claude", "skills", "datalox-pack"), "dir");

    const disable = spawnSync("node", [path.join(packDir, "bin/datalox.js"), "disable", "claude", "--json"], {
      cwd: packDir,
      encoding: "utf8",
      env: {
        ...process.env,
        HOME: homeDir,
      },
    });
    expect(disable.status).toBe(0);
    expect(spawnSync("test", ["-e", path.join(homeDir, ".claude/skills/maintain-datalox-pack")]).status).not.toBe(0);
    expect(spawnSync("test", ["-e", path.join(homeDir, ".claude/skills/datalox-pack")]).status).not.toBe(0);
    expect(await readFile(path.join(userSkillDir, "SKILL.md"), "utf8")).toContain("User-owned skill");
  }, 60000);

  it("reports Claude wrapper, hook, native skill, and MCP surfaces separately", async () => {
    const packDir = await mkdtemp(path.join(tmpdir(), "datalox-claude-surfaces-pack-"));
    const homeDir = await mkdtemp(path.join(tmpdir(), "datalox-claude-surfaces-home-"));
    const whichDir = await mkdtemp(path.join(tmpdir(), "datalox-no-claude-which-"));
    tempDirs.push(packDir, homeDir, whichDir);

    await copyPackSnapshot(repoRoot, packDir);
    const fakeWhich = path.join(whichDir, "which");
    await writeFile(fakeWhich, "#!/usr/bin/env bash\nexit 1\n", "utf8");
    await chmod(fakeWhich, 0o755);

    const install = spawnSync(process.execPath, [path.join(packDir, "bin/datalox.js"), "install", "claude", "--json"], {
      cwd: packDir,
      encoding: "utf8",
      env: {
        ...process.env,
        HOME: homeDir,
        PATH: `${whichDir}:${process.env.PATH ?? ""}`,
        DATALOX_ACTIVE_WRAPPER: "",
        DATALOX_HOST_KIND: "",
        DATALOX_ENFORCEMENT: "",
      },
    });

    expect(install.status).toBe(0);
    const parsed = parseLastJsonObject(install.stdout);
    const claude = parsed.status.adapters.claude;

    expect(claude.installed).toBe(false);
    expect(claude.automatic).toBe(false);
    expect(claude.hookInstalled).toBe(true);
    expect(claude.nativeSkillLinks.canonical).toBe(true);
    expect(claude.notes).toContain(
      "Claude Stop hook is installed, but it runs after the model turn and cannot prove pre-turn skill use.",
    );

    expect(claude.surfaces.wrapper.installed).toBe(false);
    expect(claude.surfaces.wrapper.automatic).toBe(false);
    expect(claude.surfaces.wrapper.active).toBe(false);
    expect(claude.surfaces.wrapper.preRunEnforced).toBe(false);
    expect(claude.surfaces.wrapper.notes).toContain(
      "Claude Stop hook is installed, but it cannot enforce pre-run guidance injection.",
    );

    expect(claude.surfaces.stopHook.installed).toBe(true);
    expect(claude.surfaces.stopHook.postTurnSidecar).toBe(true);
    expect(claude.surfaces.stopHook.recordsAfterTurn).toBe(true);
    expect(claude.surfaces.stopHook.preRunEnforced).toBe(false);
    expect(claude.surfaces.stopHook.notes).toContain(
      "The Stop hook is post-turn sidecar automation, not pre-run enforcement.",
    );

    expect(claude.surfaces.nativeSkills.installed).toBe(true);
    expect(claude.surfaces.nativeSkills.canonical).toBe(true);
    expect(claude.surfaces.nativeSkills.modelChosen).toBe(true);
    expect(claude.surfaces.nativeSkills.restartSensitive).toBe(true);
    expect(claude.surfaces.nativeSkills.preRunEnforced).toBe(false);

    expect(claude.surfaces.mcp.available).toBe(true);
    expect(claude.surfaces.mcp.guidanceOnly).toBe(true);
    expect(claude.surfaces.mcp.modelChosen).toBe(true);
    expect(claude.surfaces.mcp.preRunEnforced).toBe(false);

    const wrappedStatus = spawnSync(process.execPath, [path.join(packDir, "bin/datalox.js"), "status", "--repo", packDir, "--json"], {
      cwd: packDir,
      encoding: "utf8",
      env: {
        ...process.env,
        HOME: homeDir,
        PATH: `${whichDir}:${process.env.PATH ?? ""}`,
        DATALOX_ACTIVE_WRAPPER: "claude",
        DATALOX_HOST_KIND: "claude",
        DATALOX_ENFORCEMENT: "wrapper",
        DATALOX_SESSION_ID: "wrapped-claude-session",
      },
    });

    expect(wrappedStatus.status).toBe(0);
    const parsedWrappedStatus = JSON.parse(wrappedStatus.stdout);
    expect(parsedWrappedStatus.currentSession.detectedHostKind).toBe("claude");
    expect(parsedWrappedStatus.currentSession.activeWrapper).toBe("claude");
    expect(parsedWrappedStatus.currentSession.wrapperEnforced).toBe(true);
    expect(parsedWrappedStatus.currentSession.enforcementLevel).toBe("enforced");
    expect(parsedWrappedStatus.currentSession.sessionId).toBe("wrapped-claude-session");
    expect(parsedWrappedStatus.adapters.claude.surfaces.wrapper.active).toBe(true);
    expect(parsedWrappedStatus.adapters.claude.surfaces.wrapper.preRunEnforced).toBe(true);
    expect(parsedWrappedStatus.adapters.claude.surfaces.stopHook.preRunEnforced).toBe(false);
  }, 60000);

  it("runs the CLI-first setup flow from a fresh pack copy and bootstraps the current repo", async () => {
    const packDir = await mkdtemp(path.join(tmpdir(), "datalox-pack-cli-copy-"));
    const homeDir = await mkdtemp(path.join(tmpdir(), "datalox-cli-home-"));
    const hostDir = await mkdtemp(path.join(tmpdir(), "datalox-cli-host-"));
    tempDirs.push(packDir, homeDir, hostDir);

    await copyPackSnapshot(repoRoot, packDir);

    const init = spawnSync("git", ["init"], {
      cwd: hostDir,
      encoding: "utf8",
    });
    expect(init.status).toBe(0);

    const fakeCodex = path.join(homeDir, "fake-codex");
    await writeFile(fakeCodex, "#!/usr/bin/env bash\nexit 0\n", "utf8");
    await chmod(fakeCodex, 0o755);

    const setup = spawnSync("node", [path.join(packDir, "bin/datalox.js"), "setup", "codex"], {
      cwd: hostDir,
      encoding: "utf8",
      env: {
        ...process.env,
        HOME: homeDir,
        DATALOX_REAL_CODEX_BIN: fakeCodex,
      },
    });

    expect(setup.status).toBe(0);
    const resolvedPackDir = await realpath(packDir);
    expect(await readFile(path.join(homeDir, ".local/bin/codex"), "utf8")).toContain(`PACK_ROOT="${resolvedPackDir}"`);
    expect(await readFile(path.join(hostDir, "DATALOX.md"), "utf8")).toContain("source kinds: `trace`, `web`, `pdf`");
    expect(await readFile(path.join(hostDir, ".datalox/install.json"), "utf8")).toContain("\"installMode\": \"auto\"");
    expect(spawnSync("test", ["-e", path.join(hostDir, "skills/github")]).status).not.toBe(0);
    expect(spawnSync("test", ["-e", path.join(hostDir, "skills/ordercli")]).status).not.toBe(0);
    expect(spawnSync("test", ["-e", path.join(hostDir, "skills/review-ambiguous-viability-gate")]).status).not.toBe(0);
    expect(spawnSync("test", ["-e", path.join(hostDir, "agent-wiki/notes/pdf")]).status).not.toBe(0);
    expect(spawnSync("test", ["-e", path.join(hostDir, "agent-wiki/notes/web")]).status).not.toBe(0);
  }, 60000);

  it("keeps partial Datalox paths blocked for auto-bootstrap but gives explicit recovery", async () => {
    const hostDir = await mkdtemp(path.join(tmpdir(), "datalox-partial-recovery-"));
    tempDirs.push(hostDir);

    const init = spawnSync("git", ["init"], {
      cwd: hostDir,
      encoding: "utf8",
    });
    expect(init.status).toBe(0);
    await mkdir(path.join(hostDir, "agent-wiki"), { recursive: true });
    await writeFile(path.join(hostDir, "agent-wiki", "hot.md"), "# partial\n", "utf8");

    const probe = spawnSync("node", [path.join(repoRoot, "bin/datalox.js"), "probe-bootstrap", "--repo", hostDir, "--json"], {
      cwd: repoRoot,
      encoding: "utf8",
    });
    expect(probe.status).toBe(0);
    const parsedProbe = JSON.parse(probe.stdout);
    expect(parsedProbe.status).toBe("blocked");
    expect(parsedProbe.canAutoBootstrap).toBe(false);
    expect(parsedProbe.detected.hasAgentWiki).toBe(true);
    expect(parsedProbe.detected.hasInstallStamp).toBe(false);
    expect(parsedProbe.recommendedAction).toBe("explicit_adopt_from_source_pack");
    expect(parsedProbe.recoveryCommands).toEqual([
      `TARGET_REPO=${JSON.stringify(hostDir)}`,
      "git clone https://github.com/Complexity-LLC/datalox-trajectory-mcp.git",
      "cd datalox-trajectory-mcp",
      "bash bin/adopt-host-repo.sh \"$TARGET_REPO\"",
    ]);

    const autoBootstrap = spawnSync("node", [path.join(repoRoot, "bin/datalox.js"), "auto-bootstrap", "--repo", hostDir, "--json"], {
      cwd: repoRoot,
      encoding: "utf8",
    });
    expect(autoBootstrap.status).toBe(0);
    const parsedAutoBootstrap = JSON.parse(autoBootstrap.stdout);
    expect(parsedAutoBootstrap.action).toBe("none");
    expect(parsedAutoBootstrap.probeBefore.status).toBe("blocked");
    expect(spawnSync("test", ["-f", path.join(hostDir, ".datalox", "install.json")]).status).not.toBe(0);

    const adopt = spawnSync("bash", [path.join(repoRoot, "bin/adopt-host-repo.sh"), hostDir], {
      cwd: repoRoot,
      encoding: "utf8",
    });
    expect(adopt.status).toBe(0);
    expect(await readFile(path.join(hostDir, ".datalox", "install.json"), "utf8")).toContain("\"installMode\": \"manual\"");

    const repairedProbe = spawnSync("node", [path.join(repoRoot, "bin/datalox.js"), "probe-bootstrap", "--repo", hostDir, "--json"], {
      cwd: repoRoot,
      encoding: "utf8",
    });
    expect(repairedProbe.status).toBe(0);
    const parsedRepairedProbe = JSON.parse(repairedProbe.stdout);
    expect(parsedRepairedProbe.status).toBe("ready");
    expect(parsedRepairedProbe.detected.hasInstallStamp).toBe(true);
  }, 60000);

  it("reports enforced host adapters as automatic in status output", async () => {
    const packDir = await mkdtemp(path.join(tmpdir(), "datalox-pack-status-copy-"));
    const homeDir = await mkdtemp(path.join(tmpdir(), "datalox-status-home-"));
    const hostDir = await mkdtemp(path.join(tmpdir(), "datalox-status-host-"));
    tempDirs.push(packDir, homeDir, hostDir);

    await copyPackSnapshot(repoRoot, packDir);

    const init = spawnSync("git", ["init"], {
      cwd: hostDir,
      encoding: "utf8",
    });
    expect(init.status).toBe(0);

    const fakeCodex = path.join(homeDir, "fake-codex");
    await writeFile(fakeCodex, "#!/usr/bin/env bash\nexit 0\n", "utf8");
    await chmod(fakeCodex, 0o755);

    const install = spawnSync("node", [path.join(packDir, "bin/datalox.js"), "install", "codex", "--json"], {
      cwd: packDir,
      encoding: "utf8",
      env: {
        ...process.env,
        HOME: homeDir,
        DATALOX_REAL_CODEX_BIN: fakeCodex,
      },
    });
    expect(install.status).toBe(0);

    const status = spawnSync("node", [path.join(packDir, "bin/datalox.js"), "status", "--repo", hostDir, "--json"], {
      cwd: hostDir,
      encoding: "utf8",
      env: {
        ...process.env,
        HOME: homeDir,
        DATALOX_ACTIVE_WRAPPER: "",
        DATALOX_HOST_KIND: "",
        DATALOX_ENFORCEMENT: "",
        CODEX_THREAD_ID: "test-native-codex-thread",
        CODEX_INTERNAL_ORIGINATOR_OVERRIDE: "codex_vscode",
      },
    });

    expect(status.status).toBe(0);
    const parsed = JSON.parse(status.stdout);
    expect(parsed.adapters.codex.enforcementLevel).toBe("enforced");
    expect(parsed.adapters.codex.installed).toBe(true);
    expect(parsed.adapters.codex.automatic).toBe(true);
    expect(parsed.adapters.claude.enforcementLevel).toBe("enforced");
    expect(parsed.adapters.generic_cli.enforcementLevel).toBe("conditional");
    expect(parsed.adapters.mcp_only.enforcementLevel).toBe("guidance_only");
    expect(parsed.repo.bootstrapStatus).toBe("bootstrappable");
    expect(parsed.repo.enforcementLevel).toBe("enforced");
    expect(parsed.currentSession.detectedHostKind).toBe("codex");
    expect(parsed.currentSession.activeWrapper).toBeNull();
    expect(parsed.currentSession.wrapperEnforced).toBe(false);
    expect(parsed.currentSession.enforcementLevel).toBe("guidance_only");
    expect(parsed.currentSession.codexThreadId).toBe("test-native-codex-thread");
    expect(parsed.currentSession.notes).toContain(
      "Native Codex session detected without a Datalox wrapper sentinel; MCP use depends on explicit tool calls.",
    );

    const wrappedStatus = spawnSync("node", [path.join(packDir, "bin/datalox.js"), "status", "--repo", hostDir, "--json"], {
      cwd: hostDir,
      encoding: "utf8",
      env: {
        ...process.env,
        HOME: homeDir,
        DATALOX_ACTIVE_WRAPPER: "codex",
        DATALOX_HOST_KIND: "codex",
        DATALOX_ENFORCEMENT: "wrapper",
        DATALOX_SESSION_ID: "wrapped-codex-session",
      },
    });
    expect(wrappedStatus.status).toBe(0);
    const parsedWrappedStatus = JSON.parse(wrappedStatus.stdout);
    expect(parsedWrappedStatus.currentSession.detectedHostKind).toBe("codex");
    expect(parsedWrappedStatus.currentSession.activeWrapper).toBe("codex");
    expect(parsedWrappedStatus.currentSession.wrapperEnforced).toBe(true);
    expect(parsedWrappedStatus.currentSession.enforcementLevel).toBe("enforced");
    expect(parsedWrappedStatus.currentSession.sessionId).toBe("wrapped-codex-session");
    expect(parsedWrappedStatus.currentSession.notes).toContain(
      "Current process is inside the Datalox codex wrapper.",
    );

    const installJson = JSON.parse(await readFile(path.join(packDir, ".datalox", "install.json"), "utf8"));
    expect(installJson.packRootPath).toBe(await realpath(packDir));
    expect(installJson.enforcement.adapters.codex.automatic).toBe(true);
  }, 60000);

  it("keeps the codex shim working after the original real binary path changes", async () => {
    const packDir = await mkdtemp(path.join(tmpdir(), "datalox-pack-shim-refresh-"));
    const homeDir = await mkdtemp(path.join(tmpdir(), "datalox-shim-home-"));
    const fallbackDir = await mkdtemp(path.join(tmpdir(), "datalox-shim-fallback-"));
    tempDirs.push(packDir, homeDir, fallbackDir);

    await copyPackSnapshot(repoRoot, packDir);

    const originalCodex = path.join(homeDir, "fake-codex-original");
    const fallbackCodex = path.join(fallbackDir, "codex");
    await writeFile(originalCodex, "#!/usr/bin/env bash\necho original-codex\n", "utf8");
    await writeFile(fallbackCodex, "#!/usr/bin/env bash\necho fallback-codex\n", "utf8");
    await chmod(originalCodex, 0o755);
    await chmod(fallbackCodex, 0o755);

    const install = spawnSync("node", [path.join(packDir, "bin/datalox.js"), "install", "codex", "--json"], {
      cwd: packDir,
      encoding: "utf8",
      env: {
        ...process.env,
        HOME: homeDir,
        PATH: `${fallbackDir}:${process.env.PATH ?? ""}`,
        DATALOX_REAL_CODEX_BIN: originalCodex,
      },
    });
    expect(install.status).toBe(0);

    await rm(originalCodex, { force: true });

    const shimPath = path.join(homeDir, ".local", "bin", "codex");
    const version = spawnSync(shimPath, ["--version"], {
      cwd: packDir,
      encoding: "utf8",
      env: {
        ...process.env,
        HOME: homeDir,
        PATH: `${path.join(homeDir, ".local", "bin")}:${fallbackDir}:${process.env.PATH ?? ""}`,
      },
    });

    expect(version.status).toBe(0);
    expect(version.stdout.trim()).toBe("fallback-codex");
  }, 60000);
});
