# One-Correction Demo

This is the fastest clean recording path for:

`agent makes mistake -> human corrects once -> next run uses the correction`

It uses the public CLI surface:

- `resolve`
- `patch`
- `resolve`
- `lint`

## Fastest Path

From the repo root:

```bash
npm run demo:one-correction
```

That command:

- creates a clean temp demo repo
- prints the exact commands for a manual recording
- runs the full flow once so you can verify the output first

If you want to drive the terminal manually during the recording:

```bash
npm run demo:one-correction -- --setup-only
```

If you want a self-playing terminal replay that is ready to screen record:

```bash
npm run demo:one-correction:replay
```

If you want a generated transcript artifact you can paste into a post or share with someone:

```bash
npm run demo:one-correction:artifact
```

## What To Show

1. First `resolve`
2. Point out that the agent only has generic onboarding guidance
3. Run `patch` with the human correction
4. Run `resolve` again
5. Point out that the new run now includes the specific onboarding rule
6. End with `lint` or `removed-wiki-store/log.md` to show the correction persisted

## Suggested Narration

Use this roughly as-is:

1. "Here the agent can detect the right workflow, but the guidance is still generic."
2. "Now I give one correction based on what went wrong in the repo."
3. "Datalox writes that correction back into repo-local knowledge and updates the matched skill."
4. "On the next run, the agent uses the new correction instead of repeating the same mistake."

## Example Flow

The demo script prints commands in this shape:

```bash
node /abs/path/to/datalox-agent-replay/bin/datalox.js resolve --repo "$DEMO_REPO" --task "stabilize repo onboarding for coding agents" --workflow agent_adoption
node /abs/path/to/datalox-agent-replay/bin/datalox.js patch --repo "$DEMO_REPO" --task "stabilize repo onboarding for coding agents" --workflow agent_adoption --summary "A first-run coding agent needs a visible and reversible onboarding path" --observation "repo has no visible install surface for the agent" --interpretation "hidden setup keeps causing repeated onboarding mistakes" --action "add a committed README setup step and a bootstrap command before the first autonomous run"
node /abs/path/to/datalox-agent-replay/bin/datalox.js resolve --repo "$DEMO_REPO" --task "stabilize repo onboarding for coding agents" --workflow agent_adoption
node /abs/path/to/datalox-agent-replay/bin/datalox.js lint --repo "$DEMO_REPO"
```

## Recording Tips

- Keep the terminal zoomed in enough that the before and after action lists are readable.
- Leave the temp repo path visible once so people can see this is repo-local state.
- Do not over-explain the internals. The whole point is that one correction changes the next run.
