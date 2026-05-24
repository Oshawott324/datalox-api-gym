import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

import { parseDataloxRunV1, type DataloxRunV1 } from "./runTranscriptSchema.js";

export interface WriteRunTranscriptInput {
  run: DataloxRunV1;
  outDir: string;
}

export interface WriteRunTranscriptResult {
  runDir: string;
  runPath: string;
  transcriptPath: string;
  run: DataloxRunV1;
}

export async function writeRunTranscript(
  input: WriteRunTranscriptInput,
): Promise<WriteRunTranscriptResult> {
  const run = parseDataloxRunV1(input.run);
  const runDir = path.resolve(input.outDir);
  await mkdir(runDir, { recursive: true });
  const runPath = path.join(runDir, "run.json");
  const transcriptPath = path.join(runDir, "transcript.jsonl");
  await writeFile(runPath, `${JSON.stringify(run, null, 2)}\n`, "utf8");
  await writeFile(
    transcriptPath,
    `${run.messages.map((message) => JSON.stringify(message)).join("\n")}\n`,
    "utf8",
  );
  return {
    runDir,
    runPath,
    transcriptPath,
    run,
  };
}
