import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

import { sha256Hex } from "../hash.js";
import { parseDataloxRunV1, type DataloxRunV1, type RunMessage } from "../run/runTranscriptSchema.js";
import { parseSftFrameV1, type SftFrameV1 } from "./sftFrameSchema.js";

export interface ExportSftFromRunInput {
  runDir?: string;
  runPath?: string;
  outPath: string;
}

export interface ExportSftFromRunResult {
  outPath: string;
  frameCount: number;
  frames: SftFrameV1[];
}

export class SftExportError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SftExportError";
  }
}

export async function exportSftFromRun(input: ExportSftFromRunInput): Promise<ExportSftFromRunResult> {
  const runPath = resolveRunPath(input);
  const run = parseDataloxRunV1(JSON.parse(await readFile(runPath, "utf8")) as unknown);
  const frame = buildSftFrameFromRun({ run, runPath });

  await mkdir(path.dirname(input.outPath), { recursive: true });
  await writeFile(input.outPath, `${JSON.stringify(frame)}\n`, "utf8");

  return {
    outPath: input.outPath,
    frameCount: 1,
    frames: [frame],
  };
}

export function buildSftFrameFromRun(input: {
  run: DataloxRunV1;
  runPath: string;
}): SftFrameV1 {
  const { run, runPath } = input;
  assertRunExportable(run);
  if (run.stop_reason !== "final_answer") {
    throw new SftExportError(`Run ${run.id} is not SFT-exportable because stop_reason is ${run.stop_reason}.`);
  }

  const finalAssistantIndex = findFinalAssistantIndex(run.messages);
  if (finalAssistantIndex < 0) {
    throw new SftExportError(`Run ${run.id} has no final assistant target message.`);
  }

  const targetMessage = run.messages[finalAssistantIndex];
  const inputMessages = run.messages.slice(0, finalAssistantIndex);
  if (inputMessages.length === 0) {
    throw new SftExportError(`Run ${run.id} has no model-visible input messages before the SFT target.`);
  }

  const replayMissCount = run.steps.filter((step) => step.replay_miss !== undefined).length;
  if (replayMissCount > 0) {
    throw new SftExportError(`Run ${run.id} is not SFT-exportable because it contains replay misses.`);
  }

  return parseSftFrameV1({
    schema_version: "sft_frame.v1",
    id: buildFrameId(run),
    source_run_id: run.id,
    ...(run.task_ref !== undefined ? { task_ref: run.task_ref } : {}),
    fixture_refs: run.fixture_refs,
    ...(run.fixture_set_ref !== undefined ? { fixture_set_ref: run.fixture_set_ref } : {}),
    input_messages: inputMessages,
    target_message: targetMessage,
    evidence_refs: {
      run_path: runPath,
      tool_record_refs: run.steps.flatMap((step) => step.tool_record_ref !== undefined ? [step.tool_record_ref] : []),
      replay_miss_count: replayMissCount,
    },
    quality: hasErrorRecovery(run) ? "recovery" : "success",
    use_for_sft: true,
    export: run.export,
    metadata: {
      model: run.model.model,
      stop_reason: run.stop_reason,
      step_count: run.steps.length,
    },
  });
}

function resolveRunPath(input: ExportSftFromRunInput): string {
  if (input.runPath !== undefined) {
    return input.runPath;
  }
  if (input.runDir !== undefined) {
    return path.join(input.runDir, "run.json");
  }
  throw new SftExportError("SFT export requires runDir or runPath.");
}

function assertRunExportable(run: DataloxRunV1): void {
  if (run.export.allowed !== true || run.export.redaction === "blocked") {
    throw new SftExportError(`Run ${run.id} export is blocked.`);
  }
}

function findFinalAssistantIndex(messages: RunMessage[]): number {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (
      message.role === "assistant"
      && typeof message.content === "string"
      && message.content.length > 0
      && message.tool_calls === undefined
    ) {
      return index;
    }
  }
  return -1;
}

function hasErrorRecovery(run: DataloxRunV1): boolean {
  return run.steps.some((step) => step.observation?.status === "error");
}

function buildFrameId(run: DataloxRunV1): string {
  return `sft-${sha256Hex(JSON.stringify({
    run_id: run.id,
    final_answer: run.final_answer ?? "",
  })).slice(0, 16)}`;
}
