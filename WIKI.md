# Datalox Product Guidance

This branch uses `.datalox/` as the replay product data store:

```text
agent run -> tool I/O records -> replay bundle -> approval/export -> optional derivatives
```

- `.datalox/tool-io/records/`
- `.datalox/events/agent-turns/`
- `.datalox/replay-bundles/`
- `.datalox/approvals/`
- `.datalox/derivatives/trajectories/`

Use `DATALOX.md` and `AGENTS.md` for the current product contract.
