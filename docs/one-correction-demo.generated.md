# One-Correction Demo Transcript

Generated: 2026-04-16T09:21:06.200Z

This transcript is generated from a real `resolve -> patch -> resolve -> lint` run.

## Commands

```bash
export DEMO_REPO=/tmp/datalox-one-correction-demo
node bin/datalox.js resolve --repo $DEMO_REPO --task "stabilize repo onboarding for coding agents" --workflow agent_adoption
node bin/datalox.js patch --repo $DEMO_REPO --task "stabilize repo onboarding for coding agents" --workflow agent_adoption --summary "A first-run coding agent needs a visible and reversible onboarding path" --observation "repo has no visible install surface for the agent" --interpretation "hidden setup keeps causing repeated onboarding mistakes" --action "add a committed README setup step and a bootstrap command before the first autonomous run"
node bin/datalox.js resolve --repo $DEMO_REPO --task "stabilize repo onboarding for coding agents" --workflow agent_adoption
node bin/datalox.js lint --repo $DEMO_REPO
```

## Before Correction

Top skill: `agent-adoption.stabilize-repo-onboarding`

What the agent would do:
- Start with the committed onboarding playbook before letting the agent make changes.

## Human Correction

Note written or updated: `removed-wiki-store/notes/agent-adoption-repo-has-no-visible-install-surface-for-the-agent.md`
Skill operation: `update_skill`
Skill path: `$DEMO_REPO/skills/stabilize-repo-onboarding/SKILL.md`

## Next Run

Top skill: `agent-adoption.stabilize-repo-onboarding`

What the agent does now:
- Start with the committed onboarding playbook before letting the agent make changes.
- add a committed README setup step and a bootstrap command before the first autonomous run

## Pack State

Lint OK: `true`
Lint issue count: `0`

Recent log lines:
- 2026-04-16T09:21:04.289Z | create_note | A first-run coding agent needs a visible and reversible onboarding path for agent_adoption | removed-wiki-store/notes/agent-adoption-repo-has-no-visible-install-surface-for-the-agent.md
- 2026-04-16T09:21:04.295Z | update_skill | agent-adoption.stabilize-repo-onboarding updated with 2 note(s) | skills/stabilize-repo-onboarding/SKILL.md
- 2026-04-16T09:21:06.170Z | lint_pack | pack lint completed with no blocking issues | removed-wiki-store/lint.md
