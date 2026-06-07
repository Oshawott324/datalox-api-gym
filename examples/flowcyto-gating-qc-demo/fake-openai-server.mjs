import { createServer } from "node:http";

const TOOL_SEQUENCE = [
  {
    name: "open_fcs",
    arguments: {
      path: "fixture://flowcyto-gating-qc-basic/testdata/CFP_Well_A4.fcs",
      workspace_dir: "fixture://flowcyto-gating-qc-basic/workspace",
      sample_id: "sample_001",
      surface: "none",
    },
  },
  {
    name: "get_plot_context",
    arguments: {
      workspace_path: "fixture://flowcyto-gating-qc-basic/workspace/flowcyto.workspace.json",
      sample_id: "sample_001",
      parent_gate_id: "root",
      x: "FSC-A",
      y: "SSC-A",
      format: "bins",
      bin_width: 64,
      bin_height: 64,
    },
  },
  {
    name: "upsert_gate",
    arguments: {
      workspace_path: "fixture://flowcyto-gating-qc-basic/workspace/flowcyto.workspace.json",
      expected_revision: 0,
      gate: {
        id: "agent_main_population_gate",
        name: "Agent Main Population Gate",
        sample: "sample_001",
        parent: "root",
        type: "polygon",
        x: "FSC-A",
        y: "SSC-A",
        vertices: [
          [26000, 6000],
          [182000, 7000],
          [221000, 78000],
          [153000, 145000],
          [42000, 102000],
        ],
      },
    },
  },
  {
    name: "compute_gate_stats",
    arguments: {
      workspace_path: "fixture://flowcyto-gating-qc-basic/workspace/flowcyto.workspace.json",
      sample_id: "sample_001",
      gate_id: "agent_main_population_gate",
    },
  },
  {
    name: "validate_gate_qc",
    arguments: {
      workspace_path: "fixture://flowcyto-gating-qc-basic/workspace/flowcyto.workspace.json",
      sample_id: "sample_001",
      gate_id: "agent_main_population_gate",
      stats_ref: "flowcyto:gate-stats:sample_001:agent_main_population_gate:rev1",
      min_population_percent: 0,
      max_population_percent: 100,
    },
  },
  {
    name: "submit_report",
    arguments: {
      workspace_path: "fixture://flowcyto-gating-qc-basic/workspace/flowcyto.workspace.json",
      expected_revision: 1,
      report: {
        title: "Main population QC report",
        summary: "The replayed gate covers the main FSC/SSC population and passes the configured QC checks.",
        gate_id: "agent_main_population_gate",
        stats_ref: "flowcyto:gate-stats:sample_001:agent_main_population_gate:rev1",
        qc_ref: "flowcyto:gate-qc:sample_001:agent_main_population_gate:rev1",
        caveats: [
          "Statistics come from the replay-backed API world preview sample.",
          "This does not perform live wet-lab or live FCS reprocessing.",
        ],
      },
    },
  },
];

const FINAL_ANSWER = [
  "Completed the FlowCyto replayed fixture run with QC evidence.",
  "The report was agent-authored, cites the replayed stats and QC evidence refs,",
  "and includes caveats that this is a finite API world rather than live wet-lab execution.",
].join(" ");

export async function startFakeOpenAiServer(input = {}) {
  const host = input.host ?? "127.0.0.1";
  const port = input.port ?? 0;
  const requests = [];
  let completionIndex = 0;

  const server = createServer(async (request, response) => {
    if (request.method !== "POST" || request.url !== "/v1/chat/completions") {
      writeJson(response, 404, { error: { message: "Only /v1/chat/completions is implemented." } });
      return;
    }

    const body = await readRequestJson(request);
    requests.push(body);
    const nextTool = TOOL_SEQUENCE[completionIndex];
    completionIndex += 1;

    if (nextTool !== undefined) {
      writeJson(response, 200, {
        choices: [
          {
            finish_reason: "tool_calls",
            message: {
              content: null,
              tool_calls: [
                {
                  id: `call_flowcyto_${completionIndex}`,
                  type: "function",
                  function: {
                    name: nextTool.name,
                    arguments: JSON.stringify(nextTool.arguments),
                  },
                },
              ],
            },
          },
        ],
      });
      return;
    }

    writeJson(response, 200, {
      choices: [
        {
          finish_reason: "stop",
          message: {
            content: FINAL_ANSWER,
          },
        },
      ],
    });
  });

  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(port, host, () => resolve(undefined));
  });

  const address = server.address();
  if (!address || typeof address === "string") {
    throw new Error("Fake OpenAI-compatible server did not bind to a TCP port.");
  }

  return {
    baseUrl: `http://${host}:${address.port}/v1`,
    requests,
    close: () => new Promise((resolve, reject) => {
      server.close((error) => error ? reject(error) : resolve(undefined));
    }),
  };
}

async function readRequestJson(request) {
  const chunks = [];
  for await (const chunk of request) {
    chunks.push(chunk);
  }
  const text = Buffer.concat(chunks).toString("utf8");
  return text.length > 0 ? JSON.parse(text) : {};
}

function writeJson(response, statusCode, body) {
  response.writeHead(statusCode, { "content-type": "application/json" });
  response.end(`${JSON.stringify(body)}\n`);
}
