import { describe, expect, it } from "vitest";

import {
  parseScaffoldSpec,
  parseTaskSpec,
  parseVerifierSpec,
} from "../src/core/fixtures/fixtureSpecSchema.js";

describe("fixture task/verifier/scaffold spec schemas", () => {
  it("accepts metadata-only task specs", () => {
    expect(parseTaskSpec({
      schema_version: "datalox_task_spec.v1",
      id: "github-pr-review-risk",
      version: "2026-05.0",
      name: "GitHub PR review risk",
      description: "Find the actionable risk in a replayed pull request.",
      goal: "Identify whether the PR has a correctness risk.",
      fixtureRefs: ["github-pr-review-basic@2026-05.0"],
      allowedTools: ["github_pull_request_get"],
      successCriteria: ["Names the risky file and why it matters."],
    }).id).toBe("github-pr-review-risk");
  });

  it("accepts verifier specs without executing their commands", () => {
    expect(parseVerifierSpec({
      schema_version: "datalox_verifier_spec.v1",
      id: "github-pr-review-risk-verifier",
      version: "2026-05.0",
      name: "GitHub PR review verifier",
      description: "Metadata for a local verifier command.",
      verifier: {
        kind: "command",
        command: "node",
        args: ["verifiers/github-pr-review-risk.mjs"],
      },
      requiredEvidence: ["replay_bundle", "tool_io_records"],
      reward: {
        type: "binary",
        version: "risk-v1",
      },
    }).verifier.kind).toBe("command");
  });

  it("accepts scaffold specs", () => {
    expect(parseScaffoldSpec({
      schema_version: "datalox_scaffold_spec.v1",
      id: "codex-review-scaffold",
      version: "2026-05.0",
      name: "Codex review scaffold",
      description: "A prompt/tool contract for replayed PR review tasks.",
      harness: "codex",
      promptContract: "Use only replayed GitHub tools.",
      modelVisibleTools: ["github_pull_request_get"],
      contextPolicy: {
        maxTurns: 4,
        allowedFixtureRefs: ["github-pr-review-basic@2026-05.0"],
      },
    }).harness).toBe("codex");
  });

  it("rejects incomplete executable verifier metadata", () => {
    expect(() => parseVerifierSpec({
      schema_version: "datalox_verifier_spec.v1",
      id: "bad-verifier",
      version: "2026-05.0",
      name: "Bad verifier",
      description: "Missing command metadata.",
      verifier: {
        kind: "command",
      },
      requiredEvidence: ["replay_bundle"],
    })).toThrow(/command verifiers must declare command metadata/);
  });
});
