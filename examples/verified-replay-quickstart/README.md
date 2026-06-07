# Verified Replay Quickstart

This example is the shortest local proof for Datalox API Gym.

It runs a deterministic MCP fixture through the Datalox MCP VCR proxy, records
real tool observations, packs a sealed replay bundle, replays with upstream off,
shows a structured replay miss for an unseen request, and proves checksum
verification catches tampering.

Run from the repo root:

```bash
npm run demo:verified-replay
```

The command writes ignored demo output under:

```text
examples/verified-replay-quickstart/output/
```

Expected result:

```text
[record] Starting Datalox MCP VCR proxy in record mode.
[pack] Packing replay bundle verified-replay-demo.
[verify] Verifying sealed replay bundle.
[replay] Starting replay from bundle with upstream off.
[tamper] Tampering with a bundle copy and verifying failure.
[done] Verified replay quickstart passed.
```

The summary includes the bundle id, tool record count, MCP tool catalog count,
replay hit count, replay miss count, upstream calls during replay, tamper
detection status, elapsed time, and output path.

The important contract:

```text
recorded request -> recorded observation
unseen request -> replay_miss
tampered bundle -> verification failure
```
