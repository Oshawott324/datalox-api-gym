import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import path from "node:path";

import { parseReplayBundleV1 } from "../replayBundleSchema.js";
import { fixtureCachePath } from "./fixtureCache.js";
import { formatFixtureRef, parseFixtureRef } from "./fixtureRef.js";
import type { ResolvedFixtureSpecs } from "./fixtureSpecSchema.js";
import { verifyFixtureBundle } from "./installFixturePack.js";
import { readFixtureManifest } from "./readFixtureManifest.js";

export interface ResolveFixtureRuntimeInput {
  ref: string;
  cacheRoot?: string;
}

export interface FixtureRuntime {
  ref: string;
  cachePath: string;
  manifestPath: string;
  bundlePath: string;
  bundleId: string;
  bundleSha256: string;
  toolCatalogPaths: string[];
  toolCatalogAbsolutePaths: string[];
  specs: ResolvedFixtureSpecs;
  export: {
    allowed: boolean;
    redaction: "none_needed" | "applied" | "blocked";
    approval_id?: string;
  };
  toolCatalogCount: number;
}

export async function resolveFixtureRuntime(input: ResolveFixtureRuntimeInput): Promise<FixtureRuntime> {
  const ref = formatFixtureRef(parseFixtureRef(input.ref));
  const cachePath = fixtureCachePath({ ref, cacheRoot: input.cacheRoot });
  if (!existsSync(path.join(cachePath, "manifest.json"))) {
    throw new Error(`Installed fixture ${ref} was not found in fixture cache at ${cachePath}. Run datalox fixtures install ${ref} first.`);
  }
  const fixture = await readFixtureManifest(cachePath);
  const manifestRef = formatFixtureRef({
    id: fixture.manifest.id,
    version: fixture.manifest.version,
  });
  if (manifestRef !== ref) {
    throw new Error(`Installed fixture ref mismatch: requested ${ref}, installed manifest is ${manifestRef}.`);
  }
  await verifyFixtureBundle(fixture.bundlePath, fixture.manifest.bundle.sha256);

  const bundleManifest = parseReplayBundleV1(JSON.parse(
    await readFile(path.join(fixture.bundlePath, "manifest.json"), "utf8"),
  ));
  const toolCatalogPaths = bundleManifest.source.mcp_tool_catalog_paths ?? [];
  return {
    ref,
    cachePath,
    manifestPath: fixture.manifestPath,
    bundlePath: fixture.bundlePath,
    bundleId: bundleManifest.id,
    bundleSha256: fixture.manifest.bundle.sha256,
    toolCatalogPaths,
    toolCatalogAbsolutePaths: toolCatalogPaths.map((catalogPath) => path.join(fixture.bundlePath, catalogPath)),
    specs: fixture.specs,
    export: bundleManifest.export,
    toolCatalogCount: toolCatalogPaths.length,
  };
}
