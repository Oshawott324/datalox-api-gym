import { z } from "zod";

import { canonicalJson, CanonicalJsonError } from "./canonicalJson.js";

const nonEmptyString = z.string().min(1);
const jsonObject = z.record(z.string(), z.unknown());

const exportGateSchema = z
  .object({
    allowed: z.boolean(),
    redaction: z.enum(["none_needed", "applied", "blocked"]),
    approval_id: z.string().optional(),
  })
  .strict();

const mcpToolCatalogToolSchema = z
  .object({
    name: nonEmptyString,
    title: z.string().optional(),
    description: z.string().optional(),
    input_schema: jsonObject,
    output_schema: jsonObject.optional(),
    annotations: jsonObject.optional(),
    execution: jsonObject.optional(),
    icons: z.array(jsonObject).optional(),
    _meta: jsonObject.optional(),
  })
  .strict();

export const mcpToolCatalogV1Schema = z
  .object({
    schema_version: z.literal("mcp_tool_catalog.v1"),
    id: nonEmptyString,
    created_at: nonEmptyString,
    upstream: z
      .object({
        command: nonEmptyString,
        args: z.array(z.string()),
        cwd: z.string().optional(),
      })
      .strict(),
    next_cursor: z.string().optional(),
    _meta: jsonObject.optional(),
    tools: z.array(mcpToolCatalogToolSchema),
    export: exportGateSchema,
  })
  .strict()
  .superRefine((catalog, context) => {
    try {
      canonicalJson(catalog);
    } catch (error) {
      addCanonicalJsonIssue(context, [], error);
    }
  });

export type McpToolCatalogToolV1 = z.infer<typeof mcpToolCatalogToolSchema>;
export type McpToolCatalogV1 = z.infer<typeof mcpToolCatalogV1Schema>;

export class McpToolCatalogValidationError extends Error {
  readonly issues: z.ZodIssue[];

  constructor(issues: z.ZodIssue[]) {
    super(`Invalid mcp_tool_catalog.v1 artifact: ${formatZodIssues(issues)}`);
    this.name = "McpToolCatalogValidationError";
    this.issues = issues;
  }
}

export function parseMcpToolCatalogV1(input: unknown): McpToolCatalogV1 {
  const parsed = mcpToolCatalogV1Schema.safeParse(input);
  if (!parsed.success) {
    throw new McpToolCatalogValidationError(parsed.error.issues);
  }
  return parsed.data;
}

function addCanonicalJsonIssue(
  context: z.RefinementCtx,
  path: Array<string | number>,
  error: unknown,
): void {
  context.addIssue({
    code: "custom",
    path,
    message: error instanceof CanonicalJsonError
      ? `value must be canonical JSON serializable: ${error.message}`
      : "value must be canonical JSON serializable.",
  });
}

function formatZodIssues(issues: z.ZodIssue[]): string {
  return issues
    .map((issue) => {
      const issuePath = issue.path.length > 0 ? issue.path.join(".") : "<root>";
      return `${issuePath}: ${issue.message}`;
    })
    .join("; ");
}
