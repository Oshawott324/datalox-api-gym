import { readFile } from "node:fs/promises";
import path from "node:path";

import {
  parseFixtureCatalog,
  type FixtureCatalog,
  type FixtureCatalogEntry,
  type FixtureSetCatalogEntry,
} from "./fixtureCatalogSchema.js";
import { formatFixtureRef, parseFixtureRef } from "./fixtureRef.js";
import { resolveInside } from "./pathSafety.js";

export interface ReadFixtureCatalogResult {
  catalogPath: string;
  catalogRoot: string;
  catalog: FixtureCatalog;
}

export async function readFixtureCatalog(catalogPath: string): Promise<ReadFixtureCatalogResult> {
  const absoluteCatalogPath = path.resolve(catalogPath);
  const catalog = parseFixtureCatalog(JSON.parse(await readFile(absoluteCatalogPath, "utf8")));
  return {
    catalogPath: absoluteCatalogPath,
    catalogRoot: path.dirname(absoluteCatalogPath),
    catalog,
  };
}

export function findFixtureCatalogEntry(
  catalog: FixtureCatalog,
  fixtureRef: string,
): FixtureCatalogEntry {
  const ref = formatFixtureRef(parseFixtureRef(fixtureRef));
  const entry = catalog.fixtures.find((fixture) => fixture.ref === ref);
  if (!entry) {
    throw new Error(`Fixture ${ref} not found in catalog.`);
  }
  return entry;
}

export function findFixtureSetCatalogEntry(
  catalog: FixtureCatalog,
  fixtureSetRef: string,
): FixtureSetCatalogEntry {
  const ref = formatFixtureRef(parseFixtureRef(fixtureSetRef));
  const entry = catalog.fixture_sets.find((fixtureSet) => fixtureSet.ref === ref);
  if (!entry) {
    throw new Error(`Fixture set ${ref} not found in catalog.`);
  }
  return entry;
}

export function resolveCatalogEntryPath(catalogRoot: string, relativePath: string): string {
  return resolveInside(catalogRoot, relativePath);
}
