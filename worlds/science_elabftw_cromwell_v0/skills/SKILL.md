# Analysis-control qualification handoff

Use provider state as authority. Read the eLabFTW source before each submission and again before writeback. A Cromwell status 404 immediately after submit is transient evidence, not permission to resubmit. Resume a referenced in-flight UUID. Diagnose Failed from both logs and metadata. Abort a superseded Running workflow and observe Aborted. Inspect outputs and metadata only after Succeeded.

For `outputs_digest`, copy the top-level `body_sha256` from the `cromwell.get_workflow_outputs` MCP envelope. For `metadata_digest`, copy the top-level `body_sha256` from the `cromwell.get_workflow_metadata` MCP envelope. Each value digests the complete sibling `body`; do not recompute it with shell, code, or copied response text.

PATCH metadata is a JSON string. Call the result an analysis-control/qualification handoff. Do not claim the captured WDL performed biological or scientific inference.
