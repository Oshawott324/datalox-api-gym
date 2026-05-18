# TODO

The canonical implementation plan is
[docs/agent-replay-option-a-implementation-plan.md](docs/agent-replay-option-a-implementation-plan.md).

Current project model:

```text
agent tool call -> tool_io_record.v1 -> replay_bundle.v1 -> deterministic replay -> optional derivatives
```

## Open Work

- [ ] Keep replay bundle verification and MCP proxy behavior covered as new host adapters are added.
- [ ] Add downstream examples only when they consume verified `replay_bundle.v1` artifacts.
- [ ] Keep trajectory rows under `.datalox/derivatives/trajectories/` and out of the install-facing capture path.

## Done Baseline

- [x] Rename the canonical definition doc to `docs/project-definition.md`.
- [x] Remove legacy note/skill/retrieval history docs from the active docs set.
- [x] Keep first-read docs and adoption surfaces replay-first.
- [x] Keep fresh adoption from creating removed wiki/note/event stores.
