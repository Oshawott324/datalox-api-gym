import { chmod, mkdir, mkdtemp, readFile, readdir, rm, writeFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";
import { PDFDocument, StandardFonts } from "pdf-lib";

import { PRODUCT_TRAJECTORY_EVENTS_RELATIVE_DIR } from "../src/core/trajectoryExport.js";

const repoRoot = process.cwd();
const builtCliPath = path.join(repoRoot, "dist", "src", "cli", "main.js");

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
    await seedWrapperFixtureNotes(hostDir);
    return hostDir;
  }

  async function writeSyntheticTraceEvent(
    hostDir: string,
    input: {
      id: string;
      stabilityKey?: string;
      timestamp?: string;
      maintenanceStatus?: string;
      coveredByNotePath?: string;
    },
  ): Promise<void> {
    await mkdir(path.join(hostDir, "agent-wiki", "events"), { recursive: true });
    const payload = {
      version: 1,
      id: input.id,
      timestamp: input.timestamp ?? new Date().toISOString(),
      eventKind: "wrapper:codex:success",
      eventClass: "trace",
      sourceKind: "trace",
      workflow: "agent_adoption",
      task: `Synthetic wrapper backlog trace ${input.id}`,
      summary: `Synthetic wrapper backlog trace ${input.id}`,
      signal: `Synthetic wrapper backlog trace ${input.id}`,
      interpretation: "synthetic wrapper backlog test event",
      recommendedAction: "run bounded note-only maintenance",
      stabilityKey: input.stabilityKey ?? `agent_adoption::${input.id}`,
      ...(input.maintenanceStatus ? { maintenanceStatus: input.maintenanceStatus } : {}),
      ...(input.coveredByNotePath ? { coveredByNotePath: input.coveredByNotePath } : {}),
      ...(input.maintenanceStatus === "covered" ? { coveredAt: "2026-04-28T00:00:00.000Z" } : {}),
    };
    await writeFile(
      path.join(hostDir, "agent-wiki", "events", `${input.id}.json`),
      `${JSON.stringify(payload, null, 2)}\n`,
    );
  }

  async function seedWrapperFixtureNotes(hostDir: string): Promise<void> {
    const viabilityNotePath = path.join(hostDir, "agent-wiki", "notes", "viability-gate-review.md");
    const viabilitySkillDir = path.join(hostDir, "skills", "review-ambiguous-viability-gate");
    try {
      await readFile(viabilityNotePath, "utf8");
    } catch {
      await writeFile(
        viabilityNotePath,
        `---
title: Review ambiguous viability gate
workflow: flow_cytometry
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

Check the exception and escalation pattern docs before widening the gate.

## Examples

- A boundary that looks unstable and needs exception review before widening the gate.
`,
        "utf8",
      );
    }
    await mkdir(viabilitySkillDir, { recursive: true });
    await writeFile(
      path.join(viabilitySkillDir, "SKILL.md"),
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
---

# Review Ambiguous Viability Gate

Use when live and dead populations are not cleanly separated during viability gate review.

## Workflow

1. Confirm the current task really matches this skill.
2. Read the linked notes before acting.
3. Apply the note signal and action to the current loop.
4. If the case exposes a reusable gap, add or update a note and patch this skill.
`,
      "utf8",
    );
  }

  async function initGitRepo(repoPath: string): Promise<void> {
    const result = spawnSync("git", ["init"], {
      cwd: repoPath,
      encoding: "utf8",
    });
    expect(result.status).toBe(0);
  }

  async function createSamplePdf(rootDir: string, title: string): Promise<string> {
    const pdf = await PDFDocument.create();
    const font = await pdf.embedFont(StandardFonts.Helvetica);
    const first = pdf.addPage([612, 792]);
    first.drawText(title, { x: 48, y: 740, size: 24, font });
    first.drawText("Key finding one.", { x: 48, y: 700, size: 12, font });
    first.drawText("Key finding two.", { x: 48, y: 680, size: 12, font });

    const second = pdf.addPage([612, 792]);
    second.drawText("Method", { x: 48, y: 740, size: 24, font });
    second.drawText("Evidence stays grounded in the document.", { x: 48, y: 700, size: 12, font });

    const pdfPath = path.join(rootDir, `${title.toLowerCase().replace(/[^a-z0-9]+/g, "-")}.pdf`);
    await writeFile(pdfPath, await pdf.save());
    return pdfPath;
  }

  it("builds a wrapped prompt for fallback CLI hosts", async () => {
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
        "review ambiguous live dead gate",
        "--workflow",
        "flow_cytometry",
        "--prompt",
        "Review the current viability gate and tell me what to do.",
      ],
      {
        cwd: repoRoot,
        encoding: "utf8",
      },
    );

    expect(result.status).toBe(0);
    expect(result.stdout).toContain("# Datalox Loop Guidance");
    expect(result.stdout).toContain("Matched skill: none");
    expect(result.stdout).toContain("Candidate skills:");
    expect(result.stdout).toContain("flow-cytometry.review-ambiguous-viability-gate");
    expect(result.stdout).toContain("# Original Prompt");
    expect(result.stdout).toContain("Review the current viability gate and tell me what to do.");
  });

  it("runs a generic wrapped command with placeholders and env injection", async () => {
    const hostDir = await adoptHostRepo();
    const script = "process.stdout.write(JSON.stringify({prompt: process.argv[1], skill: process.env.DATALOX_MATCHED_SKILL, workflow: process.env.DATALOX_WORKFLOW}))";
    const result = spawnSync(
      "node",
      [
        builtCliPath,
        "wrap",
        "command",
        "--repo",
        hostDir,
        "--task",
        "review ambiguous live dead gate",
        "--workflow",
        "flow_cytometry",
        "--prompt",
        "Need a gate recommendation",
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
    const parsed = JSON.parse(result.stdout);
    expect(parsed.skill).toBe("");
    expect(parsed.workflow).toBe("flow_cytometry");
    expect(parsed.prompt).toContain("# Datalox Loop Guidance");
    expect(parsed.prompt).toContain("Need a gate recommendation");
    expect(result.stderr).toContain("[datalox-wrap] trajectory | missing_trajectory_row");
    const eventFiles = await readdir(path.join(hostDir, "agent-wiki", "events"));
    expect(eventFiles.length).toBe(0);
    const noteFile = await readFile(path.join(hostDir, "agent-wiki", "notes", "viability-gate-review.md"), "utf8");
    expect(noteFile).toContain("usage:");
    expect(noteFile).not.toContain("apply_count: 1");
    const readCountMatch = noteFile.match(/read_count:\s+(\d+)/);
    expect(readCountMatch).not.toBeNull();
    expect(Number.parseInt(readCountMatch?.[1] ?? "0", 10)).toBeGreaterThanOrEqual(1);
  }, 40000);

  it("records an explicit trajectory row from the default wrapper post-run path", async () => {
    const hostDir = await adoptHostRepo();
    const script = [
      "const fs = require('node:fs');",
      "const path = require('node:path');",
      "const repo = process.env.DATALOX_REPO_PATH;",
      "const rowPath = path.join(repo, '.datalox/trajectory-rows/default-wrapper-row.json');",
      "fs.mkdirSync(path.dirname(rowPath), { recursive: true });",
      "fs.writeFileSync(rowPath, JSON.stringify({",
      "schema_version: 'debugging_trajectory.v1',",
      "id: 'traj_wrapper_default',",
      "created_at: '2026-05-04T00:00:00.000Z',",
      "task: { domain: 'coding_debugging', prompt: 'Fix the wrapper trajectory capture smoke test.', language: 'javascript', environment: 'nodejs' },",
      "context: { error: 'legacy wrapper recorded a trace event instead of a trajectory row' },",
      "trajectory: [",
      "{ role: 'user', content: 'Requested wrapper trajectory capture.' },",
      "{ role: 'agent', content: 'Wrote an explicit debugging_trajectory.v1 row file.' },",
      "{ role: 'tool', content: 'Smoke command completed.', command: 'node -e <script>', exit_code: 0 }",
      "],",
      "final: { fix_summary: 'Record the explicit trajectory row supplied by the wrapped agent.', changed_files: [] },",
      "outcome: { label: 'success', verification: 'passed', command: 'node -e <script>', evidence: 'Smoke command completed.' },",
      "export: { allowed: true, redaction: 'none_needed' },",
      "curation: { tags: ['wrapper', 'trajectory'] }",
      "}));",
      "process.stdout.write('trajectory row ready\\nDATALOX_TRAJECTORY_ROW_FILE: .datalox/trajectory-rows/default-wrapper-row.json');",
    ].join(" ");
    const result = spawnSync(
      "node",
      [
        builtCliPath,
        "wrap",
        "command",
        "--repo",
        hostDir,
        "--task",
        "Fix the wrapper trajectory capture smoke test.",
        "--workflow",
        "coding_debugging",
        "--prompt",
        "Fix the wrapper trajectory capture smoke test.",
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
    expect(result.stdout.trim()).toBe("trajectory row ready");
    expect(result.stderr).toContain("[datalox-wrap] trajectory | trajectory_row");
    const eventFiles = await readdir(path.join(hostDir, PRODUCT_TRAJECTORY_EVENTS_RELATIVE_DIR));
    expect(eventFiles.length).toBe(1);
    const eventPayload = JSON.parse(
      await readFile(path.join(hostDir, PRODUCT_TRAJECTORY_EVENTS_RELATIVE_DIR, eventFiles[0]), "utf8"),
    );
    expect(eventPayload.eventKind).toBe("trajectory_row");
    expect(eventPayload.trajectoryRow.schema_version).toBe("debugging_trajectory.v1");
    expect(eventPayload.trajectoryRow.id).toBe("traj_wrapper_default");
    expect(eventPayload.trajectoryRow.curation.quality).toBe("needs_review");
    expect(eventPayload.trajectoryRow.export.source_event_paths).toContain(
      `${PRODUCT_TRAJECTORY_EVENTS_RELATIVE_DIR}/${eventFiles[0]}`,
    );
  }, 20000);

  it("fails generic wrapped commands that do not expose a Datalox prompt placeholder", async () => {
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
        "review ambiguous live dead gate",
        "--workflow",
        "flow_cytometry",
        "--prompt",
        "Need a gate recommendation",
        "--",
        "node",
        "-e",
        "process.stdout.write('plain wrapped answer')",
      ],
      {
        cwd: repoRoot,
        encoding: "utf8",
      },
    );

    expect(result.status).toBe(1);
    expect(result.stderr).toContain("__DATALOX_PROMPT__ placeholder");
    expect(await readdir(path.join(hostDir, "agent-wiki", "events"))).toHaveLength(0);
  }, 20000);

  it("records a legacy wrapper event only when the record post-run mode is requested", async () => {
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
        "review ambiguous live dead gate",
        "--workflow",
        "flow_cytometry",
        "--prompt",
        "Need a gate recommendation",
        "--post-run-mode",
        "record",
        "--",
        "node",
        "-e",
        "process.stdout.write('plain wrapped answer')",
        "__DATALOX_PROMPT__",
      ],
      {
        cwd: repoRoot,
        encoding: "utf8",
      },
    );

    expect(result.status).toBe(0);
    expect(result.stdout).toBe("plain wrapped answer");
    expect(result.stderr).toContain("[datalox-wrap] record | record_only");
    const eventFiles = await readdir(path.join(hostDir, "agent-wiki", "events"));
    expect(eventFiles.length).toBe(1);
    const eventPayload = JSON.parse(
      await readFile(path.join(hostDir, "agent-wiki", "events", eventFiles[0]), "utf8"),
    );
    expect(eventPayload.summary).toBe("plain wrapped answer");
    expect(eventPayload.eventKind).toBe("wrapper:generic:success");
    expect(eventPayload.hostKind).toBe("generic");
  }, 20000);

  it("treats DATALOX markers as optional enrichment on top of the recorded event", async () => {
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
        "review ambiguous live dead gate",
        "--workflow",
        "flow_cytometry",
        "--prompt",
        "Need a gate recommendation",
        "--post-run-mode",
        "record",
        "--",
        "node",
        "-e",
        [
          "const lines = [",
          "\"DATALOX_TITLE: Ambiguous viability gate follow-up\",",
          "\"DATALOX_SIGNAL: user kept rechecking the same unstable boundary\",",
          "\"DATALOX_INTERPRETATION: this is a reusable review judgment rather than a one-off answer\",",
          "\"DATALOX_ACTION: revisit the linked note before widening the gate\",",
          "\"DATALOX_OBSERVATION: gate drift was visible on the live/dead shoulder\",",
          "\"Visible wrapped answer\"",
          "];",
          "process.stdout.write(lines.join('\\n'));",
        ].join(" "),
        "__DATALOX_PROMPT__",
      ],
      {
        cwd: repoRoot,
        encoding: "utf8",
      },
    );

    expect(result.status).toBe(0);
    expect(result.stdout.trim()).toBe("Visible wrapped answer");
    const eventFiles = await readdir(path.join(hostDir, "agent-wiki", "events"));
    expect(eventFiles.length).toBe(1);
    const eventPayload = JSON.parse(
      await readFile(path.join(hostDir, "agent-wiki", "events", eventFiles[0]), "utf8"),
    );
    expect(eventPayload.title).toBe("Ambiguous viability gate follow-up");
    expect(eventPayload.signal).toBe("user kept rechecking the same unstable boundary");
    expect(eventPayload.interpretation).toBe(
      "this is a reusable review judgment rather than a one-off answer",
    );
    expect(eventPayload.recommendedAction).toBe("revisit the linked note before widening the gate");
    expect(eventPayload.observations).toContain("gate drift was visible on the live/dead shoulder");
    expect(eventPayload.summary).toBe("Visible wrapped answer");
  }, 20000);

  it("runs the Codex wrapper with a fake codex binary and preserves the resolved prompt envelope", async () => {
    const hostDir = await adoptHostRepo();
    const fakeCodexPath = path.join(hostDir, "fake-codex-review-envelope.sh");
    await writeFile(
      fakeCodexPath,
      `#!/usr/bin/env bash
node - <<'EOF' "$@"
if (process.env.DATALOX_MATCH_PASS === "1") {
  process.stdout.write(JSON.stringify({
    matchedSkillId: "repo-engineering.maintain-datalox-pack",
    noMatch: false,
    alternatives: ["repo-engineering.use-datalox-through-host-cli"],
    reason: "The task is directly about changing the Datalox pack guidance.",
  }));
} else {
  process.stdout.write(JSON.stringify({
    args: process.argv.slice(2),
    skill: process.env.DATALOX_MATCHED_SKILL,
    workflow: process.env.DATALOX_WORKFLOW,
    activeWrapper: process.env.DATALOX_ACTIVE_WRAPPER,
    hostKind: process.env.DATALOX_HOST_KIND,
    enforcement: process.env.DATALOX_ENFORCEMENT,
  }));
}
EOF
`,
      "utf8",
    );
    await chmod(fakeCodexPath, 0o755);
    const result = spawnSync(
      "node",
      [
        builtCliPath,
        "codex",
        "--repo",
        hostDir,
        "--task",
        "change portable pack loop bridge",
        "--workflow",
        "repo_engineering",
        "--prompt",
        "Update the pack docs to mention wrappers.",
        "--post-run-mode",
        "record",
        "--codex-bin",
        fakeCodexPath,
        "--",
        "exec",
        "--skip-git-repo-check",
        "__DATALOX_PROMPT__",
      ],
      {
        cwd: repoRoot,
        encoding: "utf8",
      },
    );

    expect(result.status).toBe(0);
    const parsed = JSON.parse(result.stdout);
    expect(parsed.skill).toBe("repo-engineering.maintain-datalox-pack");
    expect(parsed.workflow).toBe("repo_engineering");
    expect(parsed.activeWrapper).toBe("codex");
    expect(parsed.hostKind).toBe("codex");
    expect(parsed.enforcement).toBe("wrapper");
    expect(parsed.args[0]).toBe("exec");
    expect(parsed.args[2]).toContain("# Datalox Loop Guidance");
    expect(parsed.args[2]).toContain("Update the pack docs to mention wrappers.");
    expect(result.stderr).toContain("[datalox-codex] record");
    expect(await readFile(path.join(hostDir, "agent-wiki", "log.md"), "utf8")).toContain("record_event");
  }, 20000);

  it("runs automatic bounded maintenance from Codex wrapper JSON when backlog is hot", async () => {
    const hostDir = await adoptHostRepo();
    await writeSyntheticTraceEvent(hostDir, {
      id: "2026-04-28T00-00-00-000Z--codex-backlog-a",
      stabilityKey: "agent_adoption::codex-wrapper-backlog",
    });
    await writeSyntheticTraceEvent(hostDir, {
      id: "2026-04-28T00-01-00-000Z--codex-backlog-b",
      stabilityKey: "agent_adoption::codex-wrapper-backlog",
    });

    const fakeCodexPath = path.join(hostDir, "fake-codex-backlog.sh");
    await writeFile(
      fakeCodexPath,
      `#!/usr/bin/env bash
if [ "$DATALOX_MATCH_PASS" = "1" ]; then
  cat <<'EOF'
{"matchedSkillId":null,"noMatch":true,"alternatives":[],"reason":"No specific skill is needed for this backlog smoke test."}
EOF
  exit 0
fi
node -e 'process.stdout.write(JSON.stringify({args: process.argv.slice(1), skill: process.env.DATALOX_MATCHED_SKILL}))' "$@"
`,
      "utf8",
    );
    await chmod(fakeCodexPath, 0o755);

    const result = spawnSync(
      "node",
      [
        builtCliPath,
        "codex",
        "--json",
        "--repo",
        hostDir,
        "--codex-bin",
        fakeCodexPath,
        "--post-run-mode",
        "record",
        "--task",
        "Run a small command while Datalox has a maintainable backlog.",
        "--",
        "exec",
        "--skip-git-repo-check",
        "__DATALOX_PROMPT__",
      ],
      {
        cwd: repoRoot,
        encoding: "utf8",
      },
    );

    expect(result.status).toBe(0);
    const parsed = JSON.parse(result.stdout);
    expect(parsed.postRun.maintenance.status).toBe("ran");
    expect(parsed.postRun.maintenance.beforeBacklog.maintenanceRecommended).toBe(true);
    expect(parsed.postRun.maintenance.beforeBacklog.policy.level).toBe("warn");
    expect(parsed.postRun.maintenance.maintenance.skillActions).toEqual([]);
    expect(parsed.postRun.backlog.maintenanceRecommended).toBe(false);

    const hotFile = await readFile(path.join(hostDir, "agent-wiki", "hot.md"), "utf8");
    expect(hotFile).not.toContain("## Maintenance Backlog");

    const status = spawnSync("node", [builtCliPath, "status", "--repo", hostDir, "--json"], {
      cwd: repoRoot,
      encoding: "utf8",
    });
    expect(status.status).toBe(0);
    const statusBody = JSON.parse(status.stdout);
    expect(statusBody.repo.maintenanceBacklog.maintenanceRecommended).toBe(false);
    expect(statusBody.repo.maintenanceBacklog.uncoveredEvents).toBe(0);
  }, 20000);

  it("runs automatic bounded maintenance from generic wrapper command when backlog is hot", async () => {
    const hostDir = await adoptHostRepo();
    await writeSyntheticTraceEvent(hostDir, {
      id: "2026-04-28T00-00-00-000Z--generic-backlog-a",
      stabilityKey: "agent_adoption::generic-wrapper-backlog",
    });
    await writeSyntheticTraceEvent(hostDir, {
      id: "2026-04-28T00-01-00-000Z--generic-backlog-b",
      stabilityKey: "agent_adoption::generic-wrapper-backlog",
    });

    const result = spawnSync(
      "node",
      [
        builtCliPath,
        "wrap",
        "command",
        "--json",
        "--repo",
        hostDir,
        "--task",
        "Run a generic command while Datalox has a hot backlog.",
        "--prompt",
        "Run a generic command.",
        "--post-run-mode",
        "record",
        "--",
        "node",
        "-e",
        "process.stdout.write('ok')",
        "__DATALOX_PROMPT__",
      ],
      {
        cwd: repoRoot,
        encoding: "utf8",
      },
    );

    expect(result.status).toBe(0);
    const parsed = JSON.parse(result.stdout);
    expect(parsed.postRun.maintenance.status).toBe("ran");
    expect(parsed.postRun.maintenance.maintenance.skillActions).toEqual([]);
    expect(parsed.postRun.backlog.maintenanceRecommended).toBe(false);
  }, 20000);

  it("does not recursively expand prompt placeholders that appear inside wrapped prompt prose", async () => {
    const hostDir = await adoptHostRepo();
    const fakeCodexPath = path.join(hostDir, "fake-codex-literal-placeholder.sh");
    await writeFile(
      fakeCodexPath,
      "#!/usr/bin/env bash\nnode -e 'process.stdout.write(JSON.stringify({args: process.argv.slice(1)}))' \"$@\"\n",
      "utf8",
    );
    await chmod(fakeCodexPath, 0o755);

    const result = spawnSync(
      "node",
      [
        builtCliPath,
        "codex",
        "--repo",
        hostDir,
        "--post-run-mode",
        "record",
        "--codex-bin",
        fakeCodexPath,
        "--json",
        "--",
        "exec",
        "Mention __DATALOX_PROMPT__ literally in the answer contract.",
      ],
      {
        cwd: repoRoot,
        encoding: "utf8",
      },
    );

    expect(result.status).toBe(0);
    const parsed = JSON.parse(result.stdout);
    const wrappedPrompt = parsed.child.args[1];
    expect(wrappedPrompt).toContain("Mention __DATALOX_PROMPT__ literally in the answer contract.");
    expect((wrappedPrompt.match(/# Datalox Loop Guidance/g) ?? [])).toHaveLength(1);
  }, 20000);

  it("sanitizes Codex transport boilerplate before summary extraction", async () => {
    const hostDir = await adoptHostRepo();
    const fakeCodexPath = path.join(hostDir, "fake-codex-transport-noise.sh");
    await writeFile(
      fakeCodexPath,
      `#!/usr/bin/env bash
node - <<'EOF' "$@"
process.stdout.write("Visible wrapped answer");
process.stderr.write("Reading additional input from stdin...\\nOpenAI Codex v0.0.0\\n");
EOF
`,
      "utf8",
    );
    await chmod(fakeCodexPath, 0o755);

    const result = spawnSync(
      "node",
      [
        builtCliPath,
        "codex",
        "--repo",
        hostDir,
        "--post-run-mode",
        "record",
        "--codex-bin",
        fakeCodexPath,
        "--json",
        "--",
        "exec",
        "Describe this repo in one sentence.",
      ],
      {
        cwd: repoRoot,
        encoding: "utf8",
      },
    );

    expect(result.status).toBe(0);
    const parsed = JSON.parse(result.stdout);
    expect(parsed.child.stdout).toBe("Visible wrapped answer");
    expect(parsed.child.stderr).toBe("");

    const eventFiles = await readdir(path.join(hostDir, "agent-wiki", "events"));
    expect(eventFiles).toHaveLength(1);
    const eventPayload = JSON.parse(
      await readFile(path.join(hostDir, "agent-wiki", "events", eventFiles[0]), "utf8"),
    );
    expect(eventPayload.summary).toBe("Visible wrapped answer");
    expect(eventPayload.title).toBe("Visible wrapped answer");
  }, 20000);

  it("drops Codex plugin warning HTML dumps from stored transcripts", async () => {
    const hostDir = await adoptHostRepo();
    const fakeCodexPath = path.join(hostDir, "fake-codex-plugin-html-noise.sh");
    await writeFile(
      fakeCodexPath,
      `#!/usr/bin/env bash
node - <<'EOF' "$@"
process.stdout.write("Visible wrapped answer");
process.stderr.write([
  "2026-04-23T03:36:35.306762Z  WARN codex_core::plugins::manager: failed to warm featured plugin ids cache error=remote plugin sync request to https://chatgpt.com/backend-api/plugins/featured failed with status 403 Forbidden: <html>",
  "<head>",
  "window._cf_chl_opt = { token: 'noise' };",
  "<body>",
  "Enable JavaScript and cookies to continue",
  "</body>",
  "</html>"
].join("\\n"));
EOF
`,
      "utf8",
    );
    await chmod(fakeCodexPath, 0o755);

    const result = spawnSync(
      "node",
      [
        builtCliPath,
        "codex",
        "--repo",
        hostDir,
        "--post-run-mode",
        "record",
        "--codex-bin",
        fakeCodexPath,
        "--json",
        "--",
        "exec",
        "Describe this repo in one sentence.",
      ],
      {
        cwd: repoRoot,
        encoding: "utf8",
      },
    );

    expect(result.status).toBe(0);
    const parsed = JSON.parse(result.stdout);
    expect(parsed.child.stdout).toBe("Visible wrapped answer");
    expect(parsed.child.stderr).toBe("");

    const eventFiles = await readdir(path.join(hostDir, "agent-wiki", "events"));
    expect(eventFiles).toHaveLength(1);
    const eventPayload = JSON.parse(
      await readFile(path.join(hostDir, "agent-wiki", "events", eventFiles[0]), "utf8"),
    );
    expect(eventPayload.summary).toBe("Visible wrapped answer");
    expect(eventPayload.transcript).not.toContain("codex_core::plugins::manager");
    expect(eventPayload.transcript).not.toContain("<html>");
    expect(eventPayload.transcript).not.toContain("window._cf_chl_opt");
    expect(eventPayload.transcript).not.toContain("Enable JavaScript and cookies to continue");
  }, 20000);

  it("preserves real child error text while dropping Codex transport noise", async () => {
    const hostDir = await adoptHostRepo();
    const fakeCodexPath = path.join(hostDir, "fake-codex-noisy-error.sh");
    await writeFile(
      fakeCodexPath,
      `#!/usr/bin/env bash
node - <<'EOF' "$@"
process.stderr.write([
  "2026-04-23T03:36:35.306762Z  WARN codex_core::plugins::manager: failed to warm featured plugin ids cache error=remote plugin sync request to https://chatgpt.com/backend-api/plugins/featured failed with status 403 Forbidden: <html>",
  "<body>",
  "Enable JavaScript and cookies to continue",
  "</body>",
  "</html>",
  "fatal: repo bootstrap script missing"
].join("\\n"));
process.exit(1);
EOF
`,
      "utf8",
    );
    await chmod(fakeCodexPath, 0o755);

    const result = spawnSync(
      "node",
      [
        builtCliPath,
        "codex",
        "--repo",
        hostDir,
        "--post-run-mode",
        "record",
        "--codex-bin",
        fakeCodexPath,
        "--json",
        "--",
        "exec",
        "Try the documented bootstrap path and report the exact failure.",
      ],
      {
        cwd: repoRoot,
        encoding: "utf8",
      },
    );

    expect(result.status).toBe(1);
    const parsed = JSON.parse(result.stdout);
    expect(parsed.child.exitCode).toBe(1);
    expect(parsed.child.stderr).toBe("fatal: repo bootstrap script missing");

    const eventFiles = await readdir(path.join(hostDir, "agent-wiki", "events"));
    expect(eventFiles).toHaveLength(1);
    const eventPayload = JSON.parse(
      await readFile(path.join(hostDir, "agent-wiki", "events", eventFiles[0]), "utf8"),
    );
    expect(eventPayload.summary).toBe("fatal: repo bootstrap script missing");
    expect(eventPayload.transcript).toContain("fatal: repo bootstrap script missing");
    expect(eventPayload.transcript).not.toContain("codex_core::plugins::manager");
    expect(eventPayload.transcript).not.toContain("<html>");
    expect(eventPayload.transcript).not.toContain("Enable JavaScript and cookies to continue");
  }, 20000);

  it("runs the Claude wrapper with a fake claude binary and preserves the resolved prompt envelope", async () => {
    const hostDir = await adoptHostRepo();
    const fakeClaudePath = path.join(hostDir, "fake-claude.sh");
    await writeFile(
      fakeClaudePath,
      "#!/usr/bin/env bash\nnode -e 'if (process.env.DATALOX_MATCH_PASS === \"1\") { process.stdout.write(JSON.stringify({matchedSkillId:\"repo-engineering.maintain-datalox-pack\", noMatch:false, alternatives:[\"repo-engineering.use-datalox-through-host-cli\"], reason:\"The task is directly about changing the Datalox pack guidance.\"})); } else { process.stdout.write(JSON.stringify({args: process.argv.slice(1), skill: process.env.DATALOX_MATCHED_SKILL, workflow: process.env.DATALOX_WORKFLOW, activeWrapper: process.env.DATALOX_ACTIVE_WRAPPER, hostKind: process.env.DATALOX_HOST_KIND, enforcement: process.env.DATALOX_ENFORCEMENT})); }' -- \"$@\"\n",
      "utf8",
    );
    await chmod(fakeClaudePath, 0o755);

    const result = spawnSync(
      "node",
      [
        builtCliPath,
        "claude",
        "--repo",
        hostDir,
        "--task",
        "change portable pack loop bridge",
        "--workflow",
        "repo_engineering",
        "--post-run-mode",
        "record",
        "--claude-bin",
        fakeClaudePath,
        "--",
        "--print",
        "Update the pack docs to mention Claude shims.",
      ],
      {
        cwd: repoRoot,
        encoding: "utf8",
      },
    );

    expect(result.status).toBe(0);
    const parsed = JSON.parse(result.stdout);
    expect(parsed.skill).toBe("repo-engineering.maintain-datalox-pack");
    expect(parsed.workflow).toBe("repo_engineering");
    expect(parsed.activeWrapper).toBe("claude");
    expect(parsed.hostKind).toBe("claude");
    expect(parsed.enforcement).toBe("wrapper");
    expect(parsed.args[0]).toBe("--print");
    expect(parsed.args[1]).toContain("# Datalox Loop Guidance");
    expect(parsed.args[1]).toContain("Update the pack docs to mention Claude shims.");
    expect(result.stderr).toContain("[datalox-claude] record");
    expect(await readFile(path.join(hostDir, "agent-wiki", "log.md"), "utf8")).toContain("record_event");
  }, 20000);

  it("appends the wrapped prompt for Claude runs that only provide flags and no prompt slot", async () => {
    const hostDir = await adoptHostRepo();
    const fakeClaudePath = path.join(hostDir, "fake-claude-append.sh");
    await writeFile(
      fakeClaudePath,
      "#!/usr/bin/env bash\nnode -e 'if (process.env.DATALOX_MATCH_PASS === \"1\") { process.stdout.write(JSON.stringify({matchedSkillId:\"repo-engineering.maintain-datalox-pack\", noMatch:false, alternatives:[\"repo-engineering.use-datalox-through-host-cli\"], reason:\"The task is directly about changing the Datalox pack guidance.\"})); } else { process.stdout.write(JSON.stringify({args: process.argv.slice(1), skill: process.env.DATALOX_MATCHED_SKILL})); }' -- \"$@\"\n",
      "utf8",
    );
    await chmod(fakeClaudePath, 0o755);

    const result = spawnSync(
      "node",
      [
        builtCliPath,
        "claude",
        "--repo",
        hostDir,
        "--task",
        "change portable pack loop bridge",
        "--workflow",
        "repo_engineering",
        "--prompt",
        "Explain the wrapper contract.",
        "--claude-bin",
        fakeClaudePath,
        "--",
        "--model",
        "cheap-test-model",
      ],
      {
        cwd: repoRoot,
        encoding: "utf8",
      },
    );

    expect(result.status).toBe(0);
    const parsed = JSON.parse(result.stdout);
    expect(parsed.skill).toBe("repo-engineering.maintain-datalox-pack");
    expect(parsed.args[0]).toBe("--model");
    expect(parsed.args[2]).toContain("# Datalox Loop Guidance");
    expect(parsed.args[2]).toContain("Explain the wrapper contract.");
    expect(parsed.args[2]).not.toContain("score:");
  }, 20000);

  it("infers the prompt from raw codex exec args when no explicit Datalox prompt is given", async () => {
    const hostDir = await adoptHostRepo();
    const fakeCodexPath = path.join(hostDir, "fake-codex.sh");
    await writeFile(
      fakeCodexPath,
      "#!/usr/bin/env bash\nnode -e 'if (process.env.DATALOX_MATCH_PASS === \"1\") { process.stdout.write(JSON.stringify({matchedSkillId:\"repo-engineering.maintain-datalox-pack\", noMatch:false, alternatives:[\"repo-engineering.use-datalox-through-host-cli\"], reason:\"The prompt directly asks for Datalox pack guidance changes.\"})); } else { process.stdout.write(JSON.stringify({args: process.argv.slice(1), skill: process.env.DATALOX_MATCHED_SKILL})); }' \"$@\"\n",
      "utf8",
    );
    await chmod(fakeCodexPath, 0o755);
    const result = spawnSync(
      "node",
      [
        builtCliPath,
        "codex",
        "--repo",
        hostDir,
        "--post-run-mode",
        "record",
        "--codex-bin",
        fakeCodexPath,
        "--",
        "exec",
        "--skip-git-repo-check",
        "Change Datalox pack agent guidance in this repo.",
      ],
      {
        cwd: repoRoot,
        encoding: "utf8",
      },
    );

    expect(result.status).toBe(0);
    const parsed = JSON.parse(result.stdout);
    expect(parsed.skill).toBe("repo-engineering.maintain-datalox-pack");
    expect(parsed.args[0]).toBe("exec");
    expect(parsed.args[2]).toContain("# Datalox Loop Guidance");
    expect(parsed.args[2]).toContain("Matched skill: repo-engineering.maintain-datalox-pack");
    expect(parsed.args[2]).toContain("Change Datalox pack agent guidance in this repo.");
    expect(parsed.args[2]).not.toContain("score:");
  }, 20000);

  it("does not surface use-datalox-through-host-cli for a generic repo-engineering retrieval query", async () => {
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
        "evaluate issues in retrieval heuristics for datalox-pack",
        "--workflow",
        "repo_engineering",
        "--prompt",
        "Check retrieval fix drift.",
      ],
      {
        cwd: repoRoot,
        encoding: "utf8",
      },
    );

    expect(result.status).toBe(0);
    expect(result.stdout).toContain("Maintain Datalox Pack");
    expect(result.stdout).not.toContain("Use Datalox Through Host CLI");
    expect(result.stdout).toContain("workflow_match");
  }, 20000);

  it("uses the bounded Codex match adjudicator for ambiguous same-workflow online cases without exposing a false matched skill", async () => {
    const hostDir = await adoptHostRepo();
    await mkdir(path.join(hostDir, "skills", "desktop-host-stream-chunking"), { recursive: true });
    await writeFile(
      path.join(hostDir, "agent-wiki", "notes", "desktop-host-stream-chunking.md"),
      `---
title: Use async chunk parsing for long-lived agent runtime SSE in the Tauri host
workflow: desktop-agent-workspace
status: active
---

# Use async chunk parsing for long-lived agent runtime SSE in the Tauri host

## When to Use

Use when long-lived desktop agent runtime streams fail because the host proxies SSE through a blocking reqwest body adapter.

## Signal

The desktop host stream decode path fails while reading long-lived SSE output.

## Interpretation

Use async reqwest chunk reads and incremental SSE parsing instead of the blocking body adapter.

## Action

Switch the Tauri host to async chunk parsing for long-lived SSE output.
`,
      "utf8",
    );
    await writeFile(
      path.join(hostDir, "skills", "desktop-host-stream-chunking", "SKILL.md"),
      `---
name: desktop-host-stream-chunking
description: For long-lived desktop agent runtime streams, avoid the blocking reqwest body adapter in the Tauri host and use async chunk parsing instead.
metadata:
  datalox:
    id: desktop-agent-workspace.desktop-host-stream-chunking
    display_name: Use async chunk parsing for long-lived agent runtime SSE in the Tauri host
    workflow: desktop-agent-workspace
    trigger: Use when the desktop host stream decode path fails on long-lived SSE output.
    note_paths:
      - agent-wiki/notes/desktop-host-stream-chunking.md
---

# Use async chunk parsing for long-lived agent runtime SSE in the Tauri host

For long-lived desktop agent runtime streams, avoid the blocking reqwest body adapter in the Tauri host and use async chunk parsing instead.
`,
      "utf8",
    );

    const fakeCodexPath = path.join(hostDir, "fake-codex-match-adjudicator.sh");
    await writeFile(
      fakeCodexPath,
      `#!/usr/bin/env bash
if [ "$DATALOX_MATCH_PASS" = "1" ]; then
  printf '%s' "$*" > "$DATALOX_REPO_PATH/match-pass.txt"
  cat <<'EOF'
{"matchedSkillId":null,"noMatch":true,"alternatives":["desktop-agent-workspace.desktop-host-stream-chunking"],"reason":"The candidate skill is about long-lived SSE stream parsing, not PDF.js WKWebView compatibility."}
EOF
  exit 0
fi
node -e 'process.stdout.write(JSON.stringify({args: process.argv.slice(1), skill: process.env.DATALOX_MATCHED_SKILL}))' "$@"
`,
      "utf8",
    );
    await chmod(fakeCodexPath, 0o755);

    const result = spawnSync(
      "node",
      [
        builtCliPath,
        "codex",
        "--repo",
        hostDir,
        "--post-run-mode",
        "record",
        "--codex-bin",
        fakeCodexPath,
        "--task",
        "desktop runtime tauri fix",
        "--workflow",
        "desktop-agent-workspace",
        "--",
        "exec",
        "--skip-git-repo-check",
        "Fix the center-viewer PDF preview runtime error '#e.getOrInsertComputed is not a function' in the desktop app.",
      ],
      {
        cwd: repoRoot,
        encoding: "utf8",
      },
    );

    expect(result.status).toBe(0);
    const parsed = JSON.parse(result.stdout);
    expect(parsed.skill).toBe("");
    expect(parsed.args[2]).toContain("Matched skill: none");
    expect(parsed.args[2]).toContain("Use async chunk parsing for long-lived agent runtime SSE in the Tauri host");

    const matchPrompt = await readFile(path.join(hostDir, "match-pass.txt"), "utf8");
    expect(matchPrompt).toContain("\"matchedSkillId\": string | null");
    expect(matchPrompt).toContain("\"desktop-agent-workspace.desktop-host-stream-chunking\"");
    expect(matchPrompt.length).toBeLessThan(5000);
  }, 20000);

  it("routes concrete PDF paths through repo-local PDF capture before generic skill resolution", async () => {
    const hostDir = await adoptHostRepo();
    const externalDir = await mkdtemp(path.join(tmpdir(), "datalox-wrapper-pdf-source-"));
    tempDirs.push(externalDir);
    const pdfPath = await createSamplePdf(externalDir, "Wrapped Source PDF");
    const fakeCodexPath = path.join(hostDir, "fake-codex-pdf.sh");
    await writeFile(
      fakeCodexPath,
      "#!/usr/bin/env bash\nnode -e 'process.stdout.write(JSON.stringify({args: process.argv.slice(1), skill: process.env.DATALOX_MATCHED_SKILL, workflow: process.env.DATALOX_WORKFLOW, selectionBasis: process.env.DATALOX_SELECTION_BASIS}))' \"$@\"\n",
      "utf8",
    );
    await chmod(fakeCodexPath, 0o755);

    const result = spawnSync(
      "node",
      [
        builtCliPath,
        "codex",
        "--repo",
        hostDir,
        "--post-run-mode",
        "record",
        "--codex-bin",
        fakeCodexPath,
        "--",
        "exec",
        `Please read ${pdfPath} and give me a short summary.`,
      ],
      {
        cwd: repoRoot,
        encoding: "utf8",
      },
    );

    expect(result.status).toBe(0);
    const parsed = JSON.parse(result.stdout);
    const wrappedPrompt = parsed.args.join("\n");
    expect(parsed.skill).toBe("");
    expect(parsed.workflow).toBe("pdf_capture");
    expect(parsed.selectionBasis).toBe("source_kind_pdf");
    expect(wrappedPrompt).toContain("Workflow: pdf_capture");
    expect(wrappedPrompt).toContain("agent-wiki/notes/pdf/wrapped-source-pdf.md");
    expect(wrappedPrompt).not.toContain("score:");

    const capturedNotePath = path.join(hostDir, "agent-wiki", "notes", "pdf", "wrapped-source-pdf.md");
    const capturedNote = await readFile(capturedNotePath, "utf8");
    expect(capturedNote).toContain("# Wrapped Source PDF");
    expect(capturedNote).toContain("## Evidence");

    const eventFiles = await readdir(path.join(hostDir, "agent-wiki", "events"));
    expect(eventFiles.length).toBe(1);
    const eventPayload = JSON.parse(
      await readFile(path.join(hostDir, "agent-wiki", "events", eventFiles[0]), "utf8"),
    );
    expect(eventPayload.workflow).toBe("pdf_capture");
    expect(eventPayload.matchedSkillId).toBeNull();
    expect(eventPayload.matchedNotePaths).toContain("agent-wiki/notes/pdf/wrapped-source-pdf.md");
    expect(await readFile(path.join(hostDir, "agent-wiki", "log.md"), "utf8")).toContain("capture_pdf_artifact");
  }, 60000);

  it("sanitizes Codex output files when the child uses -o", async () => {
    const hostDir = await adoptHostRepo();
    const fakeCodexPath = path.join(hostDir, "fake-codex-output.sh");
    await writeFile(
      fakeCodexPath,
      `#!/usr/bin/env bash
node - <<'EOF' "$@"
const fs = require("node:fs");
const args = process.argv.slice(2);
let outputPath;
for (let index = 0; index < args.length; index += 1) {
  const arg = args[index];
  if (arg === "-o" || arg === "--output-last-message") {
    outputPath = args[index + 1];
    break;
  }
  if (arg.startsWith("--output-last-message=")) {
    outputPath = arg.slice("--output-last-message=".length);
    break;
  }
}
const payload = [
  "DATALOX_TITLE: Wrapper output sanitation",
  "DATALOX_SIGNAL: marker lines leaked into the codex output file",
  "DATALOX_INTERPRETATION: the wrapper should scrub Datalox markers from user-facing output artifacts",
  "DATALOX_ACTION: strip the marker lines before leaving the output file on disk",
  "Visible answer only",
].join("\\n");
if (outputPath) {
  fs.writeFileSync(outputPath, payload, "utf8");
}
process.stdout.write(payload);
EOF
`,
      "utf8",
    );
    await chmod(fakeCodexPath, 0o755);

    const outputFile = path.join(hostDir, "codex-last-message.txt");
    const result = spawnSync(
      "node",
      [
        builtCliPath,
        "codex",
        "--repo",
        hostDir,
        "--codex-bin",
        fakeCodexPath,
        "--",
        "exec",
        "-o",
        outputFile,
        "Inspect the onboarding path.",
      ],
      {
        cwd: repoRoot,
        encoding: "utf8",
      },
    );

    expect(result.status).toBe(0);
    expect(result.stdout.trim()).toBe("Visible answer only");
    expect(await readFile(outputFile, "utf8")).toBe("Visible answer only");
  }, 10000);

  it("auto-bootstraps a clean git repo on first wrapped Codex run", async () => {
    const hostDir = await mkdtemp(path.join(tmpdir(), "datalox-wrapper-auto-"));
    tempDirs.push(hostDir);
    await initGitRepo(hostDir);
    const fakeCodexPath = path.join(hostDir, "fake-codex-bootstrap.sh");
    await writeFile(
      fakeCodexPath,
      "#!/usr/bin/env bash\nnode -e 'process.stdout.write(JSON.stringify({args: process.argv.slice(1), skill: process.env.DATALOX_MATCHED_SKILL, repo: process.env.DATALOX_REPO_PATH}))' \"$@\"\n",
      "utf8",
    );
    await chmod(fakeCodexPath, 0o755);

    const result = spawnSync(
      "node",
      [
        builtCliPath,
        "codex",
        "--repo",
        hostDir,
        "--codex-bin",
        fakeCodexPath,
        "--",
        "exec",
        "Explain the repo onboarding path.",
      ],
      {
        cwd: repoRoot,
        encoding: "utf8",
      },
    );

    expect(result.status).toBe(0);
    const parsed = JSON.parse(result.stdout);
    expect(parsed.repo).toBe(hostDir);
    expect(parsed.args[1]).toContain("# Datalox Loop Guidance");
    expect(await readFile(path.join(hostDir, ".datalox", "install.json"), "utf8")).toContain("\"installMode\": \"auto\"");
    expect(await readFile(path.join(hostDir, "DATALOX.md"), "utf8")).toContain("Datalox");
  }, 60000);

  it("refuses auto-bootstrap when partial Datalox-owned paths already exist", async () => {
    const hostDir = await mkdtemp(path.join(tmpdir(), "datalox-wrapper-blocked-"));
    tempDirs.push(hostDir);
    await initGitRepo(hostDir);
    await mkdir(path.join(hostDir, "agent-wiki"), { recursive: true });
    await writeFile(path.join(hostDir, "agent-wiki", "hot.md"), "# partial\n", "utf8");

    const result = spawnSync(
      "node",
      [
        builtCliPath,
        "wrap",
        "prompt",
        "--repo",
        hostDir,
        "--prompt",
        "Just answer normally.",
      ],
      {
        cwd: repoRoot,
        encoding: "utf8",
      },
    );

    expect(result.status).toBe(0);
    expect(result.stdout.trim()).toBe("Just answer normally.");
    expect(spawnSync("test", ["-f", path.join(hostDir, ".datalox", "install.json")]).status).not.toBe(0);
    expect(spawnSync("test", ["-f", path.join(hostDir, "DATALOX.md")]).status).not.toBe(0);
  }, 10000);

  it("patches a matched wrapper skill when the same wrapped failure repeats", async () => {
    const hostDir = await adoptHostRepo();
    const failingScript = [
      "const lines = [",
      "\"DATALOX_TITLE: Unsupported host wrapper failure\",",
      "\"DATALOX_SIGNAL: the same unsupported host cli path kept failing under the wrapper\",",
      "\"DATALOX_INTERPRETATION: this is a reusable wrapper gap rather than a one-off child failure\",",
      "\"DATALOX_ACTION: patch the wrapper skill so future agents use the supported host path\",",
      "\"DATALOX_DECISION: patch_existing_skill\",",
      "\"fatal onboarding gap\"",
      "];",
      "process.stderr.write(lines.join('\\n'));",
      "process.exit(1);",
    ].join(" ");

    const runFailure = () =>
      spawnSync(
        "node",
        [
          builtCliPath,
          "wrap",
          "command",
          "--repo",
          hostDir,
          "--task",
          "debug repeated wrapper failure in unsupported host cli path",
          "--workflow",
          "repo_engineering",
          "--skill",
          "repo-engineering.use-datalox-through-host-cli",
          "--post-run-mode",
          "promote",
          "--prompt",
          "Debug repeated wrapper failure in unsupported host cli path",
          "--",
          "node",
          "-e",
          failingScript,
          "__DATALOX_PROMPT__",
        ],
        {
          cwd: repoRoot,
          encoding: "utf8",
        },
      );

    const first = runFailure();
    expect(first.status).toBe(1);
    expect(first.stderr).toContain("create_note_from_gap");

    const second = runFailure();
    expect(second.status).toBe(1);
    expect(second.stderr).toContain("patch_skill_with_note");

    const third = runFailure();
    expect(third.status).toBe(1);
    expect(third.stderr).toContain("patch_skill_with_note");

    const logFile = await readFile(path.join(hostDir, "agent-wiki", "log.md"), "utf8");
    const patchedSkill = await readFile(
      path.join(hostDir, "skills", "use-datalox-through-host-cli", "SKILL.md"),
      "utf8",
    );

    expect(logFile).toContain("record_event");
    expect(logFile).toContain("create_note");
    expect(logFile).toContain("update_skill");
    expect(patchedSkill).toContain("agent-wiki/notes/");
  }, 60000);

  it("does not let a repeated identical wrapped run regress from create_note_from_gap back to record_only", async () => {
    const hostDir = await adoptHostRepo();
    const statePath = path.join(hostDir, "repeat-state.txt");
    const fakeCodexPath = path.join(hostDir, "fake-codex-sticky-note.sh");
    await writeFile(
      fakeCodexPath,
      `#!/usr/bin/env bash
if [ "$DATALOX_MATCH_PASS" = "1" ]; then
  cat <<'EOF'
{"matchedSkillId":null,"noMatch":true,"alternatives":["repo-engineering.maintain-datalox-pack"],"reason":"This onboarding correction should stay note-first during the online loop."}
EOF
  exit 0
fi
count=0
if [ -f "${statePath}" ]; then
  count=$(cat "${statePath}")
fi
count=$((count + 1))
printf "%s" "$count" > "${statePath}"
if [ "$count" -eq 1 ]; then
  cat <<'EOF'
Future agents should use the committed onboarding bootstrap step.
DATALOX_SUMMARY: repos need a committed onboarding bootstrap step before autonomous edits
DATALOX_TITLE: committed onboarding bootstrap step
DATALOX_SIGNAL: onboarding keeps depending on hidden setup steps
DATALOX_INTERPRETATION: this is a reusable operational onboarding gap
DATALOX_ACTION: add the committed bootstrap step to repo guidance before autonomous edits
DATALOX_DECISION: create_operational_note
EOF
else
  printf "%s" "Future agents should use the committed onboarding bootstrap step."
fi
`,
      "utf8",
    );
    await chmod(fakeCodexPath, 0o755);

    const runWrapped = () => spawnSync(
      "node",
      [
        builtCliPath,
        "codex",
        "--repo",
        hostDir,
        "--post-run-mode",
        "promote",
        "--codex-bin",
        fakeCodexPath,
        "--json",
        "--",
        "exec",
        "--skip-git-repo-check",
        "Inspect the repo setup instructions. If there is a reusable setup gap, explain the correction for future agents in one short paragraph.",
      ],
      {
        cwd: repoRoot,
        encoding: "utf8",
      },
    );

    const first = runWrapped();
    expect(first.status).toBe(0);
    const firstParsed = JSON.parse(first.stdout);
    expect(firstParsed.postRun.result.decision.action).toBe("create_note_from_gap");

    const second = runWrapped();
    expect(second.status).toBe(0);
    const secondParsed = JSON.parse(second.stdout);
    expect(secondParsed.postRun.result.decision.action).toBe("create_note_from_gap");
  }, 60000);

  it("reuses the same promoted note when a repeated wrapped run restates the same gap with different markers", async () => {
    const hostDir = await adoptHostRepo();
    const statePath = path.join(hostDir, "repeat-state-semantics.txt");
    const fakeCodexPath = path.join(hostDir, "fake-codex-note-semantics.sh");
    await writeFile(
      fakeCodexPath,
      `#!/usr/bin/env bash
if [ "$DATALOX_MATCH_PASS" = "1" ]; then
  cat <<'EOF'
{"matchedSkillId":null,"noMatch":true,"alternatives":["repo-engineering.maintain-datalox-pack"],"reason":"This onboarding correction should stay note-first during the online loop."}
EOF
  exit 0
fi
count=0
if [ -f "${statePath}" ]; then
  count=$(cat "${statePath}")
fi
count=$((count + 1))
printf "%s" "$count" > "${statePath}"
if [ "$count" -eq 1 ]; then
  cat <<'EOF'
Future agents should use the committed onboarding bootstrap step.
DATALOX_SUMMARY: repos need a committed onboarding bootstrap step before autonomous edits
DATALOX_TITLE: committed onboarding bootstrap step
DATALOX_SIGNAL: onboarding keeps depending on hidden setup steps
DATALOX_INTERPRETATION: this is a reusable operational onboarding gap
DATALOX_ACTION: add the committed bootstrap step to repo guidance before autonomous edits
DATALOX_DECISION: create_operational_note
EOF
else
  cat <<'EOF'
Future agents should use the CLI-backed onboarding bootstrap step.
DATALOX_SUMMARY: setup docs point at missing legacy bootstrap paths instead of the CLI-backed entrypoints
DATALOX_TITLE: canonical setup path
DATALOX_SIGNAL: README.md references scripts/bootstrap.sh and START_HERE.md names missing adoption scripts
DATALOX_INTERPRETATION: onboarding is fragmented across stale wrappers and the real CLI entrypoint
DATALOX_ACTION: rewrite the host-facing setup docs to use datalox adopt, datalox bootstrap, datalox setup, and bin/setup-multi-agent.sh only
DATALOX_DECISION: record_trace
EOF
fi
`,
      "utf8",
    );
    await chmod(fakeCodexPath, 0o755);

    const runWrapped = () => spawnSync(
      "node",
      [
        builtCliPath,
        "codex",
        "--repo",
        hostDir,
        "--post-run-mode",
        "promote",
        "--codex-bin",
        fakeCodexPath,
        "--json",
        "--",
        "exec",
        "--skip-git-repo-check",
        "Inspect the repo setup instructions. If there is a reusable setup gap, explain the correction for future agents in one short paragraph.",
      ],
      {
        cwd: repoRoot,
        encoding: "utf8",
      },
    );

    const first = runWrapped();
    expect(first.status).toBe(0);
    const firstParsed = JSON.parse(first.stdout);
    expect(firstParsed.postRun.result.decision.action).toBe("create_note_from_gap");
    expect(firstParsed.postRun.result.promotion.note.payload.kind).toBe("workflow_note");

    const second = runWrapped();
    expect(second.status).toBe(0);
    const secondParsed = JSON.parse(second.stdout);
    expect(secondParsed.postRun.result.decision.action).toBe("create_note_from_gap");
    expect(secondParsed.postRun.result.promotion.note.relativePath).toBe(
      firstParsed.postRun.result.promotion.note.relativePath,
    );

    const noteFile = await readFile(path.join(hostDir, firstParsed.postRun.result.promotion.note.relativePath), "utf8");
    expect(noteFile).toContain("kind: workflow_note");
    expect(noteFile).not.toContain("kind: trace");
    expect(noteFile).toContain("workflow: unknown");
    expect(noteFile).not.toContain("Add a concrete observed case here");
    expect(noteFile).not.toContain("Add a concrete source, reviewer note, or case trace here");
    expect(noteFile).not.toContain("Add a wiki page path such as agent-wiki/notes/example.md");
  }, 60000);

  it("runs a second-pass Codex reviewer and persists reusable knowledge when review mode is enabled", async () => {
    const hostDir = await adoptHostRepo();
    const fakeCodexPath = path.join(hostDir, "fake-codex-review.sh");
    await writeFile(
      fakeCodexPath,
      `#!/usr/bin/env bash
node - <<'EOF' "$@"
const args = process.argv.slice(2);
const prompt = args[args.length - 1] || "";
if (process.env.DATALOX_REVIEW_PASS === "1" || prompt.includes("# Datalox Post-Run Review")) {
  process.stdout.write(JSON.stringify({
    action: "persist",
    reason: "the wrapped run discovered a reusable onboarding correction",
    summary: "Codex wrapper runs should expose a committed onboarding bootstrap path",
    title: "Committed onboarding bootstrap path",
    signal: "the repo relied on hidden setup instead of a committed bootstrap step",
    interpretation: "future agents will repeat the same onboarding mistake unless the workflow is written down",
    recommendedAction: "add the committed bootstrap command to the repo guidance before autonomous edits",
    observations: ["wrapped coding run had to reconstruct onboarding from scratch"],
    tags: ["reviewed", "autonomous_review"]
  }));
} else {
  process.stdout.write("Updated the onboarding docs and bootstrap guidance.");
}
EOF
`,
      "utf8",
    );
    await chmod(fakeCodexPath, 0o755);

    const result = spawnSync(
      "node",
      [
        builtCliPath,
        "codex",
        "--repo",
        hostDir,
        "--task",
        "change portable pack loop bridge",
        "--workflow",
        "repo_engineering",
        "--post-run-mode",
        "review",
        "--review-model",
        "gpt-5.4-mini",
        "--codex-bin",
        fakeCodexPath,
        "--json",
        "--",
        "exec",
        "Update the onboarding docs and bootstrap guidance.",
      ],
      {
        cwd: repoRoot,
        encoding: "utf8",
      },
    );

    expect(result.status).toBe(0);
    const parsed = JSON.parse(result.stdout);
    expect(parsed.child.stdout).toBe("Updated the onboarding docs and bootstrap guidance.");
    expect(parsed.postRun.mode).toBe("review");
    expect(parsed.postRun.review.status).toBe("completed");
    expect(parsed.postRun.review.model).toBe("gpt-5.4-mini");
    expect(parsed.postRun.review.decision.action).toBe("persist");
    expect(parsed.postRun.review.persisted.skill.operation).toBe("update_skill");
    expect(parsed.postRun.review.persisted.note.relativePath).toContain("agent-wiki/notes/");
    const logFile = await readFile(path.join(hostDir, "agent-wiki", "log.md"), "utf8");
    expect(logFile).toContain("record_event");
    expect(logFile).toContain("update_skill");
  }, 30000);

  it("sanitizes wrapped transcripts before recording and review so null-byte stderr cannot break the reviewer", async () => {
    const hostDir = await adoptHostRepo();
    const fakeCodexPath = path.join(hostDir, "fake-codex-sanitized-review.sh");
    await writeFile(
      fakeCodexPath,
      `#!/usr/bin/env bash
node - <<'EOF' "$@"
const args = process.argv.slice(2);
const prompt = args[args.length - 1] || "";
if (process.env.DATALOX_REVIEW_PASS === "1" || prompt.includes("# Datalox Post-Run Review")) {
  process.stdout.write(JSON.stringify({
    action: "noop",
    reason: "sanitized transcript remained safe for reviewer input"
  }));
} else {
  process.stdout.write("Visible wrapped answer");
  process.stderr.write("binary prefix \\u0000 survives raw output\\n" + "E".repeat(15000));
}
EOF
`,
      "utf8",
    );
    await chmod(fakeCodexPath, 0o755);

    const result = spawnSync(
      "node",
      [
        builtCliPath,
        "codex",
        "--repo",
        hostDir,
        "--post-run-mode",
        "review",
        "--review-model",
        "gpt-5.4-mini",
        "--codex-bin",
        fakeCodexPath,
        "--json",
        "--",
        "exec",
        "Inspect the wrapped output and keep the reviewer alive.",
      ],
      {
        cwd: repoRoot,
        encoding: "utf8",
      },
    );

    expect(result.status).toBe(0);
    const parsed = JSON.parse(result.stdout);
    expect(parsed.child.stdout).toBe("Visible wrapped answer");
    expect(parsed.child.stderr).not.toContain("\u0000");
    expect(parsed.postRun.mode).toBe("review");
    expect(parsed.postRun.review.status).toBe("completed");
    expect(parsed.postRun.review.decision.action).toBe("noop");

    const eventFiles = await readdir(path.join(hostDir, "agent-wiki", "events"));
    expect(eventFiles.length).toBe(1);
    const eventPayload = JSON.parse(
      await readFile(path.join(hostDir, "agent-wiki", "events", eventFiles[0]), "utf8"),
    );
    expect(eventPayload.transcript).not.toContain("\u0000");
    expect(eventPayload.transcript).toContain("[truncated ");
  }, 30000);

  it("fails generic review mode because autonomous review requires a reviewer-backed wrapper", async () => {
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
        "review ambiguous live dead gate",
        "--workflow",
        "flow_cytometry",
        "--post-run-mode",
        "review",
        "--json",
        "--",
        "node",
        "-e",
        "process.stdout.write('plain wrapped answer')",
      ],
      {
        cwd: repoRoot,
        encoding: "utf8",
      },
    );

    expect(result.status).toBe(1);
    expect(result.stderr).toContain("do not support autonomous review");
  }, 20000);

  it("uses environment defaults so wrapped Codex runs do not need explicit review flags", async () => {
    const hostDir = await adoptHostRepo();
    const fakeCodexPath = path.join(hostDir, "fake-codex-env-review.sh");
    await writeFile(
      fakeCodexPath,
      `#!/usr/bin/env bash
node - <<'EOF' "$@"
const args = process.argv.slice(2);
const prompt = args[args.length - 1] || "";
if (process.env.DATALOX_REVIEW_PASS === "1" || prompt.includes("# Datalox Post-Run Review")) {
  process.stdout.write(JSON.stringify({
    action: "persist",
    reason: "the wrapped run exposed a reusable docs correction",
    summary: "Document the committed bootstrap path before agent edits",
    title: "Document committed bootstrap path",
    signal: "agents had to infer bootstrap state from repo history",
    interpretation: "future runs will repeat the same onboarding mistake unless the path is written down",
    recommendedAction: "record the committed bootstrap command in repo guidance",
    observations: ["wrapped codex run reconstructed bootstrap from scratch"],
    tags: ["reviewed", "env_default"]
  }));
} else {
  process.stdout.write("Updated onboarding guidance.");
}
EOF
`,
      "utf8",
    );
    await chmod(fakeCodexPath, 0o755);

    const result = spawnSync(
      "node",
      [
        builtCliPath,
        "codex",
        "--repo",
        hostDir,
        "--task",
        "change portable pack loop bridge",
        "--workflow",
        "repo_engineering",
        "--codex-bin",
        fakeCodexPath,
        "--json",
        "--",
        "exec",
        "Update onboarding guidance.",
      ],
      {
        cwd: repoRoot,
        encoding: "utf8",
        env: {
          ...process.env,
          DATALOX_DEFAULT_POST_RUN_MODE: "review",
          DATALOX_DEFAULT_REVIEW_MODEL: "gpt-5.4-mini",
        },
      },
    );

    expect(result.status).toBe(0);
    const parsed = JSON.parse(result.stdout);
    expect(parsed.postRun.mode).toBe("review");
    expect(parsed.postRun.review.status).toBe("completed");
    expect(parsed.postRun.review.model).toBe("gpt-5.4-mini");
    expect(parsed.postRun.review.decision.action).toBe("persist");
  }, 30000);

  it("copies wrapper entrypoints and skills into adopted host repos", async () => {
    const hostDir = await adoptHostRepo();

    expect(await readFile(path.join(hostDir, "bin", "datalox-claude.js"), "utf8")).toContain("\"claude\"");
    expect(await readFile(path.join(hostDir, "bin", "datalox-codex.js"), "utf8")).toContain("\"codex\"");
    expect(await readFile(path.join(hostDir, "bin", "datalox-wrap.js"), "utf8")).toContain("\"wrap\"");
    expect(await readFile(path.join(hostDir, "skills", "use-datalox-through-host-cli", "SKILL.md"), "utf8")).toContain("Use Datalox Through Host CLI");
  }, 10000);
});
