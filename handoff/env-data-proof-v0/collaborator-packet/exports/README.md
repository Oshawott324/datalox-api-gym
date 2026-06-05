# Exports

## `sft.messages.examples.jsonl`

Two passing example rows exported from the runnable-world trajectories through
the World API exporter.

The system message includes the environment tool catalog plus the
task-relevant tool subset and input schemas.

Shape:

```json
{
  "schema_version": "datalox_world_sft_messages.v0",
  "task_id": "...",
  "family": "...",
  "source_run": "...",
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."},
    {
      "role": "assistant",
      "content": null,
      "tool_calls": [...]
    },
    {
      "role": "tool",
      "tool_call_id": "...",
      "name": "...",
      "content": "..."
    },
    {"role": "assistant", "content": "...final answer json..."}
  ]
}
```

This is intended for SFT loader compatibility review, not as a final training
dataset.
