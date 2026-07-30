# Galaxy Connected History FASTA V1

This immutable case records one provider-executed control and data lifecycle
against a disposable, loopback-only Galaxy 26.1.rc1 reference fixture. The
fixture used Galaxy commit `3d62013917dfc9e285c2be923b7b5b2034469d6f`,
image ID
`sha256:8e5b825e2d064707caa9f564bd5280bef0a79b666ccfee116ae7c311657eec62`,
and OCI index
`sha256:100a37301e5f4fb3ac560be5cec7ec5629400673cef8511ea2a8c17b4c8b7399`.

The successful sequence created one history, submitted `input.fa` through
Galaxy's `upload1` tool, polled the dataset from `queued` through `running` to
terminal `ok`, read the FASTA dataset and its `upload1` provenance, and read
back the exact 44 input bytes. The input and readback SHA-256 is
`d044ffc156b7f0a06cd252ec80ab8f0c0ef40ee57bbe3b0d4139f70bd8cbd39c`.
The capture also retains the observed `/api/health` 404.

The exact five tools required by the selected StarAMR workflow each returned
HTTP 404. The workflow was therefore neither imported nor invoked, and this
case makes no StarAMR execution claim.

The fixture receipt records the `galaxy-reference-v1` disposable marker,
loopback port binding, automatic container removal, successful history purge,
container absence, and named-volume removal. Galaxy rejected disposable-user
deletion with HTTP 403; fixture destruction nevertheless removed the complete
fixture and its storage. Request secrets, response secrets, and cookies were
sanitized, and the recorded raw, Base64, and SHA-256 secret scan passed.

`case_metadata.json` pins the recipe and captured artifacts. The focused
offline test additionally pins
`scripts/providers/galaxy/capture_connected_history_fasta.py` at
`sha256:e970593dca4813b3354ff750861b94948d55f744ccf774640f8ea0975cd3f024`
and verifies its fail-closed fixture inspection without running Docker:

```bash
python -m pytest -q tests/integration/test_galaxy_connected_history_fasta_case.py
```

This case grounds only the exact executed Galaxy control and data lifecycle
described above. It does not ground arbitrary Galaxy operations, arbitrary
Galaxy workflows, StarAMR import or execution, production equivalence, or
reset equivalence.
