from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from api_gym.agent_harness import AGENT_TOOL_TRACE_NAME, create_mcp_handler
from api_gym.cli import app
from api_gym.worlds.unitelabs_plate_qc_v0.sampler import SCENARIOS, sample_episode
from api_gym.worlds.unitelabs_plate_qc_v0.services import (
    aspirate,
    dispense,
    get_deck_state,
    get_labware_state,
    read_absorbance,
    submit_protocol,
)
from api_gym.worlds.unitelabs_plate_qc_v0.state import loads_json
from api_gym.worlds.unitelabs_plate_qc_v0.verifier import verify_run


EXPECTED_TOOL_NAMES = {
    "get_deck_state",
    "get_labware_state",
    "aspirate",
    "dispense",
    "read_absorbance",
    "add_workflow_note",
    "submit_protocol",
}


def test_unitelabs_sampler_is_deterministic_and_cli_supported(tmp_path: Path) -> None:
    first = sample_episode(scenario="plate_transfer_qc", seed=42, out_dir=tmp_path / "first")
    second = sample_episode(scenario="plate_transfer_qc", seed=42, out_dir=tmp_path / "second")

    assert set(SCENARIOS) == {"plate_transfer_qc"}
    assert first.task == second.task
    assert _read_text(first.run_metadata_path) == _read_text(second.run_metadata_path).replace(str(second.run_dir), str(first.run_dir))

    cli_run = tmp_path / "cli-run"
    result = CliRunner().invoke(
        app,
        [
            "sample",
            "--world",
            "unitelabs_plate_qc_v0",
            "--scenario",
            "plate_transfer_qc",
            "--seed",
            "7",
            "--out",
            str(cli_run),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["task"]["objective"] == "Evaluate whether the plate QC workflow should continue."
    assert json.loads((cli_run / "run.json").read_text(encoding="utf-8"))["world"] == "unitelabs_plate_qc_v0"


def test_unitelabs_tools_mutate_dry_run_state_and_verifier_passes(tmp_path: Path) -> None:
    episode = sample_episode(scenario="plate_transfer_qc", seed=1, out_dir=tmp_path / "run")

    initial = verify_run(episode.run_dir)
    assert initial.ok is False
    assert {check["name"] for check in initial.checks if not check["ok"]} >= {
        "valid_transfer_completed",
        "readout_after_dispense",
        "protocol_submitted",
    }

    deck = get_deck_state(episode.db_path)
    assert deck["ok"] is True
    assert deck["data"]["mode"] == "dry_run"
    assert deck["data"]["loaded_labware"] == ["source_plate", "assay_plate", "tip_rack_1"]

    source = get_labware_state(episode.db_path, labware_id="source_plate")
    assert source["ok"] is True
    assert source["data"]["wells"]["A1"]["volume_ul"] == 120

    aspirated = aspirate(episode.db_path, source="source_plate:A1", volume_ul=50, tip="tip_rack_1:A1")
    assert aspirated["ok"] is True
    assert aspirated["data"]["source_remaining_ul"] == 70

    dispensed = dispense(episode.db_path, target="assay_plate:B1", volume_ul=50, mix_after=True)
    assert dispensed["ok"] is True
    assert dispensed["data"]["target_volume_ul"] == 50

    readout = read_absorbance(episode.db_path, plate="assay_plate", wavelength_nm=600, wells=["B1"])
    assert readout["ok"] is True
    assert readout["data"]["values"]["B1"] == 0.82

    submitted = submit_protocol(
        episode.db_path,
        decision="continue",
        evidence_readout_id=readout["data"]["readout_id"],
        target_well="assay_plate:B1",
        rationale="B1 OD600 is inside the control band.",
    )
    assert submitted["ok"] is True

    final = verify_run(episode.run_dir)
    assert final.ok is True
    assert all(check["ok"] for check in final.checks)


def test_unitelabs_verifier_rejects_overdraw_and_wrong_decision(tmp_path: Path) -> None:
    overdrawn = sample_episode(scenario="plate_transfer_qc", seed=2, out_dir=tmp_path / "overdrawn")
    overdraw_result = aspirate(overdrawn.db_path, source="source_plate:A1", volume_ul=121, tip="tip_rack_1:A1")

    assert overdraw_result["ok"] is False
    assert overdraw_result["error"]["code"] == "insufficient_well_volume"
    assert verify_run(overdrawn.run_dir).ok is False

    wrong_decision = sample_episode(scenario="plate_transfer_qc", seed=3, out_dir=tmp_path / "wrong-decision")
    assert aspirate(wrong_decision.db_path, source="source_plate:A1", volume_ul=50, tip="tip_rack_1:A1")["ok"]
    assert dispense(wrong_decision.db_path, target="assay_plate:B1", volume_ul=50, mix_after=False)["ok"]
    readout = read_absorbance(wrong_decision.db_path, plate="assay_plate", wavelength_nm=600, wells=["B1"])
    assert readout["ok"]
    assert submit_protocol(
        wrong_decision.db_path,
        decision="hold",
        evidence_readout_id=readout["data"]["readout_id"],
        target_well="assay_plate:B1",
        rationale="Incorrectly holding despite acceptable OD600.",
    )["ok"]

    result = verify_run(wrong_decision.run_dir)
    assert result.ok is False
    failed = {check["name"] for check in result.checks if not check["ok"]}
    assert "decision_matches_observed_data" in failed


def test_unitelabs_verifier_rejects_wrong_submitted_target(tmp_path: Path) -> None:
    episode = sample_episode(scenario="plate_transfer_qc", seed=5, out_dir=tmp_path / "run")
    assert aspirate(episode.db_path, source="source_plate:A1", volume_ul=50, tip="tip_rack_1:A1")["ok"]
    assert dispense(episode.db_path, target="assay_plate:B1", volume_ul=50, mix_after=False)["ok"]
    readout = read_absorbance(episode.db_path, plate="assay_plate", wavelength_nm=600, wells=["B1"])
    assert readout["ok"]
    assert submit_protocol(
        episode.db_path,
        decision="continue",
        evidence_readout_id=readout["data"]["readout_id"],
        target_well="source_plate:A1",
        rationale="Wrong target well despite citing the assay readout.",
    )["ok"]

    result = verify_run(episode.run_dir)

    assert result.ok is False
    failed = {check["name"] for check in result.checks if not check["ok"]}
    assert "submitted_target_matches_expected" in failed


def test_unitelabs_verifier_rejects_readout_before_dispense(tmp_path: Path) -> None:
    episode = sample_episode(scenario="plate_transfer_qc", seed=6, out_dir=tmp_path / "run")
    assert aspirate(episode.db_path, source="source_plate:A1", volume_ul=50, tip="tip_rack_1:A1")["ok"]
    assert dispense(episode.db_path, target="assay_plate:B1", volume_ul=50, mix_after=False)["ok"]
    readout = read_absorbance(episode.db_path, plate="assay_plate", wavelength_nm=600, wells=["B1"])
    assert readout["ok"]
    assert submit_protocol(
        episode.db_path,
        decision="continue",
        evidence_readout_id=readout["data"]["readout_id"],
        target_well="assay_plate:B1",
        rationale="B1 OD600 is inside the control band.",
    )["ok"]
    with sqlite3.connect(episode.db_path) as conn:
        conn.execute("UPDATE readouts SET created_at = ? WHERE id = ?", ("2026-06-11T10:00:00Z", readout["data"]["readout_id"]))
        conn.execute("UPDATE transfers SET created_at = ?", ("2026-06-11T10:05:00Z",))

    result = verify_run(episode.run_dir)

    assert result.ok is False
    failed = {check["name"] for check in result.checks if not check["ok"]}
    assert "readout_after_dispense" in failed


def test_unitelabs_verifier_rejects_live_action_audit_in_dry_run(tmp_path: Path) -> None:
    episode = sample_episode(scenario="plate_transfer_qc", seed=7, out_dir=tmp_path / "run")
    assert aspirate(episode.db_path, source="source_plate:A1", volume_ul=50, tip="tip_rack_1:A1")["ok"]
    assert dispense(episode.db_path, target="assay_plate:B1", volume_ul=50, mix_after=False)["ok"]
    readout = read_absorbance(episode.db_path, plate="assay_plate", wavelength_nm=600, wells=["B1"])
    assert readout["ok"]
    assert submit_protocol(
        episode.db_path,
        decision="continue",
        evidence_readout_id=readout["data"]["readout_id"],
        target_well="assay_plate:B1",
        rationale="B1 OD600 is inside the control band.",
    )["ok"]
    with sqlite3.connect(episode.db_path) as conn:
        conn.execute(
            """
            INSERT INTO audit_log (
              actor, action, object_type, object_id, request_json, response_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("agent@unitelabs.example", "live.unite_api.aspirate", "hardware", "liquid_handler_1", "{}", "{}", "2026-06-11T10:00:00Z"),
        )

    result = verify_run(episode.run_dir)

    assert result.ok is False
    failed = {check["name"] for check in result.checks if not check["ok"]}
    assert "dry_run_no_live_action" in failed


def test_unitelabs_verifier_rejects_missing_expected_labware_well(tmp_path: Path) -> None:
    episode = sample_episode(scenario="plate_transfer_qc", seed=8, out_dir=tmp_path / "run")
    assert aspirate(episode.db_path, source="source_plate:A1", volume_ul=50, tip="tip_rack_1:A1")["ok"]
    assert dispense(episode.db_path, target="assay_plate:B1", volume_ul=50, mix_after=False)["ok"]
    readout = read_absorbance(episode.db_path, plate="assay_plate", wavelength_nm=600, wells=["B1"])
    assert readout["ok"]
    assert submit_protocol(
        episode.db_path,
        decision="continue",
        evidence_readout_id=readout["data"]["readout_id"],
        target_well="assay_plate:B1",
        rationale="B1 OD600 is inside the control band.",
    )["ok"]
    with sqlite3.connect(episode.db_path) as conn:
        conn.execute("DELETE FROM wells WHERE labware_id = ? AND well_id = ?", ("assay_plate", "B1"))

    result = verify_run(episode.run_dir)

    assert result.ok is False
    failed = {check["name"] for check in result.checks if not check["ok"]}
    assert "expected_labware_and_wells_exist" in failed


def test_unitelabs_task_package_and_mcp_handler_are_world_specific(tmp_path: Path) -> None:
    episode = sample_episode(scenario="plate_transfer_qc", seed=4, out_dir=tmp_path / "run")

    task_result = CliRunner().invoke(app, ["task", "--run", str(episode.run_dir)])
    assert task_result.exit_code == 0, task_result.output
    task_package = json.loads(task_result.output)

    assert task_package["schema_version"] == "api_gym.agent_task.v0"
    assert task_package["world"] == "unitelabs_plate_qc_v0"
    assert task_package["world_id"] == "unitelabs-plate-qc-v0"
    assert "Evaluate whether the plate QC workflow should continue" in task_package["agent_facing_instructions"]
    mcp_servers = task_package["recommended_mcp_config"]["mcpServers"]
    assert list(mcp_servers) == ["api-gym-unitelabs-plate-qc-v0"]
    assert mcp_servers["api-gym-unitelabs-plate-qc-v0"]["args"] == ["mcp", "--run", str(episode.run_dir)]

    handler = create_mcp_handler(episode.run_dir)
    listed = handler.handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert listed is not None
    assert {tool["name"] for tool in listed["result"]["tools"]} == EXPECTED_TOOL_NAMES

    called = handler.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "get_deck_state", "arguments": {}},
        }
    )

    assert called is not None
    assert called["result"]["isError"] is False
    assert called["result"]["structuredContent"]["data"]["dry_run"] is True

    trace_rows = [
        json.loads(line)
        for line in (episode.run_dir / AGENT_TOOL_TRACE_NAME).read_text(encoding="utf-8").splitlines()
    ]
    assert len(trace_rows) == 1
    assert trace_rows[0]["schema_version"] == "api_gym.agent_tool_call.v0"
    assert trace_rows[0]["world"] == "unitelabs_plate_qc_v0"
    assert trace_rows[0]["scenario"] == "plate_transfer_qc"
    assert trace_rows[0]["tool_name"] == "get_deck_state"
    assert trace_rows[0]["arguments"] == {}
    assert trace_rows[0]["result"] == called["result"]["structuredContent"]


def test_unitelabs_rejects_billing_only_cli_surfaces_explicitly(tmp_path: Path) -> None:
    episode = sample_episode(scenario="plate_transfer_qc", seed=9, out_dir=tmp_path / "run")
    runner = CliRunner()

    serve = runner.invoke(app, ["serve", "--run", str(episode.run_dir)])
    assert serve.exit_code == 2
    assert "unsupported_world_surface" in serve.output
    assert "unitelabs_plate_qc_v0" in serve.output

    resolve = runner.invoke(app, ["resolve", "--run", str(episode.run_dir)])
    assert resolve.exit_code == 2
    assert "unsupported_world_surface" in resolve.output
    assert "unitelabs_plate_qc_v0" in resolve.output

    run = runner.invoke(
        app,
        [
            "run",
            "--run",
            str(episode.run_dir),
            "--model",
            "fake-model",
            "--base-url",
            "http://127.0.0.1:9/v1",
            "--api-key",
            "EMPTY",
        ],
    )
    assert run.exit_code == 2
    assert "unsupported_world_surface" in run.output
    assert "unitelabs_plate_qc_v0" in run.output

    eval_result = runner.invoke(
        app,
        [
            "eval",
            "--world",
            "unitelabs_plate_qc_v0",
            "--scenarios",
            "plate_transfer_qc",
            "--seeds",
            "1",
            "--model",
            "fake-model",
            "--base-url",
            "http://127.0.0.1:9/v1",
            "--out",
            str(tmp_path / "eval.jsonl"),
        ],
    )
    assert eval_result.exit_code == 2
    assert "unsupported_world_surface" in eval_result.output
    assert "unitelabs_plate_qc_v0" in eval_result.output


def test_unitelabs_export_packages_tool_trace_and_verifier_result(tmp_path: Path) -> None:
    episode = sample_episode(scenario="plate_transfer_qc", seed=10, out_dir=tmp_path / "run")
    handler = create_mcp_handler(episode.run_dir)

    _mcp_call(handler, "aspirate", {"source": "source_plate:A1", "volume_ul": 50, "tip": "tip_rack_1:A1"})
    _mcp_call(handler, "dispense", {"target": "assay_plate:B1", "volume_ul": 50, "mix_after": True})
    readout = _mcp_call(handler, "read_absorbance", {"plate": "assay_plate", "wavelength_nm": 600, "wells": ["B1"]})
    _mcp_call(
        handler,
        "submit_protocol",
        {
            "decision": "continue",
            "evidence_readout_id": readout["data"]["readout_id"],
            "target_well": "assay_plate:B1",
            "rationale": "B1 OD600 is inside the control band.",
        },
    )
    out = tmp_path / "run-export.json"

    result = CliRunner().invoke(app, ["export", "--run", str(episode.run_dir), "--out", str(out)])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    written = json.loads(out.read_text(encoding="utf-8"))
    assert payload == written
    assert payload["schema_version"] == "api_gym.run_export.v0"
    assert payload["world"] == "unitelabs_plate_qc_v0"
    assert payload["verifier_result"]["ok"] is True
    assert [row["tool_name"] for row in payload["tool_trace"]] == [
        "aspirate",
        "dispense",
        "read_absorbance",
        "submit_protocol",
    ]
    assert payload["artifacts"]["tool_trace"] == str(episode.run_dir / AGENT_TOOL_TRACE_NAME)


def test_unitelabs_session_create_manifest_and_check_tools(tmp_path: Path) -> None:
    run_dir = tmp_path / "session-run"
    result = CliRunner().invoke(
        app,
        [
            "session",
            "create",
            "--world",
            "unitelabs_plate_qc_v0",
            "--scenario",
            "plate_transfer_qc",
            "--seed",
            "11",
            "--out",
            str(run_dir),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    manifest = json.loads(result.output)
    written = json.loads((run_dir / "session_manifest.json").read_text(encoding="utf-8"))
    assert manifest == written
    assert manifest["schema_version"] == "api_gym.world_session.v0"
    assert manifest["session_id"] == "session-run"
    assert manifest["world"] == "unitelabs_plate_qc_v0"
    assert manifest["scenario"] == "plate_transfer_qc"
    assert manifest["mode"] == "dry_run"
    assert manifest["expected_tools"] == sorted(EXPECTED_TOOL_NAMES)
    assert manifest["task_path"] == str(run_dir.resolve() / "task.json")
    assert Path(manifest["task_package"]).exists()
    assert manifest["artifacts"]["state_db"] == str(run_dir.resolve() / "state.sqlite")
    assert "Run the Datalox tool catalog check" in manifest["integration_instructions"][2]
    assert manifest["preflight"] == {
        "required": True,
        "datalox_tool_catalog_command": ["api-gym", "session", "check-tools", "--run", str(run_dir.resolve())],
        "host_requirement": "The host must compare its own agent-visible tool registry against expected_tools before rollout.",
        "proves_agent_visible_tools": False,
    }
    assert manifest["mcp"]["mcpServers"]["api-gym-unitelabs-plate-qc-v0"]["args"] == ["mcp", "--run", str(run_dir.resolve())]
    assert manifest["commands"]["check_tools"] == ["api-gym", "session", "check-tools", "--run", str(run_dir.resolve())]
    assert manifest["commands"]["finalize"] == ["api-gym", "session", "finalize", "--run", str(run_dir.resolve())]
    assert manifest["commands"]["verify"] == ["api-gym", "verify", "--run", str(run_dir.resolve())]
    assert manifest["commands"]["export"] == [
        "api-gym",
        "export",
        "--run",
        str(run_dir.resolve()),
        "--out",
        str(run_dir.resolve() / "run_export.json"),
    ]

    check = CliRunner().invoke(app, ["session", "check-tools", "--run", str(run_dir)])

    assert check.exit_code == 0, check.output
    check_payload = json.loads(check.output)
    assert check_payload == {
        "ok": True,
        "expected_tools": sorted(EXPECTED_TOOL_NAMES),
        "listed_tools": sorted(EXPECTED_TOOL_NAMES),
        "missing_tools": [],
        "unexpected_tools": [],
        "world": "unitelabs_plate_qc_v0",
    }


def test_unitelabs_session_finalize_verifies_and_exports(tmp_path: Path) -> None:
    run_dir = tmp_path / "session-finalize"
    create = CliRunner().invoke(
        app,
        [
            "session",
            "create",
            "--world",
            "unitelabs_plate_qc_v0",
            "--scenario",
            "plate_transfer_qc",
            "--seed",
            "12",
            "--out",
            str(run_dir),
        ],
    )
    assert create.exit_code == 0, create.output
    handler = create_mcp_handler(run_dir)

    _mcp_call(handler, "aspirate", {"source": "source_plate:A1", "volume_ul": 50, "tip": "tip_rack_1:A1"})
    _mcp_call(handler, "dispense", {"target": "assay_plate:B1", "volume_ul": 50, "mix_after": True})
    readout = _mcp_call(handler, "read_absorbance", {"plate": "assay_plate", "wavelength_nm": 600, "wells": ["B1"]})
    _mcp_call(
        handler,
        "submit_protocol",
        {
            "decision": "continue",
            "evidence_readout_id": readout["data"]["readout_id"],
            "target_well": "assay_plate:B1",
            "rationale": "B1 OD600 is inside the control band.",
        },
    )

    finalized = CliRunner().invoke(app, ["session", "finalize", "--run", str(run_dir), "--json"])

    assert finalized.exit_code == 0, finalized.output
    payload = json.loads(finalized.output)
    assert payload["schema_version"] == "api_gym.world_session_finalization.v0"
    assert payload["ok"] is True
    assert payload["world"] == "unitelabs_plate_qc_v0"
    assert payload["verifier_result"]["ok"] is True
    assert payload["export_path"] == str(run_dir.resolve() / "run_export.json")
    assert Path(payload["export_path"]).exists()
    exported = json.loads(Path(payload["export_path"]).read_text(encoding="utf-8"))
    assert exported["verifier_result"]["ok"] is True
    assert [row["tool_name"] for row in exported["tool_trace"]] == [
        "aspirate",
        "dispense",
        "read_absorbance",
        "submit_protocol",
    ]


def _mcp_call(handler, name: str, arguments: dict[str, object]) -> dict[str, object]:
    response = handler.handle_message(
        {
            "jsonrpc": "2.0",
            "id": name,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
    )
    assert response is not None
    assert response["result"]["isError"] is False
    return response["result"]["structuredContent"]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")
