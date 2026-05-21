import { existsSync } from "node:fs";
import { cp, mkdir, readFile, rm, rename } from "node:fs/promises";
import path from "node:path";

import { sha256Hex } from "../hash.js";
import { verifyReplayBundle } from "../replayBundle.js";
import { fixtureCachePath } from "./fixtureCache.js";
import { formatFixtureRef, parseFixtureRef } from "./fixtureRef.js";
import {
  findFixtureCatalogEntry,
  readFixtureCatalog,
  resolveCatalogEntryPath,
} from "./readFixtureCatalog.js";
import { readFixtureManifest } from "./readFixtureManifest.js";

export interface InstallFixtureInput {
  ref?: string;
  catalogPath?: string;
  sourcePath?: string;
  cacheRoot?: string;
  force?: boolean;
}

export interface InstallFixtureResult {
  ref: string;
  cachePath: string;
  manifestPath: string;
  bundlePath: string;
  bundleId: string;
  bundleSha256: string;
  alreadyInstalled: boolean;
  verified: true;
}

export async function installFixturePack(input: InstallFixtureInput): Promise<InstallFixtureResult> {
  const source = await resolveInstallSource(input);
  const ref = source.ref;
  const sourceFixtureDir = source.sourceFixtureDir;
  const targetFixtureDir = fixtureCachePath({ ref, cacheRoot: input.cacheRoot });

  const sourceFixture = await readFixtureManifest(sourceFixtureDir);
  assertFixtureMatchesRef(sourceFixture.manifest.id, sourceFixture.manifest.version, ref);
  if (source.catalogBundleSha256) {
    assertCatalogEntryMatchesManifest(source.catalogBundleSha256, sourceFixture.manifest.bundle.sha256, ref);
  }
  await verifyFixtureBundle(sourceFixture.bundlePath, sourceFixture.manifest.bundle.sha256);

  if (existsSync(targetFixtureDir)) {
    if (input.force) {
      await rm(targetFixtureDir, { recursive: true, force: true });
    } else {
      const installed = await readFixtureManifest(targetFixtureDir);
      assertFixtureMatchesRef(installed.manifest.id, installed.manifest.version, ref);
      await verifyFixtureBundle(installed.bundlePath, installed.manifest.bundle.sha256);
      return {
        ref,
        cachePath: targetFixtureDir,
        manifestPath: installed.manifestPath,
        bundlePath: installed.bundlePath,
        bundleId: installed.manifest.id,
        bundleSha256: installed.manifest.bundle.sha256,
        alreadyInstalled: true,
        verified: true,
      };
    }
  }

  await mkdir(path.dirname(targetFixtureDir), { recursive: true });
  const stagingDir = `${targetFixtureDir}.tmp-${process.pid}-${Date.now()}`;
  await rm(stagingDir, { recursive: true, force: true });
  try {
    await cp(sourceFixtureDir, stagingDir, {
      recursive: true,
      errorOnExist: false,
      force: true,
      preserveTimestamps: true,
    });
    const staged = await readFixtureManifest(stagingDir);
    await verifyFixtureBundle(staged.bundlePath, staged.manifest.bundle.sha256);
    await rename(stagingDir, targetFixtureDir);

    return {
      ref,
      cachePath: targetFixtureDir,
      manifestPath: path.join(targetFixtureDir, "manifest.json"),
      bundlePath: path.join(targetFixtureDir, staged.manifest.bundle.path),
      bundleId: staged.manifest.id,
      bundleSha256: staged.manifest.bundle.sha256,
      alreadyInstalled: false,
      verified: true,
    };
  } catch (error) {
    await rm(stagingDir, { recursive: true, force: true });
    throw error;
  }
}

async function resolveInstallSource(input: InstallFixtureInput): Promise<{
  ref: string;
  sourceFixtureDir: string;
  catalogBundleSha256?: string;
}> {
  if (input.catalogPath) {
    if (!input.ref) {
      throw new Error("Catalog fixture install requires a fixture ref.");
    }
    const ref = formatFixtureRef(parseFixtureRef(input.ref));
    const catalogResult = await readFixtureCatalog(input.catalogPath);
    const entry = findFixtureCatalogEntry(catalogResult.catalog, ref);
    return {
      ref,
      sourceFixtureDir: resolveCatalogEntryPath(catalogResult.catalogRoot, entry.source_path),
      catalogBundleSha256: entry.bundle.sha256,
    };
  }

  if (!input.sourcePath) {
    throw new Error("Fixture install requires either catalogPath/ref or sourcePath.");
  }
  const sourceFixture = await readFixtureManifest(input.sourcePath);
  const manifestRef = formatFixtureRef({
    id: sourceFixture.manifest.id,
    version: sourceFixture.manifest.version,
  });
  if (input.ref) {
    const requestedRef = formatFixtureRef(parseFixtureRef(input.ref));
    if (requestedRef !== manifestRef) {
      throw new Error(`Fixture ref mismatch: requested ${requestedRef}, manifest is ${manifestRef}.`);
    }
  }

  return {
    ref: manifestRef,
    sourceFixtureDir: sourceFixture.fixtureDir,
  };
}

export async function verifyFixtureBundle(bundlePath: string, expectedBundleDigest: string): Promise<void> {
  await verifyReplayBundle({ bundlePath });
  const checksumsDigest = sha256Hex(await readFile(path.join(bundlePath, "checksums.json")));
  if (checksumsDigest !== expectedBundleDigest) {
    throw new Error(`Fixture bundle digest mismatch: expected ${expectedBundleDigest}, got ${checksumsDigest}`);
  }
}

function assertFixtureMatchesRef(id: string, version: string, ref: string): void {
  const expectedRef = formatFixtureRef({ id, version });
  if (expectedRef !== ref) {
    throw new Error(`Fixture ref mismatch: requested ${ref}, manifest is ${expectedRef}.`);
  }
}

function assertCatalogEntryMatchesManifest(catalogDigest: string, manifestDigest: string, ref: string): void {
  if (catalogDigest !== manifestDigest) {
    throw new Error(`Catalog bundle digest for ${ref} does not match fixture manifest digest.`);
  }
}
