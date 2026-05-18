# Integration Guide: Pack ↔ Runtime

Local end-to-end test for the cloud integration between `datalox-agent-replay` (agent loop) and `datalox-knowledge-runtime` (skill registry + retrieval).

## Prerequisites

```bash
# Build the pack (one-time after code changes)
cd ~/Downloads/datalox-agent-replay
npm install && npx tsc

# Enable runtime in pack config
# Edit .datalox/config.json → set "runtime.enabled": true
```

## Start Runtime

```bash
cd ~/Downloads/datalox-knowledage-runtime
npm run dev   # → http://localhost:3000
```

## Full Flow

### 1. Register a contributor

```bash
curl -s -X POST http://localhost:3000/v1/contributor/register \
  -H "content-type: application/json" \
  -d '{"email":"you@example.com","displayName":"Your Name"}'
```

Response includes a `contributor.key` (e.g. `dlx_sk_...`). Save it for step 2.

### 2. Publish a skill

```bash
curl -s -X POST http://localhost:3000/v1/skills/publish \
  -H "content-type: application/json" \
  -H "Authorization: Bearer <your-key>" \
  -d '{
    "name": "live-dead-gating",
    "displayName": "Live/Dead Gating",
    "description": "Resolve ambiguous live/dead boundaries using viability dye thresholds",
    "workflow": "flow_cytometry",
    "trigger": "When live/dead gate placement is ambiguous",
    "skillMd": "# Live/Dead Gating\n\n## Steps\n1. Plot viability dye vs FSC-A\n2. Gate at the valley between live and dead peaks\n3. Backgate onto FSC/SSC to validate",
    "tags": ["gating", "viability"],
    "docRefs": [{"type": "url", "ref": "https://example.com/viability-guide", "label": "Viability Guide"}]
  }'
```

### 3. Resolve from pack (verify skill match)

```bash
cd ~/Downloads/datalox-agent-replay
node dist/src/cli/main.js resolve --repo . \
  --task "review ambiguous live dead gate" --json
```

Look for `runtimeGuidance.skill` in the output — it should contain the published skill.

## Other Useful API Calls

```bash
# Search skills
curl -s -X POST http://localhost:3000/v1/skills/search \
  -H "content-type: application/json" \
  -d '{"query": "gating", "limit": 5}'

# Install a skill bundle
curl -s http://localhost:3000/v1/skills/live-dead-gating/install

# Get runtime guidance directly
curl -s -X POST http://localhost:3000/v1/runtime/guidance \
  -H "content-type: application/json" \
  -d '{"task": "review ambiguous live dead gate", "workflow": "flow_cytometry"}'

# Health check
curl -s http://localhost:3000/healthz
```

## Architecture

```
datalox-agent-replay (local)              datalox-knowledge-runtime (:3000)
─────────────────────             ────────────────────────────────
resolveLoop()                     POST /v1/runtime/guidance
  ├─ local skill detection          └─ ContextCompiler.compileGuidance()
  └─ RuntimeClient ──HTTP──────────→    → selects best skill + retrieves docs
      → merges into runtimeGuidance     → returns RuntimeGuidance

promoteGap()                      POST /v1/skills/publish
  ├─ local skill promotion          └─ SkillRegistryService.publishSkill()
  └─ RuntimeClient ──HTTP──────────→    → validates docRefs, stores skill
      → result includes runtimePublish
```

Both runtime calls are wrapped in try/catch — if the service is unreachable or `runtime.enabled: false`, pack operates in local-only mode.
