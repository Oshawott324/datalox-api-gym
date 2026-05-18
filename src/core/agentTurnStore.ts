import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

import { parseAgentTurnV1, type AgentTurnV1 } from "./agentTurnSchema.js";

export const AGENT_TURNS_RELATIVE_DIR = path.join(".datalox", "events", "agent-turns");

type JsonObject = Record<string, unknown>;

export interface RecordAgentTurnInput {
  repoPath?: string;
  agentTurn: unknown;
  now?: Date;
}

export interface RecordAgentTurnResult {
  eventPath: string;
  turnId: string;
  event: {
    relativePath: string;
    payload: JsonObject;
  };
}

export function getAgentTurnFromPayload(payload: unknown): AgentTurnV1 | null {
  const object = getObject(payload);
  if (object.schema_version === "agent_turn.v1") {
    return parseAgentTurnV1(object);
  }
  const wrapped = getObject(object.agentTurn);
  if (wrapped.schema_version === "agent_turn.v1") {
    return parseAgentTurnV1(wrapped);
  }
  return null;
}

export async function recordAgentTurn(input: RecordAgentTurnInput): Promise<RecordAgentTurnResult> {
  const repoRoot = path.resolve(input.repoPath ?? process.cwd());
  const agentTurn = parseAgentTurnV1(input.agentTurn);
  const timestamp = (input.now ?? new Date()).toISOString();
  const relativePath = normalizeRelativePath(path.join(
    AGENT_TURNS_RELATIVE_DIR,
    `${safeTimestamp(timestamp)}--agent-turn-${slugify(agentTurn.id)}.json`,
  ));
  const eventPath = path.join(repoRoot, relativePath);
  const payload = buildAgentTurnEventPayload(agentTurn, relativePath, timestamp);

  await mkdir(path.dirname(eventPath), { recursive: true });
  await writeFile(eventPath, `${JSON.stringify(payload, null, 2)}\n`, {
    encoding: "utf8",
    flag: "wx",
  });

  return {
    eventPath: relativePath,
    turnId: agentTurn.id,
    event: {
      relativePath,
      payload,
    },
  };
}

function buildAgentTurnEventPayload(
  agentTurn: AgentTurnV1,
  relativePath: string,
  timestamp: string,
): JsonObject {
  return {
    version: 1,
    id: relativePath.replace(/\.json$/, ""),
    timestamp,
    eventKind: "agent_turn",
    eventClass: "trace",
    sourceKind: "trace",
    sessionId: agentTurn.session_id,
    turnId: agentTurn.id,
    summary: agentTurn.assistant_summary ?? agentTurn.user_prompt ?? `Agent turn ${agentTurn.id}`,
    agentTurn,
  };
}

function getObject(value: unknown): JsonObject {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as JsonObject) : {};
}

function safeTimestamp(timestamp: string): string {
  return timestamp.replace(/[:.]/g, "-");
}

function slugify(value: string): string {
  const slug = value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);
  return slug.length > 0 ? slug : "turn";
}

function normalizeRelativePath(filePath: string): string {
  return filePath.split(path.sep).join("/");
}
