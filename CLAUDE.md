# Claude Instructions

Claude Code can see Datalox through separate surfaces. Treat them separately:

- `datalox claude` / Claude shim wrapper: enforceable pre-run guidance injection when the active run is inside the Datalox wrapper.
- Claude Stop hook: post-turn sidecar automation. It can record, compile, and maintain after Claude responds, but it cannot force pre-turn `resolve_loop`.
- Claude native skills at `~/.claude/skills/<skill-name>`: useful discovery surface, still model-chosen and sometimes restart-sensitive.
- Claude MCP tools: guidance-only unless Claude Code actually calls them.

Product boundary:

- Datalox MCP is the product-facing instrumentation and control layer for desktop agents.
- `datalox-trajectory-mcp` is the repo-local implementation package.
- B2B trajectory data/evals are the primary product focus.
- Do not keep legacy note/skill promotion as a second product loop in this repo.
- Existing skills/notes are legacy or internal agent-guidance surfaces until migrated.
- Lean, outcome-labeled `debugging_trajectory.v1` rows are the B2B dataset/eval product.

Use `datalox status --json` to inspect the current surface state. Only treat Claude as wrapper-enforced when `currentSession.activeWrapper` is `"claude"` and `currentSession.wrapperEnforced` is `true`.

On each loop:

1. if legacy full-pack MCP tools are available, call `resolve_loop` before internal Datalox maintenance work
2. read `docs/product-definition.md` and `docs/trajectory-dataset-schema.md` when export/data fields are involved
3. record grounded events in `agent-wiki/events/` or call `record_turn_result` after meaningful outcomes
4. use `skills/` and linked notes only where current host guidance still requires them
5. route new product behavior through structured events and trajectory rows
6. refresh `agent-wiki/index.md`, `log.md`, `lint.md`, and `hot.md`

When changing trajectory export, export gates, redaction states, or dataset fields, read `docs/trajectory-dataset-schema.md` first. Raw traces are not sellable data.

Useful commands:

- `datalox capture-web --repo . --url <url> --artifact design-doc`
- `datalox capture-web --repo . --url <url> --artifact design-tokens`
- `datalox capture-pdf --repo . --path <pdf-path>`
