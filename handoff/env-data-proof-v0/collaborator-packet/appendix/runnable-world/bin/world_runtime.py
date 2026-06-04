#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


WORLD_ROOT = Path(__file__).resolve().parents[1]
TASKS_ROOT = WORLD_ROOT / "tasks"


class WorldError(Exception):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise WorldError(f"Expected JSON object: {path}")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")


def append_jsonl(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(data, sort_keys=True, separators=(",", ":")))
        handle.write("\n")


def load_run(run_dir: Path) -> dict[str, Any]:
    return read_json(run_dir / "run.json")


def load_task(task_id: str) -> tuple[Path, dict[str, Any]]:
    task_dir = TASKS_ROOT / task_id
    task_path = task_dir / "task.json"
    if not task_path.exists():
        raise WorldError(f"Unknown task: {task_id}")
    return task_dir, read_json(task_path)


def create_run(task_id: str, run_dir: Path) -> dict[str, Any]:
    task_dir, task = load_task(task_id)
    workspace = run_dir / "workspace"
    if run_dir.exists():
        shutil.rmtree(run_dir)
    workspace.mkdir(parents=True)
    shutil.copytree(task_dir / "artifacts", workspace / "artifacts")
    shutil.copy(task_dir / "README.md", workspace / "README.md")
    shutil.copy(task_dir / "task.json", workspace / "task.json")
    write_json(workspace / "state.json", {"schema_version": "datalox_world_workspace_state.v0", "task_id": task_id})
    install_workspace_wrappers(run_dir, workspace)
    run = {
        "schema_version": "datalox_world_run.v0",
        "run_id": run_dir.name,
        "task_id": task_id,
        "family": task["family"],
        "created_at": utc_now(),
        "world_id": read_json(WORLD_ROOT / "world.json")["world_id"],
        "run_dir": str(run_dir),
        "workspace_dir": str(workspace),
        "trajectory_path": str(run_dir / "trajectory.jsonl"),
        "verifier_result_path": str(run_dir / "verifier_result.json"),
    }
    write_json(run_dir / "run.json", run)
    append_jsonl(run_dir / "trajectory.jsonl", {
        "type": "task_initialized",
        "created_at": utc_now(),
        "task_id": task_id,
        "workspace_dir": str(workspace),
    })
    return run


def install_workspace_wrappers(run_dir: Path, workspace: Path) -> None:
    wrappers = {
        "datalox_tool": "datalox_tool.py",
        "submit_answer": "submit_answer.py",
    }
    for wrapper_name, script_name in wrappers.items():
        wrapper_path = workspace / wrapper_name
        script_path = WORLD_ROOT / "bin" / script_name
        wrapper_path.write_text(
            "\n".join([
                "#!/usr/bin/env python3",
                "import subprocess",
                "import sys",
                f"SCRIPT = {str(script_path)!r}",
                f"RUN_DIR = {str(run_dir)!r}",
                "raise SystemExit(subprocess.call(['python3', SCRIPT, '--run', RUN_DIR, *sys.argv[1:]]))",
                "",
            ]),
            encoding="utf-8",
        )
        wrapper_path.chmod(0o755)


def call_tool(run_dir: Path, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    run = load_run(run_dir)
    task_id = run["task_id"]
    _, task = load_task(task_id)
    if tool_name not in task["allowed_tools"]:
        observation = {
            "ok": False,
            "error": {
                "code": "tool_not_allowed",
                "message": f"Tool is not allowed for task {task_id}: {tool_name}",
            },
        }
    elif task_id == "fastq-qc-nanopore-fail-001":
        observation = call_fastq_tool(run_dir, tool_name, arguments)
    elif task_id == "molecule-primer-validation-001":
        observation = call_molecule_tool(run_dir, tool_name, arguments)
    else:
        raise WorldError(f"No local tool runtime for task: {task_id}")

    event = {
        "type": "tool_call",
        "created_at": utc_now(),
        "task_id": task_id,
        "tool_name": tool_name,
        "arguments": arguments,
        "observation": observation,
        "ok": bool(observation.get("ok", True)),
    }
    append_jsonl(run_dir / "trajectory.jsonl", event)
    return observation


def call_fastq_tool(run_dir: Path, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    workspace = Path(load_run(run_dir)["workspace_dir"])
    if tool_name == "workspace.list_files":
        return {
            "ok": True,
            "files": sorted(
                str(path.relative_to(workspace))
                for path in (workspace / "artifacts").rglob("*")
                if path.is_file()
            ),
        }
    if tool_name == "provenance.inspect":
        return {
            "ok": True,
            "primary_source_id": "source:multiqc-fastqc-nan-reads",
            "primary_url": "https://raw.githubusercontent.com/MultiQC/test-data/main/data/modules/fastqc/nan_reads/fastqc_data.txt",
            "publication_policy": "frozen local artifact in runnable-world preview",
            "evidence_id": "source:fastq-qc-nanopore-fail-001/primary",
        }
    if tool_name == "artifact.read_text":
        path = safe_workspace_path(workspace, string_arg(arguments, "path"))
        text = path.read_text(encoding="utf-8")
        return {
            "ok": True,
            "path": str(path.relative_to(workspace.resolve())),
            "text": text,
            "excerpt": text[:2000],
            "evidence_id": "file:fastqc_data",
        }
    if tool_name == "fastqc.parse_report":
        path = safe_workspace_path(workspace, string_arg(arguments, "path"))
        parsed = parse_fastqc(path.read_text(encoding="utf-8"))
        write_json(workspace / "state.json", {
            **read_json(workspace / "state.json"),
            "fastqc_report": parsed,
        })
        return {"ok": True, **parsed}
    if tool_name == "qc_policy.evaluate":
        state = read_json(workspace / "state.json")
        report = state.get("fastqc_report")
        if not isinstance(report, dict):
            report = parse_fastqc((workspace / "artifacts" / "fastqc_data.txt").read_text(encoding="utf-8"))
        failed = set(report.get("failed_modules", []))
        checks = []
        for module, check_name in [
            ("Per base sequence quality", "per_base_sequence_quality"),
            ("Adapter Content", "adapter_content"),
        ]:
            checks.append({
                "name": check_name,
                "status": "fail" if module in failed else "pass",
                "observed": "module failed" if module in failed else "module passed",
                "evidence_id": "metric:fastqc.parsed_report",
            })
        return {
            "ok": True,
            "evidence_id": "metric:fastq.policy_result",
            "diagnosis_class": "fastq_qc_decision",
            "severity": "fail" if any(check["status"] == "fail" for check in checks) else "pass",
            "next_action": "trim_or_filter_reads" if any(check["status"] == "fail" for check in checks) else "continue_downstream",
            "checks": checks,
        }
    raise WorldError(f"Unhandled FASTQ tool: {tool_name}")


def parse_fastqc(text: str) -> dict[str, Any]:
    module_statuses: list[dict[str, str]] = []
    basic_statistics: dict[str, str] = {}
    current_module = ""
    in_basic = False
    for line in text.splitlines():
        if line.startswith(">>") and not line.startswith(">>END_MODULE"):
            parts = line[2:].split("\t")
            current_module = parts[0]
            status = parts[1] if len(parts) > 1 else "unknown"
            module_statuses.append({"name": current_module, "status": status})
            in_basic = current_module == "Basic Statistics"
            continue
        if line.startswith(">>END_MODULE"):
            in_basic = False
            current_module = ""
            continue
        if in_basic and line and not line.startswith("#") and "\t" in line:
            key, value = line.split("\t", 1)
            basic_statistics[key] = value
    return {
        "evidence_id": "metric:fastqc.parsed_report",
        "sample_id": basic_statistics.get("Filename", "unknown"),
        "basic_statistics": basic_statistics,
        "module_statuses": module_statuses,
        "failed_modules": [item["name"] for item in module_statuses if item["status"] == "fail"],
        "warning_modules": [item["name"] for item in module_statuses if item["status"] == "warn"],
    }


def call_molecule_tool(run_dir: Path, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    workspace = Path(load_run(run_dir)["workspace_dir"])
    state = read_json(workspace / "state.json")
    if tool_name == "open_sequence":
        path = safe_workspace_path(workspace, string_arg(arguments, "path"))
        molecule_id = arguments.get("molecule_id", "mol_circular")
        sequence = parse_genbank_sequence(path.read_text(encoding="utf-8"))
        molecule = {
            "id": molecule_id,
            "name": "pCircular",
            "length": len(sequence),
            "topology": "circular",
            "moleculeType": "dna",
            "alphabet": "iupac_dna",
            "sourceFormat": "genbank",
            "sequenceDigest": f"sha256:{sha256_text(sequence)}",
        }
        state.update({
            "molecule": molecule,
            "sequence": sequence,
            "revision": 0,
            "primers": [],
        })
        write_json(workspace / "state.json", state)
        return {
            "ok": True,
            "tool": "open_sequence",
            "workspace_path": "state.json",
            "molecule_ids": [molecule_id],
            "previous_revision": 0,
            "revision": 0,
            "evidence_ids": ["tool_io:molecule-primer-validation-001/open_sequence/0", f"molecule:{molecule_id}"],
        }
    if tool_name == "get_sequence_context":
        require_molecule_loaded(state)
        molecule = state["molecule"]
        result = {
            "ok": True,
            "tool": "get_sequence_context",
            "molecule": molecule,
            "revision": state["revision"],
            "features": [{
                "id": "feat_mol_circular_source",
                "moleculeId": molecule["id"],
                "name": "source",
                "type": "source",
                "segments": [{"start": 1, "end": molecule["length"], "strand": "+"}],
                "qualifiers": {"note": "complete sequence"},
            }],
            "primers": state.get("primers", []),
            "evidence_ids": [
                "tool_io:molecule-primer-validation-001/get_sequence_context/1",
                f"molecule:{molecule['id']}",
            ],
        }
        if arguments.get("include_sequence") is True:
            result["sequence"] = state["sequence"]
        return result
    if tool_name == "upsert_primer":
        require_molecule_loaded(state)
        expected_revision = int(arguments.get("expected_revision", -1))
        if expected_revision != state["revision"]:
            return {
                "ok": False,
                "error": {
                    "code": "stale_revision",
                    "message": "Workspace revision does not match expected_revision.",
                    "current_revision": state["revision"],
                    "expected_revision": expected_revision,
                },
            }
        primer = arguments.get("primer")
        if not isinstance(primer, dict):
            raise WorldError("upsert_primer requires primer object")
        primer_id = string_arg(primer, "id")
        primer_sequence = string_arg(primer, "sequence").upper()
        molecule_id = string_arg(primer, "molecule_id")
        bindings = find_bindings(state["sequence"], primer_sequence)
        stored_primer = {
            "id": primer_id,
            "name": primer.get("name", primer_id),
            "sequence": primer_sequence,
            "moleculeId": molecule_id,
            "binding": {"segments": bindings, "mismatches": []},
        }
        state["primers"] = [
            existing for existing in state.get("primers", [])
            if existing.get("id") != primer_id
        ] + [stored_primer]
        state["revision"] = state["revision"] + 1
        write_json(workspace / "state.json", state)
        return {
            "ok": True,
            "tool": "upsert_primer",
            "primer_id": primer_id,
            "action": "created",
            "binding": stored_primer["binding"],
            "revision": state["revision"],
            "evidence_ids": [
                "tool_io:molecule-primer-validation-001/upsert_primer/2",
                f"primer:{primer_id}",
            ],
        }
    if tool_name == "validate_workspace":
        require_molecule_loaded(state)
        issues = []
        if not state.get("primers"):
            issues.append({"code": "missing_primer", "message": "No primer has been added."})
        return {
            "ok": len(issues) == 0,
            "tool": "validate_workspace",
            "valid": len(issues) == 0,
            "issues": issues,
            "revision": state["revision"],
            "evidence_ids": ["tool_io:molecule-primer-validation-001/validate_workspace/3"],
        }
    raise WorldError(f"Unhandled molecule tool: {tool_name}")


def submit_answer(run_dir: Path, answer_path: Path) -> dict[str, Any]:
    run = load_run(run_dir)
    task_id = run["task_id"]
    _, task = load_task(task_id)
    answer = read_json(answer_path)
    result = verify_answer(task, answer, run_dir / "trajectory.jsonl")
    result.update({
        "schema_version": "datalox_runnable_world_verifier_result.v0",
        "task_id": task_id,
        "answer_path": str(answer_path),
        "created_at": utc_now(),
    })
    write_json(run_dir / "verifier_result.json", result)
    append_jsonl(run_dir / "trajectory.jsonl", {
        "type": "submit_answer",
        "created_at": utc_now(),
        "task_id": task_id,
        "answer": answer,
        "verifier_result": result,
        "reward": result["reward"],
    })
    return result


def verify_answer(task: dict[str, Any], answer: dict[str, Any], trajectory_path: Path) -> dict[str, Any]:
    verifier = task["verifier"]
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, expected: Any = None, actual: Any = None) -> None:
        item: dict[str, Any] = {"name": name, "passed": bool(passed)}
        if expected is not None:
            item["expected"] = expected
        if actual is not None:
            item["actual"] = actual
        checks.append(item)

    check("task_id", answer.get("task_id") == task["task_id"], task["task_id"], answer.get("task_id"))
    check("family", answer.get("family") == task["family"], task["family"], answer.get("family"))
    check(
        "diagnosis_class",
        nested(answer, ["diagnosis", "class"]) == verifier["diagnosis_class"],
        verifier["diagnosis_class"],
        nested(answer, ["diagnosis", "class"]),
    )
    check(
        "next_action_type",
        nested(answer, ["next_action", "type"]) == verifier["next_action_type"],
        verifier["next_action_type"],
        nested(answer, ["next_action", "type"]),
    )
    check("missing_fields_empty", answer.get("missing_fields") == [], [], answer.get("missing_fields"))

    evidence_ids = list_arg(answer, "evidence_ids")
    captured_evidence = captured_evidence_ids(trajectory_path)
    for evidence_id in verifier["required_evidence_ids"]:
        check(f"required_evidence:{evidence_id}", evidence_id in evidence_ids, evidence_id, evidence_ids)
        check(f"captured_evidence:{evidence_id}", evidence_id in captured_evidence, evidence_id, sorted(captured_evidence))
    extra_uncaptured = sorted(set(evidence_ids) - captured_evidence)
    check("no_uncaptured_evidence_ids", len(extra_uncaptured) == 0, [], extra_uncaptured)

    avoided = list_arg(answer, "forbidden_actions_avoided")
    for action in verifier["required_forbidden_actions_avoided"]:
        check(f"forbidden_action_avoided:{action}", action in avoided, action, avoided)

    if task["task_id"] == "fastq-qc-nanopore-fail-001":
        family = answer.get("family_output", {})
        if not isinstance(family, dict):
            family = {}
        check(
            "family_diagnosis_class",
            nested(family, ["diagnosis", "class"]) == verifier["diagnosis_class"],
            verifier["diagnosis_class"],
            nested(family, ["diagnosis", "class"]),
        )
        check(
            "family_severity",
            nested(family, ["diagnosis", "severity"]) == verifier["family_checks"]["severity"],
            verifier["family_checks"]["severity"],
            nested(family, ["diagnosis", "severity"]),
        )
        computed = family.get("computed_checks", [])
        if not isinstance(computed, list):
            computed = []
        computed_names = {item.get("name"): item for item in computed if isinstance(item, dict)}
        for name in verifier["family_checks"]["computed_check_names"]:
            item = computed_names.get(name)
            check(f"computed_check:{name}", isinstance(item, dict) and item.get("status") == "fail", "fail", item)
    if task["task_id"] == "molecule-primer-validation-001":
        family = answer.get("family_output", {})
        if not isinstance(family, dict):
            family = {}
        family_checks = verifier["family_checks"]
        for key in ["operation", "molecule_id", "workspace_revision"]:
            check(f"family_{key}", family.get(key) == family_checks[key], family_checks[key], family.get(key))
        primer_ids = family.get("primer_ids", [])
        check("family_primer_id", family_checks["primer_id"] in primer_ids, family_checks["primer_id"], primer_ids)

    passed = all(item["passed"] for item in checks)
    return {
        "passed": passed,
        "reward": 1 if passed else 0,
        "checks": checks,
    }


def captured_evidence_ids(trajectory_path: Path) -> set[str]:
    evidence: set[str] = set()
    if not trajectory_path.exists():
        return evidence
    for line in trajectory_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        observation = event.get("observation")
        if not isinstance(observation, dict):
            continue
        evidence_id = observation.get("evidence_id")
        if isinstance(evidence_id, str):
            evidence.add(evidence_id)
        evidence_ids = observation.get("evidence_ids")
        if isinstance(evidence_ids, list):
            evidence.update(item for item in evidence_ids if isinstance(item, str))
    return evidence


def export_sft(run_dir: Path, out_path: Path) -> dict[str, Any]:
    run = load_run(run_dir)
    _, task = load_task(run["task_id"])
    verifier_result = read_json(run_dir / "verifier_result.json")
    if verifier_result.get("passed") is not True:
        raise WorldError("Cannot export SFT from a non-passing run.")

    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": "You are an agent running in a Datalox runnable world. Use local tools and cite evidence ids.",
        },
        {
            "role": "user",
            "content": task["prompt"],
        },
    ]
    final_answer = None
    tool_index = 0
    for line in (run_dir / "trajectory.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        if event.get("type") == "tool_call":
            tool_index += 1
            call_id = f"call_{tool_index}"
            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": event["tool_name"],
                        "arguments": json.dumps(event["arguments"], sort_keys=True),
                    },
                }],
            })
            messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "name": event["tool_name"],
                "content": json.dumps(event["observation"], sort_keys=True),
            })
        if event.get("type") == "submit_answer" and event.get("verifier_result", {}).get("passed") is True:
            final_answer = event["answer"]
    if final_answer is None:
        raise WorldError("Passing submit_answer event not found.")
    messages.append({
        "role": "assistant",
        "content": json.dumps(final_answer, sort_keys=True),
    })
    row = {
        "schema_version": "datalox_world_sft_messages.v0",
        "task_id": run["task_id"],
        "family": run["family"],
        "source_run": str(run_dir),
        "messages": messages,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True))
        handle.write("\n")
    return {"ok": True, "out": str(out_path), "rows": 1}


def parse_genbank_sequence(text: str) -> str:
    in_origin = False
    parts: list[str] = []
    for line in text.splitlines():
        if line.startswith("ORIGIN"):
            in_origin = True
            continue
        if line.startswith("//"):
            break
        if in_origin:
            parts.append(re.sub("[^A-Za-z]", "", line))
    sequence = "".join(parts).upper()
    if not sequence:
        raise WorldError("No ORIGIN sequence found in GenBank artifact.")
    return sequence


def find_bindings(sequence: str, primer: str) -> list[dict[str, Any]]:
    doubled = sequence + sequence
    length = len(sequence)
    primer_len = len(primer)
    segments: list[dict[str, Any]] = []
    for index in range(length):
        if doubled[index:index + primer_len] == primer:
            start = index + 1
            end = ((index + primer_len - 1) % length) + 1
            segments.append({"start": start, "end": end, "strand": "+"})
    rc = reverse_complement(primer)
    for index in range(length):
        if doubled[index:index + primer_len] == rc:
            start = index + 1
            end = ((index + primer_len - 1) % length) + 1
            segments.append({"start": start, "end": end, "strand": "-"})
    return segments


def reverse_complement(sequence: str) -> str:
    table = str.maketrans("ACGTNacgtn", "TGCANtgcan")
    return sequence.translate(table)[::-1].upper()


def require_molecule_loaded(state: dict[str, Any]) -> None:
    if "molecule" not in state or "sequence" not in state:
        raise WorldError("Call open_sequence before molecule tools that require workspace state.")


def safe_workspace_path(workspace: Path, relative_path: str) -> Path:
    path = (workspace / relative_path).resolve()
    workspace_resolved = workspace.resolve()
    if workspace_resolved not in [path, *path.parents]:
        raise WorldError(f"Path escapes workspace: {relative_path}")
    if not path.exists():
        raise WorldError(f"Path does not exist: {relative_path}")
    return path


def string_arg(arguments: dict[str, Any], key: str) -> str:
    value = arguments.get(key)
    if not isinstance(value, str) or not value:
        raise WorldError(f"Expected non-empty string argument: {key}")
    return value


def list_arg(value: dict[str, Any], key: str) -> list[Any]:
    item = value.get(key)
    return item if isinstance(item, list) else []


def nested(value: dict[str, Any], keys: list[str]) -> Any:
    current: Any = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
