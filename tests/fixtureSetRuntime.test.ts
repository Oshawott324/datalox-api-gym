import { cp, mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { installFixtureSet } from "../src/core/fixtures/installFixtureSet.js";
import { resolveFixtureSetRuntime } from "../src/core/fixtures/resolveFixtureSetRuntime.js";
import { FixtureToolCollisionError } from "../src/core/fixtures/validateToolCollisions.js";
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

interface FixtureSpec {
  id: string;
  toolName: string;
  server: string;
}

async function writeFixture(root: string, spec: FixtureSpec): Promise<{
  ref: string;
  catalogEntry: Record<string, unknown>;
}> {
  const version = "2026-05.0";
  const ref = `${spec.id}@${version}`;
  const fixtureDir = path.join(root, "fixtures", spec.id);
  const sourceRepo = path.join(root, "sources", spec.id);
  await mkdir(fixtureDir, { recursive: true });
  await mkdir(sourceRepo, { recursive: true });

  await recordToolIo({
    repoPath: sourceRepo,
    sessionId: `${spec.id}-session`,
    turnId: `${spec.id}-turn`,
    callId: `${spec.id}-call`,
    toolName: spec.toolName,
    arguments: {
      id: spec.id,
    },
    observation: {
      status: "ok",
      content: {
        fixture: spec.id,
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
    bundleId: spec.id,
    now: new Date("2026-05-20T01:00:00.000Z"),
    export: {
      allowed: true,
      redaction: "none_needed",
      approval_id: "fixture-public",
    },
  });
  const fixtureBundleDir = path.join(fixtureDir, "replay-bundle", spec.id);
  await mkdir(path.dirname(fixtureBundleDir), { recursive: true });
  await cp(path.join(sourceRepo, bundle.bundlePath), fixtureBundleDir, { recursive: true });
  const bundleSha256 = sha256Hex(await readFile(path.join(fixtureBundleDir, "checksums.json")));
  const manifest = {
    $schema: "../../schemas/fixture-manifest.schema.json",
    id: spec.id,
    version,
    name: spec.id,
    description: `Fixture ${spec.id}.`,
    status: "verified",
    engine: {
      package: "datalox-api-gym",
      minimumVersion: "0.1.0",
    },
    tools: [
      {
        surface: "mcp",
        server: spec.server,
        operations: [spec.toolName],
      },
    ],
    bundle: {
      path: `replay-bundle/${spec.id}`,
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
      tags: [spec.server],
    },
  };
  await writeFile(path.join(fixtureDir, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);
  await writeFile(path.join(fixtureDir, "eval-prompts.jsonl"), "{}\n");

  return {
    ref,
    catalogEntry: {
      id: spec.id,
      version,
      ref,
      name: manifest.name,
      description: manifest.description,
      status: manifest.status,
      source_path: `fixtures/${spec.id}`,
      manifest_path: `fixtures/${spec.id}/manifest.json`,
      tools: manifest.tools,
      tags: manifest.release.tags,
      bundle: {
        path: `fixtures/${spec.id}/replay-bundle/${spec.id}`,
        schema_version: "replay_bundle.v1",
        sha256: bundleSha256,
      },
      eval_prompts: {
        path: `fixtures/${spec.id}/eval-prompts.jsonl`,
        count: 1,
      },
      release: {
        immutable: false,
        license: "UNRELEASED",
        archive_path: `archives/fixtures/${spec.id}-${version}.tgz`,
        checksum_path: `archives/fixtures/${spec.id}-${version}.tgz.sha256`,
      },
    },
  };
}

async function createFixtureSetRepo(options?: { collide?: boolean }): Promise<{
  catalogPath: string;
  fixtureSetRef: string;
}> {
  const root = await makeTempDir("datalox-fixture-set-runtime-");
  const slack = await writeFixture(root, {
    id: "slack-support-thread-basic",
    toolName: "slack_conversation_replies",
    server: "slack",
  });
  const search = await writeFixture(root, {
    id: "search-policy-corpus-basic",
    toolName: options?.collide ? "slack_conversation_replies" : "search_query",
    server: "search",
  });
  const fixtureSetId = options?.collide ? "collision-set-basic" : "support-triage-basic";
  const version = "2026-05.0";
  const fixtureSetRef = `${fixtureSetId}@${version}`;
  const fixtureSetDir = path.join(root, "fixture-sets", fixtureSetId);
  await mkdir(fixtureSetDir, { recursive: true });
  await mkdir(path.join(fixtureSetDir, "tasks"), { recursive: true });
  await mkdir(path.join(fixtureSetDir, "verifiers"), { recursive: true });
  await mkdir(path.join(fixtureSetDir, "scaffolds"), { recursive: true });
  await writeFile(path.join(fixtureSetDir, "tasks", "support-triage.json"), `${JSON.stringify({
    schema_version: "datalox_task_spec.v1",
    id: "support-triage",
    version,
    name: "Support triage",
    description: "Summarize support context with search grounding.",
    goal: "Use Slack and search fixtures to draft a support response.",
    fixtureRefs: [slack.ref, search.ref],
    allowedTools: ["slack_conversation_replies", "search_query"],
    successCriteria: ["Summarizes the customer issue.", "Cites the relevant policy."],
  }, null, 2)}\n`);
  await writeFile(path.join(fixtureSetDir, "verifiers", "support-triage.json"), `${JSON.stringify({
    schema_version: "datalox_verifier_spec.v1",
    id: "support-triage-verifier",
    version,
    name: "Support triage verifier",
    description: "Metadata for support triage answer verification.",
    verifier: {
      kind: "manual",
    },
    requiredEvidence: ["replay_bundle", "tool_io_records"],
    reward: {
      type: "rubric",
      version: "support-v1",
    },
  }, null, 2)}\n`);
  await writeFile(path.join(fixtureSetDir, "scaffolds", "support-agent.json"), `${JSON.stringify({
    schema_version: "datalox_scaffold_spec.v1",
    id: "support-agent-scaffold",
    version,
    name: "Support agent scaffold",
    description: "A support-agent prompt/tool contract.",
    harness: "codex",
    promptContract: "Use the replayed Slack and search tools only.",
    modelVisibleTools: ["slack_conversation_replies", "search_query"],
  }, null, 2)}\n`);
  const fixtureSetManifest = {
    $schema: "../../schemas/fixture-set-manifest.schema.json",
    id: fixtureSetId,
    version,
    name: fixtureSetId,
    description: "Composed world set.",
    status: "verified",
    fixtures: [slack.ref, search.ref],
    evalPrompts: {
      path: "eval-prompts.jsonl",
      count: 1,
    },
    specs: {
      taskSpecs: [{ path: "tasks/support-triage.json" }],
      verifierSpecs: [{ path: "verifiers/support-triage.json" }],
      scaffoldSpecs: [{ path: "scaffolds/support-agent.json" }],
    },
    release: {
      immutable: false,
      license: "UNRELEASED",
      tags: ["support"],
    },
  };
  await writeFile(path.join(fixtureSetDir, "manifest.json"), `${JSON.stringify(fixtureSetManifest, null, 2)}\n`);
  await writeFile(path.join(fixtureSetDir, "eval-prompts.jsonl"), "{}\n");

  const catalog = {
    schema_version: "datalox_fixture_catalog.v1",
    repository: {
      name: "datalox-api-gym-worlds",
      package: "@datalox/api-gym-worlds",
    },
    engine_contract: {
      package: "datalox-api-gym",
      minimum_version: "0.1.0",
      commands: {
        install_fixture_set: "datalox fixture-sets install <fixture-set-ref>",
      },
    },
    fixtures: [slack.catalogEntry, search.catalogEntry],
    fixture_sets: [
      {
        id: fixtureSetId,
        version,
        ref: fixtureSetRef,
        name: fixtureSetManifest.name,
        description: fixtureSetManifest.description,
        status: fixtureSetManifest.status,
        source_path: `fixture-sets/${fixtureSetId}`,
        manifest_path: `fixture-sets/${fixtureSetId}/manifest.json`,
        fixtures: fixtureSetManifest.fixtures,
        tags: fixtureSetManifest.release.tags,
        eval_prompts: {
          path: `fixture-sets/${fixtureSetId}/eval-prompts.jsonl`,
          count: 1,
        },
        specs: {
          task_specs: [
            {
              path: `fixture-sets/${fixtureSetId}/tasks/support-triage.json`,
              id: "support-triage",
              version,
            },
          ],
          verifier_specs: [
            {
              path: `fixture-sets/${fixtureSetId}/verifiers/support-triage.json`,
              id: "support-triage-verifier",
              version,
            },
          ],
          scaffold_specs: [
            {
              path: `fixture-sets/${fixtureSetId}/scaffolds/support-agent.json`,
              id: "support-agent-scaffold",
              version,
            },
          ],
        },
        release: {
          immutable: false,
          license: "UNRELEASED",
          archive_path: `archives/fixture-sets/${fixtureSetId}-${version}.tgz`,
          checksum_path: `archives/fixture-sets/${fixtureSetId}-${version}.tgz.sha256`,
        },
      },
    ],
  };
  const catalogPath = path.join(root, "catalog.json");
  await writeFile(catalogPath, `${JSON.stringify(catalog, null, 2)}\n`);
  return { catalogPath, fixtureSetRef };
}

describe("world set runtime", () => {
  it("installs a world set by installing member fixtures without copying replay data into the set", async () => {
    const fixtureRepo = await createFixtureSetRepo();
    const cacheRoot = await makeTempDir("datalox-fixture-set-cache-");

    const install = await installFixtureSet({
      ref: fixtureRepo.fixtureSetRef,
      catalogPath: fixtureRepo.catalogPath,
      cacheRoot,
    });

    expect(install.ref).toBe(fixtureRepo.fixtureSetRef);
    expect(install.fixtures.map((fixture) => fixture.ref)).toEqual([
      "slack-support-thread-basic@2026-05.0",
      "search-policy-corpus-basic@2026-05.0",
    ]);
    expect(existsSync(path.join(install.cachePath, "replay-bundle"))).toBe(false);

    const runtime = await resolveFixtureSetRuntime({
      ref: fixtureRepo.fixtureSetRef,
      cacheRoot,
    });
    expect(runtime.activeFixtureRefs).toEqual([
      "slack-support-thread-basic@2026-05.0",
      "search-policy-corpus-basic@2026-05.0",
    ]);
    expect(runtime.bundlePaths).toHaveLength(2);
    expect(runtime.specs).toMatchObject({
      taskSpecs: [
        {
          id: "support-triage",
          ref: "support-triage@2026-05.0",
          path: "tasks/support-triage.json",
        },
      ],
      verifierSpecs: [
        {
          id: "support-triage-verifier",
          ref: "support-triage-verifier@2026-05.0",
          path: "verifiers/support-triage.json",
        },
      ],
      scaffoldSpecs: [
        {
          id: "support-agent-scaffold",
          ref: "support-agent-scaffold@2026-05.0",
          path: "scaffolds/support-agent.json",
        },
      ],
    });
  });

  it("fails before replay when member fixtures expose colliding tool names", async () => {
    const fixtureRepo = await createFixtureSetRepo({ collide: true });
    const cacheRoot = await makeTempDir("datalox-fixture-set-cache-collision-");
    await installFixtureSet({
      ref: fixtureRepo.fixtureSetRef,
      catalogPath: fixtureRepo.catalogPath,
      cacheRoot,
    });

    await expect(resolveFixtureSetRuntime({
      ref: fixtureRepo.fixtureSetRef,
      cacheRoot,
    })).rejects.toBeInstanceOf(FixtureToolCollisionError);
  });
});
