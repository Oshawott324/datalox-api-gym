import { spawnSync } from "node:child_process";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import {
  packReplayBundle,
  REPLAY_BUNDLES_RELATIVE_DIR,
  ReplayBundleVerificationError,
  verifyReplayBundle,
} from "../src/core/replayBundle.js";
import { AGENT_TURNS_RELATIVE_DIR } from "../src/core/agentTurnStore.js";
import { recordToolIo, TOOL_IO_RECORDS_RELATIVE_DIR } from "../src/core/toolIoStore.js";

const repoRoot = process.cwd();
const builtCliPath = path.join(repoRoot, "dist", "src", "cli", "main.js");

describe("replay_bundle.v1 pack and verify", () => {
  const tempDirs: string[] = [];

  afterEach(async () => {
    await Promise.all(tempDirs.splice(0).map((dir) => rm(dir, { recursive: true, force: true })));
  });

  async function makeTempRepo(): Promise<string> {
    const tempDir = await mkdtemp(path.join(tmpdir(), "datalox-replay-bundle-"));
    tempDirs.push(tempDir);
    return tempDir;
  }

  async function writeAgentTurn(repoPath: string, id: string, sessionId = "session-1"): Promise<string> {
    const relativePath = path.join(AGENT_TURNS_RELATIVE_DIR, `${id}.json`);
    const absolutePath = path.join(repoPath, relativePath);
    await mkdir(path.dirname(absolutePath), { recursive: true });
    await writeFile(absolutePath, `${JSON.stringify({
      schema_version: "agent_turn.v1",
      id,
      session_id: sessionId,
      turn_index: 0,
      created_at: "2026-05-16T00:00:00.000Z",
      user_prompt: "Find the reimbursement policy.",
      assistant_summary: "Searched the policy tool and returned the matching policy rows.",
      tool_calls: [
        {
          tool: "search_policy",
          call_id: "call-1",
          args_summary: "taxi reimbursement",
        },
      ],
      verification: {
        status: "passed",
        evidence: "Tool returned two relevant policy documents.",
      },
      export: {
        allowed: true,
        redaction: "none_needed",
      },
    }, null, 2)}\n`, "utf8");
    return relativePath;
  }

  async function seedReplaySources(repoPath: string): Promise<void> {
    await recordToolIo({
      repoPath,
      sessionId: "session-1",
      turnId: "turn-1",
      callId: "call-1",
      toolName: "search_policy",
      arguments: {
        query: "Beijing business-trip taxi reimbursement limit",
        top_k: 5,
      },
      observation: {
        status: "ok",
        content: ["doc1 ...", "doc2 ..."],
      },
      export: {
        allowed: true,
        redaction: "none_needed",
      },
      now: new Date("2026-05-16T00:00:00.000Z"),
    });
    await writeAgentTurn(repoPath, "turn-1");
  }

  async function packSeededBundle(repoPath: string, bundleId: string) {
    await seedReplaySources(repoPath);
    return packReplayBundle({
      repoPath,
      bundleId,
      now: new Date("2026-05-16T01:00:00.000Z"),
      export: {
        allowed: true,
        redaction: "none_needed",
      },
    });
  }

  it("packs deterministic manifests and checksums, then verifies immediately", async () => {
    const repoPath = await makeTempRepo();
    const result = await packSeededBundle(repoPath, "bundle-one");

    expect(result.bundlePath).toBe(`${REPLAY_BUNDLES_RELATIVE_DIR}/bundle-one`);
    expect(result.manifest).toMatchObject({
      schema_version: "replay_bundle.v1",
      id: "bundle-one",
      created_at: "2026-05-16T01:00:00.000Z",
      source: {
        repo_path: repoPath,
        session_ids: ["session-1"],
      },
      replay: {
        tool_record_count: 1,
        turn_count: 1,
        deterministic: true,
      },
      checksums_path: "checksums.json",
      export: {
        allowed: true,
        redaction: "none_needed",
      },
    });
    expect(result.manifest.source.tool_io_record_paths).toHaveLength(1);
    expect(result.manifest.source.tool_io_record_paths[0]).toMatch(/^tool-io\/.+\.json$/);
    expect(result.manifest.source.turn_event_paths).toEqual(["agent-turns/turn-1.json"]);
    expect(result.checksums.files.map((entry) => entry.path)).toEqual([
      "agent-turns/turn-1.json",
      "manifest.json",
      result.manifest.source.tool_io_record_paths[0],
    ].sort());

    await expect(verifyReplayBundle({
      repoPath,
      bundlePath: result.bundlePath,
    })).resolves.toMatchObject({
      verified: true,
      checkedFiles: 3,
      manifest: {
        id: "bundle-one",
      },
    });
  });

  it("verifies a sealed bundle after source tool and turn stores are removed", async () => {
    const repoPath = await makeTempRepo();
    const result = await packSeededBundle(repoPath, "bundle-without-source");

    await rm(path.join(repoPath, TOOL_IO_RECORDS_RELATIVE_DIR), { recursive: true, force: true });
    await rm(path.join(repoPath, AGENT_TURNS_RELATIVE_DIR), { recursive: true, force: true });

    await expect(verifyReplayBundle({
      repoPath,
      bundlePath: result.bundlePath,
    })).resolves.toMatchObject({
      verified: true,
      manifest: {
        id: "bundle-without-source",
      },
    });
  });

  it("fails verification when a bundled file is modified", async () => {
    const repoPath = await makeTempRepo();
    const result = await packSeededBundle(repoPath, "bundle-modified");
    const toolRecordPath = path.join(repoPath, result.bundlePath, result.manifest.source.tool_io_record_paths[0]);

    await writeFile(toolRecordPath, `${JSON.stringify({
      schema_version: "tool_io_record.v1",
      id: "tampered",
    }, null, 2)}\n`, "utf8");

    await expect(verifyReplayBundle({
      repoPath,
      bundlePath: result.bundlePath,
    })).rejects.toMatchObject({
      issues: expect.arrayContaining([
        expect.stringContaining("checksum_mismatch"),
      ]),
    });
  });

  it("fails verification when a bundled file is removed", async () => {
    const repoPath = await makeTempRepo();
    const result = await packSeededBundle(repoPath, "bundle-removed");

    await rm(path.join(repoPath, result.bundlePath, "agent-turns", "turn-1.json"));

    await expect(verifyReplayBundle({
      repoPath,
      bundlePath: result.bundlePath,
    })).rejects.toMatchObject({
      issues: expect.arrayContaining([
        "listed_file_missing: agent-turns/turn-1.json",
      ]),
    });
  });

  it("fails verification when an unlisted file is added", async () => {
    const repoPath = await makeTempRepo();
    const result = await packSeededBundle(repoPath, "bundle-added");

    await writeFile(path.join(repoPath, result.bundlePath, "extra.json"), "{}\n", "utf8");

    await expect(verifyReplayBundle({
      repoPath,
      bundlePath: result.bundlePath,
    })).rejects.toMatchObject({
      issues: expect.arrayContaining([
        "unlisted_file_present: extra.json",
      ]),
    });
  });

  it("fails verification when the manifest points outside bundle artifact roots", async () => {
    const repoPath = await makeTempRepo();
    const result = await packSeededBundle(repoPath, "bundle-outside-path");
    const manifestPath = path.join(repoPath, result.bundlePath, "manifest.json");
    const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
    manifest.source.tool_io_record_paths = ["../tool-io/record.json"];
    await writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");

    await expect(verifyReplayBundle({
      repoPath,
      bundlePath: result.bundlePath,
    })).rejects.toBeInstanceOf(ReplayBundleVerificationError);
  });

  it("packs and verifies through the built CLI", async () => {
    const repoPath = await makeTempRepo();
    await seedReplaySources(repoPath);

    const pack = spawnSync("node", [
      builtCliPath,
      "bundle",
      "pack",
      "--repo",
      repoPath,
      "--bundle-id",
      "cli-bundle",
      "--json",
    ], {
      cwd: repoPath,
      encoding: "utf8",
    });

    expect(pack.status).toBe(0);
    const parsedPack = JSON.parse(pack.stdout);
    expect(parsedPack.manifest.id).toBe("cli-bundle");

    const verify = spawnSync("node", [
      builtCliPath,
      "bundle",
      "verify",
      "--repo",
      repoPath,
      "--bundle",
      parsedPack.bundlePath,
      "--json",
    ], {
      cwd: repoPath,
      encoding: "utf8",
    });

    expect(verify.status).toBe(0);
    expect(JSON.parse(verify.stdout)).toMatchObject({
      verified: true,
      manifest: {
        id: "cli-bundle",
      },
    });
  });
});
