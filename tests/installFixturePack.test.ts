import { cp, mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { listInstalledFixtures } from "../src/core/fixtures/fixtureCache.js";
import { installFixturePack } from "../src/core/fixtures/installFixturePack.js";
import { resolveFixtureRuntime } from "../src/core/fixtures/resolveFixtureRuntime.js";
import { sha256Hex } from "../src/core/hash.js";
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
    });
    expect(install.cachePath).toBe(path.join(cacheRoot, "github-pr-review-basic", "2026-05.0"));

    const runtime = await resolveFixtureRuntime({
      ref: fixtureRepo.fixtureRef,
      cacheRoot,
    });
    expect(runtime).toMatchObject({
      ref: fixtureRepo.fixtureRef,
      bundleId: "github-pr-review-basic",
      toolCatalogCount: 0,
      export: {
        allowed: true,
        redaction: "none_needed",
        approval_id: "fixture-public",
      },
    });
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
});
