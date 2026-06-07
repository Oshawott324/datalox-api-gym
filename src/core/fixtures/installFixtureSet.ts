import { existsSync } from "node:fs";
import { cp, mkdir, rm } from "node:fs/promises";
import path from "node:path";

import { fixtureSetCachePath } from "./fixtureCache.js";
import { formatFixtureRef, parseFixtureRef } from "./fixtureRef.js";
import type { ResolvedFixtureSpecs } from "./fixtureSpecSchema.js";
import { installFixturePack, type InstallFixtureResult } from "./installFixturePack.js";
import {
  findFixtureSetCatalogEntry,
  readFixtureCatalog,
  resolveCatalogEntryPath,
} from "./readFixtureCatalog.js";
import { readFixtureSetManifest } from "./readFixtureManifest.js";

export interface InstallFixtureSetInput {
  ref: string;
  catalogPath: string;
  cacheRoot?: string;
  force?: boolean;
}

export interface InstallFixtureSetResult {
  ref: string;
  cachePath: string;
  manifestPath: string;
  specs: ResolvedFixtureSpecs;
  fixtures: InstallFixtureResult[];
  alreadyInstalled: boolean;
}

export async function installFixtureSet(input: InstallFixtureSetInput): Promise<InstallFixtureSetResult> {
  const ref = formatFixtureRef(parseFixtureRef(input.ref));
  const catalogResult = await readFixtureCatalog(input.catalogPath);
  const entry = findFixtureSetCatalogEntry(catalogResult.catalog, ref);
  const sourceFixtureSetDir = resolveCatalogEntryPath(catalogResult.catalogRoot, entry.source_path);
  const targetFixtureSetDir = fixtureSetCachePath({ ref, cacheRoot: input.cacheRoot });

  const sourceFixtureSet = await readFixtureSetManifest(sourceFixtureSetDir);
  const manifestRef = formatFixtureRef({
    id: sourceFixtureSet.manifest.id,
    version: sourceFixtureSet.manifest.version,
  });
  if (manifestRef !== ref) {
    throw new Error(`World set ref mismatch: requested ${ref}, manifest is ${manifestRef}.`);
  }

  const installedFixtures: InstallFixtureResult[] = [];
  for (const memberRef of sourceFixtureSet.manifest.fixtures) {
    installedFixtures.push(await installFixturePack({
      ref: memberRef,
      catalogPath: input.catalogPath,
      cacheRoot: input.cacheRoot,
      force: input.force,
    }));
  }

  if (existsSync(targetFixtureSetDir)) {
    if (!input.force) {
      const installed = await readFixtureSetManifest(targetFixtureSetDir);
      return {
        ref,
        cachePath: targetFixtureSetDir,
        manifestPath: installed.manifestPath,
        specs: installed.specs,
        fixtures: installedFixtures,
        alreadyInstalled: true,
      };
    }
    await rm(targetFixtureSetDir, { recursive: true, force: true });
  }

  await mkdir(path.dirname(targetFixtureSetDir), { recursive: true });
  await cp(sourceFixtureSetDir, targetFixtureSetDir, {
    recursive: true,
    errorOnExist: false,
    force: true,
    preserveTimestamps: true,
  });
  const installedSet = await readFixtureSetManifest(targetFixtureSetDir);
  return {
    ref,
    cachePath: targetFixtureSetDir,
    manifestPath: installedSet.manifestPath,
    specs: installedSet.specs,
    fixtures: installedFixtures,
    alreadyInstalled: false,
  };
}
