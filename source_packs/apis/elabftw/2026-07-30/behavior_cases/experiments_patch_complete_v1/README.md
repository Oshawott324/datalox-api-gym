# eLabFTW Experiments PATCH Complete Behavior V1

This directory contains one immutable behavior program captured from a fresh,
disposable eLabFTW 5.6.10 service by the generic behavior harvester.

- `connector.json`: exact provider, engine, auth, boundary, source, and fixture
  pins.
- `recipe.json`: the required before/success/duplicate/native-failure/resulting
  program.
- `fixture_receipt.json`: sanitized evidence generated from running-container
  and image inspection.
- `capture.json`: full safe request/response evidence from the real service.
- `case_metadata.json`: immutable digests, coverage, and explicit claim bounds.

See `docs/elabftw-complete-behavior-case.md` for review details. The older
`2026-07-26/raw/reference_sequences/experiments_create_patch_get_v0.json`
remains historical selected evidence and is not the complete behavior case.

