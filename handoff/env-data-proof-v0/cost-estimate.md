# Env Data Proof v0 Cost Estimate

Updated: 2026-05-29

## Why This File Exists

For Hugging Face publication, include cost and provenance metadata early. The
first public artifact should explain what was collected, what was copied versus
linked, and what it cost to create the replay/SFT handoff. This is not part of
the task output schema; it is publication and planning metadata.

## Publication Cost Notes

- The primary v0 now uses five scientific-data fixture worlds. The workflow
  issue candidate CSV is reserve material only.
- The current selection stores public source URLs, pins, ETags, and planning
  metadata. It should publish derived parser/checker observations first, not
  raw source artifacts.
- Before uploading replay bundles or copied observations to Hugging Face, review
  each source license and platform terms. Public URL provenance is lower risk
  than republishing raw scientific files.
- Hugging Face dataset cards should include license, provenance, intended use,
  limitations, and collection process metadata.
- Small CSV/JSONL metadata and replay manifests should be tiny. Large logs or
  binary artifacts should be avoided in v0 unless needed for the verifier.

## Estimated Human Time

| Work Item | Unit Estimate | V0 Estimate |
|---|---:|---:|
| Source/pin/license review | 30-90 min/world | 4-8 hours for 5 scientific-data worlds |
| Fixture artifact generation | 1-3 hours/world | 8-15 hours for 5 worlds |
| Parser/checker tool implementation | 1-4 hours/tool family | 12-24 hours for FastQC, Qualimap, FCS, mmCIF, single-cell QC |
| Replay observation capture | 45-120 min/world | 6-10 hours for 5 worlds |
| Deterministic verifier design | 45-120 min/world | 6-10 hours for 5 worlds |
| Baseline run + failure report | 15-45 min/world | 2-4 hours for 5 worlds |
| Verified teacher trajectories | 45-120 min/world | 6-10 hours for 5 worlds |
| HF dataset card and publish review | one-time | 3-6 hours |

The 5-world scientific-data seed is for evidence/replay/verifier validation
only. A reliable lift experiment needs at least 30/10/10 tasks, and a credible
public demo should target 80/20/20.

| Scale Target | Human-Time Planning Range | Direct-Spend Planning Range |
|---|---:|---:|
| 5-world scientific-data seed | 45-85 hours | $0-$150 |
| 30/10/10 MVP lift test | 60-120 hours | $300-$500 |
| 80/20/20 credible demo | 150-300 hours | $600-$1,500 |

## Estimated Direct Spend

| Stage | Expected Direct Spend | Notes |
|---|---:|---|
| Source plan only | $0 | Uses public URLs, git pins, ETags, and local metadata. |
| Parser/checker and replay smoke | $0-$50 | Mostly local CPU work unless paid APIs/models are used. |
| Cheap baseline eval | $0-$100 | Depends on local model vs hosted API. Use a cheap model first. |
| Minimal SFT LoRA | $50-$500 | 1.5B-3B LoRA on a small train split; record actual GPU/provider/runtime. |
| Credible demo rerun | $600-$1,500 | Only after the v0 handoff shows a real signal. |

## HF Readiness Gate

Publish only after these are true:

- every included world has a public source URL or approved private provenance id
- copied source content has license/terms review
- replay bundles do not expose private tokens, credentials, or personal data
- the dataset card states collection cost, compute cost, and limitations
- the release includes locked seed split, verifier versions, and replay bundle ids
