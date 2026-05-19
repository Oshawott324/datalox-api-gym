import { existsSync } from "node:fs";
import { mkdir, readdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

import {
  buildToolIoRequestHash,
  parseToolIoRecordV1,
  type ToolIoObservationV1,
  type ToolIoRecordV1,
} from "./toolIoSchema.js";

export const TOOL_IO_RECORDS_RELATIVE_DIR = path.join(".datalox", "tool-io", "records");

export interface RecordToolIoInput {
  repoPath?: string;
  sessionId?: string;
  turnId?: string;
  callId: string;
  toolName: string;
  arguments: unknown;
  observation: ToolIoObservationV1;
  source?: {
    host?: string;
    mcp_server?: string;
    command?: string;
  };
  export?: {
    allowed: boolean;
    redaction: "none_needed" | "applied" | "blocked";
    approval_id?: string;
  };
  now?: Date;
}

export interface RecordToolIoResult {
  recordPath: string;
  record: ToolIoRecordV1;
}

export interface ReplayToolIoInput {
  repoPath?: string;
  toolName: string;
  arguments: unknown;
  sequenceIndex: number;
}

export class ToolIoReplayMissError extends Error {
  readonly requestHash: string;
  readonly sequenceIndex: number;

  constructor(requestHash: string, sequenceIndex: number) {
    super(`No tool_io_record.v1 replay record for request_hash=${requestHash} sequence_index=${sequenceIndex}.`);
    this.name = "ToolIoReplayMissError";
    this.requestHash = requestHash;
    this.sequenceIndex = sequenceIndex;
  }
}

export class DuplicateToolIoReplayKeyError extends Error {
  readonly requestHash: string;
  readonly sequenceIndex: number;

  constructor(requestHash: string, sequenceIndex: number) {
    super(`Multiple tool_io_record.v1 records found for request_hash=${requestHash} sequence_index=${sequenceIndex}.`);
    this.name = "DuplicateToolIoReplayKeyError";
    this.requestHash = requestHash;
    this.sequenceIndex = sequenceIndex;
  }
}

export async function recordToolIo(input: RecordToolIoInput): Promise<RecordToolIoResult> {
  const repoRoot = resolveRepoRoot(input.repoPath);
  const requestHash = buildToolIoRequestHash(input.toolName, input.arguments);
  const sequenceIndex = await nextSequenceIndex(repoRoot, requestHash);
  const createdAt = (input.now ?? new Date()).toISOString();
  const record = parseToolIoRecordV1({
    schema_version: "tool_io_record.v1",
    id: buildToolIoRecordId(requestHash, sequenceIndex, input.callId),
    ...(input.sessionId !== undefined ? { session_id: input.sessionId } : {}),
    ...(input.turnId !== undefined ? { turn_id: input.turnId } : {}),
    call_id: input.callId,
    tool_name: input.toolName,
    arguments: input.arguments,
    request_hash: requestHash,
    sequence_index: sequenceIndex,
    observation: input.observation,
    created_at: createdAt,
    ...(input.source !== undefined ? { source: input.source } : {}),
    export: input.export ?? {
      allowed: false,
      redaction: "blocked",
    },
  });
  const recordPath = normalizeRelativePath(path.join(
    TOOL_IO_RECORDS_RELATIVE_DIR,
    `${record.request_hash}--${record.sequence_index}--${slugify(record.call_id)}.json`,
  ));
  const absoluteRecordPath = path.join(repoRoot, recordPath);

  await mkdir(path.dirname(absoluteRecordPath), { recursive: true });
  await writeFile(absoluteRecordPath, `${JSON.stringify(record, null, 2)}\n`, {
    encoding: "utf8",
    flag: "wx",
  });

  return {
    recordPath,
    record,
  };
}

export async function replayToolIoObservation(input: ReplayToolIoInput): Promise<ToolIoObservationV1> {
  const record = await findToolIoRecord(input);
  return record.observation;
}

export async function findToolIoRecord(input: ReplayToolIoInput): Promise<ToolIoRecordV1> {
  const repoRoot = resolveRepoRoot(input.repoPath);
  const requestHash = buildToolIoRequestHash(input.toolName, input.arguments);
  const records = await readToolIoRecords(repoRoot);
  const matches = records.filter((record) => (
    record.request_hash === requestHash && record.sequence_index === input.sequenceIndex
  ));

  if (matches.length === 0) {
    throw new ToolIoReplayMissError(requestHash, input.sequenceIndex);
  }
  if (matches.length > 1) {
    throw new DuplicateToolIoReplayKeyError(requestHash, input.sequenceIndex);
  }
  return matches[0];
}

export async function readToolIoRecords(repoPath?: string): Promise<ToolIoRecordV1[]> {
  const repoRoot = resolveRepoRoot(repoPath);
  const recordsRoot = path.join(repoRoot, TOOL_IO_RECORDS_RELATIVE_DIR);
  if (!existsSync(recordsRoot)) {
    return [];
  }

  const recordPaths = await listJsonFiles(recordsRoot);
  const records: ToolIoRecordV1[] = [];
  for (const recordPath of recordPaths.sort()) {
    records.push(parseToolIoRecordV1(JSON.parse(await readFile(recordPath, "utf8"))));
  }
  return records.sort((first, second) => (
    first.request_hash.localeCompare(second.request_hash)
    || first.sequence_index - second.sequence_index
    || first.id.localeCompare(second.id)
  ));
}

async function nextSequenceIndex(repoRoot: string, requestHash: string): Promise<number> {
  const existingRecords = await readToolIoRecords(repoRoot);
  const matchingIndexes = existingRecords
    .filter((record) => record.request_hash === requestHash)
    .map((record) => record.sequence_index);
  if (matchingIndexes.length === 0) {
    return 0;
  }
  return Math.max(...matchingIndexes) + 1;
}

async function listJsonFiles(directory: string): Promise<string[]> {
  const entries = await readdir(directory, { withFileTypes: true });
  const files: string[] = [];
  for (const entry of entries) {
    const absolutePath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      files.push(...await listJsonFiles(absolutePath));
    } else if (entry.isFile() && entry.name.endsWith(".json")) {
      files.push(absolutePath);
    }
  }
  return files;
}

function buildToolIoRecordId(requestHash: string, sequenceIndex: number, callId: string): string {
  return `toolio-${requestHash.slice(0, 16)}-${sequenceIndex}-${slugify(callId)}`;
}

function resolveRepoRoot(repoPath: string | undefined): string {
  return path.resolve(repoPath ?? process.cwd());
}

function slugify(value: string): string {
  const slug = value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);
  return slug.length > 0 ? slug : "tool-call";
}

function normalizeRelativePath(filePath: string): string {
  return filePath.split(path.sep).join("/");
}
