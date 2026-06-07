import json
import tempfile
import unittest
from pathlib import Path

from datalox_world.drivers.runnable_world import RunnableWorldDriver
from datalox_world.exporters import export_sft_messages
from datalox_world.prompting import render_system_prompt
from datalox_world.types import ToolCall


ROOT = Path(__file__).resolve().parents[2]
WORLD_SPEC = ROOT / "world-api" / "world.spec.json"
RUNNABLE_WORLD = ROOT / "runnable-world"


class WorldApiSmokeTest(unittest.TestCase):
    def test_runnable_world_lifecycle_and_tool_prompt(self):
        with tempfile.TemporaryDirectory(prefix="datalox-world-api-") as tmp:
            driver = RunnableWorldDriver(WORLD_SPEC, RUNNABLE_WORLD)
            reset = driver.reset("fastq-qc-nanopore-fail-001", Path(tmp) / "fastq")

            self.assertEqual(reset.task_id, "fastq-qc-nanopore-fail-001")
            tool_names = [tool["name"] for tool in reset.tools]
            self.assertIn("workspace.list_files", tool_names)
            self.assertIn("open_sequence", tool_names)
            self.assertIn("workspace.list_files", reset.observation["task_tool_names"])
            self.assertNotIn("open_sequence", reset.observation["task_tool_names"])
            self.assertIn("prompt", reset.observation)
            self.assertIn("workspace_dir", reset.observation)

            system_prompt = render_system_prompt(reset.tools, reset.observation["task_tool_names"])
            self.assertIn("Task-relevant tools:", system_prompt)
            self.assertIn("workspace.list_files", system_prompt)
            self.assertIn("List files", system_prompt)
            self.assertNotIn("open_sequence", system_prompt)
            self.assertNotIn("Environment tool catalog:", system_prompt)
            self.assertNotIn("input_schema:", system_prompt)

            listed = driver.step(reset.session_id, ToolCall("workspace.list_files", {}))
            self.assertFalse(listed.terminated)
            self.assertEqual(listed.reward, 0)
            self.assertIn("artifacts/fastqc_data.txt", listed.observation["files"])

            report = driver.step(
                reset.session_id,
                ToolCall("fastqc.parse_report", {"path": "artifacts/fastqc_data.txt"}),
            )
            self.assertIn("Per base sequence quality", report.observation["failed_modules"])

            policy = driver.step(
                reset.session_id,
                ToolCall("qc_policy.evaluate", {"report_ref": "metric:fastqc.parsed_report"}),
            )
            self.assertEqual(policy.observation["next_action"], "trim_or_filter_reads")

            answer = _fastq_answer(include_file_evidence=False)
            final = driver.finalize(reset.session_id, answer)
            self.assertTrue(final.passed)
            self.assertEqual(final.reward, 1)
            self.assertTrue(final.terminated)

            after_done = driver.step(reset.session_id, ToolCall("workspace.list_files", {}))
            self.assertTrue(after_done.terminated)
            self.assertFalse(after_done.observation["ok"])
            self.assertEqual(after_done.observation["error"]["code"], "session_finalized")

            exported = driver.export(reset.session_id, "sft_messages", Path(tmp) / "sft.jsonl")
            self.assertEqual(exported.rows, 1)
            row = json.loads(Path(exported.path).read_text(encoding="utf-8").strip())
            self.assertEqual(row["schema_version"], "datalox_world_sft_messages.v0")
            self.assertEqual(row["provider_format"], "openai_chat")
            self.assertEqual(row["tool_choice"], "auto")
            self.assertIn("workspace.list_files", row["messages"][0]["content"])
            self.assertNotIn("open_sequence", row["messages"][0]["content"])
            self.assertIn("Task-relevant tools:", row["messages"][0]["content"])
            self.assertIn("Final answer", row["messages"][0]["content"])
            self.assertNotIn("Environment tool catalog:", row["messages"][0]["content"])
            self.assertNotIn("input_schema:", row["messages"][0]["content"])
            self.assertEqual(
                [tool["function"]["name"] for tool in row["tools"]],
                reset.observation["task_tool_names"],
            )
            self.assertEqual(row["tools"][0]["type"], "function")
            self.assertEqual(row["tools"][0]["function"]["parameters"]["type"], "object")
            self.assertNotIn("input_schema", row["tools"][0]["function"])
            self.assertTrue(any(message["role"] == "tool" for message in row["messages"]))

    def test_export_function_rejects_non_passing_runs(self):
        with tempfile.TemporaryDirectory(prefix="datalox-world-api-") as tmp:
            driver = RunnableWorldDriver(WORLD_SPEC, RUNNABLE_WORLD)
            reset = driver.reset("fastq-qc-nanopore-fail-001", Path(tmp) / "fastq")
            driver.step(reset.session_id, ToolCall("workspace.list_files", {}))
            final = driver.finalize(reset.session_id, {
                "task_id": "fastq-qc-nanopore-fail-001",
                "family": "scientific-data-qc",
                "diagnosis": {"class": "fastq_qc_decision", "summary": "Looks fine."},
                "evidence_ids": [],
                "next_action": {"type": "continue_downstream", "summary": "No action."},
                "missing_fields": [],
                "forbidden_actions_avoided": [],
            })
            self.assertFalse(final.passed)

            with self.assertRaises(ValueError):
                export_sft_messages(reset.run_dir, reset.tools, Path(tmp) / "bad.jsonl")


def _fastq_answer(include_file_evidence: bool) -> dict:
    evidence_ids = ["metric:fastqc.parsed_report", "metric:fastq.policy_result"]
    if include_file_evidence:
        evidence_ids.insert(0, "file:fastqc_data")
    return {
        "task_id": "fastq-qc-nanopore-fail-001",
        "family": "scientific-data-qc",
        "diagnosis": {
            "class": "fastq_qc_decision",
            "summary": "Nanopore read QC fails key FastQC modules.",
        },
        "evidence_ids": evidence_ids,
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
            "evidence_ids": evidence_ids,
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
    }


if __name__ == "__main__":
    unittest.main()
