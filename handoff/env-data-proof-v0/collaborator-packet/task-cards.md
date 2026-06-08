# MCP Seed v0 Task Cards

These are the active tasks. Removed parser/report-only tasks are not part of this handoff.

## FlowCyto gate edit

- Task id: `flowcyto-existing-gate-edit-revision`
- Family: `flowcyto`
- Split: `train`
- Tool path: `open_fcs -> get_plot_context -> upsert_gate -> upsert_gate -> compute_gate_stats -> validate_gate_qc -> submit_report`
- Source status: Repo FlowCyto FCS fixture; public flowCore recapture still pending

## FlowCyto gating QC report

- Task id: `flowcyto-gating-qc-success`
- Family: `flowcyto`
- Split: `train`
- Tool path: `open_fcs -> get_plot_context -> upsert_gate -> compute_gate_stats -> validate_gate_qc -> submit_report`
- Source status: Repo FlowCyto FCS fixture; public flowCore recapture still pending

## FlowCyto stale revision recovery

- Task id: `flowcyto-gating-qc-stale-revision-failure`
- Family: `flowcyto`
- Split: `dev`
- Tool path: `open_fcs -> get_plot_context -> upsert_gate -> compute_gate_stats -> validate_gate_qc -> submit_report -> submit_report`
- Source status: Repo FlowCyto FCS fixture; recovery failure is real tool behavior

## FlowCyto report validation recovery

- Task id: `flowcyto-gating-qc-report-validation-failure`
- Family: `flowcyto`
- Split: `test`
- Tool path: `open_fcs -> get_plot_context -> upsert_gate -> compute_gate_stats -> validate_gate_qc -> submit_report -> submit_report`
- Source status: Repo FlowCyto FCS fixture; validation failure is real tool behavior

## Lambda GenBank feature annotation

- Task id: `molecule-genbank-feature-annotation-001`
- Family: `molecule-biology`
- Split: `train`
- Tool path: `open_sequence -> get_sequence_context -> upsert_feature -> validate_workspace`
- Source status: NCBI NC_001416.1 raw source plus parser-safe derived GenBank artifact

## Lambda restriction digest

- Task id: `molecule-restriction-digest-001`
- Family: `molecule-biology`
- Split: `train`
- Tool path: `open_sequence -> get_sequence_context -> find_restriction_sites -> simulate_digest`
- Source status: NCBI NC_001416.1 raw source plus parser-safe derived GenBank artifact

## Lambda PCR simulation

- Task id: `molecule-pcr-simulation-001`
- Family: `molecule-biology`
- Split: `train`
- Tool path: `open_sequence -> get_sequence_context -> upsert_primer -> upsert_primer -> simulate_pcr -> validate_workspace`
- Source status: NCBI NC_001416.1 raw source plus parser-safe derived GenBank artifact

## Lambda ORF translation annotation

- Task id: `molecule-orf-translation-annotation`
- Family: `molecule-biology`
- Split: `train`
- Tool path: `open_sequence -> get_sequence_context -> find_orfs -> translate_region -> upsert_feature -> validate_workspace`
- Source status: NCBI NC_001416.1 raw source plus parser-safe derived GenBank artifact

## Lambda edit then GenBank export

- Task id: `molecule-export-genbank-after-edit`
- Family: `molecule-biology`
- Split: `dev`
- Tool path: `open_sequence -> get_sequence_context -> upsert_feature -> validate_workspace -> export_genbank -> validate_workspace`
- Source status: NCBI NC_001416.1 raw source plus parser-safe derived GenBank artifact

## Protein ligand binding-site annotation

- Task id: `protein-binding-site-annotation`
- Family: `protein-mcp`
- Split: `train`
- Tool path: `open_structure -> list_ligands -> annotate_binding_site -> get_scene_annotations -> validate_workspace`
- Source status: Protein MCP hemoglobin CIF fixture; public source pin pending

## Protein view revision-safe style update

- Task id: `protein-view-revision-safe-style`
- Family: `protein-mcp`
- Split: `train`
- Tool path: `open_structure -> open_protein_viewer -> get_structure_context -> update_protein_view -> validate_workspace`
- Source status: Protein MCP 1tii PDB fixture; public source pin pending

## Protein ligand scene repair

- Task id: `protein-ligand-contact-scene-repair`
- Family: `protein-mcp`
- Split: `test`
- Tool path: `open_structure -> list_ligands -> get_scene_annotations -> annotate_binding_site -> get_scene_annotations -> validate_workspace`
- Source status: Protein MCP hemoglobin CIF fixture; public source pin pending

