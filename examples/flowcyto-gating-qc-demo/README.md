# FlowCyto Gating QC Visible Demo

This demo makes the Step 2 proof visible.

It uses a deterministic fake OpenAI-compatible endpoint as the cheap model
server, but every environment interaction goes through the real Datalox replay
runtime and the published FlowCyto fixture set.

The proof path is:

```text
install fixture set
-> run model through replayed FlowCyto tools
-> reject live/API drift through replay_miss
-> write run.json and transcript.jsonl
-> export one sft_frame.v1
-> render demo-report.html
```

Run it from the Agent Replay checkout:

```bash
cd /Users/yifanjin/datalox-agent-replay
npm run build
node examples/flowcyto-gating-qc-demo/run-demo.mjs \
  --catalog /Users/yifanjin/datalox-replay-fixtures/catalog.json
open examples/flowcyto-gating-qc-demo/output/demo-report.html
```

Generated artifacts:

```text
examples/flowcyto-gating-qc-demo/output/install.json
examples/flowcyto-gating-qc-demo/output/run-result.json
examples/flowcyto-gating-qc-demo/output/run/run.json
examples/flowcyto-gating-qc-demo/output/run/transcript.jsonl
examples/flowcyto-gating-qc-demo/output/export.json
examples/flowcyto-gating-qc-demo/output/flowcyto-qc.sft.jsonl
examples/flowcyto-gating-qc-demo/output/replay-miss-proof.json
examples/flowcyto-gating-qc-demo/output/terminal.log
examples/flowcyto-gating-qc-demo/output/demo-report.html
```

What this proves:

- `flowcyto-gating-qc-basic@2026-06.0` installs as a fixture set.
- `datalox run` can execute a prompt-driven OpenAI-compatible agent loop
  against replayed FlowCyto tools.
- Replay hits return recorded observations from the fixture world.
- Unrecorded tool arguments return a structured `replay_miss` with
  `liveFallback: false`.
- `datalox export sft` derives one `sft_frame.v1` from the run artifact.

This does not prove a live FlowCyto MCP server is running. That belongs in the
`datalox-flow-cyto-mcp` repo. This demo proves the installed snapshot world can
be consumed by Agent Replay and exported for training/eval users.
