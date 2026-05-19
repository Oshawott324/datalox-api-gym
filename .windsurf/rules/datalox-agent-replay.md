# Datalox Rules

Read `AGENTS.md` and `DATALOX.md`.

Use Datalox Agent Replay as an MCP-compatible VCR for agent tools.

Write replay evidence under `.datalox/tool-io/records/`,
`.datalox/events/agent-turns/`, and `.datalox/replay-bundles/`.

Do not create a parallel wiki, note, or event store. Trajectory rows are
optional derivatives only after replay evidence exists.
