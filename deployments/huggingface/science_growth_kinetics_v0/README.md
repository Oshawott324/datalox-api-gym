---
title: Datalox Science Growth Kinetics
emoji: "\U0001F9EA"
colorFrom: green
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
short_description: Remote MCP dry-run world for science agents.
---

# Datalox Science Growth Kinetics

This Docker Space exposes one allowlisted API Gym world,
`science_growth_kinetics_v0`, through the gated runtime's remote session API
and Streamable HTTP MCP transport.

This Space package contains deployment glue only. When this directory is
synced to Hugging Face, the resulting Space repository contains no world,
provider, verifier, or runtime implementation. Those inputs are loaded from
the pinned revisions during build or startup. Python dependencies are
exact-pinned in `requirements.lock`; the private runtime is installed at the
exact commit recorded below.

## Pinned inputs

| Component | Repository | Commit |
| --- | --- | --- |
| API Gym and world bundle | `Oshawott324/datalox-api-gym` | `ca47eb299ae1ea9f96848807c3d74395d486cce4` |
| Gated runtime | `Oshawott324/datalox-gated-runtime` | `ce5372623ddbab41dab169e4e0d0fc1c000a56c2` |

The service is dry-run only. It does not enable live provider routing or
hardware execution.

PyLabRobot 0.2.1 lazily downloads the official Opentrons 300 uL tip-rack
definition on first use. The Docker build invokes that public PyLabRobot loader
once and verifies the resulting cache file against SHA-256
`afcaf30f86c3112b40246677d9f4dbef20bef938e0f65b8835195f448e058fd8`.
Provider execution therefore does not make an undeclared network request
during a session.

## Service surface

`GET /` returns a compact JSON service manifest with the world ID, dry-run
boundary, route map, and pinned source commits. The same ASGI process owns both
that manifest and the remote runtime service; there is no second server or
proxy.

The container exposes:

- `GET /health`
- `POST /sessions`
- `POST /sessions/{session_id}/mcp` for Streamable HTTP MCP
- `POST /sessions/{session_id}/finalize`
- `GET /sessions/{session_id}/export`
- `DELETE /sessions/{session_id}`

Create a seeded session:

```bash
curl -sS \
  -H 'content-type: application/json' \
  -d '{"example":"science_growth_kinetics_v0","seed":0}' \
  http://localhost:7860/sessions
```

The response contains an opaque `session_id`, bearer `token`, task, and
session-specific `mcp_url`. Send `Authorization: Bearer <token>` to the MCP,
finalize, export, and delete endpoints. An MCP client must also send a `Host`
and, when it uses one, an `Origin` accepted by the configured allowlists.

Finalization closes the MCP session, runs the hidden verifier, and returns the
strict public run export. Session state, faults, scheduled events, and hidden
verifier inputs are not part of that export.

## Configuration

The image listens on `0.0.0.0:7860`. These runtime environment variables are
available:

| Variable | Default | Meaning |
| --- | --- | --- |
| `DATALOX_ALLOWED_HOSTS` | `localhost:*,127.0.0.1:*` | Comma-separated MCP `Host` allowlist. At least one value is required. |
| `DATALOX_ALLOWED_ORIGINS` | empty | Comma-separated MCP `Origin` allowlist. |
| `DATALOX_MAX_SESSIONS` | `4` | Maximum concurrent sessions. |
| `DATALOX_SESSION_TTL_SECONDS` | `1800` | Session lifetime in seconds. |
| `DATALOX_CLEANUP_INTERVAL_SECONDS` | `5` | Expired-session cleanup interval. |
| `DATALOX_RUNS_ROOT` | `/home/user/runs` | Ephemeral run directory inside the container. |

The ASGI wrapper automatically adds Hugging Face's built-in `SPACE_HOST` to the
host allowlist and `https://SPACE_HOST` to the origin allowlist. Explicit
values remain useful for custom domains or non-HF clients:

```text
DATALOX_ALLOWED_HOSTS=<space-subdomain>.hf.space
DATALOX_ALLOWED_ORIGINS=https://<space-subdomain>.hf.space
```

Add local entries as additional comma-separated values only when local clients
also need access.

## Runtime authentication

The image build uses only public inputs and requires no secret. API Gym is
public, while the gated runtime repository is private.

At container startup, the entrypoint installs the exact runtime commit through
one of two explicit modes:

1. `DATALOX_RUNTIME_SOURCE` points to a read-only local source archive whose
   `.datalox-source-revision` contains the pinned full commit; or
2. `GITHUB_TOKEN` provides read access to the private runtime repository.

For the private-repository mode, the entrypoint writes the token to a
mode-`0600` temporary `.netrc`, installs the exact Git commit without placing
the token in a URL or process argument, removes the credential directory, and
unsets `GITHUB_TOKEN` before starting the service.

For a Docker Space, add `GITHUB_TOKEN` as a runtime Space Secret. Do not add it
as a Space Variable or Docker build argument. Hugging Face documents that
Docker Space Variables are supplied to the image build as build arguments,
while runtime Secrets are available to the running container.

Build the credential-free image locally:

```bash
docker build -t datalox-science-growth-space:local .
```

## Local smoke test

With Docker running and a clean local checkout at the pinned runtime commit:

```bash
RUNTIME_SOURCE=/absolute/path/to/datalox-gated-runtime ./scripts/smoke.sh
```

The script verifies the checkout commit and cleanliness, exports that exact
commit to a temporary source directory inside this repository, mounts the
archive read-only, builds the image without credentials, and starts it on local
port `17860`. It then checks the root manifest and health, loads the seed-0
reference trajectory from the installed world bundle, executes all 22 calls
through the actual Streamable HTTP MCP client, finalizes the session, and
asserts:

- 22 public ledger events;
- all 11 named world checks pass;
- overall verification passes; and
- provider execution counts are OT-2 `9`, incubator `2`, and plate reader `1`.

The script removes both the container and temporary source archive.

To test an already-built image:

```bash
RUNTIME_SOURCE=/absolute/path/to/datalox-gated-runtime \
SKIP_BUILD=1 \
IMAGE=datalox-science-growth-space:local \
./scripts/smoke.sh
```

## Publication blocker

This wrapper is not yet a publicly reproducible Space. Anyone can reproduce
the credential-free base image, but only authorized users can start the
service because startup installs the private runtime. A public service would
also execute private runtime code in an internet-facing container, so the
Space should remain private until the runtime distribution decision is made.

Public deployment remains blocked until one of these exists:

1. the pinned gated runtime revision is public; or
2. an installable runtime artifact is published with distribution terms that
   permit its use in a public Space.

Once that is resolved, remove the startup credential path and install the
immutable public artifact in the Dockerfile instead.

Hugging Face references:

- [Docker Spaces](https://huggingface.co/docs/hub/spaces-sdks-docker)
- [Spaces configuration](https://huggingface.co/docs/hub/spaces-config-reference)
