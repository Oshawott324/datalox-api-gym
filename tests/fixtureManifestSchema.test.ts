import { mkdir, mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { parseFixtureRef } from "../src/core/fixtures/fixtureRef.js";
import { parseFixtureManifest } from "../src/core/fixtures/fixtureManifestSchema.js";
import { parseFixtureSetManifest } from "../src/core/fixtures/fixtureSetSchema.js";
import { readFixtureManifest, readFixtureSetManifest } from "../src/core/fixtures/readFixtureManifest.js";

const sha256 = "0".repeat(64);

function fixtureManifest(overrides: Record<string, unknown> = {}) {
  return {
    $schema: "../../schemas/fixture-manifest.schema.json",
    id: "github-pr-review-basic",
    version: "2026-05.0",
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
      path: "replay-bundle/github-pr-review-basic",
      schemaVersion: "replay_bundle.v1",
      sha256,
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
    ...overrides,
  };
}

function fixtureSetManifest(overrides: Record<string, unknown> = {}) {
  return {
    $schema: "../../schemas/fixture-set-manifest.schema.json",
    id: "support-triage-basic",
    version: "2026-05.0",
    name: "Support Triage Basic",
    description: "A composed support triage world.",
    status: "verified",
    fixtures: [
      "slack-support-thread-basic@2026-05.0",
      "search-policy-corpus-basic@2026-05.0",
    ],
    evalPrompts: {
      path: "eval-prompts.jsonl",
      count: 1,
    },
    release: {
      immutable: false,
      license: "UNRELEASED",
      tags: ["support"],
    },
    ...overrides,
  };
}

describe("fixture refs", () => {
  it("parses pinned fixture refs", () => {
    expect(parseFixtureRef("github-pr-review-basic@2026-05.0")).toEqual({
      id: "github-pr-review-basic",
      version: "2026-05.0",
    });
  });

  it("rejects unpinned or malformed fixture refs", () => {
    expect(() => parseFixtureRef("github-pr-review-basic")).toThrow(/Invalid fixture ref/);
    expect(() => parseFixtureRef("GitHub@2026-05.0")).toThrow(/Invalid fixture ref/);
    expect(() => parseFixtureRef("github@latest")).toThrow(/Invalid fixture ref/);
  });
});

describe("fixture manifest schema", () => {
  it("accepts the fixture repo manifest shape", () => {
    expect(parseFixtureManifest(fixtureManifest()).id).toBe("github-pr-review-basic");
  });

  it("rejects unsafe paths", () => {
    expect(() => parseFixtureManifest(fixtureManifest({
      bundle: {
        path: "../outside",
        schemaVersion: "replay_bundle.v1",
        sha256,
      },
    }))).toThrow(/Invalid fixture manifest/);
  });

  it("does not allow blocked redaction to be verified", () => {
    expect(() => parseFixtureManifest(fixtureManifest({
      provenance: {
        source: "curated-recording",
        recordedAt: "2026-05-20",
        reviewedBy: "datalox",
        redaction: "blocked",
      },
    }))).toThrow(/blocked redaction/);
  });

  it("reads a manifest and resolves bundle paths inside the fixture directory", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "datalox-fixture-manifest-"));
    const fixtureDir = path.join(root, "github-pr-review-basic");
    await mkdir(fixtureDir, { recursive: true });
    await writeFile(path.join(fixtureDir, "manifest.json"), `${JSON.stringify(fixtureManifest(), null, 2)}\n`);

    const result = await readFixtureManifest(fixtureDir);
    expect(result.bundlePath).toBe(path.join(fixtureDir, "replay-bundle", "github-pr-review-basic"));
  });
});

describe("fixture set manifest schema", () => {
  it("accepts a composed fixture set shape", () => {
    expect(parseFixtureSetManifest(fixtureSetManifest()).fixtures).toEqual([
      "slack-support-thread-basic@2026-05.0",
      "search-policy-corpus-basic@2026-05.0",
    ]);
  });

  it("requires pinned member fixture refs", () => {
    expect(() => parseFixtureSetManifest(fixtureSetManifest({
      fixtures: ["slack-support-thread-basic"],
    }))).toThrow(/Invalid fixture-set manifest/);
  });

  it("reads a fixture-set manifest and checks directory alignment", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "datalox-fixture-set-"));
    const fixtureSetDir = path.join(root, "support-triage-basic");
    await mkdir(fixtureSetDir, { recursive: true });
    await writeFile(path.join(fixtureSetDir, "manifest.json"), `${JSON.stringify(fixtureSetManifest(), null, 2)}\n`);

    const result = await readFixtureSetManifest(fixtureSetDir);
    expect(result.manifest.id).toBe("support-triage-basic");
  });
});
