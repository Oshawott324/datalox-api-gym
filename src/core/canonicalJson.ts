export class CanonicalJsonError extends Error {
  readonly path: string;

  constructor(path: string, message: string) {
    super(`${path}: ${message}`);
    this.name = "CanonicalJsonError";
    this.path = path;
  }
}

export function canonicalJson(value: unknown): string {
  return serializeCanonicalJson(value, "$", new Set<object>());
}

function serializeCanonicalJson(
  value: unknown,
  valuePath: string,
  seen: Set<object>,
): string {
  if (value === null) {
    return "null";
  }

  switch (typeof value) {
    case "boolean":
      return value ? "true" : "false";
    case "number":
      if (!Number.isFinite(value)) {
        throw new CanonicalJsonError(valuePath, "number must be finite.");
      }
      return JSON.stringify(value);
    case "string":
      return JSON.stringify(value);
    case "undefined":
      throw new CanonicalJsonError(valuePath, "undefined is not valid JSON.");
    case "bigint":
      throw new CanonicalJsonError(valuePath, "bigint is not valid JSON.");
    case "function":
      throw new CanonicalJsonError(valuePath, "function is not valid JSON.");
    case "symbol":
      throw new CanonicalJsonError(valuePath, "symbol is not valid JSON.");
    case "object":
      return serializeCanonicalJsonObject(value, valuePath, seen);
  }

  throw new CanonicalJsonError(valuePath, `unsupported JSON value type: ${typeof value}.`);
}

function serializeCanonicalJsonObject(
  value: object,
  valuePath: string,
  seen: Set<object>,
): string {
  if (seen.has(value)) {
    throw new CanonicalJsonError(valuePath, "circular references are not valid JSON.");
  }

  seen.add(value);
  try {
    if (Array.isArray(value)) {
      return serializeCanonicalJsonArray(value, valuePath, seen);
    }

    if (!isPlainJsonObject(value)) {
      throw new CanonicalJsonError(valuePath, "only plain JSON objects are allowed.");
    }

    const symbolKeys = Object.getOwnPropertySymbols(value);
    if (symbolKeys.length > 0) {
      throw new CanonicalJsonError(valuePath, "symbol keys are not valid JSON.");
    }

    const record = value as Record<string, unknown>;
    const parts = Object.keys(record)
      .sort()
      .map((key) => {
        const childPath = `${valuePath}.${key}`;
        return `${JSON.stringify(key)}:${serializeCanonicalJson(record[key], childPath, seen)}`;
      });
    return `{${parts.join(",")}}`;
  } finally {
    seen.delete(value);
  }
}

function serializeCanonicalJsonArray(
  value: unknown[],
  valuePath: string,
  seen: Set<object>,
): string {
  const parts: string[] = [];
  for (let index = 0; index < value.length; index += 1) {
    if (!Object.prototype.hasOwnProperty.call(value, index)) {
      throw new CanonicalJsonError(`${valuePath}[${index}]`, "sparse arrays are not valid JSON.");
    }
    parts.push(serializeCanonicalJson(value[index], `${valuePath}[${index}]`, seen));
  }
  return `[${parts.join(",")}]`;
}

function isPlainJsonObject(value: object): boolean {
  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
}
