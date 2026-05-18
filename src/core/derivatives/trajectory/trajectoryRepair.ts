import { readFile } from "node:fs/promises";
import path from "node:path";

import {
  getTrajectoryRowInput,
  recordTrajectory,
  resolveRecordedTrajectoryEventPath,
} from "./trajectoryExport.js";
import {
  type DebuggingTrajectoryV1,
  parseDebuggingTrajectoryV1,
  withDefaultTrajectoryCurationQuality,
} from "./trajectorySchema.js";

export interface RepairTrajectoryInput {
  repoPath?: string;
  eventPath: string;
  trajectoryRow: unknown;
  now?: Date;
}

export interface RepairTrajectoryResult {
  originalEventPath: string;
  repairEventPath: string;
  trajectoryId: string;
  sellable: boolean;
  blockedReasons: string[];
}

export async function repairTrajectory(input: RepairTrajectoryInput): Promise<RepairTrajectoryResult> {
  const repoRoot = path.resolve(input.repoPath ?? process.cwd());
  const originalEventPath = normalizeRelativePath(path.relative(
    repoRoot,
    resolveRecordedTrajectoryEventPath(repoRoot, input.eventPath),
  ));
  const originalEvent = JSON.parse(await readFile(path.join(repoRoot, originalEventPath), "utf8"));
  if (getTrajectoryRowInput(originalEvent) === undefined) {
    throw new Error("eventPath must point to an event with trajectoryRow.");
  }

  const row = buildRepairedRow(input.trajectoryRow, originalEventPath);
  const recorded = await recordTrajectory({
    repoPath: repoRoot,
    trajectoryRow: row,
    now: input.now,
  });

  return {
    originalEventPath,
    repairEventPath: recorded.eventPath,
    trajectoryId: recorded.trajectoryId,
    sellable: recorded.sellable,
    blockedReasons: recorded.blockedReasons,
  };
}

function buildRepairedRow(rowInput: unknown, originalEventPath: string): DebuggingTrajectoryV1 {
  const row = withDefaultTrajectoryCurationQuality(parseDebuggingTrajectoryV1(rowInput));
  const source_event_paths = Array.from(new Set([
    ...(row.export.source_event_paths ?? []),
    originalEventPath,
  ]));
  return {
    ...row,
    export: {
      ...row.export,
      source_event_paths,
    },
    metadata: {
      ...(row.metadata ?? {}),
      datalox_repaired_from_event_path: originalEventPath,
    },
  };
}

function normalizeRelativePath(filePath: string): string {
  return filePath.split(path.sep).join("/");
}
