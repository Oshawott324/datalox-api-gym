# Review Questions

Please answer these directly.

1. Can your agent harness plug into this world shape?

Expected answer:

```text
usable as-is / needs thin wrapper / incompatible
```

2. What environment API do you prefer?

Options to consider:

```text
local workspace commands
Python reset/step/finalize
HTTP service
MCP server
other internal runner shape
```

3. Is `exports/sft.messages.examples.jsonl` close enough to your SFT loader?

Please flag exact required changes, for example:

```text
assistant.content must be empty string instead of null
tool_calls field name differs
tool role payload needs a different envelope
function names need sanitization
messages need additional metadata
```

4. For eval or RL, is `trajectory.jsonl` enough?

If not, what is missing?

```text
tool schema snapshots
state snapshots
reward fields
split metadata
failure labels
model metadata
token/cost metadata
other
```

5. Would you train from successful trajectories like these after real model
rollout collection?

Expected answer:

```text
yes / only after conversion / no
```

6. What minimum dataset size is worth the first trainable run?

Current assumption:

```text
30 train / 10 dev / 10 test minimum for first signal
80 train / 20 dev / 20 test preferred if we want a more credible result
```

7. Which trainable open-weight base model and SFT runner would you use first?

Please include the reason if there is an obvious constraint.

