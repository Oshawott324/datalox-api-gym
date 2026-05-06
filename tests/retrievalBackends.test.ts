import { chmod, mkdir, mkdtemp, readFile, readdir, rm, writeFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { tmpdir } from "node:os";
import path from "node:path";
import process from "node:process";

import { afterEach, describe, expect, it } from "vitest";

import { resolveLoop, syncNoteRetrieval } from "../src/core/packCore.js";

const repoRoot = process.cwd();
const builtCliPath = path.join(repoRoot, "dist", "src", "cli", "main.js");

function buildConfig(notesBackend: "native" | "qmd") {
  return {
    version: 1,
    mode: "repo_only",
    project: {
      id: "demo",
      name: "Demo",
    },
    sources: [
      {
        kind: "local_repo",
        name: "repo-pack",
        enabled: true,
        root: ".datalox",
      },
    ],
    agent: {
      profile: "local_first",
      nativeSkillPolicy: "preserve",
      detectOnEveryLoop: true,
      configReadOrder: [
        "env:DATALOX_CONFIG_JSON",
        ".datalox/config.local.json",
        ".datalox/config.json",
        "AGENTS.md",
      ],
      interfaceOrder: [
        "skill_loop",
        "runtime_compile",
      ],
    },
    paths: {
      seedSkillsDir: "skills",
      seedNotesDir: "agent-wiki/notes",
      hostSkillsDir: "skills",
      hostNotesDir: "agent-wiki/notes",
    },
    retrieval: {
      notesBackend,
    },
    runtime: {
      enabled: false,
      baseUrl: "http://localhost:3000",
      defaultWorkflow: "flow_cytometry",
      requestTimeoutMs: 10000,
      endpoints: {
        compile: "/v1/runtime/compile",
      },
    },
    auth: {
      apiKeyEnv: "DATALOX_API_KEY",
      contributorKeyEnv: "DATALOX_CONTRIBUTOR_KEY",
    },
  };
}

async function createPack(tempDir: string, notesBackend: "native" | "qmd" = "native") {
  await mkdir(path.join(tempDir, ".datalox"), { recursive: true });
  await mkdir(path.join(tempDir, "skills", "review-ambiguous-viability-gate"), { recursive: true });
  await mkdir(path.join(tempDir, "agent-wiki", "notes"), { recursive: true });
  await mkdir(path.join(tempDir, "agent-wiki", "events"), { recursive: true });

  await writeFile(
    path.join(tempDir, ".datalox", "config.json"),
    `${JSON.stringify(buildConfig(notesBackend), null, 2)}\n`,
    "utf8",
  );
  await writeFile(
    path.join(tempDir, ".datalox", "manifest.json"),
    `${JSON.stringify({ version: 1, adopted: true }, null, 2)}\n`,
    "utf8",
  );
  await writeFile(
    path.join(tempDir, ".datalox", "install.json"),
    `${JSON.stringify({
      version: 1,
      installedAt: "2026-04-15T00:00:00.000Z",
      installMode: "manual",
      packRootPath: tempDir,
    }, null, 2)}\n`,
    "utf8",
  );
  await writeFile(path.join(tempDir, "AGENTS.md"), "# Demo agent instructions\n", "utf8");
  await writeFile(path.join(tempDir, "CLAUDE.md"), "# Demo claude instructions\n", "utf8");
  await writeFile(path.join(tempDir, "DATALOX.md"), "# Datalox\n", "utf8");

  await writeFile(
    path.join(tempDir, "skills", "review-ambiguous-viability-gate", "SKILL.md"),
    `---
name: review-ambiguous-viability-gate
description: Use when live and dead populations are not cleanly separated during viability gate review.
metadata:
  datalox:
    id: flow-cytometry.review-ambiguous-viability-gate
    workflow: flow_cytometry
    trigger: Use when live/dead separation is ambiguous during viability gate review.
    note_paths:
      - agent-wiki/notes/viability-gate-review.md
    tags:
      - flow_cytometry
      - viability
      - review
---

# Review Ambiguous Viability Gate

## When to Use

Use when live/dead separation is ambiguous during viability gate review.

## Workflow

1. Read the linked note before changing the gate.
2. Treat this as a judgment step, not a mechanical threshold change.

## Notes

- agent-wiki/notes/viability-gate-review.md
`,
    "utf8",
  );

  await writeFile(
    path.join(tempDir, "agent-wiki", "notes", "viability-gate-review.md"),
    `---
title: Review ambiguous viability gate
workflow: flow_cytometry
skill: flow-cytometry.review-ambiguous-viability-gate
status: active
---

# Review ambiguous viability gate

## When to Use

Use this note when viability review is ambiguous and the live/dead split is not clearly separable.

## Signal

Live and dead populations are not cleanly separated during viability gate review.

## Interpretation

This is a judgment step, not a mechanical threshold change.

## Action

Check the exception and escalation note before widening the gate.

## Examples

- A boundary that looks unstable and needs exception review before widening the gate.

## Evidence

- agent-wiki/events/example.json
`,
    "utf8",
  );

  await writeFile(
    path.join(tempDir, "agent-wiki", "notes", "reversible-onboarding.md"),
    `---
title: Make onboarding visible and reversible
workflow: agent_adoption
status: active
---

# Make onboarding visible and reversible

## When to Use

Use this note when a new repo needs a visible and reversible onboarding path before the first managed run.

## Signal

New repos keep failing because the install surface is hidden or irreversible.

## Interpretation

This is a reusable onboarding gap, not a one-off setup complaint.

## Action

Make the onboarding path visible and reversible before asking the next agent to continue.

## Examples

- A repo where agents keep failing because there is no visible install entrypoint.

## Evidence

- agent-wiki/events/example.json
`,
    "utf8",
  );

  await writeFile(
    path.join(tempDir, "agent-wiki", "notes", "generic-onboarding.md"),
    `---
title: Generic onboarding fallback
workflow: agent_adoption
status: active
---

# Generic onboarding fallback

## When to Use

Use this note when onboarding needs a generic follow-up.

## Signal

Setup is incomplete.

## Interpretation

The repo may need more setup work.

## Action

Inspect the current setup and continue with the next safe step.

## Examples

- A repo where setup is only partially complete.
`,
    "utf8",
  );

  await writeFile(
    path.join(tempDir, "agent-wiki", "notes", "archived-onboarding.md"),
    `---
title: Make onboarding visible and reversible
workflow: agent_adoption
status: archived
---

# Make onboarding visible and reversible

## When to Use

Use this archived note when a new repo needs a visible and reversible onboarding path before the first managed run.

## Signal

New repos keep failing because the install surface is hidden or irreversible.

## Interpretation

This note should no longer be used.

## Action

Do not use this archived note.
`,
    "utf8",
  );
}

async function createFakeQmd(tempDir: string) {
  const statePath = path.join(tempDir, "qmd-state.json");
  const scriptPath = path.join(tempDir, "fake-qmd.mjs");
  await writeFile(
    scriptPath,
    `#!/usr/bin/env node
import { existsSync, readFileSync, writeFileSync } from "node:fs";

const statePath = process.env.DATALOX_QMD_STATE_FILE;
const args = process.argv.slice(2);
const state = statePath && existsSync(statePath)
  ? JSON.parse(readFileSync(statePath, "utf8"))
  : { collections: {}, calls: [] };

state.calls.push(args);

function save() {
  if (statePath) {
    writeFileSync(statePath, JSON.stringify(state, null, 2));
  }
}

if (args[0] === "collection" && args[1] === "list") {
  const names = Object.keys(state.collections);
  if (names.length === 0) {
    console.log("No collections found. Run 'qmd collection add .' to create one.");
  } else {
    console.log(\`Collections (\${names.length}):\\n\`);
    for (const name of names) {
      console.log(\`\${name} (qmd://\${name}/)\`);
      console.log(\`  Pattern: \${state.collections[name].mask}\`);
      console.log("");
    }
  }
  save();
  process.exit(0);
}

if (args[0] === "collection" && args[1] === "add") {
  const nameIndex = args.indexOf("--name");
  const maskIndex = args.indexOf("--mask");
  const name = nameIndex >= 0 ? args[nameIndex + 1] : "notes";
  const mask = maskIndex >= 0 ? args[maskIndex + 1] : "**/*.md";
  state.collections[name] = { path: args[2], mask };
  save();
  console.log(\`Collection '\${name}' created\`);
  process.exit(0);
}

if (args[0] === "collection" && args[1] === "remove") {
  delete state.collections[args[2]];
  save();
  console.log(\`Collection '\${args[2]}' removed\`);
  process.exit(0);
}

if (args[0] === "query") {
  const collectionIndex = args.indexOf("-c");
  const collection = collectionIndex >= 0 ? args[collectionIndex + 1] : "notes";
  const customResults = process.env.DATALOX_QMD_RESULTS_JSON;
  if (customResults) {
    save();
    console.log(customResults.replaceAll("__COLLECTION__", collection));
    process.exit(0);
  }
  const noteFile = process.env.DATALOX_QMD_NOTE_FILE || "reversible-onboarding.md";
  const noteTitle = process.env.DATALOX_QMD_NOTE_TITLE || "Retrieved note";
  save();
  console.log(JSON.stringify([
    {
      score: 0.91,
      file: \`qmd://\${collection}/\${noteFile}\`,
      title: noteTitle,
      snippet: "retrieved by fake qmd"
    }
  ], null, 2));
  process.exit(0);
}

save();
console.error(\`unsupported fake qmd command: \${args.join(" ")}\`);
process.exit(1);
`,
    "utf8",
  );
  await chmod(scriptPath, 0o755);
  return {
    scriptPath,
    statePath,
  };
}

async function readQmdState(statePath: string) {
  return JSON.parse(await readFile(statePath, "utf8"));
}

describe("retrieval backends", () => {
  const tempDirs: string[] = [];
  const originalQmdBin = process.env.DATALOX_QMD_BIN;
  const originalQmdStateFile = process.env.DATALOX_QMD_STATE_FILE;
  const originalQmdNoteFile = process.env.DATALOX_QMD_NOTE_FILE;
  const originalQmdNoteTitle = process.env.DATALOX_QMD_NOTE_TITLE;
  const originalQmdResultsJson = process.env.DATALOX_QMD_RESULTS_JSON;

  afterEach(async () => {
    if (originalQmdBin === undefined) {
      delete process.env.DATALOX_QMD_BIN;
    } else {
      process.env.DATALOX_QMD_BIN = originalQmdBin;
    }
    if (originalQmdStateFile === undefined) {
      delete process.env.DATALOX_QMD_STATE_FILE;
    } else {
      process.env.DATALOX_QMD_STATE_FILE = originalQmdStateFile;
    }
    if (originalQmdNoteFile === undefined) {
      delete process.env.DATALOX_QMD_NOTE_FILE;
    } else {
      process.env.DATALOX_QMD_NOTE_FILE = originalQmdNoteFile;
    }
    if (originalQmdNoteTitle === undefined) {
      delete process.env.DATALOX_QMD_NOTE_TITLE;
    } else {
      process.env.DATALOX_QMD_NOTE_TITLE = originalQmdNoteTitle;
    }
    if (originalQmdResultsJson === undefined) {
      delete process.env.DATALOX_QMD_RESULTS_JSON;
    } else {
      process.env.DATALOX_QMD_RESULTS_JSON = originalQmdResultsJson;
    }
    await Promise.all(tempDirs.splice(0).map((dir) => rm(dir, { recursive: true, force: true })));
  });

  it("syncs repo-scoped qmd note collections through the public CLI", async () => {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-qmd-sync-"));
    tempDirs.push(tempDir);
    const repoA = path.join(tempDir, "repo-a");
    const repoB = path.join(tempDir, "repo-b");
    await createPack(repoA, "qmd");
    await createPack(repoB, "qmd");

    const fakeQmd = await createFakeQmd(tempDir);
    const env = {
      ...process.env,
      DATALOX_QMD_BIN: fakeQmd.scriptPath,
      DATALOX_QMD_STATE_FILE: fakeQmd.statePath,
    };

    const syncA = spawnSync("node", [builtCliPath, "retrieval", "sync", "--repo", repoA, "--json"], {
      cwd: repoRoot,
      encoding: "utf8",
      env,
    });
    const syncB = spawnSync("node", [builtCliPath, "retrieval", "sync", "--repo", repoB, "--json"], {
      cwd: repoRoot,
      encoding: "utf8",
      env,
    });

    expect(syncA.status).toBe(0);
    expect(syncB.status).toBe(0);

    const resultA = JSON.parse(syncA.stdout);
    const resultB = JSON.parse(syncB.stdout);
    expect(resultA.backend).toBe("qmd");
    expect(resultA.synced).toBe(true);
    expect(resultA.collectionName).not.toBe(resultB.collectionName);
    expect(resultA.notesDir).toBe("agent-wiki/notes");

    const state = await readQmdState(fakeQmd.statePath);
    expect(Object.keys(state.collections)).toContain(resultA.collectionName);
    expect(Object.keys(state.collections)).toContain(resultB.collectionName);
  }, 25000);

  it("keeps skill-linked notes primary even when the qmd backend is selected", async () => {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-qmd-priority-"));
    tempDirs.push(tempDir);
    await createPack(tempDir, "qmd");
    const fakeQmd = await createFakeQmd(tempDir);

    process.env.DATALOX_QMD_BIN = fakeQmd.scriptPath;
    process.env.DATALOX_QMD_STATE_FILE = fakeQmd.statePath;

    const result = await resolveLoop({
      repoPath: tempDir,
      task: "review ambiguous live dead gate",
      workflow: "flow_cytometry",
    });

    expect(result.matches[0].skill.id).toBe("flow-cytometry.review-ambiguous-viability-gate");
    expect(result.matches[0].linkedNotes[0].path).toBe("agent-wiki/notes/viability-gate-review.md");

    const state = await readQmdState(fakeQmd.statePath).catch(() => ({ calls: [] }));
    expect(state.calls ?? []).toHaveLength(0);
  });

  it("retrieves direct notes through qmd json output when no skill matches", async () => {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-qmd-direct-"));
    tempDirs.push(tempDir);
    await createPack(tempDir, "qmd");
    const fakeQmd = await createFakeQmd(tempDir);

    process.env.DATALOX_QMD_BIN = fakeQmd.scriptPath;
    process.env.DATALOX_QMD_STATE_FILE = fakeQmd.statePath;
    process.env.DATALOX_QMD_NOTE_FILE = "reversible-onboarding.md";
    process.env.DATALOX_QMD_NOTE_TITLE = "Make onboarding visible and reversible";

    const result = await resolveLoop({
      repoPath: tempDir,
      task: "make onboarding visible and reversible for a new repo",
      workflow: "agent_adoption",
    });

    expect(result.directNoteBackend).toBe("qmd");
    expect(result.selectionBasis).toBe("direct_note_query");
    expect(result.matches).toHaveLength(0);
    expect(result.directNoteMatches[0].note.path).toBe("agent-wiki/notes/reversible-onboarding.md");
    expect(result.directNoteMatches[0].whyMatched).toContain("title_match");
    expect(result.directNoteMatches[0]).not.toHaveProperty("score");
    expect(result.directNoteMatches[0]).not.toHaveProperty("backendScore");
    expect(result.loopGuidance.whatToDoNow[0]).toContain("visible and reversible");
    expect(result.loopGuidance.watchFor[0]).toContain("install surface is hidden or irreversible");
  });

  it("keeps archived notes out of native direct-note retrieval", async () => {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-native-notes-"));
    tempDirs.push(tempDir);
    await createPack(tempDir, "native");

    const result = await resolveLoop({
      repoPath: tempDir,
      task: "make onboarding visible and reversible for a new repo",
      workflow: "agent_adoption",
    });

    expect(result.directNoteBackend).toBe("native");
    expect(result.directNoteMatches[0].note.path).toBe("agent-wiki/notes/reversible-onboarding.md");
    expect(result.directNoteMatches.some((entry: { note: { path: string } }) =>
      entry.note.path === "agent-wiki/notes/archived-onboarding.md")).toBe(false);
  });

  it("reranks qmd candidates with Datalox note structure instead of raw qmd order", async () => {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-qmd-rerank-"));
    tempDirs.push(tempDir);
    await createPack(tempDir, "qmd");
    const fakeQmd = await createFakeQmd(tempDir);

    process.env.DATALOX_QMD_BIN = fakeQmd.scriptPath;
    process.env.DATALOX_QMD_STATE_FILE = fakeQmd.statePath;
    process.env.DATALOX_QMD_RESULTS_JSON = JSON.stringify([
      {
        score: 0.99,
        file: "qmd://__COLLECTION__/generic-onboarding.md",
        title: "Generic onboarding fallback",
        snippet: "generic fallback",
      },
      {
        score: 0.41,
        file: "qmd://__COLLECTION__/reversible-onboarding.md",
        title: "Make onboarding visible and reversible",
        snippet: "specific onboarding guidance",
      },
    ], null, 2);

    const result = await resolveLoop({
      repoPath: tempDir,
      task: "make onboarding visible and reversible for a new repo",
      workflow: "agent_adoption",
    });

    expect(result.directNoteBackend).toBe("qmd");
    expect(result.directNoteMatches[0].note.path).toBe("agent-wiki/notes/reversible-onboarding.md");
    expect(result.directNoteMatches[0].whyMatched).toContain("title_match");
    expect(result.directNoteMatches[0]).not.toHaveProperty("score");
    expect(result.directNoteMatches[0]).not.toHaveProperty("backendScore");
  });

  it("does not let usage counters outrank a better-fitting note", async () => {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-native-usage-rank-"));
    tempDirs.push(tempDir);
    await createPack(tempDir, "native");
    await writeFile(
      path.join(tempDir, "agent-wiki", "notes", "generic-onboarding.md"),
      `---
title: Generic onboarding fallback
workflow: agent_adoption
status: active
usage:
  read_count: 999
  apply_count: 999
  evidence_count: 999
---

# Generic onboarding fallback

## When to Use

Use this note when onboarding needs a generic follow-up.

## Signal

Setup is incomplete.

## Interpretation

The repo may need more setup work.

## Action

Inspect the current setup and continue with the next safe step.

## Examples

- A repo where setup is only partially complete.
`,
      "utf8",
    );

    const result = await resolveLoop({
      repoPath: tempDir,
      task: "make onboarding visible and reversible for a new repo",
      workflow: "agent_adoption",
    });

    expect(result.directNoteBackend).toBe("native");
    expect(result.directNoteMatches[0].note.path).toBe("agent-wiki/notes/reversible-onboarding.md");
    expect(result.directNoteMatches[0].whyMatched).toContain("title_match");
  });

  it("uses an unknown workflow for unscoped repo-context resolution without a match", async () => {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-native-repo-context-"));
    tempDirs.push(tempDir);
    await createPack(tempDir, "native");

    const result = await resolveLoop({
      repoPath: tempDir,
    });

    expect(result.selectionBasis).toBe("repo_context");
    expect(result.matches).toHaveLength(0);
    expect(result.directNoteMatches).toHaveLength(0);
    expect(result.workflow).toBe("unknown");
  });

  it("tracks read and apply usage for qmd direct notes through the wrapped loop", async () => {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-qmd-wrap-"));
    tempDirs.push(tempDir);
    await createPack(tempDir, "qmd");
    const fakeQmd = await createFakeQmd(tempDir);

    const env = {
      ...process.env,
      DATALOX_QMD_BIN: fakeQmd.scriptPath,
      DATALOX_QMD_STATE_FILE: fakeQmd.statePath,
      DATALOX_QMD_NOTE_FILE: "reversible-onboarding.md",
      DATALOX_QMD_NOTE_TITLE: "Make onboarding visible and reversible",
    };

    const result = spawnSync(
      "node",
      [
        builtCliPath,
        "wrap",
        "command",
        "--repo",
        tempDir,
        "--task",
        "make onboarding visible and reversible for a new repo",
        "--workflow",
        "agent_adoption",
        "--prompt",
        "Need the onboarding guidance.",
        "--post-run-mode",
        "record",
        "--",
        "node",
        "-e",
        "process.stdout.write('wrapped direct note answer')",
        "__DATALOX_PROMPT__",
      ],
      {
        cwd: repoRoot,
        encoding: "utf8",
        env,
      },
    );

    expect(result.status).toBe(0);
    expect(result.stdout).toBe("wrapped direct note answer");
    expect(result.stderr).toContain("[datalox-wrap] record | record_only");

    const noteFile = await readFile(path.join(tempDir, "agent-wiki", "notes", "reversible-onboarding.md"), "utf8");
    expect(noteFile).toContain("read_count: 1");
    expect(noteFile).toContain("apply_count: 1");

    const eventsDir = path.join(tempDir, "agent-wiki", "events");
    const [eventFile] = await readdir(eventsDir);
    const eventPayload = JSON.parse(await readFile(path.join(eventsDir, eventFile), "utf8"));
    expect(eventPayload.matchedNotePaths).toContain("agent-wiki/notes/reversible-onboarding.md");
    expect(eventPayload.hostKind).toBe("generic");
  }, 20000);

  it("returns a clear no-op sync result for the native backend", async () => {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-native-sync-"));
    tempDirs.push(tempDir);
    await createPack(tempDir, "native");

    const result = await syncNoteRetrieval({ repoPath: tempDir });

    expect(result).toEqual({
      backend: "native",
      synced: false,
      reason: "native backend does not require index sync",
    });
  });
});
