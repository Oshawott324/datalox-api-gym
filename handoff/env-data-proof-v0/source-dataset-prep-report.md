# Source Dataset Preparation Report

## Active Source Policy

Only high-value MCP-backed tasks remain active. Parser/report-only tasks and toy molecule primer tasks were removed.

## Source Status

- Molecule Biology uses NCBI `NC_001416.1` as raw provenance and a parser-safe derived GenBank file that removes only `<` and `>` coordinate fuzz markers. The molecule MCP capture passed on the derived file.
- FlowCyto uses the sibling FlowCyto MCP FCS fixture for v0 capture. Public-source recapture is still required before public benchmark claims.
- Protein MCP uses sibling repo structure fixtures for v0 capture. Public-source recapture is still required before public benchmark claims.

## Gate

This v0 packet is ready for collaborator loader/harness review. It is not ready for a public lift claim.
