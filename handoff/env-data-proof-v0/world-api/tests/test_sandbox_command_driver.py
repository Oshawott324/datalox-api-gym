import json
import tempfile
import textwrap
import unittest
from pathlib import Path

from datalox_world.drivers.sandbox_command import SandboxCommandDriver
from datalox_world.types import ToolCall


class SandboxCommandDriverTest(unittest.TestCase):
    def test_command_driver_delegates_lifecycle_to_external_runtime(self):
        with tempfile.TemporaryDirectory(prefix="datalox-sandbox-driver-") as tmp:
            root = Path(tmp)
            reset_script = _script(root / "reset.py", """
                import json, sys
                task_id, run_dir = sys.argv[1], sys.argv[2]
                print(json.dumps({
                    "session_id": "sandbox-session",
                    "task_id": task_id,
                    "observation": {"prompt": "sandbox task", "run_dir": run_dir},
                    "tools": [{
                        "name": "sandbox.echo",
                        "description": "Echo a value through the sandbox runtime.",
                        "input_schema": {"type": "object", "properties": {"value": {"type": "string"}}}
                    }]
                }))
            """)
            step_script = _script(root / "step.py", """
                import json, sys
                session_id, tool_name, arguments_json = sys.argv[1], sys.argv[2], sys.argv[3]
                print(json.dumps({
                    "observation": {
                        "ok": True,
                        "session_id": session_id,
                        "tool_name": tool_name,
                        "arguments": json.loads(arguments_json)
                    },
                    "reward": 0,
                    "terminated": False,
                    "truncated": False,
                    "info": {"backend": "fake-sandbox"}
                }))
            """)
            finalize_script = _script(root / "finalize.py", """
                import json, sys
                session_id, answer_json = sys.argv[1], sys.argv[2]
                answer = json.loads(answer_json)
                print(json.dumps({
                    "passed": answer.get("ok") is True,
                    "reward": 1 if answer.get("ok") is True else 0,
                    "terminated": True,
                    "info": {"session_id": session_id}
                }))
            """)

            driver = SandboxCommandDriver({
                "reset_command": ["python3", str(reset_script), "{task_id}", "{run_dir}"],
                "step_command": ["python3", str(step_script), "{session_id}", "{tool_name}", "{arguments_json}"],
                "finalize_command": ["python3", str(finalize_script), "{session_id}", "{answer_json}"],
            })

            reset = driver.reset("sandbox-task", root / "run")
            self.assertEqual(reset.session_id, "sandbox-session")
            self.assertEqual(reset.tools[0]["name"], "sandbox.echo")

            step = driver.step(reset.session_id, ToolCall("sandbox.echo", {"value": "hello"}))
            self.assertFalse(step.terminated)
            self.assertEqual(step.observation["arguments"]["value"], "hello")

            final = driver.finalize(reset.session_id, {"ok": True})
            self.assertTrue(final.passed)
            self.assertEqual(final.reward, 1)


def _script(path: Path, source: str) -> Path:
    path.write_text(textwrap.dedent(source).strip() + "\n", encoding="utf-8")
    path.chmod(0o755)
    return path


if __name__ == "__main__":
    unittest.main()
