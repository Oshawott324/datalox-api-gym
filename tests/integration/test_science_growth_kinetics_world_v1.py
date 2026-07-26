from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytest.importorskip("pylabrobot")
pytest.importorskip("datalox_gated_runtime.world_v1.admission")

from datalox_gated_runtime.world_v1.admission import admit_world
from datalox_gated_runtime.world_v1.admission_runtime import (
    runtime_admission_callbacks,
)
from datalox_gated_runtime.world_v1.backend import (
    WorldBundleBackend,
    initialize_world_bundle_session,
)
from datalox_gated_runtime.world_v1.bundle import validate_world_bundle
from datalox_gated_runtime.world_v1.contracts import ActorContext
from api_gym.worlds.source_refs import validate_world_source_refs

REPO_ROOT = Path(__file__).resolve().parents[2]
WORLD = REPO_ROOT / "worlds" / "science_growth_kinetics_v0"
BUILDER = REPO_ROOT / "scripts" / "worlds" / "build_science_growth_kinetics.py"
TRAJECTORIES = WORLD / "tests" / "trajectories" / "growth.json"
BRIDGE_SOURCE = (
    REPO_ROOT
    / "api_gym"
    / "provider_components"
    / "pylabrobot"
    / "world_bridge.py"
)
BRIDGE_COPY = WORLD / "world" / "v1" / "provider_pylabrobot.py"


def test_growth_world_build_is_deterministic_and_self_contained() -> None:
    result = subprocess.run(
        [sys.executable, str(BUILDER), "--check"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert BRIDGE_COPY.read_bytes() == BRIDGE_SOURCE.read_bytes()

    bundle = validate_world_bundle(WORLD)
    assert bundle.manifest.world_id == "science_growth_kinetics_v0"
    assert len(bundle.episodes) == 12
    assert {episode["family_id"] for episode in bundle.episodes} == {
        "growth_nominal_v1",
        "growth_resource_recovery_v1",
        "growth_async_freshness_recovery_v1",
    }
    assert len(bundle.tools) == 11
    assert {source["grounding_level"] for source in bundle.sources} == {
        "G0_BENCHMARK_DEFINED",
        "G1_OFFICIAL_DOCS",
        "G2_LOCAL_EXECUTED",
    }
    source_refs = validate_world_source_refs("science_growth_kinetics_v0")
    assert source_refs["ok"] is True
    assert source_refs["missing_records"] == []
    assert source_refs["missing_world_evidence"] == []
    compatibility = json.loads((WORLD / "compatibility.json").read_text())
    assert compatibility["schema_version"] == "datalox_world_compatibility_v1"
    assert compatibility["runtime"]["tested_git_commit"] == "ce53726"
    assert compatibility["providers"]["pylabrobot"]["tested_version"] == "0.2.1"


def test_growth_world_full_runtime_admission_passes() -> None:
    report = admit_world(
        WORLD,
        callbacks=runtime_admission_callbacks(),
        admitted_at="2026-07-26T00:00:00+00:00",
    )

    assert report.admitted is True
    payload = report.to_dict()
    assert payload["coverage"] == {
        "episode_count": 12,
        "negative_trajectory_count": 4,
        "operation_families": [
            "incubation",
            "liquid_handling",
            "logical_time",
            "plate_reading",
            "scientific_record",
        ],
        "parity_case_count": 1,
        "reference_trajectory_count": 12,
        "role_count": 1,
        "tool_count": 11,
        "trajectory_count": 17,
    }
    assert all(check["passed"] for check in payload["checks"].values())


def test_low_resource_error_is_structured_and_backup_transfer_executes(
    tmp_path: Path,
) -> None:
    episode_id = "growth-kinetics-004"
    run_dir = tmp_path / "run"
    initialize_world_bundle_session(
        source_bundle_dir=WORLD,
        run_dir=run_dir,
        episode_id=episode_id,
    )
    backend = WorldBundleBackend(run_dir=run_dir)
    actor = ActorContext("science-agent", "scientist_agent")
    try:
        before = backend.session.get_state("deck")
        failed = backend.handle(
            backend.request_for_tool(
                "pylabrobot.transfer",
                {
                    "source_well": "A4",
                    "target_well": "A4",
                    "tip_spot": "A1",
                    "volume_ul": 200.0,
                },
                actor=actor,
            )
        )
        assert failed is not None
        assert failed.status_code == 409
        assert failed.decision_kind == "deny"
        assert failed.body["error"]["code"] == "PYLABROBOT_TOO_LITTLE_LIQUID"
        assert backend.session.get_state("deck") == before

        recovered = backend.handle(
            backend.request_for_tool(
                "pylabrobot.transfer",
                {
                    "source_well": "G12",
                    "target_well": "A4",
                    "tip_spot": "A1",
                    "volume_ul": 200.0,
                },
                actor=actor,
            )
        )
        assert recovered is not None
        assert recovered.status_code == 200
        provider = recovered.body["provider_execution"]
        assert provider["grounding_level"] == "simulator_executed"
        assert provider["provider"]["backend"] == "OpentronsOT2Simulator"
        assert provider["tip_available"] is False
        deck = backend.session.get_state("deck")
        assert deck["source_volumes_ul"]["G12"] == 20.0
        assert deck["target_volumes_ul"]["A4"] == 200.0
        assert deck["tip_availability"]["A1"] is False
    finally:
        backend.close()


def test_provider_bridge_executes_inside_async_mcp_context(tmp_path: Path) -> None:
    run_dir = tmp_path / "async-run"
    initialize_world_bundle_session(
        source_bundle_dir=WORLD,
        run_dir=run_dir,
        episode_id="growth-kinetics-000",
    )
    backend = WorldBundleBackend(run_dir=run_dir)
    actor = ActorContext("science-agent", "scientist_agent")

    async def invoke_transfer() -> object:
        return backend.handle(
            backend.request_for_tool(
                "pylabrobot.transfer",
                {
                    "source_well": "A1",
                    "target_well": "A1",
                    "tip_spot": "A1",
                    "volume_ul": 200.0,
                },
                actor=actor,
            )
        )

    try:
        response = asyncio.run(invoke_transfer())
        assert response is not None
        assert response.status_code == 200
        assert response.body["provider_execution"]["grounding_level"] == (
            "simulator_executed"
        )
    finally:
        backend.close()


def test_reference_verification_is_vector_only_and_fast(tmp_path: Path) -> None:
    trajectories = json.loads(TRAJECTORIES.read_text())["trajectories"]
    reference = next(
        item for item in trajectories if item["id"] == "reference-growth-kinetics-000"
    )
    run_dir = tmp_path / "reference"
    initialize_world_bundle_session(
        source_bundle_dir=WORLD,
        run_dir=run_dir,
        episode_id=reference["episode_id"],
    )
    backend = WorldBundleBackend(run_dir=run_dir)
    actor = ActorContext("science-agent", "scientist_agent")
    try:
        for step in reference["steps"]:
            response = backend.handle(
                backend.request_for_tool(
                    step["tool_name"],
                    step["arguments"],
                    actor=actor,
                )
            )
            assert response is not None
            assert response.status_code < 400, (step, response.body)

        result = backend.verify()
        payload = result.to_dict()
        assert payload["passed"] is True
        assert payload["failure_codes"] == []
        assert len(payload["checks"]) == 11
        assert "reward" not in payload
        assert "score" not in payload

        readback = backend.handle(
            backend.request_for_tool(
                "pylabrobot.get_kinetic_read",
                {"job_id": "run-001"},
                actor=actor,
            )
        )
        assert readback is not None
        assert "series" not in readback.body
        assert readback.body["series_summary"]["well_count"] == 9
        assert readback.body["series_summary"]["total_values"] == 5409
        assert len(json.dumps(readback.body)) < 10_000

        timings = []
        for _ in range(30):
            started = time.perf_counter()
            assert backend.verify().passed is True
            timings.append((time.perf_counter() - started) * 1000)
        p95 = sorted(timings)[int(len(timings) * 0.95) - 1]
        assert p95 < 100

        events = backend.session.verifier_events()
        executed = [
            event["payload"]["provider_execution"]["provider"]["backend"]
            for event in events
            if event.get("event_type") == "growth_operation"
            and isinstance(event.get("payload", {}).get("provider_execution"), dict)
        ]
        assert "OpentronsOT2Simulator" in executed
        assert "IncubatorChatterboxBackend" in executed
        assert "PlateReaderChatterboxBackend" in executed
    finally:
        backend.close()


def test_selected_ot2_evidence_executes_discard_not_tip_return() -> None:
    capture = json.loads(
        (WORLD / "evidence" / "ot2_success_v0.json").read_text()
    )
    operation_ids = [
        step["operation_id"] for step in capture["sequence"]["steps"]
    ]
    assert "pylabrobot.ot2.discard_tip" in operation_ids
    discard = next(
        step
        for step in capture["sequence"]["steps"]
        if step["operation_id"] == "pylabrobot.ot2.discard_tip"
    )
    assert discard["implementation"].endswith("LiquidHandler.discard_tips")
