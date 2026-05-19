import { existsSync } from "node:fs";
import { mkdir, readdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

import type { ListToolsResult } from "@modelcontextprotocol/sdk/types.js";

import { canonicalJson } from "./canonicalJson.js";
import { sha256Hex } from "./hash.js";
import {
  parseMcpToolCatalogV1,
  type McpToolCatalogToolV1,
  type McpToolCatalogV1,
} from "./mcpToolCatalogSchema.js";

export const MCP_TOOL_CATALOGS_RELATIVE_DIR = path.join(".datalox", "mcp-tool-catalogs");

interface ExportGate {
  allowed: boolean;
  redaction: "none_needed" | "applied" | "blocked";
  approval_id?: string;
}

export interface RecordMcpToolCatalogInput {
  repoPath?: string;
  upstream: {
    command: string;
    args: string[];
    cwd?: string;
  };
  listToolsResult: ListToolsResult;
  export?: ExportGate;
  now?: Date;
}

export interface RecordMcpToolCatalogResult {
  catalogPath: string;
  catalog: McpToolCatalogV1;
}

export async function recordMcpToolCatalog(
  input: RecordMcpToolCatalogInput,
): Promise<RecordMcpToolCatalogResult> {
  const repoRoot = resolveRepoRoot(input.repoPath);
  const createdAt = (input.now ?? new Date()).toISOString();
  const candidate = {
    schema_version: "mcp_tool_catalog.v1",
    id: "pending",
    created_at: createdAt,
    upstream: input.upstream,
    ...(input.listToolsResult.nextCursor !== undefined
      ? { next_cursor: input.listToolsResult.nextCursor }
      : {}),
    ...(input.listToolsResult._meta !== undefined ? { _meta: input.listToolsResult._meta } : {}),
    tools: input.listToolsResult.tools.map(toolToCatalogTool),
    export: input.export ?? {
      allowed: false,
      redaction: "blocked",
    },
  };
  const id = buildCatalogId({
    created_at: candidate.created_at,
    upstream: candidate.upstream,
    ...(candidate.next_cursor !== undefined ? { next_cursor: candidate.next_cursor } : {}),
    ...(candidate._meta !== undefined ? { _meta: candidate._meta } : {}),
    tools: candidate.tools,
    export: candidate.export,
  });
  const catalog = parseMcpToolCatalogV1({
    ...candidate,
    id,
  });
  const catalogPath = normalizeRelativePath(path.join(
    MCP_TOOL_CATALOGS_RELATIVE_DIR,
    `${catalog.id}.json`,
  ));
  const absoluteCatalogPath = path.join(repoRoot, catalogPath);

  await mkdir(path.dirname(absoluteCatalogPath), { recursive: true });
  await writeFile(absoluteCatalogPath, `${JSON.stringify(catalog, null, 2)}\n`, {
    encoding: "utf8",
    flag: "wx",
  });

  return {
    catalogPath,
    catalog,
  };
}

export async function readMcpToolCatalogs(repoPath?: string): Promise<McpToolCatalogV1[]> {
  const repoRoot = resolveRepoRoot(repoPath);
  const catalogsRoot = path.join(repoRoot, MCP_TOOL_CATALOGS_RELATIVE_DIR);
  if (!existsSync(catalogsRoot)) {
    return [];
  }

  const catalogPaths = await listJsonFiles(catalogsRoot);
  const catalogs: McpToolCatalogV1[] = [];
  for (const catalogPath of catalogPaths.sort()) {
    catalogs.push(parseMcpToolCatalogV1(JSON.parse(await readFile(catalogPath, "utf8"))));
  }
  return catalogs.sort(compareMcpToolCatalogs);
}

export function mcpToolCatalogToListToolsResult(catalog: McpToolCatalogV1): ListToolsResult {
  return {
    ...(catalog._meta !== undefined ? { _meta: catalog._meta } : {}),
    ...(catalog.next_cursor !== undefined ? { nextCursor: catalog.next_cursor } : {}),
    tools: catalog.tools.map(catalogToolToTool),
  };
}

export function strictPassthroughToolCatalogTool(toolName: string): McpToolCatalogToolV1 {
  return {
    name: toolName,
    description: `Datalox replay-mode proxy for recorded tool ${toolName}.`,
    input_schema: {
      type: "object",
      additionalProperties: true,
    },
  };
}

export function compareMcpToolCatalogs(
  first: McpToolCatalogV1,
  second: McpToolCatalogV1,
): number {
  return first.created_at.localeCompare(second.created_at) || first.id.localeCompare(second.id);
}

function toolToCatalogTool(tool: ListToolsResult["tools"][number]): McpToolCatalogToolV1 {
  return parseCatalogTool({
    name: tool.name,
    ...(tool.title !== undefined ? { title: tool.title } : {}),
    ...(tool.description !== undefined ? { description: tool.description } : {}),
    input_schema: tool.inputSchema,
    ...(tool.outputSchema !== undefined ? { output_schema: tool.outputSchema } : {}),
    ...(tool.annotations !== undefined ? { annotations: tool.annotations } : {}),
    ...(tool.execution !== undefined ? { execution: tool.execution } : {}),
    ...(tool.icons !== undefined ? { icons: tool.icons } : {}),
    ...(tool._meta !== undefined ? { _meta: tool._meta } : {}),
  });
}

function catalogToolToTool(tool: McpToolCatalogToolV1): ListToolsResult["tools"][number] {
  return {
    name: tool.name,
    ...(tool.title !== undefined ? { title: tool.title } : {}),
    ...(tool.description !== undefined ? { description: tool.description } : {}),
    inputSchema: tool.input_schema as ListToolsResult["tools"][number]["inputSchema"],
    ...(tool.output_schema !== undefined
      ? { outputSchema: tool.output_schema as NonNullable<ListToolsResult["tools"][number]["outputSchema"]> }
      : {}),
    ...(tool.annotations !== undefined
      ? { annotations: tool.annotations as NonNullable<ListToolsResult["tools"][number]["annotations"]> }
      : {}),
    ...(tool.execution !== undefined
      ? { execution: tool.execution as NonNullable<ListToolsResult["tools"][number]["execution"]> }
      : {}),
    ...(tool.icons !== undefined
      ? { icons: tool.icons as NonNullable<ListToolsResult["tools"][number]["icons"]> }
      : {}),
    ...(tool._meta !== undefined ? { _meta: tool._meta } : {}),
  };
}

function parseCatalogTool(tool: unknown): McpToolCatalogToolV1 {
  return parseMcpToolCatalogV1({
    schema_version: "mcp_tool_catalog.v1",
    id: "validation-only",
    created_at: "1970-01-01T00:00:00.000Z",
    upstream: {
      command: "validation-only",
      args: [],
    },
    tools: [tool],
    export: {
      allowed: false,
      redaction: "blocked",
    },
  }).tools[0];
}

function buildCatalogId(payload: unknown): string {
  return `mcp-tool-catalog-${sha256Hex(canonicalJson(payload)).slice(0, 24)}`;
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

function resolveRepoRoot(repoPath: string | undefined): string {
  return path.resolve(repoPath ?? process.cwd());
}

function normalizeRelativePath(filePath: string): string {
  return filePath.split(path.sep).join("/");
}
