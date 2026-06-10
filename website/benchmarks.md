# Benchmarks

Benchmarks will be derived from verified world runs.

The primary loop is:

```text
API world -> task scenario -> agent run -> verifier/replay evidence -> training/eval exports
```

Phase 0 does not define benchmark rows yet. Future exports should stay
downstream from verified run evidence.
