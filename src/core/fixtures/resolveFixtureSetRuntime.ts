import { fixtureSetCachePath } from "./fixtureCache.js";
import { formatFixtureRef, parseFixtureRef } from "./fixtureRef.js";
import type { ResolvedFixtureSpecs } from "./fixtureSpecSchema.js";
import { readFixtureSetManifest } from "./readFixtureManifest.js";
import { resolveFixtureRuntime, type FixtureRuntime } from "./resolveFixtureRuntime.js";
import { validateNoToolNameCollisions } from "./validateToolCollisions.js";

export interface ResolveFixtureSetRuntimeInput {
  ref: string;
  cacheRoot?: string;
}

export interface FixtureSetRuntime {
  ref: string;
  cachePath: string;
  manifestPath: string;
  evalPromptsPath?: string;
  splitsPath?: string;
  specs: ResolvedFixtureSpecs;
  fixtures: FixtureRuntime[];
  bundlePaths: string[];
  activeFixtureRefs: string[];
}

export async function resolveFixtureSetRuntime(input: ResolveFixtureSetRuntimeInput): Promise<FixtureSetRuntime> {
  const ref = formatFixtureRef(parseFixtureRef(input.ref));
  const cachePath = fixtureSetCachePath({ ref, cacheRoot: input.cacheRoot });
  const fixtureSet = await readFixtureSetManifest(cachePath);
  const manifestRef = formatFixtureRef({
    id: fixtureSet.manifest.id,
    version: fixtureSet.manifest.version,
  });
  if (manifestRef !== ref) {
    throw new Error(`Installed world set ref mismatch: requested ${ref}, installed manifest is ${manifestRef}.`);
  }

  const fixtures = [];
  for (const memberRef of fixtureSet.manifest.fixtures) {
    fixtures.push(await resolveFixtureRuntime({
      ref: memberRef,
      cacheRoot: input.cacheRoot,
    }));
  }
  await validateNoToolNameCollisions(fixtures);

  return {
    ref,
    cachePath,
    manifestPath: fixtureSet.manifestPath,
    ...(fixtureSet.evalPromptsPath !== undefined ? { evalPromptsPath: fixtureSet.evalPromptsPath } : {}),
    ...(fixtureSet.splitsPath !== undefined ? { splitsPath: fixtureSet.splitsPath } : {}),
    specs: fixtureSet.specs,
    fixtures,
    bundlePaths: fixtures.map((fixture) => fixture.bundlePath),
    activeFixtureRefs: fixtures.map((fixture) => fixture.ref),
  };
}
