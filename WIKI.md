# Datalox Replay Guidance

This branch uses `.datalox/` as the replay replay data store:

```text
agent tool call -> tool_io_record.v1 -> replay_bundle.v1 -> deterministic replay -> optional derivatives
```

- `.datalox/tool-io/records/`
- `.datalox/events/agent-turns/`
- `.datalox/replay-bundles/`
- `.datalox/approvals/`
- `.datalox/derivatives/trajectories/`

Use `DATALOX.md` and `AGENTS.md` for the current replay contract.
