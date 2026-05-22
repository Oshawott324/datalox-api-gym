import { cp, mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { listInstalledFixtures } from "../src/core/fixtures/fixtureCache.js";
import { installFixturePack } from "../src/core/fixtures/installFixturePack.js";
import { resolveFixtureRuntime } from "../src/core/fixtures/resolveFixtureRuntime.js";
import { sha256Hex } from "../src/core/hash.js";
import { recordMcpToolCatalog } from "../src/core/mcpToolCatalogStore.js";
import { packReplayBundle } from "../src/core/replayBundle.js";
import { recordToolIo } from "../src/core/toolIoStore.js";

const tempDirs: string[] = [];

afterEach(async () => {
  await Promise.all(tempDirs.splice(0).map((dir) => rm(dir, { recursive: true, force: true })));
});

async function makeTempDir(prefix: string): Promise<string> {
  const dir = await mkdtemp(path.join(tmpdir(), prefix));
  tempDirs.push(dir);
  return dir;
}

async function createFixtureRepo(): Promise<{
  root: string;
  catalogPath: string;
  fixtureDir: string;
  fixtureRef: string;
}> {
  const root = await makeTempDir("datalox-fixture-install-repo-");
  const fixtureId = "github-pr-review-basic";
  const version = "2026-05.0";
  const fixtureRef = `${fixtureId}@${version}`;
  const fixtureDir = path.join(root, "fixtures", fixtureId);
  const sourceRepo = path.join(root, "source");
  await mkdir(fixtureDir, { recursive: true });
  await mkdir(sourceRepo, { recursive: true });
  await mkdir(path.join(fixtureDir, "tasks"), { recursive: true });
  await mkdir(path.join(fixtureDir, "verifiers"), { recursive: true });
  await mkdir(path.join(fixtureDir, "scaffolds"), { recursive: true });

  await recordToolIo({
    repoPath: sourceRepo,
    sessionId: "session-1",
    turnId: "turn-1",
    callId: "call-1",
    toolName: "github_pull_request_get",
    arguments: {
      owner: "datalox",
      repo: "demo",
      pull_number: 42,
    },
    observation: {
      status: "ok",
      content: {
        number: 42,
        title: "Fix replay fixture install",
      },
    },
    export: {
      allowed: true,
      redaction: "none_needed",
    },
    now: new Date("2026-05-20T00:00:00.000Z"),
  });
  await recordMcpToolCatalog({
    repoPath: sourceRepo,
    upstream: {
      command: "github-mcp",
      args: [],
    },
    listToolsResult: {
      tools: [
        {
          name: "github_pull_request_get",
          inputSchema: {
            type: "object",
            properties: {
              owner: { type: "string" },
              repo: { type: "string" },
              pull_number: { type: "number" },
            },
            required: ["owner", "repo", "pull_number"],
          },
        },
      ],
    },
    export: {
      allowed: true,
      redaction: "none_needed",
      approval_id: "fixture-public",
    },
    now: new Date("2026-05-20T00:30:00.000Z"),
  });

  const bundle = await packReplayBundle({
    repoPath: sourceRepo,
    sourceRepoPath: ".",
    bundleId: fixtureId,
    now: new Date("2026-05-20T01:00:00.000Z"),
    export: {
      allowed: true,
      redaction: "none_needed",
      approval_id: "fixture-public",
    },
  });
  const fixtureBundleDir = path.join(fixtureDir, "replay-bundle", fixtureId);
  await mkdir(path.dirname(fixtureBundleDir), { recursive: true });
  await cp(path.join(sourceRepo, bundle.bundlePath), fixtureBundleDir, { recursive: true });
  const bundleSha256 = sha256Hex(await readFile(path.join(fixtureBundleDir, "checksums.json")));

  await writeFile(path.join(fixtureDir, "tasks", "github-pr-review-risk.json"), `${JSON.stringify({
    schema_version: "datalox_task_spec.v1",
    id: "github-pr-review-risk",
    version,
    name: "GitHub PR Review Risk",
    description: "Find the actionable correctness risk in a replayed pull request.",
    goal: "Inspect PR #42 and report the main risk.",
    fixtureRefs: [fixtureRef],
    allowedTools: ["github_pull_request_get"],
    successCriteria: ["Names the risky file and explains the failure mode."],
  }, null, 2)}\n`);
  await writeFile(path.join(fixtureDir, "verifiers", "github-pr-review-risk.json"), `${JSON.stringify({
    schema_version: "datalox_verifier_spec.v1",
    id: "github-pr-review-risk-verifier",
    version,
    name: "GitHub PR Review Risk Verifier",
    description: "Metadata for verifying the PR review answer.",
    verifier: {
      kind: "command",
      command: "node",
      args: ["verifiers/github-pr-review-risk.mjs"],
    },
    requiredEvidence: ["replay_bundle", "tool_io_records"],
    reward: {
      type: "binary",
      version: "risk-v1",
    },
  }, null, 2)}\n`);
  await writeFile(path.join(fixtureDir, "scaffolds", "codex-review.json"), `${JSON.stringify({
    schema_version: "datalox_scaffold_spec.v1",
    id: "codex-review-scaffold",
    version,
    name: "Codex Review Scaffold",
    description: "A prompt/tool contract for replayed PR review tasks.",
    harness: "codex",
    promptContract: "Use only replayed GitHub tools.",
    modelVisibleTools: ["github_pull_request_get"],
    contextPolicy: {
      maxTurns: 4,
      allowedFixtureRefs: [fixtureRef],
    },
  }, null, 2)}\n`);

  const manifest = {
    $schema: "../../schemas/fixture-manifest.schema.json",
    id: fixtureId,
    version,
    name: "GitHub PR Review Basic",
    description: "A finite GitHub pull request review world.",
    status: "verified",
    engine: {
      package: "datalox-agent-replay",
      minimumVersion: "0.1.0",
    },
    tools: [
      {
        surface: "mcp",
        server: "github",
        operations: ["pull_request.get"],
      },
    ],
    bundle: {
      path: `replay-bundle/${fixtureId}`,
      schemaVersion: "replay_bundle.v1",
      sha256: bundleSha256,
    },
    evalPrompts: {
      path: "eval-prompts.jsonl",
      count: 1,
    },
    specs: {
      taskSpecs: [{ path: "tasks/github-pr-review-risk.json" }],
      verifierSpecs: [{ path: "verifiers/github-pr-review-risk.json" }],
      scaffoldSpecs: [{ path: "scaffolds/codex-review.json" }],
    },
    provenance: {
      source: "curated-recording",
      recordedAt: "2026-05-20",
      reviewedBy: "datalox",
      redaction: "none_needed",
    },
    release: {
      immutable: false,
      license: "UNRELEASED",
      tags: ["github"],
    },
  };
  await writeFile(path.join(fixtureDir, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);
  await writeFile(path.join(fixtureDir, "eval-prompts.jsonl"), `${JSON.stringify({
    id: "github-pr-review-basic.summary.v1",
    prompt: "Inspect PR #42.",
  })}\n`);

  const catalog = {
    schema_version: "datalox_fixture_catalog.v1",
    repository: {
      name: "datalox-replay-fixtures",
      package: "@datalox/replay-fixtures",
    },
    engine_contract: {
      package: "datalox-agent-replay",
      minimum_version: "0.1.0",
      commands: {
        install_fixture: "datalox fixtures install <fixture-ref>",
      },
    },
    fixtures: [
      {
        id: fixtureId,
        version,
        ref: fixtureRef,
        name: manifest.name,
        description: manifest.description,
        status: manifest.status,
        source_path: `fixtures/${fixtureId}`,
        manifest_path: `fixtures/${fixtureId}/manifest.json`,
        tools: manifest.tools,
        tags: manifest.release.tags,
        bundle: {
          path: `fixtures/${fixtureId}/replay-bundle/${fixtureId}`,
          schema_version: "replay_bundle.v1",
          sha256: bundleSha256,
        },
        eval_prompts: {
          path: `fixtures/${fixtureId}/eval-prompts.jsonl`,
          count: 1,
        },
        specs: {
          task_specs: [
            {
              path: `fixtures/${fixtureId}/tasks/github-pr-review-risk.json`,
              id: "github-pr-review-risk",
              version,
            },
          ],
          verifier_specs: [
            {
              path: `fixtures/${fixtureId}/verifiers/github-pr-review-risk.json`,
              id: "github-pr-review-risk-verifier",
              version,
            },
          ],
          scaffold_specs: [
            {
              path: `fixtures/${fixtureId}/scaffolds/codex-review.json`,
              id: "codex-review-scaffold",
              version,
            },
          ],
        },
        release: {
          immutable: false,
          license: "UNRELEASED",
          archive_path: `archives/fixtures/${fixtureId}-${version}.tgz`,
          checksum_path: `archives/fixtures/${fixtureId}-${version}.tgz.sha256`,
        },
      },
    ],
    fixture_sets: [],
  };
  const catalogPath = path.join(root, "catalog.json");
  await writeFile(catalogPath, `${JSON.stringify(catalog, null, 2)}\n`);

  return { root, catalogPath, fixtureDir, fixtureRef };
}

describe("fixture install/cache", () => {
  it("fails clearly when resolving a fixture that has not been installed", async () => {
    const cacheRoot = await makeTempDir("datalox-fixture-cache-missing-");

    await expect(resolveFixtureRuntime({
      ref: "github-pr-review-basic@2026-05.0",
      cacheRoot,
    })).rejects.toThrow(/Installed fixture github-pr-review-basic@2026-05\.0 was not found/);
  });

  it("installs one fixture from a local catalog and resolves its runtime", async () => {
    const fixtureRepo = await createFixtureRepo();
    const cacheRoot = await makeTempDir("datalox-fixture-cache-");

    const install = await installFixturePack({
      ref: fixtureRepo.fixtureRef,
      catalogPath: fixtureRepo.catalogPath,
      cacheRoot,
    });

    expect(install).toMatchObject({
      ref: fixtureRepo.fixtureRef,
      alreadyInstalled: false,
      verified: true,
      bundleId: "github-pr-review-basic",
      specs: {
        taskSpecs: [
          {
            id: "github-pr-review-risk",
            ref: "github-pr-review-risk@2026-05.0",
            path: "tasks/github-pr-review-risk.json",
          },
        ],
      },
    });
    expect(install.cachePath).toBe(path.join(cacheRoot, "github-pr-review-basic", "2026-05.0"));
    expect(install.specs.taskSpecs[0].absolutePath).toBe(
      path.join(install.cachePath, "tasks", "github-pr-review-risk.json"),
    );

    const runtime = await resolveFixtureRuntime({
      ref: fixtureRepo.fixtureRef,
      cacheRoot,
    });
    expect(runtime).toMatchObject({
      ref: fixtureRepo.fixtureRef,
      bundleId: "github-pr-review-basic",
      toolCatalogCount: 1,
      toolCatalogPaths: [
        expect.stringMatching(/^mcp-tool-catalogs\/mcp-tool-catalog-/),
      ],
      specs: {
        taskSpecs: [
          {
            id: "github-pr-review-risk",
            ref: "github-pr-review-risk@2026-05.0",
            path: "tasks/github-pr-review-risk.json",
          },
        ],
        verifierSpecs: [
          {
            id: "github-pr-review-risk-verifier",
            ref: "github-pr-review-risk-verifier@2026-05.0",
            path: "verifiers/github-pr-review-risk.json",
          },
        ],
        scaffoldSpecs: [
          {
            id: "codex-review-scaffold",
            ref: "codex-review-scaffold@2026-05.0",
            path: "scaffolds/codex-review.json",
          },
        ],
      },
      export: {
        allowed: true,
        redaction: "none_needed",
        approval_id: "fixture-public",
      },
    });
    expect(runtime.toolCatalogAbsolutePaths).toHaveLength(1);
    expect(runtime.toolCatalogAbsolutePaths[0]).toBe(path.join(runtime.bundlePath, runtime.toolCatalogPaths[0]));
  });

  it("is idempotent when the same verified fixture is already cached", async () => {
    const fixtureRepo = await createFixtureRepo();
    const cacheRoot = await makeTempDir("datalox-fixture-cache-idempotent-");

    await installFixturePack({
      ref: fixtureRepo.fixtureRef,
      catalogPath: fixtureRepo.catalogPath,
      cacheRoot,
    });
    const second = await installFixturePack({
      ref: fixtureRepo.fixtureRef,
      catalogPath: fixtureRepo.catalogPath,
      cacheRoot,
    });

    expect(second.alreadyInstalled).toBe(true);
  });

  it("installs one fixture directly from a local fixture directory and lists it from cache", async () => {
    const fixtureRepo = await createFixtureRepo();
    const cacheRoot = await makeTempDir("datalox-fixture-cache-direct-");

    const install = await installFixturePack({
      sourcePath: fixtureRepo.fixtureDir,
      cacheRoot,
    });

    expect(install).toMatchObject({
      ref: fixtureRepo.fixtureRef,
      alreadyInstalled: false,
      verified: true,
      bundleId: "github-pr-review-basic",
    });

    const installed = await listInstalledFixtures({ cacheRoot });
    expect(installed.map((fixture) => fixture.ref)).toEqual([fixtureRepo.fixtureRef]);
    expect(installed[0]).toMatchObject({
      status: "verified",
      bundleSha256: install.bundleSha256,
      tools: [
        {
          surface: "mcp",
          server: "github",
          operations: ["pull_request.get"],
        },
      ],
    });
  });

  it("refuses to install a fixture whose bundle checksum does not match its manifest", async () => {
    const fixtureRepo = await createFixtureRepo();
    const cacheRoot = await makeTempDir("datalox-fixture-cache-tamper-");
    const manifestPath = path.join(fixtureRepo.root, "fixtures", "github-pr-review-basic", "manifest.json");
    const manifest = JSON.parse(await readFile(manifestPath, "utf8")) as {
      bundle: { sha256: string };
    };
    manifest.bundle.sha256 = "f".repeat(64);
    await writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);

    await expect(installFixturePack({
      ref: fixtureRepo.fixtureRef,
      catalogPath: fixtureRepo.catalogPath,
      cacheRoot,
    })).rejects.toThrow(/Catalog bundle digest|Fixture bundle digest/);
  });

  it("refuses to install a fixture with an invalid referenced task spec", async () => {
    const fixtureRepo = await createFixtureRepo();
    const cacheRoot = await makeTempDir("datalox-fixture-cache-bad-spec-");
    await writeFile(
      path.join(fixtureRepo.root, "fixtures", "github-pr-review-basic", "tasks", "github-pr-review-risk.json"),
      `${JSON.stringify({
        schema_version: "datalox_task_spec.v1",
        id: "github-pr-review-risk",
        version: "2026-05.0",
        name: "GitHub PR Review Risk",
        description: "Missing success criteria.",
        goal: "Inspect PR #42.",
      }, null, 2)}\n`,
    );

    await expect(installFixturePack({
      ref: fixtureRepo.fixtureRef,
      catalogPath: fixtureRepo.catalogPath,
      cacheRoot,
    })).rejects.toThrow(/Invalid task spec/);
  });
});
