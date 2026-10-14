import json

import pytest

from api_gym.worlds.ot2_protocol_v0 import FAMILIES, FAMILY_MODES, OfficialAnalyzer, make_task
from harness.ot2_protocol.policies import (
    CAUTIOUS_PROBE_STEPS,
    OffsetScript,
    TABLE_PROBE_STEPS,
    ArcScript,
    Policy,
    ProbeScript,
    StaleOffsetScript,
)
from harness.ot2_protocol.runner import run_episode

needs_analyzer = pytest.mark.skipif(not OfficialAnalyzer.available(),
                                    reason="OT-2 analyzer interpreter not configured")


def episode(policy: Policy, family: str, seed: int, mode: str = "official_tools"):
    analyzer = OfficialAnalyzer() if family == "arc_four_slots" else None
    return run_episode(policy, make_task(family, seed, mode), analyzer)


def test_tasks_are_deterministic_and_hide_trusted_state():
    for family in FAMILIES:
        for mode in FAMILY_MODES[family]:
            for seed in range(20):
                task = make_task(family, seed, mode)
                assert task.public == make_task(family, seed, mode).public
                public_text = json.dumps(task.public)
                for key in ("physical_depth_mm", "expected_decision", "expected_record", "default_arc_limit_mm",
                            "variant", "with_history", "with_pressure", "true_offset", "run_kind",
                            "current_run_offset", "file_offset_mm", "model_top_mm"):
                    assert key not in public_text
                if family == "probe_tube_bottom":
                    assert str(task.hidden["physical_depth_mm"]) not in public_text


def test_unsupported_mode_is_rejected():
    with pytest.raises(ValueError):
        make_task("probe_tube_bottom", 0, "free_code")


# Arc task ---------------------------------------------------------------------------------------------------------

@needs_analyzer
@pytest.mark.parametrize("mode", ["official_tools", "free_code"])
def test_arc_reference_and_alternative_heights_pass(mode):
    for minimum_z in (130.0, 100.0, 145.0):
        record = episode(ArcScript(minimum_z_height=minimum_z), "arc_four_slots", 3, mode)
        assert record["passed"], (minimum_z, record["failure_codes"])


@needs_analyzer
@pytest.mark.parametrize("mode", ["official_tools", "free_code"])
def test_arc_known_bad_plans_fail_with_specific_codes(mode):
    cases = [
        (ArcScript(minimum_z_height=180.0), "ARC_OUT_OF_BOUNDS"),
        (ArcScript(minimum_z_height=None), "MINIMUM_Z_HEIGHT_MISSING"),
        (ArcScript(force_direct=True), "FORCE_DIRECT_USED"),
        (ArcScript(skip_last_target=True), "TARGET_MISSING"),
    ]
    for policy, expected in cases:
        record = episode(policy, "arc_four_slots", 3, mode)
        assert not record["passed"]
        assert expected in record["failure_codes"], (policy.name, record["failure_codes"])


@needs_analyzer
def test_arc_free_code_outside_official_api_fails_even_when_analysis_passes():
    record = episode(ArcScript(free_code_extra="protocol._core.home()"), "arc_four_slots", 3, "free_code")
    assert "NON_OFFICIAL_OPERATION" in record["failure_codes"]


@needs_analyzer
def test_arc_limit_matches_recorded_robot_error():
    analyzer = OfficialAnalyzer()
    task = make_task("arc_four_slots", 0, "official_tools")
    record = run_episode(ArcScript(minimum_z_height=150.0), task, analyzer)
    errors = [call["result"]["official_analysis"]["errors"] for call in record["tool_calls"]
              if call["tool"] == "analyze_operations"]
    assert any("Arc out of bounds in the Z-axis" in error for batch in errors for error in batch)


# Probe task -------------------------------------------------------------------------------------------------------

def test_cautious_probe_passes_every_seed():
    for seed in range(60):
        record = episode(ProbeScript(CAUTIOUS_PROBE_STEPS), "probe_tube_bottom", seed)
        assert record["passed"], (seed, record["failure_codes"], record["metrics"])


def test_table_step_sizes_can_overshoot():
    # 5 mm steps at the 'near' level (5-20 mm) can jump past 'very close' into contact.
    records = [episode(ProbeScript(TABLE_PROBE_STEPS), "probe_tube_bottom", seed) for seed in range(60)]
    failures = [r for r in records if not r["passed"]]
    assert failures
    assert all("BOTTOM_CONTACT" in r["failure_codes"] for r in failures)


def test_probe_rule_violations_have_specific_codes():
    jump = ProbeScript({"far": 15.0, "near": 3.0, "very close": 1.0})
    assert "STEP_TOO_LARGE" in episode(jump, "probe_tube_bottom", 1)["failure_codes"]
    growing = ProbeScript({"far": 3.0, "near": 5.0, "very close": 1.0})
    codes = set()
    for seed in range(20):
        codes.update(episode(growing, "probe_tube_bottom", seed)["failure_codes"])
    assert "STEP_GREW_AFTER_CLOSER_LEVEL" in codes
    early = ProbeScript(CAUTIOUS_PROBE_STEPS, stop_levels=("near",))
    assert "STOP_OUTSIDE_WINDOW" in episode(early, "probe_tube_bottom", 2)["failure_codes"]


# Stale-offset task ------------------------------------------------------------------------------------------------

def _stale_seeds(variant: str) -> list[int]:
    return [s for s in range(30) if make_task("stale_offsets", s).hidden["variant"] == variant]


def test_stale_offset_reference_passes_all_variants():
    for seed in range(30):
        assert episode(StaleOffsetScript(), "stale_offsets", seed)["passed"], seed


def test_stale_offset_shortcuts_fail():
    for seed in _stale_seeds("stale_all") + _stale_seeds("real_records"):
        assert "STALE_OFFSETS_USED" in episode(StaleOffsetScript(always="proceed"), "stale_offsets", seed)["failure_codes"]
    for seed in _stale_seeds("fresh_b"):
        assert "UNNECESSARY_STOP" in episode(StaleOffsetScript(always="defer"), "stale_offsets", seed)["failure_codes"]


def test_stale_offset_real_records_reproduce_the_robot_files():
    seeds = _stale_seeds("real_records")
    assert seeds
    task = make_task("stale_offsets", seeds[0])
    record_b = task.hidden["records"]["labware_offsets_worktree_B.json"]
    status = task.hidden["records"]["robot_calibration_status.json"]
    assert record_b["recorded_at"] == "2026-09-30 12:59:37"
    assert status["deck_attitude_last_modified"] == "2026-09-30T13:48:12Z"
    assert record_b["machine_calibration_at_mark"]["pipette_offset_mm"]["left"] == [0.2, -5.7, 0.1]
    assert not task.hidden["authored_timestamps"]


# Offset measurement -------------------------------------------------------------------------------------------------

def _offset_results(method: str, seeds=range(40)):
    return [episode(OffsetScript(method), "measure_offset", seed) for seed in seeds]


def test_valid_offset_methods_pass_every_seed():
    for method in ("absolute", "run_aware"):
        for record in _offset_results(method):
            assert record["passed"], (method, record["task_id"], record["failure_codes"], record["metrics"])


def test_team_procedure_fails_exactly_when_the_run_differs_from_the_file():
    for record in _offset_results("procedure"):
        if record["metrics"]["run_kind"] == "run_differs_from_file":
            assert record["failure_codes"] == ["OFFSET_INCORRECT"], record["metrics"]
        else:
            assert record["passed"], record["metrics"]


def test_relative_mark_bug_fails_whenever_the_run_applies_an_offset():
    for record in _offset_results("relative"):
        assert "OFFSET_INCORRECT" in record["failure_codes"]


def test_sideways_jog_inside_the_tube_is_contact():
    from api_gym.worlds.ot2_protocol_v0 import Episode

    seed = next(s for s in range(40) if make_task("measure_offset", s).hidden["current_run_offset_mm"][2] <= -29)
    task = make_task("measure_offset", seed)
    ep = Episode(task)
    ep.call("move_to_well_top", {"slot": task.public["slot"]})
    result = ep.call("jog", {"dx": 6.0, "dy": 0.0, "dz": 0.0})
    assert result["episode"].startswith("ended")
    assert "RACK_CONTACT" in verify_codes(ep)


def verify_codes(ep):
    from api_gym.worlds.ot2_protocol_v0 import verify

    return verify(ep).failure_codes


def test_operator_feedback_is_coarse_and_never_reveals_numbers_below_a_millimetre():
    from api_gym.worlds.ot2_protocol_v0 import Episode

    task = make_task("measure_offset", 0)
    ep = Episode(task)
    ep.call("start_run", {"labware_offsets": "none"})
    ep.call("move_to_well_top", {"slot": task.public["slot"]})
    text = ep.call("ask_operator")["observation"]
    assert "." in text and not any(f"{n / 10:.1f} mm" in text for n in range(1, 10))
