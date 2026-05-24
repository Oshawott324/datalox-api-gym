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
        adapter: {
          protocol: "mcp",
          toolCatalogSource: "replay-bundle",
        },
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
    trust: {
      schemaVersion: "datalox_fixture_trust_input.v1",
      verifiedAt: "2026-05-22T00:00:00Z",
      verifiedBy: "datalox",
      reviewType: "synthetic-public-fixture",
      export: {
        allowed: true,
        redaction: "none_needed",
      },
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
    toolCollisionPolicy: {
      mode: "fail",
    },
    evalPrompts: {
      path: "eval-prompts.jsonl",
      count: 1,
    },
    splits: {
      path: "splits.json",
    },
    trust: {
      schemaVersion: "datalox_fixture_trust_input.v1",
      verifiedAt: "2026-05-22T00:00:00Z",
      verifiedBy: "datalox",
      reviewType: "composed-public-fixture-set",
      export: {
        allowed: true,
        redaction: "none_needed",
      },
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

  it("accepts metadata-only spec references", () => {
    expect(parseFixtureManifest(fixtureManifest({
      specs: {
        taskSpecs: [{ path: "tasks/github-pr-review-risk.json" }],
        verifierSpecs: [{ path: "verifiers/github-pr-review-risk.json" }],
        scaffoldSpecs: [{ path: "scaffolds/codex-review.json" }],
      },
    })).specs?.taskSpecs?.[0].path).toBe("tasks/github-pr-review-risk.json");
  });

  it("rejects unsafe paths", () => {
    expect(() => parseFixtureManifest(fixtureManifest({
      bundle: {
        path: "../outside",
        schemaVersion: "replay_bundle.v1",
        sha256,
      },
    }))).toThrow(/Invalid fixture manifest/);
    expect(() => parseFixtureManifest(fixtureManifest({
      specs: {
        taskSpecs: [{ path: "../tasks/bad.json" }],
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

  it("reads and validates referenced spec files", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "datalox-fixture-specs-"));
    const fixtureDir = path.join(root, "github-pr-review-basic");
    await mkdir(path.join(fixtureDir, "tasks"), { recursive: true });
    await writeFile(path.join(fixtureDir, "tasks", "github-pr-review-risk.json"), `${JSON.stringify({
      schema_version: "datalox_task_spec.v1",
      id: "github-pr-review-risk",
      version: "2026-05.0",
      name: "GitHub PR review risk",
      description: "Find the actionable risk in a replayed pull request.",
      goal: "Identify the correctness risk.",
      fixtureRefs: ["github-pr-review-basic@2026-05.0"],
      allowedTools: ["github_pull_request_get"],
      successCriteria: ["Names the risky file."],
    }, null, 2)}\n`);
    await writeFile(path.join(fixtureDir, "manifest.json"), `${JSON.stringify(fixtureManifest({
      specs: {
        taskSpecs: [{ path: "tasks/github-pr-review-risk.json" }],
      },
    }), null, 2)}\n`);

    const result = await readFixtureManifest(fixtureDir);
    expect(result.specs.taskSpecs).toMatchObject([
      {
        id: "github-pr-review-risk",
        version: "2026-05.0",
        ref: "github-pr-review-risk@2026-05.0",
        path: "tasks/github-pr-review-risk.json",
      },
    ]);
  });
});

describe("fixture set manifest schema", () => {
  it("accepts a composed fixture set shape", () => {
    expect(parseFixtureSetManifest(fixtureSetManifest()).fixtures).toEqual([
      "slack-support-thread-basic@2026-05.0",
      "search-policy-corpus-basic@2026-05.0",
    ]);
  });

  it("accepts fixture-set spec references", () => {
    expect(parseFixtureSetManifest(fixtureSetManifest({
      specs: {
        taskSpecs: [{ path: "tasks/support-triage.json" }],
      },
    })).specs?.taskSpecs?.[0].path).toBe("tasks/support-triage.json");
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
    await writeFile(path.join(fixtureSetDir, "splits.json"), `${JSON.stringify({
      schema_version: "datalox_task_splits.v1",
      fixtureSetRef: "support-triage-basic@2026-05.0",
      splits: {
        train: ["support-triage"],
        dev: [],
        test: [],
      },
    }, null, 2)}\n`);
    await writeFile(path.join(fixtureSetDir, "manifest.json"), `${JSON.stringify(fixtureSetManifest(), null, 2)}\n`);

    const result = await readFixtureSetManifest(fixtureSetDir);
    expect(result.manifest.id).toBe("support-triage-basic");
    expect(result.splitsPath).toBe(path.join(fixtureSetDir, "splits.json"));
  });
});
