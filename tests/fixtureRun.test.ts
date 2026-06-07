import { cp, mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { evalFixtureSetOpenAiCompatible } from "../src/core/run/openAiCompatibleFixtureEval.js";
import { sha256Hex } from "../src/core/hash.js";
import { recordMcpToolCatalog } from "../src/core/mcpToolCatalogStore.js";
import { packReplayBundle } from "../src/core/replayBundle.js";
import { recordToolIo } from "../src/core/toolIoStore.js";

const tempDirs: string[] = [];

afterEach(async () => {
  await Promise.all(tempDirs.splice(0).map((dir) => rm(dir, { recursive: true, force: true })));
});

async function makeTempDir(prefix: string): Promise<string> {
  const dir = await mkdtemp(path.join(tmpdir(), prefix));
  tempDirs.push(dir);
  return dir;
}

async function createRunnableFixtureRepo(): Promise<{
  catalogPath: string;
  cacheRoot: string;
  fixtureSetRef: string;
}> {
  const root = await makeTempDir("datalox-run-fixtures-");
  const cacheRoot = await makeTempDir("datalox-run-cache-");
  const sourceRepo = path.join(root, "source");
  const fixtureId = "search-policy-corpus-basic";
  const fixtureVersion = "2026-05.0";
  const fixtureRef = `${fixtureId}@${fixtureVersion}`;
  const fixtureDir = path.join(root, "fixtures", fixtureId);
  await mkdir(sourceRepo, { recursive: true });
  await mkdir(fixtureDir, { recursive: true });

  await recordToolIo({
    repoPath: sourceRepo,
    callId: "search-call-1",
    toolName: "search_query",
    arguments: {
      query: "invoice webhook",
    },
    observation: {
      status: "ok",
      content: {
        hits: [
          {
            title: "Webhook delay policy",
            snippet: "Escalate delayed invoice webhooks with the event id and customer id.",
          },
        ],
      },
    },
    export: {
      allowed: true,
      redaction: "none_needed",
    },
    now: new Date("2026-05-20T00:00:00.000Z"),
  });
  await recordMcpToolCatalog({
    repoPath: sourceRepo,
    upstream: {
      command: "policy-search-mcp",
      args: [],
    },
    listToolsResult: {
      tools: [
        {
          name: "search_query",
          description: "Search the replayed policy corpus.",
          inputSchema: {
            type: "object",
            properties: {
              query: { type: "string" },
            },
            required: ["query"],
            additionalProperties: false,
          },
        },
      ],
    },
    export: {
      allowed: true,
      redaction: "none_needed",
    },
    now: new Date("2026-05-20T00:30:00.000Z"),
  });
  const bundle = await packReplayBundle({
    repoPath: sourceRepo,
    sourceRepoPath: ".",
    bundleId: fixtureId,
    export: {
      allowed: true,
      redaction: "none_needed",
    },
    now: new Date("2026-05-20T01:00:00.000Z"),
  });
  const fixtureBundleDir = path.join(fixtureDir, "replay-bundle", fixtureId);
  await mkdir(path.dirname(fixtureBundleDir), { recursive: true });
  await cp(path.join(sourceRepo, bundle.bundlePath), fixtureBundleDir, { recursive: true });
  const bundleSha256 = sha256Hex(await readFile(path.join(fixtureBundleDir, "checksums.json")));

  await writeFile(path.join(fixtureDir, "manifest.json"), `${JSON.stringify({
    $schema: "../../schemas/fixture-manifest.schema.json",
    id: fixtureId,
    version: fixtureVersion,
    name: "Search Policy Corpus Basic",
    description: "A finite policy-search replay-backed world.",
    status: "verified",
    engine: {
      package: "datalox-api-gym",
      minimumVersion: "0.1.0",
    },
    tools: [
      {
        surface: "mcp",
        server: "search",
        operations: ["search.query"],
        adapter: {
          protocol: "mcp",
          toolCatalogSource: "replay-bundle",
        },
      },
    ],
    bundle: {
      path: `replay-bundle/${fixtureId}`,
      schemaVersion: "replay_bundle.v1",
      sha256: bundleSha256,
    },
    evalPrompts: {
      path: "eval-prompts.jsonl",
      count: 1,
    },
    provenance: {
      source: "curated-recording",
      recordedAt: "2026-05-20",
      reviewedBy: "datalox",
      redaction: "none_needed",
    },
    trust: {
      schemaVersion: "datalox_fixture_trust_input.v1",
      verifiedAt: "2026-05-22T00:00:00Z",
      verifiedBy: "datalox",
      reviewType: "synthetic-public-fixture",
      export: {
        allowed: true,
        redaction: "none_needed",
      },
    },
    release: {
      immutable: false,
      license: "UNRELEASED",
      tags: ["search"],
    },
  }, null, 2)}\n`);
  await writeFile(path.join(fixtureDir, "eval-prompts.jsonl"), "{}\n");

  const fixtureSetId = "support-triage-basic";
  const fixtureSetVersion = "2026-06.0";
  const fixtureSetRef = `${fixtureSetId}@${fixtureSetVersion}`;
  const fixtureSetDir = path.join(root, "fixture-sets", fixtureSetId);
  await mkdir(path.join(fixtureSetDir, "tasks"), { recursive: true });
  await mkdir(path.join(fixtureSetDir, "verifiers"), { recursive: true });
  await mkdir(path.join(fixtureSetDir, "scaffolds"), { recursive: true });
  await writeFile(path.join(fixtureSetDir, "tasks", "support-triage-01.json"), `${JSON.stringify({
    schema_version: "datalox_task_spec.v1",
    id: "support-triage-01",
    version: fixtureSetVersion,
    name: "Support triage 01",
    description: "Find policy evidence for delayed invoice webhooks.",
    goal: "Use replayed policy-search observations to answer the support task.",
    taskFamily: "support_triage",
    difficulty: "easy",
    expectedTools: ["search_query"],
    forbiddenBehavior: ["claim live search access"],
    sftEligible: true,
    preferenceEligible: false,
    fixtureRefs: [fixtureRef],
    allowedTools: ["search_query"],
    successCriteria: ["Cites replayed policy evidence."],
    constraints: ["Use only replayed tools."],
  }, null, 2)}\n`);
  await writeFile(path.join(fixtureSetDir, "verifiers", "support-triage-01-verifier.json"), `${JSON.stringify({
    schema_version: "datalox_verifier_spec.v1",
    id: "support-triage-01-verifier",
    version: fixtureSetVersion,
    name: "Support triage 01 verifier",
    description: "Metadata-only verifier.",
    verifier: {
      kind: "manual",
    },
    requiredEvidence: ["replay_bundle", "tool_io_records", "final_answer"],
    reward: {
      type: "rubric",
      version: "support_triage_reference_v1-rubric",
      maxScore: 1,
      referenceRewardId: "support_triage_reference_v1",
    },
  }, null, 2)}\n`);
  await writeFile(path.join(fixtureSetDir, "scaffolds", "support-agent.json"), `${JSON.stringify({
    schema_version: "datalox_scaffold_spec.v1",
    id: "support-agent",
    version: fixtureSetVersion,
    name: "Support agent",
    description: "Replay-only support scaffold.",
    harness: `datalox replay --fixture-set ${fixtureSetRef}`,
    promptContract: "Use only replayed observations.",
    modelVisibleTools: ["search_query"],
    contextPolicy: {
      maxTurns: 4,
      allowedFixtureRefs: [fixtureRef],
    },
  }, null, 2)}\n`);
  await writeFile(path.join(fixtureSetDir, "eval-prompts.jsonl"), `${JSON.stringify({
    id: "support-triage-basic.support-triage-01.v1",
    taskSpecId: "support-triage-01",
    title: "Support triage 01",
    objective: "Find replayed policy evidence.",
    prompt: "Find policy evidence for delayed invoice webhooks. Return issue, evidence, risk, and next action.",
    allowedFixtures: [fixtureRef],
    expectedOutcome: {
      mustMention: ["replayed evidence"],
      mustNotDo: ["claim live search access"],
    },
    replay: {
      expectedMisses: [],
      allowedMisses: [],
    },
  })}\n`);
  await writeFile(path.join(fixtureSetDir, "splits.json"), `${JSON.stringify({
    schema_version: "datalox_task_splits.v1",
    fixtureSetRef,
    splits: {
      train: ["support-triage-01"],
      dev: [],
      test: [],
    },
  }, null, 2)}\n`);
  await writeFile(path.join(fixtureSetDir, "manifest.json"), `${JSON.stringify({
    $schema: "../../schemas/fixture-set-manifest.schema.json",
    id: fixtureSetId,
    version: fixtureSetVersion,
    name: "Support Triage Basic",
    description: "A runnable support world set.",
    status: "verified",
    fixtures: [fixtureRef],
    toolCollisionPolicy: {
      mode: "fail",
    },
    evalPrompts: {
      path: "eval-prompts.jsonl",
      count: 1,
    },
    splits: {
      path: "splits.json",
    },
    specs: {
      taskSpecs: [{ path: "tasks/support-triage-01.json" }],
      verifierSpecs: [{ path: "verifiers/support-triage-01-verifier.json" }],
      scaffoldSpecs: [{ path: "scaffolds/support-agent.json" }],
    },
    trust: {
      schemaVersion: "datalox_fixture_trust_input.v1",
      verifiedAt: "2026-05-22T00:00:00Z",
      verifiedBy: "datalox",
      reviewType: "composed-public-fixture-set",
      export: {
        allowed: true,
        redaction: "none_needed",
      },
    },
    release: {
      immutable: false,
      license: "UNRELEASED",
      tags: ["support", "sft"],
    },
  }, null, 2)}\n`);

  const archiveSha256 = "1".repeat(64);
  const checksumSha256 = "2".repeat(64);
  await writeFile(path.join(root, "catalog.json"), `${JSON.stringify({
    schema_version: "datalox_fixture_catalog.v1",
    repository: {
      name: "datalox-api-gym-worlds",
      package: "@datalox/api-gym-worlds",
    },
    engine_contract: {
      package: "datalox-api-gym",
      minimum_version: "0.1.0",
      commands: {
        install_fixture_set: "datalox fixture-sets install <fixture-set-ref>",
        eval_fixture_set: "datalox eval --fixture-set <fixture-set-ref>",
      },
    },
    fixtures: [
      {
        id: fixtureId,
        version: fixtureVersion,
        ref: fixtureRef,
        name: "Search Policy Corpus Basic",
        description: "A finite policy-search replay-backed world.",
        status: "verified",
        source_path: `fixtures/${fixtureId}`,
        manifest_path: `fixtures/${fixtureId}/manifest.json`,
        tools: [
          {
            surface: "mcp",
            server: "search",
            operations: ["search.query"],
            adapter: {
              protocol: "mcp",
              toolCatalogSource: "replay-bundle",
            },
          },
        ],
        tags: ["search"],
        bundle: {
          path: `fixtures/${fixtureId}/replay-bundle/${fixtureId}`,
          schema_version: "replay_bundle.v1",
          sha256: bundleSha256,
        },
        eval_prompts: {
          path: `fixtures/${fixtureId}/eval-prompts.jsonl`,
          count: 1,
        },
        release: {
          immutable: false,
          license: "UNRELEASED",
          archive_path: `archives/fixtures/${fixtureId}-${fixtureVersion}.tgz`,
          archive_sha256: archiveSha256,
          checksum_path: `archives/fixtures/${fixtureId}-${fixtureVersion}.tgz.sha256`,
          checksum_sha256: checksumSha256,
        },
      },
    ],
    fixture_sets: [
      {
        id: fixtureSetId,
        version: fixtureSetVersion,
        ref: fixtureSetRef,
        name: "Support Triage Basic",
        description: "A runnable support world set.",
        status: "verified",
        source_path: `fixture-sets/${fixtureSetId}`,
        manifest_path: `fixture-sets/${fixtureSetId}/manifest.json`,
        fixtures: [fixtureRef],
        tags: ["support", "sft"],
        eval_prompts: {
          path: `fixture-sets/${fixtureSetId}/eval-prompts.jsonl`,
          count: 1,
        },
        specs: {
          task_specs: [
            {
              path: `fixture-sets/${fixtureSetId}/tasks/support-triage-01.json`,
              id: "support-triage-01",
              version: fixtureSetVersion,
            },
          ],
          verifier_specs: [
            {
              path: `fixture-sets/${fixtureSetId}/verifiers/support-triage-01-verifier.json`,
              id: "support-triage-01-verifier",
              version: fixtureSetVersion,
            },
          ],
          scaffold_specs: [
            {
              path: `fixture-sets/${fixtureSetId}/scaffolds/support-agent.json`,
              id: "support-agent",
              version: fixtureSetVersion,
            },
          ],
        },
        splits: {
          path: `fixture-sets/${fixtureSetId}/splits.json`,
          counts: {
            train: 1,
            dev: 0,
            test: 0,
          },
          task_count: 1,
        },
        release: {
          immutable: false,
          license: "UNRELEASED",
          archive_path: `archives/fixture-sets/${fixtureSetId}-${fixtureSetVersion}.tgz`,
          archive_sha256: archiveSha256,
          checksum_path: `archives/fixture-sets/${fixtureSetId}-${fixtureSetVersion}.tgz.sha256`,
          checksum_sha256: checksumSha256,
        },
      },
    ],
    reference_rewards: [
      {
        id: "support_triage_reference_v1",
        status: "reference_only",
        task_family: "support_triage",
        path: "reference-rewards/support_triage_reference_v1.json",
        sha256: "3".repeat(64),
      },
    ],
  }, null, 2)}\n`);

  return {
    catalogPath: path.join(root, "catalog.json"),
    cacheRoot,
    fixtureSetRef,
  };
}

describe("OpenAI-compatible world set runs", () => {
  it("runs a selected split task against replayed tools and writes fixture-run JSONL", async () => {
    const repo = await createRunnableFixtureRepo();
    const outputPath = path.join(await makeTempDir("datalox-run-output-"), "runs.jsonl");
    const requests: Array<Record<string, unknown>> = [];

    const result = await evalFixtureSetOpenAiCompatible({
      fixtureSetRef: repo.fixtureSetRef,
      catalogPath: repo.catalogPath,
      cacheRoot: repo.cacheRoot,
      outputPath,
      split: "train",
      maxTasks: 1,
      maxTurns: 3,
      model: "fake-cheap-model",
      baseUrl: "https://model.test/v1",
      apiKey: "test-key",
      now: new Date("2026-05-24T00:00:00.000Z"),
      chatCompletionClient: async (request) => {
        requests.push(request as unknown as Record<string, unknown>);
        if (requests.length === 1) {
          return {
            id: "chatcmpl-tool",
            choices: [
              {
                index: 0,
                finish_reason: "tool_calls",
                message: {
                  role: "assistant",
                  content: null,
                  tool_calls: [
                    {
                      id: "call_search",
                      type: "function",
                      function: {
                        name: "search_query",
                        arguments: JSON.stringify({ query: "invoice webhook" }),
                      },
                    },
                  ],
                },
              },
            ],
          };
        }
        return {
          id: "chatcmpl-final",
          choices: [
            {
              index: 0,
              finish_reason: "stop",
              message: {
                role: "assistant",
                content: "Used replayed evidence from the webhook delay policy.",
              },
            },
          ],
        };
      },
    });

    expect(result).toMatchObject({
      fixtureSetRef: repo.fixtureSetRef,
      outputPath,
      liveFallback: false,
      tasks: [
        {
          taskSpecId: "support-triage-01",
          status: "completed",
          replayMisses: [],
        },
      ],
    });
    expect(((requests[0].tools as Array<{ function: { name: string } }>)).map((tool) => tool.function.name))
      .toEqual(["search_query"]);
    expect(JSON.stringify(requests[0].messages)).toContain("Do not call live tools");
    expect(JSON.stringify(requests[1].messages)).toContain("Webhook delay policy");

    const rows = (await readFile(outputPath, "utf8")).trim().split("\n").map((line) => JSON.parse(line));
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      schema_version: "datalox_fixture_run.v1",
      fixture_set_ref: repo.fixtureSetRef,
      split: "train",
      task: {
        task_spec_id: "support-triage-01",
        task_family: "support_triage",
        difficulty: "easy",
      },
      replay: {
        live_fallback: false,
        misses: [],
      },
      sft: {
        use: true,
      },
      preference: {
        use: false,
      },
      final_answer: "Used replayed evidence from the webhook delay policy.",
    });
  });

  it("returns replay misses to the model without calling live tools", async () => {
    const repo = await createRunnableFixtureRepo();
    const outputPath = path.join(await makeTempDir("datalox-run-miss-output-"), "runs.jsonl");

    const result = await evalFixtureSetOpenAiCompatible({
      fixtureSetRef: repo.fixtureSetRef,
      catalogPath: repo.catalogPath,
      cacheRoot: repo.cacheRoot,
      outputPath,
      split: "train",
      maxTasks: 1,
      maxTurns: 3,
      model: "fake-cheap-model",
      baseUrl: "https://model.test/v1",
      apiKey: "test-key",
      chatCompletionClient: async (request) => {
        const messages = request.messages as Array<{ role: string }>;
        if (!messages.some((message) => message.role === "tool")) {
          return {
            id: "chatcmpl-miss",
            choices: [
              {
                index: 0,
                finish_reason: "tool_calls",
                message: {
                  role: "assistant",
                  content: null,
                  tool_calls: [
                    {
                      id: "call_search_miss",
                      type: "function",
                      function: {
                        name: "search_query",
                        arguments: JSON.stringify({ query: "unrecorded live status" }),
                      },
                    },
                  ],
                },
              },
            ],
          };
        }
        const toolMessage = messages.find((message): message is { role: "tool"; content: string } => (
          message.role === "tool"
        ));
        expect(JSON.parse(toolMessage?.content ?? "{}")).toMatchObject({
          error: {
            code: "replay_miss",
            liveFallback: false,
          },
        });
        return {
          id: "chatcmpl-final",
          choices: [
            {
              index: 0,
              finish_reason: "stop",
              message: {
                role: "assistant",
                content: "The requested live status is outside the replay-backed world.",
              },
            },
          ],
        };
      },
    });

    expect(result.tasks[0]).toMatchObject({
      status: "completed_with_replay_miss",
      replayMisses: [
        {
          toolName: "search_query",
          sequenceIndex: 0,
          liveFallback: false,
        },
      ],
    });
    const row = JSON.parse((await readFile(outputPath, "utf8")).trim());
    expect(row.replay.misses).toMatchObject([
      {
        tool_name: "search_query",
        sequence_index: 0,
        live_fallback: false,
      },
    ]);
  });
});
