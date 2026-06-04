#!/usr/bin/env python3
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


WORLD_ROOT = Path(__file__).resolve().parents[1]


class RunnableWorldSmokeTest(unittest.TestCase):
    def test_fastq_oracle_and_bad_answer(self):
        with tempfile.TemporaryDirectory(prefix="datalox-fastq-world-") as tmp:
            run_dir = Path(tmp) / "run"
            self._init_task("fastq-qc-nanopore-fail-001", run_dir)
            workspace = run_dir / "workspace"

            listed = self._tool(workspace, "workspace.list_files", {})
            self.assertIn("artifacts/fastqc_data.txt", listed["files"])

            text = self._tool(workspace, "artifact.read_text", {"path": "artifacts/fastqc_data.txt"})
            self.assertEqual(text["evidence_id"], "file:fastqc_data")

            report = self._tool(workspace, "fastqc.parse_report", {"path": "artifacts/fastqc_data.txt"})
            self.assertIn("Per base sequence quality", report["failed_modules"])

            policy = self._tool(workspace, "qc_policy.evaluate", {"report_ref": report["evidence_id"]})
            self.assertEqual(policy["next_action"], "trim_or_filter_reads")

            answer_path = workspace / "answer.json"
            answer_path.write_text(json.dumps({
                "task_id": "fastq-qc-nanopore-fail-001",
                "family": "scientific-data-qc",
                "diagnosis": {
                    "class": "fastq_qc_decision",
                    "summary": "Nanopore read QC fails key FastQC modules.",
                },
                "evidence_ids": [
                    "file:fastqc_data",
                    "metric:fastqc.parsed_report",
                    "metric:fastq.policy_result",
                ],
                "next_action": {
                    "type": "trim_or_filter_reads",
                    "summary": "Trim or filter reads before downstream use.",
                },
                "missing_fields": [],
                "forbidden_actions_avoided": [
                    "called_live_service",
                    "used_uncited_evidence",
                ],
                "family_output": {
                    "diagnosis": {
                        "class": "fastq_qc_decision",
                        "summary": "Nanopore read QC fails key FastQC modules.",
                        "severity": "fail",
                    },
                    "affected_artifacts": ["sample:sample1_S1_L001_R2_001.fastq.gz"],
                    "computed_checks": [
                        {
                            "name": "per_base_sequence_quality",
                            "status": "fail",
                            "observed": "module failed",
                            "evidence_id": "metric:fastqc.parsed_report",
                        },
                        {
                            "name": "adapter_content",
                            "status": "fail",
                            "observed": "module failed",
                            "evidence_id": "metric:fastqc.parsed_report",
                        },
                    ],
                    "evidence_ids": [
                        "file:fastqc_data",
                        "metric:fastqc.parsed_report",
                        "metric:fastq.policy_result",
                    ],
                    "next_action": {
                        "type": "trim_or_filter_reads",
                        "summary": "Trim or filter reads before downstream use.",
                    },
                    "missing_fields": [],
                    "forbidden_actions_avoided": [
                        "called_live_service",
                        "used_uncited_evidence",
                    ],
                },
            }), encoding="utf-8")
            result = self._submit(workspace, answer_path)
            self.assertTrue(result["passed"])
            self.assertEqual(result["reward"], 1)

            bad_path = workspace / "bad-answer.json"
            bad_path.write_text(json.dumps({
                "task_id": "fastq-qc-nanopore-fail-001",
                "family": "scientific-data-qc",
                "diagnosis": {"class": "fastq_qc_decision", "summary": "Looks fine."},
                "evidence_ids": [],
                "next_action": {"type": "continue_downstream", "summary": "No action."},
                "missing_fields": [],
                "forbidden_actions_avoided": [],
            }), encoding="utf-8")
            bad = self._submit(workspace, bad_path)
            self.assertFalse(bad["passed"])
            self.assertEqual(bad["reward"], 0)

            events = self._trajectory(run_dir)
            self.assertGreaterEqual(len([event for event in events if event["type"] == "tool_call"]), 3)
            self.assertEqual(events[-1]["type"], "submit_answer")

    def test_molecule_oracle_and_sft_export(self):
        with tempfile.TemporaryDirectory(prefix="datalox-molecule-world-") as tmp:
            run_dir = Path(tmp) / "run"
            self._init_task("molecule-primer-validation-001", run_dir)
            workspace = run_dir / "workspace"

            opened = self._tool(workspace, "open_sequence", {
                "path": "artifacts/circular.gb",
                "molecule_id": "mol_circular",
            })
            self.assertEqual(opened["revision"], 0)

            context = self._tool(workspace, "get_sequence_context", {
                "molecule_id": "mol_circular",
                "include_sequence": True,
            })
            self.assertEqual(context["molecule"]["topology"], "circular")

            primer = self._tool(workspace, "upsert_primer", {
                "expected_revision": 0,
                "primer": {
                    "id": "primer_seed_fwd",
                    "name": "seed forward primer",
                    "sequence": "ACGT",
                    "molecule_id": "mol_circular",
                },
            })
            self.assertEqual(primer["revision"], 1)

            validation = self._tool(workspace, "validate_workspace", {})
            self.assertTrue(validation["valid"])

            answer_path = workspace / "answer.json"
            answer_path.write_text(json.dumps({
                "task_id": "molecule-primer-validation-001",
                "family": "molecule-biology",
                "diagnosis": {
                    "class": "molecule_primer_decision",
                    "summary": "Primer was inserted through the domain tool.",
                },
                "evidence_ids": [
                    "tool_io:molecule-primer-validation-001/get_sequence_context/1",
                    "tool_io:molecule-primer-validation-001/upsert_primer/2",
                    "tool_io:molecule-primer-validation-001/validate_workspace/3",
                    "molecule:mol_circular",
                    "primer:primer_seed_fwd",
                ],
                "next_action": {
                    "type": "upsert_primer",
                    "summary": "Persist the primer through the domain tool.",
                },
                "missing_fields": [],
                "forbidden_actions_avoided": [
                    "patched_workspace_json_directly",
                    "inferred_sequence_from_prose",
                ],
                "family_output": {
                    "workspace_revision": 1,
                    "molecule_id": "mol_circular",
                    "operation": "primer_validation",
                    "tool_result_refs": [
                        "tool_io:molecule-primer-validation-001/get_sequence_context/1",
                        "tool_io:molecule-primer-validation-001/upsert_primer/2",
                        "tool_io:molecule-primer-validation-001/validate_workspace/3",
                        "molecule:mol_circular",
                        "primer:primer_seed_fwd",
                    ],
                    "primer_ids": ["primer_seed_fwd"],
                },
            }), encoding="utf-8")
            result = self._submit(workspace, answer_path)
            self.assertTrue(result["passed"])

            out_path = Path(tmp) / "sft.jsonl"
            completed = subprocess.run(
                [
                    "python3",
                    str(WORLD_ROOT / "bin" / "export_sft.py"),
                    "--run",
                    str(run_dir),
                    "--out",
                    str(out_path),
                ],
                cwd=WORLD_ROOT,
                text=True,
                capture_output=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            row = json.loads(out_path.read_text(encoding="utf-8").strip())
            self.assertEqual(row["task_id"], "molecule-primer-validation-001")
            self.assertEqual(row["messages"][0]["role"], "system")
            self.assertTrue(any(message["role"] == "tool" for message in row["messages"]))

    def _init_task(self, task_id, run_dir):
        completed = subprocess.run(
            [
                "python3",
                str(WORLD_ROOT / "bin" / "init_task.py"),
                "--task",
                task_id,
                "--run",
                str(run_dir),
            ],
            cwd=WORLD_ROOT,
            text=True,
            capture_output=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue((run_dir / "workspace" / "README.md").exists())
        self.assertTrue((run_dir / "workspace" / "datalox_tool").exists())
        self.assertTrue((run_dir / "workspace" / "submit_answer").exists())

    def _tool(self, workspace, tool_name, arguments):
        completed = subprocess.run(
            [str(workspace / "datalox_tool"), tool_name, json.dumps(arguments)],
            cwd=workspace,
            text=True,
            capture_output=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)

    def _submit(self, workspace, answer_path):
        completed = subprocess.run(
            [str(workspace / "submit_answer"), str(answer_path)],
            cwd=workspace,
            text=True,
            capture_output=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)

    def _trajectory(self, run_dir):
        lines = (run_dir / "trajectory.jsonl").read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines if line.strip()]


if __name__ == "__main__":
    unittest.main()
