# Agent Configuration

The agent-facing contract is intentionally small.

Product boundary:

- Datalox MCP is the product-facing instrumentation and control layer.
- `datalox-trajectory-mcp` is the repo-local implementation package.
- B2B trajectory data/evals are the primary product focus.
- Do not keep legacy note/skill promotion as a second product loop in this repo.
- Existing skills/notes are legacy or internal agent-guidance surfaces until migrated.
- Lean, outcome-labeled trajectory export creates the dataset/eval asset.

## Legacy/Internal Guidance Model

- `skill` = the primary reusable workflow entrypoint
- `note` = grounded supporting knowledge that a skill can point to

Current legacy guidance behavior may still be:

1. detect the relevant skill
2. read `skills/<name>/SKILL.md`
3. read the linked `metadata.datalox.note_paths`
4. act from the skill plus its linked notes

## Main Surfaces

```text
.datalox/
  manifest.json
  config.json
skills/
agent-wiki/
  notes/
  events/
  index.md
  log.md
  lint.md
  hot.md
```

## Read Order

1. `.datalox/manifest.json`
2. `.datalox/config.json`
3. `docs/product-definition.md`
4. `docs/trajectory-dataset-schema.md` when touching trajectory recording, export, or data sale
5. `agent-wiki/hot.md`
6. selected `skills/<name>/SKILL.md`
7. linked `metadata.datalox.note_paths`

## Write Rule

New product writes should go to:

- `agent-wiki/events/`
- trajectory JSONL export artifacts that follow `debugging_trajectory.v1`

Legacy skill/note writes may still happen for current host guidance, but new product work should not depend on them.

Legacy supporting folders may still be readable during migration, but they are no longer the primary surface.

## Source Kinds

Concrete source kinds only:

- `trace`
- `web`
- `pdf`

## Product Export Target

- `debugging_trajectory.v1`

Legacy `skill` and `note` outputs may still exist for current host guidance, but new product work should target trajectory rows. Trajectory dataset rows must follow [trajectory-dataset-schema.md](./trajectory-dataset-schema.md), not introduce another repo-local knowledge page type.

## Trajectory Export

The exported debugging trajectory row is:

```text
problem -> context -> trajectory -> final fix -> verification -> outcome
```

Before treating an event as exportable data, ensure the row has:

- explicit schema version
- task prompt or problem statement
- minimal context
- concise trajectory steps
- final fix summary
- verification status
- outcome label
- small export gate

## Capture

- `capture-web` writes repo-local notes plus optional design artifacts
- `capture-pdf` writes repo-local notes from PDFs

## Lint

Lint checks:

- missing linked notes
- malformed notes
- missing skill playbook sections
- orphan notes
- overlapping skills

## Machine Setup

The user's agent may perform one-time machine setup.

Preferred first-time setup from the repo the user wants Datalox to manage:

```bash
TARGET_REPO="$(pwd)"
git clone https://github.com/Complexity-LLC/datalox-pack.git datalox-trajectory-mcp
cd datalox-trajectory-mcp
bash bin/setup-multi-agent.sh claude
bash bin/adopt-host-repo.sh "$TARGET_REPO"
node bin/datalox.js status --repo "$TARGET_REPO" --json
```

`https://github.com/Complexity-LLC/datalox-pack.git` is the current public GitHub source repo. `datalox-trajectory-mcp` is the local checkout/package name. Do not use `https://github.com/Complexity-LLC/datalox-trajectory-mcp.git` until that GitHub repo exists.

The source clone owns `bin/adopt-host-repo.sh`. The adopted host repo owns host-local shims such as `bin/setup-multi-agent.sh`, `bin/install-default-host-integrations.sh`, and `bin/disable-default-host-integrations.sh`.

After setup, the user should keep using `codex` or `claude` normally from the target repo.

Claude native skills install at `~/.claude/skills/<skill-name>/SKILL.md`. Restart Claude Code only if it was already running before `~/.claude/skills` existed, or if the host does not pick up the new links live.

The Claude hook is sidecar post-run automation. `CLAUDE.md`, wrapper/shim paths, MCP tools, and repo-local `skills/` remain the fallback when native skills are not surfaced.

## Stop

To stop Datalox-managed host interception:

- `bash bin/disable-default-host-integrations.sh`
- `node bin/datalox.js disable all --json`

To keep the wrapper but stop autonomous post-run review:

- set `DATALOX_DEFAULT_POST_RUN_MODE=off`
- or pass `--post-run-mode off`
