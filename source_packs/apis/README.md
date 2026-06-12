# API Source Packs

`source_packs/apis` stores API source substrate before it becomes an API Gym
world.

This directory is for raw and normalized provider evidence:

- raw OpenAPI files, docs captures, test-mode probe outputs, and observed error
  rows
- normalized operation catalogs derived from those sources
- grounded response cases that can gate original-shaped provider API calls
- candidate notes about which operations could support a future world

This directory is not for worlds, MCP tools, resettable sessions, run exports,
or fake provider implementations. A source pack can describe provider behavior,
but it must not duplicate a provider API under `worlds/` or create sample
provider directories merely to look realistic.

Validate a provider/version pack before selecting it into a world:

```bash
api-gym source-pack validate source_packs/apis/<provider>/<version>
```

## Boundary

The canonical pipeline is:

```text
source_packs/apis/<provider>/<version>
  -> normalized operation catalog
  -> world candidate design
  -> worlds/<world_id>
  -> MCP/session/runtime
  -> run_export
  -> datalox-rollout-collector
```

`source_packs/apis/<provider>/<version>` is the source substrate boundary. It
can hold provider facts and normalized operation records. It does not hold
mutable episode state, verifier state, task packages, MCP adapters, or session
manifests.

Once a source pack is selected for a world, the world references it through
`worlds/<world_id>/source_refs.json`. The world owns the resettable state,
action contract, dynamics backend, observations, verifier, and run evidence.
The source pack remains upstream evidence and should not be copied into a fake
provider API tree.

## Expected Shape

Use a provider/version folder only when real source material exists:

```text
source_packs/apis/<provider>/<version>/
  source_pack.json
  docs_index.jsonl
  operations.jsonl
  schemas.jsonl
  examples.jsonl
  response_cases.jsonl
  probes.jsonl
  observed_errors.jsonl
  world_candidates.jsonl
  raw/
```

Do not create placeholder providers such as `stripe`, `zendesk`, or
`unitelabs` without source files. Empty directories are not evidence.
List only files that exist in `source_pack.json.records`; partial packs are
valid when they cite real sources and validate cleanly.

## Agent Rules

- Treat this directory as source substrate, not runtime code.
- Ground every provider claim in a source document, explicit contract, safe
  test-mode probe, or recorded observation.
- Treat `response_cases.jsonl` as the response-gating surface: the agent may
  call an original-shaped API, but a dry-run gate returns a selected sampled
  response case instead of calling the live provider.
- Do not guess provider semantics from a world implementation.
- Do not add live provider execution unless a separate live-gate policy exists
  and the user explicitly approves it.
- Keep records append-only when possible; prefer JSONL rows that agents can
  inspect, filter, and transform with code.
- Use stable IDs so worlds can cite source records without copying them.
- Keep provider source packs separate from `run_export` evidence. Dataset
  manifests, split assignment, labels, and validation reports belong downstream
  in `datalox-rollout-collector`.

## Minimal `source_refs.json`

Worlds cite selected source packs instead of duplicating them:

```json
{
  "schema_version": "api_gym.world_source_refs.v0",
  "world": "example_world_v0",
  "source_packs": [
    {
      "source_pack_id": "api.example.2026-06-12",
      "path": "../../source_packs/apis/example/2026-06-12/source_pack.json",
      "records": [
        "operation:listWidgets",
        "schema:Widget",
        "observed_error:listWidgets:401"
      ],
      "role": "operation_grounding"
    }
  ]
}
```

`source_refs.json` is a citation surface. It should tell an agent which source
records justify the world contract. It should not expose hidden verifier state
or mutable session state.

See [schema.md](schema.md) for minimal record schemas.
