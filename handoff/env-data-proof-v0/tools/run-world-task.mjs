#!/usr/bin/env node
import { createHash } from "node:crypto";
import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { verifyTaskAnswer } from "./verify-seed-answers.mjs";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const envRoot = path.resolve(scriptDir, "..");
const repoRoot = path.resolve(envRoot, "../..");
const defaultWorldPath = path.join(envRoot, "world.spec.json");

const DEFAULT_SYSTEM_PROMPT = [
  "You are operating a Datalox agent-native scientific tool world.",
  "Use the exposed tools to gather evidence before answering.",
  "Do not call forbidden tools, live services, web browsers, local shell commands, or hidden files.",
  "When enough evidence is available, return only one JSON object that validates against the task output schema.",
].join(" ");

export async function runWorldTask(input) {
  const task = await resolveTask(input);
  const observations = await readObservationRows(path.join(task.taskDir, "tools", "tool-observations.jsonl"));
  const world = await readWorld(input.worldPath);
  const toolWorld = buildSnapshotToolWorld({
    spec: task.spec,
    observations,
  });
  const createdAt = (input.now ? new Date(input.now) : new Date()).toISOString();
  const runId = input.runId ?? buildRunId({
    createdAt,
    taskId: task.spec.task_id,
    model: input.model,
    worldId: world.world_id ?? "world",
  });
  const outDir = path.resolve(input.outDir);
  await fs.mkdir(outDir, { recursive: true });

  const messages = buildInitialMessages({
    spec: task.spec,
    toolWorld,
    systemPrompt: input.systemPrompt,
  });
  const toolIoRecords = [];
  const steps = [];
  const maxSteps = input.maxSteps ?? 12;
  let stopReason = "max_steps";
  let finalAnswer;
  let verifierResult;
  let finalParseError;

  for (let index = 0; index < maxSteps; index += 1) {
    const assistant = await createChatCompletion({
      baseUrl: input.baseUrl,
      apiKey: input.apiKey,
      model: input.model,
      timeoutMs: input.timeoutMs ?? 30000,
      body: {
        model: input.model,
        messages,
        tools: toolWorld.tools,
        tool_choice: "auto",
        parallel_tool_calls: false,
        ...(input.temperature !== undefined ? { temperature: input.temperature } : {}),
        ...(input.maxTokens !== undefined ? { max_tokens: input.maxTokens } : {}),
      },
    });
    const assistantMessage = assistantMessageFromResponse(assistant);
    messages.push(assistantMessage);

    if (!assistantMessage.tool_calls || assistantMessage.tool_calls.length === 0) {
      try {
        finalAnswer = parseStrictJsonObject(assistantMessage.content);
        const finalAnswerPath = path.join(outDir, "final_answer.json");
        await writeJson(finalAnswerPath, finalAnswer);
        verifierResult = await verifyTaskAnswer({
          taskDir: task.taskDir,
          answer: finalAnswer,
          answerPath: finalAnswerPath,
        });
        await writeJson(path.join(outDir, "verifier_result.json"), verifierResult);
        stopReason = "final_answer";
      } catch (error) {
        finalParseError = error instanceof Error ? error.message : String(error);
        stopReason = "final_parse_error";
        await writeJson(path.join(outDir, "verifier_result.json"), {
          schema_version: "agent_native_seed_verifier_result.v0",
          task_id: task.spec.task_id,
          family: task.spec.family,
          answer_path: path.relative(repoRoot, path.join(outDir, "final_answer.json")),
          passed: false,
          checks: [
            {
              name: "final_answer_json",
              passed: false,
              message: finalParseError,
            },
          ],
        });
      }
      steps.push({
        index,
        assistant_message: assistantMessage,
      });
      break;
    }

    if (assistantMessage.tool_calls.length > 1) {
      stopReason = "parallel_tool_call_rejected";
      steps.push({
        index,
        assistant_message: assistantMessage,
        error: "parallel tool calls are disabled for this world runner",
      });
      break;
    }

    const toolCall = assistantMessage.tool_calls[0];
    const toolArguments = parseToolArguments(toolCall.function.arguments, toolCall.function.name);
    const toolResult = toolWorld.callTool({
      modelToolName: toolCall.function.name,
      callId: toolCall.id,
      arguments: toolArguments,
      createdAt,
      runId,
      stepIndex: index,
    });
    const toolMessage = {
      role: "tool",
      tool_call_id: toolCall.id,
      name: toolCall.function.name,
      content: JSON.stringify(toolResult.toolMessageContent),
    };
    messages.push(toolMessage);
    toolIoRecords.push(toolResult.toolIoRecord);
    steps.push({
      index,
      assistant_message: assistantMessage,
      tool_call: {
        id: toolCall.id,
        model_tool_name: toolCall.function.name,
        tool_name: toolResult.toolName,
        arguments: toolArguments,
      },
      tool_message: toolMessage,
      observation_status: toolResult.toolIoRecord.observation.status,
      ...(toolResult.replayMiss ? { replay_miss: toolResult.replayMiss } : {}),
    });

    if (toolResult.replayMiss) {
      stopReason = "replay_miss";
      break;
    }
  }

  const run = {
    schema_version: "agent_native_world_run.v0",
    run_id: runId,
    world_id: world.world_id ?? "unknown",
    task_id: task.spec.task_id,
    family: task.spec.family,
    created_at: createdAt,
    model: {
      provider: "openai_compatible",
      model: input.model,
      base_url: input.baseUrl,
    },
    mode: "snapshot_observation_v0",
    live_fallback: false,
    messages_path: "messages.jsonl",
    tool_io_path: "tool_io.jsonl",
    final_answer_path: finalAnswer ? "final_answer.json" : null,
    verifier_result_path: "verifier_result.json",
    sft_tool_messages_path: verifierResult?.passed ? "sft.tool_messages.jsonl" : null,
    stop_reason: stopReason,
    tool_call_count: toolIoRecords.length,
    verifier_passed: verifierResult?.passed ?? false,
    failed_checks: verifierResult ? verifierResult.checks.filter((check) => !check.passed).map((check) => ({
      name: check.name,
      message: check.message,
    })) : [],
    tool_name_map: toolWorld.toolNameMap,
    steps,
  };

  await writeJsonl(path.join(outDir, "messages.jsonl"), messages);
  await writeJsonl(path.join(outDir, "tool_io.jsonl"), toolIoRecords);
  await writeJson(path.join(outDir, "run.json"), run);
  if (verifierResult?.passed) {
    await writeJsonl(path.join(outDir, "sft.tool_messages.jsonl"), [
      buildSftToolMessagesRow({
        task,
        run,
        messages,
        finalAnswer,
        verifierResult,
      }),
    ]);
  }

  return {
    ok: stopReason === "final_answer" && verifierResult?.passed === true,
    outDir,
    run,
    finalAnswer,
    verifierResult,
  };
}

function buildInitialMessages({ spec, toolWorld, systemPrompt }) {
  return [
    {
      role: "system",
      content: systemPrompt ?? DEFAULT_SYSTEM_PROMPT,
    },
    {
      role: "user",
      content: [
        spec.prompt,
        "",
        `Task id: ${spec.task_id}`,
        `Family: ${spec.family}`,
        `Shared output schema: ${spec.output_schema}`,
        `Family output schema: ${spec.family_output_schema}`,
        "",
        "Allowed model-visible tools:",
        JSON.stringify(toolWorld.tools.map((tool) => ({
          name: tool.function.name,
          description: tool.function.description,
          original_tool_name: toolWorld.originalNameForModelName.get(tool.function.name),
        })), null, 2),
        "",
        "Forbidden actions:",
        JSON.stringify(spec.forbidden_tools, null, 2),
        "",
        "Expected evidence path:",
        JSON.stringify(spec.expected_tool_path, null, 2),
        "",
        "Return the final answer as raw JSON only. Do not wrap it in Markdown.",
      ].join("\n"),
    },
  ];
}

function buildSnapshotToolWorld({ spec, observations }) {
  const exposedOriginalNames = new Set(observations
    .map((row) => row.tool_name)
    .filter((toolName) => spec.allowed_tools.includes(toolName)));
  const tools = [];
  const originalNameForModelName = new Map();
  const modelNameForOriginalName = new Map();
  for (const originalName of [...exposedOriginalNames].sort()) {
    const modelName = uniqueModelToolName(originalName, modelNameForOriginalName);
    modelNameForOriginalName.set(originalName, modelName);
    originalNameForModelName.set(modelName, originalName);
    const examples = observations.filter((row) => row.tool_name === originalName).map((row) => row.request);
    tools.push({
      type: "function",
      function: {
        name: modelName,
        description: [
          `Snapshot tool for original Datalox tool ${originalName}.`,
          "Arguments must match the current task world state; use values returned by earlier tool observations when available.",
          `Captured request example: ${truncate(JSON.stringify(examples[0] ?? {}), 900)}`,
        ].join(" "),
        parameters: inferObjectSchema(examples),
      },
    });
  }

  const recordsByReplayKey = new Map();
  const sourceCounters = new Map();
  for (const row of observations) {
    const requestHash = buildToolIoRequestHash(row.tool_name, row.request);
    const sequenceIndex = nextCounter(sourceCounters, requestHash);
    recordsByReplayKey.set(`${requestHash}:${sequenceIndex}`, {
      row,
      requestHash,
      sequenceIndex,
    });
  }
  const runCounters = new Map();

  return {
    tools,
    originalNameForModelName,
    toolNameMap: Object.fromEntries([...originalNameForModelName.entries()].map(([modelName, originalName]) => [modelName, originalName])),
    callTool({ modelToolName, callId, arguments: toolArguments, createdAt, runId, stepIndex }) {
      const originalName = originalNameForModelName.get(modelToolName);
      if (!originalName) {
        const observation = {
          status: "error",
          error_code: "unknown_tool",
          error_message: `Tool ${modelToolName} is not exposed by this world.`,
        };
        return buildToolResult({
          runId,
          callId,
          stepIndex,
          toolName: modelToolName,
          toolArguments,
          observation,
          createdAt,
          replayMiss: {
            code: "unknown_tool",
            message: observation.error_message,
            liveFallback: false,
          },
        });
      }

      const requestHash = buildToolIoRequestHash(originalName, toolArguments);
      const sequenceIndex = nextCounter(runCounters, requestHash);
      const source = recordsByReplayKey.get(`${requestHash}:${sequenceIndex}`);
      if (!source) {
        const replayMiss = {
          code: "replay_miss",
          message: `Replay miss for ${originalName} request_hash=${requestHash} sequence_index=${sequenceIndex}.`,
          request_hash: requestHash,
          sequence_index: sequenceIndex,
          tool_name: originalName,
          available_tool_names: [...originalNameForModelName.values()].sort(),
          liveFallback: false,
        };
        return buildToolResult({
          runId,
          callId,
          stepIndex,
          toolName: originalName,
          toolArguments,
          observation: {
            status: "error",
            error_code: "replay_miss",
            error_message: replayMiss.message,
            content: replayMiss,
          },
          createdAt,
          sequenceIndex,
          replayMiss,
        });
      }

      return buildToolResult({
        runId,
        callId,
        stepIndex,
        toolName: originalName,
        toolArguments,
        observation: toToolIoObservation(source.row.observation),
        createdAt,
        sourceRow: source.row,
        sequenceIndex,
      });
    },
  };
}

function buildToolResult({
  runId,
  callId,
  stepIndex,
  toolName,
  toolArguments,
  observation,
  createdAt,
  sourceRow,
  sequenceIndex,
  replayMiss,
}) {
  const requestHash = buildToolIoRequestHash(toolName, toolArguments);
  const toolIoRecord = {
    schema_version: "tool_io_record.v1",
    id: `tool_io:${runId}/${stepIndex}/${safeId(toolName)}`,
    call_id: callId,
    tool_name: toolName,
    arguments: toolArguments,
    request_hash: requestHash,
    sequence_index: sequenceIndex ?? 0,
    observation,
    created_at: createdAt,
    source: {
      host: "datalox-world-runner",
      command: "handoff/env-data-proof-v0/tools/run-world-task.mjs",
    },
    export: {
      allowed: true,
      redaction: "none_needed",
    },
  };
  const toolMessageContent = sourceRow ? {
    observation: sourceRow.observation,
    evidence_ids: sourceRow.evidence_ids,
    workspace_revision: sourceRow.workspace_revision,
  } : observation;
  return {
    toolName,
    toolIoRecord,
    toolMessageContent,
    replayMiss,
  };
}

function toToolIoObservation(observation) {
  if (observation && typeof observation === "object" && observation.ok === false) {
    return {
      status: "error",
      content: observation,
      error_code: typeof observation.error_code === "string" ? observation.error_code : "tool_error",
      error_message: typeof observation.error_message === "string" ? observation.error_message : "Tool returned ok=false.",
    };
  }
  return {
    status: "ok",
    content: observation,
  };
}

function buildSftToolMessagesRow({ task, run, messages, finalAnswer, verifierResult }) {
  return {
    schema_version: "agent_native_world_run_tool_message_sft_row.v0",
    task_id: task.spec.task_id,
    family: task.spec.family,
    split: task.spec.split,
    source_kind: "world_runner_snapshot_observation_v0",
    runtime_kind: "snapshot_observation_v0",
    message_format: "openai_tool_messages",
    messages,
    source_run_path: "run.json",
    verifier_result_path: "verifier_result.json",
    evidence_ids: finalAnswer.evidence_ids ?? [],
    verifier_passed: verifierResult.passed,
    export_gate: {
      allowed: true,
      redaction: "none_needed",
    },
  };
}

async function resolveTask(input) {
  if (input.taskPath) {
    const taskPath = path.resolve(input.taskPath);
    return {
      taskDir: path.dirname(taskPath),
      spec: await readJson(taskPath),
    };
  }
  const worldPath = path.resolve(input.worldPath ?? defaultWorldPath);
  const world = await readWorld(worldPath);
  const taskId = input.taskId;
  if (!taskId) throw new Error("Pass --task=<task.spec.json> or --task-id=<task_id>.");
  const worldRoot = path.dirname(worldPath);
  const roots = Array.isArray(world.task_roots) && world.task_roots.length > 0 ? world.task_roots : ["families"];
  for (const root of roots) {
    const taskSpecPaths = await findFiles(path.resolve(worldRoot, root), "task.spec.json");
    for (const taskSpecPath of taskSpecPaths) {
      const spec = await readJson(taskSpecPath);
      if (spec.task_id === taskId) {
        return {
          taskDir: path.dirname(taskSpecPath),
          spec,
        };
      }
    }
  }
  throw new Error(`Task ${taskId} not found in ${worldPath}.`);
}

async function readWorld(worldPath) {
  return readJson(path.resolve(worldPath ?? defaultWorldPath));
}

async function findFiles(root, fileName) {
  const entries = await fs.readdir(root, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const fullPath = path.join(root, entry.name);
    if (entry.isDirectory()) files.push(...await findFiles(fullPath, fileName));
    if (entry.isFile() && entry.name === fileName) files.push(fullPath);
  }
  return files;
}

async function readObservationRows(filePath) {
  const content = await fs.readFile(filePath, "utf8");
  return content.trim().split(/\r?\n/).filter(Boolean).map((line) => JSON.parse(line));
}

async function createChatCompletion({ baseUrl, apiKey, body, timeoutMs }) {
  const url = `${baseUrl.replace(/\/$/, "")}/chat/completions`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        ...(apiKey ? { authorization: `Bearer ${apiKey}` } : {}),
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    if (!response.ok) {
      const text = await response.text().catch(() => "");
      throw new Error(`OpenAI-compatible POST ${url} failed (${response.status}): ${text}`);
    }
    return await response.json();
  } finally {
    clearTimeout(timer);
  }
}

function assistantMessageFromResponse(response) {
  const message = response?.choices?.[0]?.message;
  if (!message || typeof message !== "object") throw new Error("OpenAI-compatible response missing assistant message.");
  return {
    role: "assistant",
    content: message.content ?? null,
    ...(Array.isArray(message.tool_calls) && message.tool_calls.length > 0 ? {
      tool_calls: message.tool_calls.map(parseModelToolCall),
    } : {}),
  };
}

function parseModelToolCall(toolCall) {
  if (!toolCall || typeof toolCall !== "object") throw new Error("Tool call must be an object.");
  if (typeof toolCall.id !== "string" || toolCall.id.length === 0) throw new Error("Tool call missing id.");
  if (!toolCall.function || typeof toolCall.function !== "object") throw new Error("Tool call missing function.");
  if (typeof toolCall.function.name !== "string" || toolCall.function.name.length === 0) throw new Error("Tool call missing function.name.");
  if (typeof toolCall.function.arguments !== "string") throw new Error("Tool call function.arguments must be a JSON string.");
  return {
    id: toolCall.id,
    type: "function",
    function: {
      name: toolCall.function.name,
      arguments: toolCall.function.arguments,
    },
  };
}

function parseToolArguments(argumentsJson, toolName) {
  const parsed = JSON.parse(argumentsJson);
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error(`Tool ${toolName} arguments must be a JSON object.`);
  }
  return parsed;
}

function parseStrictJsonObject(content) {
  if (typeof content !== "string" || content.trim().length === 0) {
    throw new Error("Final answer must be a non-empty JSON string.");
  }
  const parsed = JSON.parse(content);
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("Final answer JSON must be an object.");
  }
  return parsed;
}

function inferObjectSchema(examples) {
  const objectExamples = examples.filter((example) => example && typeof example === "object" && !Array.isArray(example));
  const allKeys = [...new Set(objectExamples.flatMap((example) => Object.keys(example)))].sort();
  const required = allKeys.filter((key) => objectExamples.length > 0 && objectExamples.every((example) => Object.prototype.hasOwnProperty.call(example, key)));
  return {
    type: "object",
    additionalProperties: true,
    properties: Object.fromEntries(allKeys.map((key) => [key, inferValueSchema(objectExamples.map((example) => example[key]))])),
    ...(required.length > 0 ? { required } : {}),
  };
}

function inferValueSchema(values) {
  const nonNull = values.filter((value) => value !== null && value !== undefined);
  const types = new Set(nonNull.map((value) => Array.isArray(value) ? "array" : typeof value));
  if (types.size === 1) {
    const [type] = [...types];
    if (type === "string" || type === "number" || type === "boolean") return { type };
    if (type === "array") return { type: "array", items: {} };
    if (type === "object") return { type: "object", additionalProperties: true };
  }
  return {};
}

function uniqueModelToolName(originalName, existing) {
  const base = toolNameToModelName(originalName);
  let candidate = base;
  let suffix = 2;
  while ([...existing.values()].includes(candidate)) {
    candidate = `${base}_${suffix}`;
    suffix += 1;
  }
  return candidate;
}

export function toolNameToModelName(toolName) {
  const sanitized = toolName.replace(/[^a-zA-Z0-9_-]/g, "__");
  if (/^[a-zA-Z_]/.test(sanitized)) return sanitized.slice(0, 64);
  return `tool_${sanitized}`.slice(0, 64);
}

function buildToolIoRequestHash(toolName, toolArguments) {
  return sha256Hex(canonicalJson({ arguments: toolArguments, tool_name: toolName }));
}

function buildRunId(input) {
  return `world-run-${sha256Hex(canonicalJson(input)).slice(0, 16)}`;
}

function nextCounter(counters, key) {
  const next = counters.get(key) ?? 0;
  counters.set(key, next + 1);
  return next;
}

function canonicalJson(value) {
  return serializeCanonicalJson(value);
}

function serializeCanonicalJson(value) {
  if (value === null) return "null";
  if (typeof value === "string") return JSON.stringify(value);
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) throw new Error("Numbers in canonical JSON must be finite.");
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) return `[${value.map(serializeCanonicalJson).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${serializeCanonicalJson(value[key])}`).join(",")}}`;
  }
  throw new Error(`Unsupported canonical JSON value: ${typeof value}.`);
}

function sha256Hex(value) {
  return createHash("sha256").update(value).digest("hex");
}

function safeId(value) {
  return value.replace(/[^a-zA-Z0-9._:@#/?=-]+/g, "_");
}

function truncate(value, maxLength) {
  return value.length <= maxLength ? value : `${value.slice(0, maxLength)}...`;
}

async function readJson(filePath) {
  return JSON.parse(await fs.readFile(filePath, "utf8"));
}

async function writeJson(filePath, value) {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.writeFile(filePath, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

async function writeJsonl(filePath, rows) {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.writeFile(filePath, rows.length === 0 ? "" : `${rows.map((row) => JSON.stringify(row)).join("\n")}\n`, "utf8");
}

function parseArgs(argv) {
  const args = { _: [] };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (!arg.startsWith("--")) {
      args._.push(arg);
      continue;
    }
    const key = arg.slice(2);
    const next = argv[index + 1];
    const value = next !== undefined && !next.startsWith("--") ? next : true;
    if (value !== true) index += 1;
    if (args[key] === undefined) args[key] = value;
    else if (Array.isArray(args[key])) args[key].push(value);
    else args[key] = [args[key], value];
  }
  return args;
}

function requireString(args, key) {
  if (typeof args[key] !== "string" || args[key].trim().length === 0) {
    throw new Error(`--${key} is required.`);
  }
  return args[key];
}

function optionalNumber(value) {
  if (value === undefined) return undefined;
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) throw new Error(`Expected number, got ${JSON.stringify(value)}.`);
  return parsed;
}

function optionalInteger(value) {
  if (value === undefined) return undefined;
  const parsed = Number.parseInt(value, 10);
  if (!Number.isInteger(parsed) || parsed < 1 || String(parsed) !== String(value)) {
    throw new Error(`Expected positive integer, got ${JSON.stringify(value)}.`);
  }
  return parsed;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const args = parseArgs(process.argv.slice(2));
  runWorldTask({
    worldPath: typeof args.world === "string" ? args.world : defaultWorldPath,
    taskPath: typeof args.task === "string" ? args.task : undefined,
    taskId: typeof args["task-id"] === "string" ? args["task-id"] : undefined,
    model: requireString(args, "model"),
    baseUrl: requireString(args, "base-url"),
    apiKey: typeof args["api-key"] === "string" ? args["api-key"] : undefined,
    outDir: requireString(args, "out"),
    maxSteps: optionalInteger(args["max-steps"]),
    maxTokens: optionalInteger(args["max-tokens"]),
    timeoutMs: optionalInteger(args["timeout-ms"]),
    temperature: optionalNumber(args.temperature),
    now: typeof args.now === "string" ? args.now : undefined,
    runId: typeof args["run-id"] === "string" ? args["run-id"] : undefined,
  }).then((result) => {
    process.stdout.write(`${JSON.stringify({
      ok: result.ok,
      out_dir: path.relative(repoRoot, result.outDir),
      task_id: result.run.task_id,
      stop_reason: result.run.stop_reason,
      tool_call_count: result.run.tool_call_count,
      verifier_passed: result.run.verifier_passed,
      failed_checks: result.run.failed_checks,
    }, null, 2)}\n`);
    if (args["require-pass"] === true && !result.ok) process.exitCode = 1;
  }).catch((error) => {
    process.stderr.write(`${error.stack ?? error.message}\n`);
    process.exitCode = 1;
  });
}
