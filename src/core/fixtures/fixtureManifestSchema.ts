import { z } from "zod";

import { isSafeRelativePath } from "./pathSafety.js";

const nonEmptyString = z.string().min(1);
const fixtureId = z.string().regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/);
const fixtureVersion = z.string().regex(/^[0-9]{4}-[0-9]{2}\.[0-9]+$/);
const sha256Hex = z.string().regex(/^[a-f0-9]{64}$/);
const safeRelativePath = z.string().min(1).refine(isSafeRelativePath, {
  message: "path must be a safe relative path inside the fixture directory",
});

const engineSchema = z
  .object({
    package: nonEmptyString,
    minimumVersion: z.string().regex(/^[0-9]+(?:\.[0-9]+){2}(?:[-+][A-Za-z0-9.-]+)?$/),
  })
  .strict();

const toolSurfaceSchema = z
  .object({
    surface: z.enum(["mcp", "api", "cli"]),
    server: z.string().regex(/^[A-Za-z0-9_.:/-]+$/),
    operations: z.array(z.string().regex(/^[A-Za-z0-9_.:/-]+$/)).min(1),
  })
  .strict();

const bundleSchema = z
  .object({
    path: safeRelativePath,
    schemaVersion: z.literal("replay_bundle.v1"),
    sha256: sha256Hex,
  })
  .strict();

const evalPromptsSchema = z
  .object({
    path: safeRelativePath,
    count: z.number().int().positive(),
  })
  .strict();

const provenanceSchema = z
  .object({
    source: nonEmptyString,
    recordedAt: z.string().regex(/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/),
    reviewedBy: nonEmptyString,
    redaction: z.enum(["none_needed", "applied", "blocked"]),
    notes: z.string().min(1).optional(),
  })
  .strict();

const releaseSchema = z
  .object({
    immutable: z.boolean(),
    license: nonEmptyString,
    tags: z.array(z.string().regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/)).min(1),
  })
  .strict();

export const fixtureManifestSchema = z
  .object({
    $schema: nonEmptyString,
    id: fixtureId,
    version: fixtureVersion,
    name: nonEmptyString,
    description: nonEmptyString,
    status: z.enum(["draft", "verified", "released", "deprecated"]),
    engine: engineSchema,
    tools: z.array(toolSurfaceSchema).min(1),
    bundle: bundleSchema,
    evalPrompts: evalPromptsSchema,
    provenance: provenanceSchema,
    release: releaseSchema,
  })
  .strict()
  .superRefine((manifest, context) => {
    if (manifest.status === "released" && !manifest.release.immutable) {
      context.addIssue({
        code: "custom",
        path: ["release", "immutable"],
        message: "released fixtures must be immutable",
      });
    }
    if (
      manifest.provenance.redaction === "blocked"
      && (manifest.status === "verified" || manifest.status === "released")
    ) {
      context.addIssue({
        code: "custom",
        path: ["provenance", "redaction"],
        message: "blocked redaction cannot be verified or released",
      });
    }
  });

export type FixtureManifest = z.infer<typeof fixtureManifestSchema>;

export class FixtureManifestValidationError extends Error {
  readonly issues: z.ZodIssue[];

  constructor(issues: z.ZodIssue[]) {
    super(`Invalid fixture manifest: ${formatZodIssues(issues)}`);
    this.name = "FixtureManifestValidationError";
    this.issues = issues;
  }
}

export function parseFixtureManifest(input: unknown): FixtureManifest {
  const parsed = fixtureManifestSchema.safeParse(input);
  if (!parsed.success) {
    throw new FixtureManifestValidationError(parsed.error.issues);
  }
  return parsed.data;
}

function formatZodIssues(issues: z.ZodIssue[]): string {
  return issues
    .map((issue) => {
      const issuePath = issue.path.length > 0 ? issue.path.join(".") : "<root>";
      return `${issuePath}: ${issue.message}`;
    })
    .join("; ");
}
