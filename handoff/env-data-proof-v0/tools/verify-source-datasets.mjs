#!/usr/bin/env node
import Ajv from "ajv";
import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const envRoot = path.resolve(scriptDir, "..");
const schemaPath = path.join(envRoot, "schema", "source-dataset-manifest.schema.json");
const defaultManifestPath = path.join(envRoot, "source-datasets.manifest.json");
const manifestPath = process.argv.find((arg) => arg.startsWith("--manifest="))?.slice("--manifest=".length) ?? defaultManifestPath;
const strictHeaders = process.argv.includes("--strict-headers");

const TIMEOUT_MS = 20000;

async function main() {
  const manifest = await readJson(manifestPath);
  const schema = await readJson(schemaPath);
  validateManifest(schema, manifest);

  const checks = [];
  for (const source of manifest.sources) {
    if (source.primary_url.includes("eutils.ncbi.nlm.nih.gov")) {
      await sleep(400);
    }
    checks.push(await verifySource(source));
  }

  const failures = checks.filter((check) => !check.ok);
  process.stdout.write(`${JSON.stringify({
    ok: failures.length === 0,
    manifest: path.relative(process.cwd(), manifestPath),
    source_count: manifest.sources.length,
    checked_sources: checks.length,
    failures,
  }, null, 2)}\n`);

  if (failures.length > 0) process.exitCode = 1;
}

function validateManifest(schema, manifest) {
  const ajv = new Ajv({ allErrors: true, strict: false, validateFormats: false });
  const validate = ajv.compile(schema);
  if (!validate(manifest)) {
    throw new Error(`source dataset manifest failed schema validation: ${ajv.errorsText(validate.errors)}`);
  }

  const ids = new Set(manifest.sources.map((source) => source.source_id));
  if (ids.size !== manifest.sources.length) {
    throw new Error("source dataset manifest contains duplicate source_id values");
  }

  for (const sourceSet of manifest.source_sets) {
    for (const sourceId of sourceSet.source_ids) {
      if (!ids.has(sourceId)) {
        throw new Error(`source set ${sourceSet.set_id} references missing source_id ${sourceId}`);
      }
    }
  }
}

async function verifySource(source) {
  const method = source.verification.method === "head" ? "HEAD" : "GET";
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), TIMEOUT_MS);

  try {
    const response = await fetch(source.primary_url, {
      method,
      redirect: "follow",
      signal: controller.signal,
    });
    await response.body?.cancel();

    const contentType = response.headers.get("content-type") ?? "";
    const contentLength = response.headers.get("content-length");
    const etag = response.headers.get("etag");
    const expectedPrefix = source.verification.expected_content_type_prefix;

    const errors = [];
    if (response.status !== source.verification.expected_status) {
      errors.push(`expected HTTP ${source.verification.expected_status}, got ${response.status}`);
    }
    if (expectedPrefix && !contentType.startsWith(expectedPrefix)) {
      errors.push(`expected content-type prefix ${expectedPrefix}, got ${contentType || "missing"}`);
    }
    if (strictHeaders && source.pin.content_length && contentLength && source.pin.content_length !== contentLength) {
      errors.push(`expected content-length ${source.pin.content_length}, got ${contentLength}`);
    }
    if (strictHeaders && source.pin.etag && etag && source.pin.etag !== etag) {
      errors.push(`expected etag ${source.pin.etag}, got ${etag}`);
    }

    return {
      source_id: source.source_id,
      ok: errors.length === 0,
      status: response.status,
      method,
      final_url: response.url,
      content_type: contentType,
      ...(contentLength ? { content_length: contentLength } : {}),
      ...(etag ? { etag } : {}),
      ...(errors.length > 0 ? { errors } : {}),
    };
  } catch (error) {
    return {
      source_id: source.source_id,
      ok: false,
      method,
      errors: [error instanceof Error ? error.message : String(error)],
    };
  } finally {
    clearTimeout(timeout);
  }
}

async function readJson(filePath) {
  return JSON.parse(await fs.readFile(filePath, "utf8"));
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.stack : String(error)}\n`);
  process.exitCode = 1;
});
