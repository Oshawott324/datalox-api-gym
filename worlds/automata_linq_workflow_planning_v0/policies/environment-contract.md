# Automata LINQ Environment Contract

This world is a dry-run API Gym environment. It must not call live Automata
LINQ APIs, publish or deploy workflows, start/pause/resume/stop/reset devices,
respond to hardware errors, restart hubs, mutate transport configuration,
rotate credentials, or dereference log-export URLs.

Agent-facing errors should be structured for repair. Workflow API errors keep
the `detail` shape, backend errors keep the `message` shape, and unavailable
plan results should tell the agent to inspect plan status until
`result_available` is true.

HTTP routes and MCP tools are thin adapters over the same service layer and
SQLite state. The verifier checks final workflow state, plan evidence, stale
plan repair, and boundary enforcement. Do not describe the dynamics as
high-fidelity Automata runtime behavior without approved captures or concrete
provider examples.
