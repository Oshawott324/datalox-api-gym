import { z } from "zod";

import { isSafeRelativePath } from "./pathSafety.js";

const nonEmptyString = z.string().min(1);
const fixtureId = z.string().regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/);
const fixtureVersion = z.string().regex(/^[0-9]{4}-[0-9]{2}\.[0-9]+$/);
const fixtureRef = z.string().regex(/^[a-z0-9]+(?:-[a-z0-9]+)*@[0-9]{4}-[0-9]{2}\.[0-9]+$/);
const safeRelativePath = z.string().min(1).refine(isSafeRelativePath, {
  message: "path must be a safe relative path inside the fixture-set directory",
});

const evalPromptsSchema = z
  .object({
    path: safeRelativePath,
    count: z.number().int().positive(),
  })
  .strict();

const releaseSchema = z
  .object({
    immutable: z.boolean(),
    license: nonEmptyString,
    tags: z.array(z.string().regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/)).min(1),
  })
  .strict();

export const fixtureSetManifestSchema = z
  .object({
    $schema: nonEmptyString,
    id: fixtureId,
    version: fixtureVersion,
    name: nonEmptyString,
    description: nonEmptyString,
    status: z.enum(["draft", "verified", "released", "deprecated"]),
    fixtures: z.array(fixtureRef).min(1),
    evalPrompts: evalPromptsSchema.optional(),
    release: releaseSchema,
  })
  .strict()
  .superRefine((manifest, context) => {
    if (manifest.status === "released" && !manifest.release.immutable) {
      context.addIssue({
        code: "custom",
        path: ["release", "immutable"],
        message: "released fixture sets must be immutable",
      });
    }
  });

export type FixtureSetManifest = z.infer<typeof fixtureSetManifestSchema>;

export class FixtureSetManifestValidationError extends Error {
  readonly issues: z.ZodIssue[];

  constructor(issues: z.ZodIssue[]) {
    super(`Invalid fixture-set manifest: ${formatZodIssues(issues)}`);
    this.name = "FixtureSetManifestValidationError";
    this.issues = issues;
  }
}

export function parseFixtureSetManifest(input: unknown): FixtureSetManifest {
  const parsed = fixtureSetManifestSchema.safeParse(input);
  if (!parsed.success) {
    throw new FixtureSetManifestValidationError(parsed.error.issues);
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
