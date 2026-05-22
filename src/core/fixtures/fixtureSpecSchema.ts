import { readFile } from "node:fs/promises";

import { z } from "zod";

import { isSafeRelativePath, resolveInside } from "./pathSafety.js";

const nonEmptyString = z.string().min(1);
const specId = z.string().regex(/^[a-z0-9]+(?:[._-][a-z0-9]+)*$/);
const specVersion = z.string().regex(/^[0-9]{4}-[0-9]{2}\.[0-9]+$/);
const fixtureRef = z.string().regex(/^[a-z0-9]+(?:-[a-z0-9]+)*@[0-9]{4}-[0-9]{2}\.[0-9]+$/);
const toolName = z.string().regex(/^[A-Za-z0-9_.:/-]+$/);
const safeRelativePath = z.string().min(1).refine(isSafeRelativePath, {
  message: "path must be a safe relative path inside the fixture or fixture-set directory",
});

const specFileReferenceSchema = z
  .object({
    path: safeRelativePath,
  })
  .strict();

export const fixtureSpecReferencesSchema = z
  .object({
    taskSpecs: z.array(specFileReferenceSchema).optional(),
    verifierSpecs: z.array(specFileReferenceSchema).optional(),
    scaffoldSpecs: z.array(specFileReferenceSchema).optional(),
  })
  .strict()
  .superRefine((specs, context) => {
    const seenPaths = new Set<string>();
    for (const [kind, entries] of Object.entries(specs)) {
      for (const entry of entries ?? []) {
        const key = `${kind}:${entry.path}`;
        if (seenPaths.has(key)) {
          context.addIssue({
            code: "custom",
            path: [kind, "path"],
            message: `duplicate spec path ${entry.path}`,
          });
        }
        seenPaths.add(key);
      }
    }
  });

const taskSpecBaseSchema = z
  .object({
    id: specId,
    version: specVersion,
    name: nonEmptyString,
    description: nonEmptyString,
  })
  .strict();

export const taskSpecSchema = taskSpecBaseSchema
  .extend({
    schema_version: z.literal("datalox_task_spec.v1"),
    goal: nonEmptyString,
    fixtureRefs: z.array(fixtureRef).optional(),
    allowedTools: z.array(toolName).optional(),
    successCriteria: z.array(nonEmptyString).min(1),
    constraints: z.array(nonEmptyString).optional(),
  })
  .strict();

export const verifierSpecSchema = taskSpecBaseSchema
  .extend({
    schema_version: z.literal("datalox_verifier_spec.v1"),
    verifier: z
      .object({
        kind: z.enum(["manual", "command", "mcp", "http", "external"]),
        command: nonEmptyString.optional(),
        args: z.array(z.string()).optional(),
        toolName: toolName.optional(),
        endpoint: nonEmptyString.optional(),
      })
      .strict(),
    requiredEvidence: z.array(z.enum([
      "replay_bundle",
      "tool_io_records",
      "mcp_tool_catalog",
      "agent_turns",
      "final_answer",
      "runtime_artifacts",
    ])).min(1),
    reward: z
      .object({
        type: z.enum(["none", "binary", "score", "rubric"]),
        version: nonEmptyString,
        maxScore: z.number().positive().optional(),
      })
      .strict()
      .optional(),
    antiHackingChecks: z.array(nonEmptyString).optional(),
  })
  .strict()
  .superRefine((spec, context) => {
    if (spec.verifier.kind === "command" && !spec.verifier.command) {
      context.addIssue({
        code: "custom",
        path: ["verifier", "command"],
        message: "command verifiers must declare command metadata",
      });
    }
    if (spec.verifier.kind === "mcp" && !spec.verifier.toolName) {
      context.addIssue({
        code: "custom",
        path: ["verifier", "toolName"],
        message: "mcp verifiers must declare toolName metadata",
      });
    }
    if (spec.verifier.kind === "http" && !spec.verifier.endpoint) {
      context.addIssue({
        code: "custom",
        path: ["verifier", "endpoint"],
        message: "http verifiers must declare endpoint metadata",
      });
    }
  });

export const scaffoldSpecSchema = taskSpecBaseSchema
  .extend({
    schema_version: z.literal("datalox_scaffold_spec.v1"),
    harness: nonEmptyString,
    promptContract: nonEmptyString.optional(),
    modelVisibleTools: z.array(toolName).optional(),
    contextPolicy: z
      .object({
        maxTurns: z.number().int().positive().optional(),
        allowedFixtureRefs: z.array(fixtureRef).optional(),
      })
      .strict()
      .optional(),
  })
  .strict();

export type FixtureSpecReferences = z.infer<typeof fixtureSpecReferencesSchema>;
export type TaskSpec = z.infer<typeof taskSpecSchema>;
export type VerifierSpec = z.infer<typeof verifierSpecSchema>;
export type ScaffoldSpec = z.infer<typeof scaffoldSpecSchema>;
export type FixtureSpecKind = "task" | "verifier" | "scaffold";

export interface ResolvedFixtureSpec {
  kind: FixtureSpecKind;
  schemaVersion: "datalox_task_spec.v1" | "datalox_verifier_spec.v1" | "datalox_scaffold_spec.v1";
  id: string;
  version: string;
  ref: string;
  path: string;
  absolutePath: string;
}

export interface ResolvedFixtureSpecs {
  taskSpecs: ResolvedFixtureSpec[];
  verifierSpecs: ResolvedFixtureSpec[];
  scaffoldSpecs: ResolvedFixtureSpec[];
}

export class FixtureSpecValidationError extends Error {
  readonly issues: z.ZodIssue[];

  constructor(kind: string, filePath: string, issues: z.ZodIssue[]) {
    super(`Invalid ${kind} spec ${filePath}: ${formatZodIssues(issues)}`);
    this.name = "FixtureSpecValidationError";
    this.issues = issues;
  }
}

export function emptyResolvedFixtureSpecs(): ResolvedFixtureSpecs {
  return {
    taskSpecs: [],
    verifierSpecs: [],
    scaffoldSpecs: [],
  };
}

export async function readFixtureSpecs(
  baseDir: string,
  references?: FixtureSpecReferences,
): Promise<ResolvedFixtureSpecs> {
  if (!references) {
    return emptyResolvedFixtureSpecs();
  }

  const specs = {
    taskSpecs: await readSpecGroup(baseDir, "task", references.taskSpecs ?? [], taskSpecSchema),
    verifierSpecs: await readSpecGroup(baseDir, "verifier", references.verifierSpecs ?? [], verifierSpecSchema),
    scaffoldSpecs: await readSpecGroup(baseDir, "scaffold", references.scaffoldSpecs ?? [], scaffoldSpecSchema),
  };
  assertUniqueSpecRefs(specs);
  return specs;
}

export function resolvedFixtureSpecRefs(specs: ResolvedFixtureSpecs): {
  taskSpecs: string[];
  verifierSpecs: string[];
  scaffoldSpecs: string[];
} {
  return {
    taskSpecs: specs.taskSpecs.map((spec) => spec.ref),
    verifierSpecs: specs.verifierSpecs.map((spec) => spec.ref),
    scaffoldSpecs: specs.scaffoldSpecs.map((spec) => spec.ref),
  };
}

export function parseTaskSpec(input: unknown): TaskSpec {
  return parseSpec("task", "<inline>", input, taskSpecSchema);
}

export function parseVerifierSpec(input: unknown): VerifierSpec {
  return parseSpec("verifier", "<inline>", input, verifierSpecSchema);
}

export function parseScaffoldSpec(input: unknown): ScaffoldSpec {
  return parseSpec("scaffold", "<inline>", input, scaffoldSpecSchema);
}

async function readSpecGroup<T extends TaskSpec | VerifierSpec | ScaffoldSpec>(
  baseDir: string,
  kind: FixtureSpecKind,
  references: { path: string }[],
  schema: z.ZodType<T>,
): Promise<ResolvedFixtureSpec[]> {
  const specs = [];
  for (const reference of references) {
    const absolutePath = resolveInside(baseDir, reference.path);
    const parsed = parseSpec(kind, reference.path, JSON.parse(await readFile(absolutePath, "utf8")), schema);
    specs.push({
      kind,
      schemaVersion: parsed.schema_version,
      id: parsed.id,
      version: parsed.version,
      ref: `${parsed.id}@${parsed.version}`,
      path: reference.path,
      absolutePath,
    });
  }
  return specs;
}

function parseSpec<T>(
  kind: string,
  filePath: string,
  input: unknown,
  schema: z.ZodType<T>,
): T {
  const parsed = schema.safeParse(input);
  if (!parsed.success) {
    throw new FixtureSpecValidationError(kind, filePath, parsed.error.issues);
  }
  return parsed.data;
}

function assertUniqueSpecRefs(specs: ResolvedFixtureSpecs): void {
  const seen = new Set<string>();
  for (const group of [specs.taskSpecs, specs.verifierSpecs, specs.scaffoldSpecs]) {
    for (const spec of group) {
      const key = `${spec.kind}:${spec.ref}`;
      if (seen.has(key)) {
        throw new Error(`Duplicate ${spec.kind} spec ref ${spec.ref}.`);
      }
      seen.add(key);
    }
  }
}

function formatZodIssues(issues: z.ZodIssue[]): string {
  return issues
    .map((issue) => {
      const issuePath = issue.path.length > 0 ? issue.path.join(".") : "<root>";
      return `${issuePath}: ${issue.message}`;
    })
    .join("; ");
}
