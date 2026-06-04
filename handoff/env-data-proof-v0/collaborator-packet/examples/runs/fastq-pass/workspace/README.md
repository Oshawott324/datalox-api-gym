# FASTQ QC Task

Inspect the sequencing QC workspace and produce a structured QC decision.

Use local tools only. Do not use live web access.

Useful calls:

```bash
./datalox_tool workspace.list_files '{}'
./datalox_tool artifact.read_text '{"path":"artifacts/fastqc_data.txt"}'
./datalox_tool fastqc.parse_report '{"path":"artifacts/fastqc_data.txt"}'
./datalox_tool qc_policy.evaluate '{"report_ref":"metric:fastqc.parsed_report"}'
```

Write `answer.json` and submit it:

```bash
./submit_answer answer.json
```
