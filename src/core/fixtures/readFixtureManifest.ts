import { readFile } from "node:fs/promises";
import path from "node:path";

import { parseFixtureManifest, type FixtureManifest } from "./fixtureManifestSchema.js";
import { parseFixtureSetManifest, type FixtureSetManifest } from "./fixtureSetSchema.js";
import { readFixtureSpecs, type ResolvedFixtureSpecs } from "./fixtureSpecSchema.js";
import { resolveInside } from "./pathSafety.js";

export interface ReadFixtureManifestResult {
  fixtureDir: string;
  manifestPath: string;
  manifest: FixtureManifest;
  bundlePath: string;
  evalPromptsPath: string;
  specs: ResolvedFixtureSpecs;
}

export interface ReadFixtureSetManifestResult {
  fixtureSetDir: string;
  manifestPath: string;
  manifest: FixtureSetManifest;
  evalPromptsPath?: string;
  splitsPath?: string;
  specs: ResolvedFixtureSpecs;
}

export async function readFixtureManifest(fixtureDir: string): Promise<ReadFixtureManifestResult> {
  const absoluteFixtureDir = path.resolve(fixtureDir);
  const manifestPath = path.join(absoluteFixtureDir, "manifest.json");
  const manifest = parseFixtureManifest(JSON.parse(await readFile(manifestPath, "utf8")));
  const directoryName = path.basename(absoluteFixtureDir);
  const parentDirectoryName = path.basename(path.dirname(absoluteFixtureDir));
  if (directoryName !== manifest.id && parentDirectoryName !== manifest.id) {
    throw new Error(`Fixture directory ${directoryName} does not match manifest id ${manifest.id}.`);
  }
  return {
    fixtureDir: absoluteFixtureDir,
    manifestPath,
    manifest,
    bundlePath: resolveInside(absoluteFixtureDir, manifest.bundle.path),
    evalPromptsPath: resolveInside(absoluteFixtureDir, manifest.evalPrompts.path),
    specs: await readFixtureSpecs(absoluteFixtureDir, manifest.specs),
  };
}

export async function readFixtureSetManifest(fixtureSetDir: string): Promise<ReadFixtureSetManifestResult> {
  const absoluteFixtureSetDir = path.resolve(fixtureSetDir);
  const manifestPath = path.join(absoluteFixtureSetDir, "manifest.json");
  const manifest = parseFixtureSetManifest(JSON.parse(await readFile(manifestPath, "utf8")));
  const directoryName = path.basename(absoluteFixtureSetDir);
  const parentDirectoryName = path.basename(path.dirname(absoluteFixtureSetDir));
  if (directoryName !== manifest.id && parentDirectoryName !== manifest.id) {
    throw new Error(`Fixture-set directory ${directoryName} does not match manifest id ${manifest.id}.`);
  }
  return {
    fixtureSetDir: absoluteFixtureSetDir,
    manifestPath,
    manifest,
    ...(manifest.evalPrompts
      ? { evalPromptsPath: resolveInside(absoluteFixtureSetDir, manifest.evalPrompts.path) }
      : {}),
    ...(manifest.splits
      ? { splitsPath: resolveInside(absoluteFixtureSetDir, manifest.splits.path) }
      : {}),
    specs: await readFixtureSpecs(absoluteFixtureSetDir, manifest.specs),
  };
}
