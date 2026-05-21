const fixtureIdPattern = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const fixtureVersionPattern = /^[0-9]{4}-[0-9]{2}\.[0-9]+$/;
const fixtureRefPattern = /^([a-z0-9]+(?:-[a-z0-9]+)*)@([0-9]{4}-[0-9]{2}\.[0-9]+)$/;

export interface FixtureRef {
  id: string;
  version: string;
}

export class FixtureRefError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "FixtureRefError";
  }
}

export function parseFixtureRef(input: string): FixtureRef {
  const match = fixtureRefPattern.exec(input);
  if (!match) {
    throw new FixtureRefError(`Invalid fixture ref ${JSON.stringify(input)}. Expected <fixture-id>@<version>, for example github-pr-review-basic@2026-05.0.`);
  }
  return {
    id: match[1],
    version: match[2],
  };
}

export function formatFixtureRef(ref: FixtureRef): string {
  assertFixtureId(ref.id);
  assertFixtureVersion(ref.version);
  return `${ref.id}@${ref.version}`;
}

export function assertFixtureId(input: string): void {
  if (!fixtureIdPattern.test(input)) {
    throw new FixtureRefError(`Invalid fixture id ${JSON.stringify(input)}. Expected lowercase kebab-case.`);
  }
}

export function assertFixtureVersion(input: string): void {
  if (!fixtureVersionPattern.test(input)) {
    throw new FixtureRefError(`Invalid fixture version ${JSON.stringify(input)}. Expected YYYY-MM.N.`);
  }
}

export function fixtureRefEquals(left: FixtureRef, right: FixtureRef): boolean {
  return left.id === right.id && left.version === right.version;
}
