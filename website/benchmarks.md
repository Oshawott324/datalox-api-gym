# Benchmarks

Benchmarks are downstream from verified world sessions.

The primary loop is:

```text
world package
  -> task scenario
  -> agent rollout through tools
  -> verifier outcome
  -> run_export evidence
  -> rollout collector dataset package
```

API Gym should not define train/dev/test splits, quality labels, or dataset
manifests. Those belong to `datalox-rollout-collector`.

API Gym benchmark artifacts should contain enough upstream evidence for a
collector to package later:

- world id and world version
- scenario and seed
- task package
- tool trace
- verifier result
- run export
