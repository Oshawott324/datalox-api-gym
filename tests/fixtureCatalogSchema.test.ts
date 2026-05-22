import { mkdir, mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { describe, expect, it } from "vitest";

import {
  findFixtureCatalogEntry,
  findFixtureSetCatalogEntry,
  readFixtureCatalog,
  resolveCatalogEntryPath,
} from "../src/core/fixtures/readFixtureCatalog.js";

const sha256 = "1".repeat(64);

function catalog() {
  return {
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
        id: "github-pr-review-basic",
        version: "2026-05.0",
        ref: "github-pr-review-basic@2026-05.0",
        name: "GitHub PR Review Basic",
        description: "A finite GitHub PR world.",
        status: "verified",
        source_path: "fixtures/github-pr-review-basic",
        manifest_path: "fixtures/github-pr-review-basic/manifest.json",
        tools: [
          {
            surface: "mcp",
            server: "github",
            operations: ["pull_request.get"],
          },
        ],
        tags: ["github"],
        bundle: {
          path: "fixtures/github-pr-review-basic/replay-bundle/github-pr-review-basic",
          schema_version: "replay_bundle.v1",
          sha256,
        },
        eval_prompts: {
          path: "fixtures/github-pr-review-basic/eval-prompts.jsonl",
          count: 1,
        },
        specs: {
          task_specs: [
            {
              path: "fixtures/github-pr-review-basic/tasks/github-pr-review-risk.json",
              id: "github-pr-review-risk",
              version: "2026-05.0",
            },
          ],
        },
        release: {
          immutable: false,
          license: "UNRELEASED",
          archive_path: "archives/fixtures/github-pr-review-basic-2026-05.0.tgz",
          checksum_path: "archives/fixtures/github-pr-review-basic-2026-05.0.tgz.sha256",
        },
      },
    ],
    fixture_sets: [
      {
        id: "support-triage-basic",
        version: "2026-05.0",
        ref: "support-triage-basic@2026-05.0",
        name: "Support Triage Basic",
        description: "A composed support world.",
        status: "verified",
        source_path: "fixture-sets/support-triage-basic",
        manifest_path: "fixture-sets/support-triage-basic/manifest.json",
        fixtures: ["github-pr-review-basic@2026-05.0"],
        tags: ["support"],
        eval_prompts: {
          path: "fixture-sets/support-triage-basic/eval-prompts.jsonl",
          count: 1,
        },
        specs: {
          task_specs: [
            {
              path: "fixture-sets/support-triage-basic/tasks/support-triage.json",
              id: "support-triage",
              version: "2026-05.0",
            },
          ],
        },
        release: {
          immutable: false,
          license: "UNRELEASED",
          archive_path: "archives/fixture-sets/support-triage-basic-2026-05.0.tgz",
          checksum_path: "archives/fixture-sets/support-triage-basic-2026-05.0.tgz.sha256",
        },
      },
    ],
  };
}

describe("fixture catalog schema", () => {
  it("reads the engine-facing catalog and finds fixture refs", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "datalox-fixture-catalog-"));
    const catalogPath = path.join(root, "catalog.json");
    await writeFile(catalogPath, `${JSON.stringify(catalog(), null, 2)}\n`);

    const result = await readFixtureCatalog(catalogPath);
    expect(findFixtureCatalogEntry(result.catalog, "github-pr-review-basic@2026-05.0").source_path)
      .toBe("fixtures/github-pr-review-basic");
    expect(findFixtureSetCatalogEntry(result.catalog, "support-triage-basic@2026-05.0").fixtures)
      .toEqual(["github-pr-review-basic@2026-05.0"]);
  });

  it("rejects catalog paths that escape the catalog root", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "datalox-fixture-catalog-bad-"));
    const badCatalog = catalog();
    badCatalog.fixtures[0].source_path = "../fixtures/github-pr-review-basic";
    const catalogPath = path.join(root, "catalog.json");
    await writeFile(catalogPath, `${JSON.stringify(badCatalog, null, 2)}\n`);

    await expect(readFixtureCatalog(catalogPath)).rejects.toThrow(/Invalid fixture catalog/);
  });

  it("resolves safe catalog entry paths inside the catalog root", () => {
    expect(resolveCatalogEntryPath("/tmp/catalog-root", "fixtures/github-pr-review-basic"))
      .toBe("/tmp/catalog-root/fixtures/github-pr-review-basic");
    expect(() => resolveCatalogEntryPath("/tmp/catalog-root", "../escape")).toThrow(/Unsafe relative path/);
  });

  it("fails clearly for missing fixture refs", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "datalox-fixture-catalog-missing-"));
    const catalogPath = path.join(root, "catalog.json");
    await mkdir(root, { recursive: true });
    await writeFile(catalogPath, `${JSON.stringify(catalog(), null, 2)}\n`);
    const result = await readFixtureCatalog(catalogPath);

    expect(() => findFixtureCatalogEntry(result.catalog, "missing-fixture@2026-05.0"))
      .toThrow(/not found in catalog/);
  });
});
