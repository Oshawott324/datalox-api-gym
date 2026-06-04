# Molecule Primer Validation Task

Import the circular GenBank fixture, inspect sequence context, add one
verifier-specified primer through the local domain-style tool, then validate the
workspace.

Use local tools only. Do not patch workspace JSON directly.

Useful calls:

```bash
./datalox_tool open_sequence '{"path":"artifacts/circular.gb","molecule_id":"mol_circular"}'
./datalox_tool get_sequence_context '{"molecule_id":"mol_circular","include_sequence":true}'
./datalox_tool upsert_primer '{"expected_revision":0,"primer":{"id":"primer_seed_fwd","name":"seed forward primer","sequence":"ACGT","molecule_id":"mol_circular"}}'
./datalox_tool validate_workspace '{}'
```

Write `answer.json` and submit it:

```bash
./submit_answer answer.json
```
