import path from "node:path";

export function isSafeRelativePath(input: string): boolean {
  if (input.length === 0 || path.isAbsolute(input) || input.includes("\\")) {
    return false;
  }
  const normalized = normalizeFixtureRelativePath(input);
  return normalized !== ".." && !normalized.startsWith("../");
}

export function normalizeFixtureRelativePath(input: string): string {
  return path.posix.normalize(input.replaceAll(path.sep, "/"));
}

export function resolveInside(basePath: string, relativePath: string): string {
  if (!isSafeRelativePath(relativePath)) {
    throw new Error(`Unsafe relative path: ${relativePath}`);
  }
  const resolved = path.resolve(basePath, relativePath);
  const base = path.resolve(basePath);
  const relative = path.relative(base, resolved);
  if (relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative))) {
    return resolved;
  }
  throw new Error(`Path escapes base directory: ${relativePath}`);
}
