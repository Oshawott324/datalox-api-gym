import { homedir } from "node:os";
import { readdir } from "node:fs/promises";
import path from "node:path";

import type { FixtureManifest } from "./fixtureManifestSchema.js";
import { formatFixtureRef, parseFixtureRef } from "./fixtureRef.js";
import { readFixtureManifest } from "./readFixtureManifest.js";

export const DEFAULT_FIXTURE_CACHE_RELATIVE_DIR = path.join(".datalox", "fixtures");

export function defaultFixtureCacheRoot(): string {
  return process.env.DATALOX_FIXTURE_CACHE
    ? path.resolve(process.env.DATALOX_FIXTURE_CACHE)
    : path.join(homedir(), DEFAULT_FIXTURE_CACHE_RELATIVE_DIR);
}

export function fixtureCachePath(input: {
  ref: string;
  cacheRoot?: string;
}): string {
  const ref = parseFixtureRef(input.ref);
  return path.join(path.resolve(input.cacheRoot ?? defaultFixtureCacheRoot()), ref.id, ref.version);
}

export function fixtureSetCachePath(input: {
  ref: string;
  cacheRoot?: string;
}): string {
  const ref = parseFixtureRef(input.ref);
  return path.join(path.resolve(input.cacheRoot ?? defaultFixtureCacheRoot()), "fixture-sets", ref.id, ref.version);
}

export function fixtureRefFromCachePath(cachePath: string): string {
  const version = path.basename(cachePath);
  const id = path.basename(path.dirname(cachePath));
  return formatFixtureRef({ id, version });
}

export interface InstalledFixtureSummary {
  ref: string;
  cachePath: string;
  manifestPath: string;
  status: "draft" | "verified" | "released" | "deprecated";
  tools: FixtureManifest["tools"];
  bundleSha256: string;
}

export async function listInstalledFixtures(input: {
  cacheRoot?: string;
} = {}): Promise<InstalledFixtureSummary[]> {
  const root = path.resolve(input.cacheRoot ?? defaultFixtureCacheRoot());
  let idEntries;
  try {
    idEntries = await readdir(root, { withFileTypes: true });
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") {
      return [];
    }
    throw error;
  }

  const fixtures: InstalledFixtureSummary[] = [];
  for (const idEntry of idEntries) {
    if (!idEntry.isDirectory() || idEntry.name === "fixture-sets") {
      continue;
    }
    const idDir = path.join(root, idEntry.name);
    const versionEntries = await readdir(idDir, { withFileTypes: true });
    for (const versionEntry of versionEntries) {
      if (!versionEntry.isDirectory()) {
        continue;
      }
      const cachePath = path.join(idDir, versionEntry.name);
      const installed = await readFixtureManifest(cachePath);
      fixtures.push({
        ref: formatFixtureRef({
          id: installed.manifest.id,
          version: installed.manifest.version,
        }),
        cachePath,
        manifestPath: installed.manifestPath,
        status: installed.manifest.status,
        tools: installed.manifest.tools,
        bundleSha256: installed.manifest.bundle.sha256,
      });
    }
  }

  return fixtures.sort((first, second) => first.ref.localeCompare(second.ref));
}
