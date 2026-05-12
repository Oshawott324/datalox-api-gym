# Claude Instructions

Claude Code can see Datalox through separate surfaces. Treat them separately:

- `datalox claude` / Claude shim wrapper: enforceable pre-run guidance injection when the active run is inside the Datalox wrapper.
- Claude Stop hook: post-turn sidecar automation. It can record, compile, and maintain after Claude responds, but it cannot force pre-turn `resolve_loop`.
- Claude native skills at `~/.claude/skills/<skill-name>`: legacy optional discovery surface when installed with `--include-legacy-guidance`, still model-chosen and sometimes restart-sensitive.
- Claude MCP tools: guidance-only unless Claude Code actually calls them.

Product boundary:

- Datalox MCP is the product-facing instrumentation and control layer for desktop agents.
- `datalox-trajectory-mcp` is the repo-local implementation package.
- B2B approved session data plus derived trajectory/evals are the primary product focus.
- Do not keep legacy note/skill promotion as a second product loop in this repo.
- Existing skills/notes are legacy or internal agent-guidance surfaces until migrated.
- `agent_turn.v1` events are the simple capture primitive.
- Approved anonymized session bundles are the source B2B data asset.
- Lean, outcome-labeled `debugging_trajectory.v1` rows are compact training/eval derivatives.

Use `datalox status --json` to inspect the current surface state. Only treat Claude as wrapper-enforced when `currentSession.activeWrapper` is `"claude"` and `currentSession.wrapperEnforced` is `true`.

On each loop:

1. if legacy full-pack MCP tools are available, call `resolve_loop` before internal Datalox maintenance work
2. read `docs/product-definition.md`, `docs/agent-turn-schema.md`, and `docs/trajectory-dataset-schema.md` when export/data fields are involved
3. record new product events under `.datalox/events/`; use `agent-wiki/events/` only for legacy traces
4. use `skills/` and linked notes only when this repo has explicit legacy guidance
5. route new product behavior through captured `agent_turn.v1` events first, assemble sessions, then derive trajectory rows when useful
6. leave `agent-wiki/` alone unless this repo already has legacy compatibility content

When changing session capture, trajectory export, export gates, redaction states, or dataset fields, read `docs/product-definition.md` first, `docs/agent-turn-schema.md` before changing turn shape, and `docs/trajectory-dataset-schema.md` before changing row shape. Unapproved raw traces are not sellable data.

Useful commands:

- `datalox capture-web --repo . --url <url> --artifact design-doc`
- `datalox capture-web --repo . --url <url> --artifact design-tokens`
- `datalox capture-pdf --repo . --path <pdf-path>`
