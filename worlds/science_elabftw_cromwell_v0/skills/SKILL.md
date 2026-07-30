# Analysis-control qualification handoff

Use provider state as authority. Read the eLabFTW source before each submission and again before writeback. A Cromwell status 404 immediately after submit is transient evidence, not permission to resubmit. Resume a referenced in-flight UUID. Diagnose Failed from both logs and metadata. Abort a superseded Running workflow and observe Aborted. Inspect outputs and metadata only after Succeeded.

Compute required digests with code:

```python
import hashlib, json

def digest(value):
    body = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(body.encode()).hexdigest()
```

PATCH metadata is a JSON string. Call the result an analysis-control/qualification handoff. Do not claim the captured WDL performed biological or scientific inference.
