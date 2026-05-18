export type CliArgs = Record<string, string | string[] | boolean> & { _: string[] };

export function parseCliArgs(argv: string[]): CliArgs {
  const parsed: CliArgs = { _: [] };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--") {
      parsed._.push(...argv.slice(index + 1));
      break;
    }
    if (!arg.startsWith("--")) {
      parsed._.push(arg);
      continue;
    }

    const key = arg.slice(2);
    const next = argv[index + 1];
    const hasValue = next !== undefined && !next.startsWith("--");
    const value = hasValue ? next : true;

    if (hasValue) {
      index += 1;
    }

    const existing = parsed[key];
    if (existing === undefined) {
      parsed[key] = value;
      continue;
    }

    if (Array.isArray(existing)) {
      existing.push(value as string);
      parsed[key] = existing;
      continue;
    }

    parsed[key] = [existing as string, value as string];
  }

  return parsed;
}

export function toStringArray(value: string | string[] | boolean | undefined): string[] {
  if (value === undefined || value === false) {
    return [];
  }
  if (value === true) {
    return [];
  }
  return Array.isArray(value) ? value : [value];
}
