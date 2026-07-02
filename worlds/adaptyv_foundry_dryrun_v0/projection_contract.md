# Projection Contract

## Source System

Adaptyv Foundry API shape records and public Adaptyv/Proteinbase replay-style
campaign evidence selected through the source pack and
`public_replay_sources.json`.

## Projected Entities

- organization
- token scope
- target
- sequence
- experiment
- quote
- invoice marker
- experiment update
- result
- campaign decision
- logical clock

## Mutable State

All mutable state lives in the run-local SQLite database. Write actions in later
tasks must mutate only this database and append audit/event evidence. Live
network execution, real credentials, real quote confirmation, and real payment
or order effects are outside the world boundary.

## Hidden State

The sampler writes hidden replay and verifier data under `hidden/` and stores
expected-resolution events with `visible_to_agent = 0` in SQLite. Hidden state
includes measured replay results, result-arrival schedules, quote schedules,
oracle plans, known-bad plans, and verifier expectations.

## Agent-Visible State

Agent-visible setup is limited to `task.json`, generated `agent_task.json`, MCP
observations, source references, and files under `visible_artifacts/`.

## Outcome Source

`scientific_outcome_source` is `public_replay` for v0. These measured outcomes
are replay fixtures for verifier ground truth only and cite stable row IDs from
`public_replay_sources.json`. They are not predictions for novel sequences.

## Stochastic Source

`stochastic_source_status` is `assumption_for_calibration`. Schedules are
deterministically generated from scenario templates plus `environment_seed` and
are not provider behavior claims.

## Live Boundary

Any live execution attempt must remain blocked in dry-run state and should be
recorded as `LIVE_EXECUTION_FORBIDDEN` when concrete tools are implemented.
