import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORLD_API = ROOT / "world-api"
WORLD_SPEC = WORLD_API / "world.spec.json"
MCP = WORLD_API / "datalox_world" / "adapters" / "mcp_stdio.py"


class McpStdioSmokeTest(unittest.TestCase):
    def test_mcp_lists_current_task_tools_and_calls_step(self):
        with tempfile.TemporaryDirectory(prefix="datalox-world-mcp-") as tmp:
            server = subprocess.Popen(
                [
                    "python3",
                    str(MCP),
                    "--world",
                    str(WORLD_SPEC),
                    "--task-id",
                    "fastq-qc-nanopore-fail-001",
                    "--run",
                    str(Path(tmp) / "mcp-run"),
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                init = _rpc(server, "initialize", {})
                self.assertEqual(init["result"]["serverInfo"]["name"], "datalox-world-api")

                listed = _rpc(server, "tools/list", {})
                names = [tool["name"] for tool in listed["result"]["tools"]]
                self.assertIn("workspace.list_files", names)
                self.assertIn("open_sequence", names)
                self.assertIn("datalox_submit_answer", names)

                tool = next(item for item in listed["result"]["tools"] if item["name"] == "workspace.list_files")
                self.assertIn("description", tool)
                self.assertIn("inputSchema", tool)

                called = _rpc(server, "tools/call", {
                    "name": "workspace.list_files",
                    "arguments": {},
                })
                structured = called["result"]["structuredContent"]
                self.assertIn("artifacts/fastqc_data.txt", structured["files"])

                _rpc(server, "tools/call", {
                    "name": "fastqc.parse_report",
                    "arguments": {"path": "artifacts/fastqc_data.txt"},
                })
                _rpc(server, "tools/call", {
                    "name": "qc_policy.evaluate",
                    "arguments": {"report_ref": "metric:fastqc.parsed_report"},
                })
                submitted = _rpc(server, "tools/call", {
                    "name": "datalox_submit_answer",
                    "arguments": {"answer": _fastq_answer()},
                })
                self.assertTrue(submitted["result"]["structuredContent"]["passed"])
                self.assertEqual(submitted["result"]["structuredContent"]["reward"], 1.0)
            finally:
                server.kill()
                server.communicate(timeout=5)


def _rpc(server, method, params):
    request_id = _rpc.next_id
    _rpc.next_id += 1
    server.stdin.write(json.dumps({
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": params,
    }) + "\n")
    server.stdin.flush()
    line = server.stdout.readline()
    assert line, server.stderr.read()
    return json.loads(line)


_rpc.next_id = 1


def _fastq_answer():
    return {
        "task_id": "fastq-qc-nanopore-fail-001",
        "family": "scientific-data-qc",
        "diagnosis": {
            "class": "fastq_qc_decision",
            "summary": "Nanopore read QC fails key FastQC modules.",
        },
        "evidence_ids": [
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
    }


if __name__ == "__main__":
    unittest.main()
