# Public Source Pins

This directory holds public source artifacts downloaded for the next env-data
proof expansion. Keep task rows simple; use this file only for source pinning
and recapture planning.

## Molecule Biology

Current ready input:

- `lambda_nc001416`
- Local artifact: `handoff/env-data-proof-v0/source-artifacts/derived/NC_001416.1.parser-safe.gb`
- Public source: `https://www.ncbi.nlm.nih.gov/sviewer/viewer.cgi?id=NC_001416.1&db=nuccore&report=genbank&retmode=text`
- Status: already pinned and used by the 5 ready molecule-biology tasks.

Use this input first for planned molecule-biology expansion. It supports
feature annotation, restriction digest, PCR simulation, ORF translation, and
GenBank export/reopen tasks without new input data.

## FlowCyto

Downloaded source archive:

- `flowcyto/flowWorkspaceData_3.24.0.tar.gz`
- Public source: `https://bioconductor.org/packages/release/data/experiment/src/contrib/flowWorkspaceData_3.24.0.tar.gz`
- Package page: `https://bioconductor.org/packages/release/data/experiment/html/flowWorkspaceData.html`
- DOI: `10.18129/B9.bioc.flowWorkspaceData`
- License shown by Bioconductor: `GPL-2`
- SHA256: `1A935924E2A94E25DCB19E28E3AB52ED62773C33765BD18B04143411DA4D67CC`

Extracted FCS candidates:

- `flowcyto/flowWorkspaceData/inst/extdata/CytoTrol_CytoTrol_1.fcs`
- `flowcyto/flowWorkspaceData/inst/extdata/CytoTrol_CytoTrol_2.fcs`
- `flowcyto/flowWorkspaceData/inst/extdata/a2004_O1T2pb05i_A1_A01.fcs`
- `flowcyto/flowWorkspaceData/inst/extdata/a2004_O1T2pb05i_A2_A02.fcs`
- `flowcyto/flowWorkspaceData/inst/extdata/diva/124500.fcs`

Recommended first FlowCyto recapture target:

- Input id: `flowcyto_cytotrol_1`
- File: `flowcyto/flowWorkspaceData/inst/extdata/CytoTrol_CytoTrol_1.fcs`
- SHA256: `08AEEB17AE4AE399492FFBD77BC9090934BD977CC517C8C10D7D2DEB83E03FBE`
- Reason: FlowCyto MCP metadata shows FSC-A, FSC-H, FSC-W, SSC-A, Time, and
  marker channels including CD4 PcpCy55, CD38 APC, CD8 APCH7, CD3 V450,
  HLA-DR V500, CCR7 PE, and CD45RA PECy7.

This file should replace the repo-only `flowcyto_cfp_well_a4` fixture for
public recapture. It can support main-population gating, doublet exclusion,
marker-positive gating, and marker-pair tasks.

## Protein MCP

Downloaded public RCSB artifacts:

- Input id: `protein_1hbb_cif`
- File: `protein/1HBB.cif`
- Public source: `https://files.rcsb.org/download/1HBB.cif`
- SHA256: `5349621471F8538A187533AE959E8C706F0CA838D2A1D9E3B4632A50D189878F`

- Input id: `protein_1tii_pdb`
- File: `protein/1TII.pdb`
- Public source: `https://files.rcsb.org/download/1TII.pdb`
- SHA256: `D767BB001C384BA66B8EA80970398DF62DC1D89A23B45829A0E77A6AC894884A`

Use these for protein source-pin recapture before promoting protein rows from
`needs_source_pin` to `ready`.
