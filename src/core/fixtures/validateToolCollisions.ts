import { readReplayBundleMcpToolCatalogs, readReplayBundleToolIoRecords } from "../replayBundle.js";
import type { FixtureRuntime } from "./resolveFixtureRuntime.js";

export interface ToolCollision {
  toolName: string;
  fixtureRefs: string[];
}

export class FixtureToolCollisionError extends Error {
  readonly collisions: ToolCollision[];

  constructor(collisions: ToolCollision[]) {
    super(`Fixture tool-name collisions: ${collisions.map((collision) => (
      `${collision.toolName} in ${collision.fixtureRefs.join(", ")}`
    )).join("; ")}`);
    this.name = "FixtureToolCollisionError";
    this.collisions = collisions;
  }
}

export async function validateNoToolNameCollisions(runtimes: FixtureRuntime[]): Promise<void> {
  const toolOwners = new Map<string, Set<string>>();
  for (const runtime of runtimes) {
    const toolNames = await readRuntimeToolNames(runtime);
    for (const toolName of toolNames) {
      const owners = toolOwners.get(toolName) ?? new Set<string>();
      owners.add(runtime.ref);
      toolOwners.set(toolName, owners);
    }
  }

  const collisions = Array.from(toolOwners.entries())
    .filter(([, owners]) => owners.size > 1)
    .map(([toolName, owners]) => ({
      toolName,
      fixtureRefs: Array.from(owners).sort(),
    }))
    .sort((first, second) => first.toolName.localeCompare(second.toolName));

  if (collisions.length > 0) {
    throw new FixtureToolCollisionError(collisions);
  }
}

async function readRuntimeToolNames(runtime: FixtureRuntime): Promise<string[]> {
  const catalogs = await readReplayBundleMcpToolCatalogs({ bundlePath: runtime.bundlePath });
  if (catalogs.length > 0) {
    return Array.from(new Set(catalogs.flatMap((catalog) => catalog.tools.map((tool) => tool.name)))).sort();
  }
  const records = await readReplayBundleToolIoRecords({ bundlePath: runtime.bundlePath });
  return Array.from(new Set(records.map((record) => record.tool_name))).sort();
}
