import { z } from "zod";

import { isSafeRelativePath } from "./pathSafety.js";

const nonEmptyString = z.string().min(1);
const fixtureId = z.string().regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/);
const fixtureVersion = z.string().regex(/^[0-9]{4}-[0-9]{2}\.[0-9]+$/);
const fixtureRef = z.string().regex(/^[a-z0-9]+(?:-[a-z0-9]+)*@[0-9]{4}-[0-9]{2}\.[0-9]+$/);
const sha256Hex = z.string().regex(/^[a-f0-9]{64}$/);
const safeRelativePath = z.string().min(1).refine(isSafeRelativePath, {
  message: "path must be a safe relative path inside the catalog root",
});
const exportGateSchema = z
  .object({
    allowed: z.boolean(),
    redaction: z.enum(["none_needed", "applied", "blocked"]),
    approval_id: z.string().optional(),
  })
  .strict();

const toolSurfaceSchema = z
  .object({
    surface: z.enum(["mcp", "api", "http", "cli", "browser", "sandbox"]),
    server: z.string(),
    operations: z.array(z.string()).min(1),
    adapter: z
      .object({
        protocol: z.string().optional(),
        toolCatalogSource: z.string().optional(),
      })
      .strict()
      .optional(),
  })
  .strict();

const releaseCatalogSchema = z
  .object({
    immutable: z.boolean(),
    license: nonEmptyString,
    archive_path: safeRelativePath,
    archive_sha256: sha256Hex.optional(),
    checksum_path: safeRelativePath,
    checksum_sha256: sha256Hex.optional(),
  })
  .strict();

const catalogTrustSchema = z
  .object({
    schema_version: z.literal("datalox_fixture_trust.v1"),
    artifact_ref: fixtureRef,
    verified_at: nonEmptyString,
    verified_by: nonEmptyString,
    review_type: nonEmptyString,
    export: exportGateSchema,
    provenance: z
      .object({
        source: nonEmptyString,
        recorded_at: nonEmptyString,
        reviewed_by: nonEmptyString,
        redaction: z.enum(["none_needed", "applied", "blocked"]),
      })
      .strict()
      .optional(),
    bundle: z
      .object({
        id: nonEmptyString,
        path: safeRelativePath,
        sha256: sha256Hex,
        export: exportGateSchema,
      })
      .strict()
      .optional(),
    archive: z
      .object({
        path: safeRelativePath,
        sha256: sha256Hex,
      })
      .strict()
      .optional(),
    tool_catalogs: z
      .array(z
        .object({
          path: safeRelativePath,
          id: nonEmptyString,
          sha256: sha256Hex,
          tool_names: z.array(nonEmptyString),
          export: exportGateSchema,
        })
        .strict())
      .optional(),
    member_fixtures: z
      .array(z
        .object({
          ref: fixtureRef,
          bundle_sha256: sha256Hex,
          archive_sha256: sha256Hex,
          export: exportGateSchema,
        })
        .strict())
      .optional(),
  })
  .strict();

const evalPromptsCatalogSchema = z
  .object({
    path: safeRelativePath,
    count: z.number().int().positive(),
  })
  .strict();

const specCatalogEntrySchema = z
  .object({
    path: safeRelativePath,
    id: z.string().regex(/^[a-z0-9]+(?:[._-][a-z0-9]+)*$/),
    version: fixtureVersion,
  })
  .strict();

const specsCatalogSchema = z
  .object({
    task_specs: z.array(specCatalogEntrySchema).optional(),
    verifier_specs: z.array(specCatalogEntrySchema).optional(),
    scaffold_specs: z.array(specCatalogEntrySchema).optional(),
  })
  .strict();

const fixtureCatalogEntrySchema = z
  .object({
    id: fixtureId,
    version: fixtureVersion,
    ref: fixtureRef,
    name: nonEmptyString,
    description: nonEmptyString,
    status: z.enum(["draft", "verified", "released", "deprecated"]),
    source_path: safeRelativePath,
    manifest_path: safeRelativePath,
    tools: z.array(toolSurfaceSchema).min(1),
    tags: z.array(z.string()).min(1),
    bundle: z
      .object({
        path: safeRelativePath,
        schema_version: z.literal("replay_bundle.v1"),
        sha256: sha256Hex,
      })
      .strict(),
    eval_prompts: evalPromptsCatalogSchema,
    specs: specsCatalogSchema.optional(),
    release: releaseCatalogSchema,
    trust: catalogTrustSchema.optional(),
  })
  .strict();

const fixtureSetSplitsCatalogSchema = z
  .object({
    path: safeRelativePath,
    counts: z
      .object({
        train: z.number().int().nonnegative(),
        dev: z.number().int().nonnegative(),
        test: z.number().int().nonnegative(),
      })
      .strict(),
    task_count: z.number().int().positive(),
  })
  .strict();

const fixtureSetCatalogEntrySchema = z
  .object({
    id: fixtureId,
    version: fixtureVersion,
    ref: fixtureRef,
    name: nonEmptyString,
    description: nonEmptyString,
    status: z.enum(["draft", "verified", "released", "deprecated"]),
    source_path: safeRelativePath,
    manifest_path: safeRelativePath,
    fixtures: z.array(fixtureRef).min(1),
    tags: z.array(z.string()).min(1),
    eval_prompts: evalPromptsCatalogSchema.optional(),
    specs: specsCatalogSchema.optional(),
    splits: fixtureSetSplitsCatalogSchema.optional(),
    release: releaseCatalogSchema,
    trust: catalogTrustSchema.optional(),
  })
  .strict();

const referenceRewardCatalogEntrySchema = z
  .object({
    id: nonEmptyString,
    status: z.literal("reference_only"),
    task_family: nonEmptyString,
    path: safeRelativePath,
    sha256: sha256Hex,
  })
  .strict();

export const fixtureCatalogSchema = z
  .object({
    schema_version: z.literal("datalox_fixture_catalog.v1"),
    repository: z
      .object({
        name: nonEmptyString,
        package: nonEmptyString,
      })
      .strict(),
    engine_contract: z
      .object({
        package: nonEmptyString,
        minimum_version: nonEmptyString,
        commands: z.record(z.string(), z.string()),
      })
      .strict(),
    fixtures: z.array(fixtureCatalogEntrySchema),
    fixture_sets: z.array(fixtureSetCatalogEntrySchema),
    reference_rewards: z.array(referenceRewardCatalogEntrySchema).optional(),
  })
  .strict();

export type FixtureCatalog = z.infer<typeof fixtureCatalogSchema>;
export type FixtureCatalogEntry = z.infer<typeof fixtureCatalogEntrySchema>;
export type FixtureSetCatalogEntry = z.infer<typeof fixtureSetCatalogEntrySchema>;

export class FixtureCatalogValidationError extends Error {
  readonly issues: z.ZodIssue[];

  constructor(issues: z.ZodIssue[]) {
    super(`Invalid fixture catalog: ${formatZodIssues(issues)}`);
    this.name = "FixtureCatalogValidationError";
    this.issues = issues;
  }
}

export function parseFixtureCatalog(input: unknown): FixtureCatalog {
  const parsed = fixtureCatalogSchema.safeParse(input);
  if (!parsed.success) {
    throw new FixtureCatalogValidationError(parsed.error.issues);
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
