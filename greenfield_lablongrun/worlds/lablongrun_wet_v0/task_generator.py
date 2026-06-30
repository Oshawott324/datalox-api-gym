"""Template-driven LabLongRun-Wet task generation and admission."""

from __future__ import annotations

import hashlib
import json
import random
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import Any

from greenfield_lablongrun.core.schemas import read_json, write_json
from greenfield_lablongrun.worlds.lablongrun_wet_v0 import state
from greenfield_lablongrun.worlds.lablongrun_wet_v0.tools import expected_tools


WORLD_ID = "lablongrun_wet_v0"
DEFAULT_TEMPLATE_ID = "od600_nominal"
DEFAULT_DIFFICULTY = "short"
WORLD_DIR = Path(__file__).parent
TEMPLATE_CATALOG = WORLD_DIR / "templates" / "task_templates.json"
SOURCE_REFS_PATH = WORLD_DIR / "source_refs.json"
ALLOWED_STOCHASTIC_SOURCE_STATUSES = {
    "none",
    "assumption_for_calibration",
    "domain_reviewed",
    "partner_reported",
    "source_grounded",
}
ALLOWED_FAILURE_TYPES = {"verifier_check", "tool_error"}
DEAD_VOLUME_UL = 5.0
SCHEDULE_REFS = {
    "fault": "hidden/fault_schedule.json",
    "noise": "hidden/noise_schedule.json",
}
HIDDEN_LEAK_TOKENS = (
    "verifier_expectations",
    "oracle_plan",
    "known_bad_plans",
    "expected_final_volumes_ul",
    "expected_decision",
    "target_well_ref",
    "hidden/",
)


@dataclass(frozen=True)
class GeneratedTask:
    task_dir: Path
    task_id: str
    template_id: str
    seed: int
    difficulty: str
    admission_path: Path

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_dir": str(self.task_dir),
            "task_id": self.task_id,
            "template_id": self.template_id,
            "seed": self.seed,
            "difficulty": self.difficulty,
            "admission": str(self.admission_path),
        }


@dataclass(frozen=True)
class AdmissionResult:
    task_dir: Path
    admitted: bool
    checks: list[dict[str, Any]]
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return self.payload


def generate_task(
    template_id: str,
    seed: int,
    difficulty: str,
    out: Path,
    *,
    clean: bool = False,
    admit: bool = True,
) -> GeneratedTask:
    """Render one task bundle from a hand-calibrated template."""

    template = _get_template(template_id)
    if difficulty not in template["difficulty_targets"]:
        raise ValueError(f"Template {template_id!r} does not define difficulty {difficulty!r}.")

    out_dir = out.resolve()
    if clean and out_dir.exists():
        shutil.rmtree(out_dir)
    if out_dir.exists() and any(out_dir.iterdir()):
        raise FileExistsError(f"Task directory already exists and is not empty: {out_dir}")

    out_dir.mkdir(parents=True, exist_ok=True)
    visible_dir = out_dir / "visible_artifacts"
    hidden_dir = out_dir / "hidden"
    visible_dir.mkdir()
    hidden_dir.mkdir()

    parameters = _resolve_parameters(template, seed)
    task_id = f"{template_id}__seed_{seed:04d}"
    horizon = template["difficulty_targets"][difficulty]
    artifact_names = sorted(template["visible_artifacts"].keys())
    environment_seed = int(seed)
    task_projection_metadata = _task_projection_metadata(template)
    fault_schedule = _deterministic_schedule("fault", environment_seed, template, parameters, difficulty)
    noise_schedule = _deterministic_schedule("noise", environment_seed, template, parameters, difficulty)

    state.seed_initial_state(
        out_dir / "initial_state.sqlite",
        source_volume_ul=float(parameters["source_volume_ul"]),
        diluent_volume_ul=float(parameters["diluent_start_volume_ul"]),
        stock_corrected_od600=float(parameters["stock_corrected_od600"]),
        acceptance_band={
            "min": float(parameters["acceptance_min"]),
            "max": float(parameters["acceptance_max"]),
        },
        fault_schedule=fault_schedule,
    )

    write_json(
        out_dir / "task.json",
        {
            "schema_version": "greenfield_lablongrun.task.v0",
            "world": WORLD_ID,
            "scenario": template["scenario"],
            "task_id": task_id,
            "template_id": template_id,
            "seed": seed,
            "environment_seed": environment_seed,
            "difficulty": difficulty,
            "failure_mode": template["lab_failure_mode"],
            **task_projection_metadata,
            "objective": _render_string(template["objective"], _render_context(template, parameters, seed, difficulty)),
            "expected_tools": expected_tools(),
            "visible_artifacts": artifact_names,
            "source_refs": template["source_refs"],
            "schedule_refs": dict(SCHEDULE_REFS),
            "oracle_strategy": template["oracle_strategy"],
            "known_bad_plan_strategy": template["known_bad_plan_strategy"],
            "expected_failure_codes": template["expected_failure_codes"],
            "verifier_predicates": template["verifier_predicates"],
            "expected_horizon": {
                "bin": difficulty,
                "min_tool_calls": int(horizon["min_tool_calls"]),
                "max_tool_calls": int(horizon["max_tool_calls"]),
            },
        },
    )
    write_json(
        out_dir / "agent_task.json",
        {
            "schema_version": "greenfield_lablongrun.agent_task.v0",
            "instructions": [
                _render_string(line, _render_context(template, parameters, seed, difficulty))
                for line in template["agent_instructions"]
            ],
            "available_artifacts": artifact_names,
            "available_tools": expected_tools(),
            "hidden_state_warning": "Do not assume direct access to state.sqlite or verifier expectations.",
        },
    )
    write_json(
        hidden_dir / "verifier_expectations.json",
        _verifier_expectations(template, parameters, artifact_names, difficulty),
    )
    write_json(
        hidden_dir / "oracle_plan.json",
        {
            "schema_version": "greenfield_lablongrun.oracle_plan.v0",
            "plan_id": "oracle",
            "strategy": template["oracle_strategy"],
            "steps": oracle_steps(parameters),
        },
    )
    write_json(
        hidden_dir / "known_bad_plans.json",
        {
            "schema_version": "greenfield_lablongrun.known_bad_plans.v0",
            "plans": _known_bad_plans(template, parameters),
        },
    )
    write_json(hidden_dir / "fault_schedule.json", fault_schedule)
    write_json(hidden_dir / "noise_schedule.json", noise_schedule)
    write_json(out_dir / "source_refs_snapshot.json", source_refs())
    _write_visible_artifacts(visible_dir, template, parameters, seed, difficulty)

    if admit:
        validate_generated_task(out_dir)

    return GeneratedTask(
        task_dir=out_dir,
        task_id=task_id,
        template_id=template_id,
        seed=seed,
        difficulty=difficulty,
        admission_path=out_dir / "admission.json",
    )


def generate_suite(suite_spec: Path, out: Path) -> list[GeneratedTask]:
    """Generate a JSON-defined suite into one output directory."""

    spec = read_json(suite_spec)
    entries = spec.get("tasks")
    if not isinstance(entries, list) or not entries:
        raise ValueError("Suite spec must contain a non-empty 'tasks' list.")

    out_dir = out.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    generated: list[GeneratedTask] = []
    for entry in entries:
        template_id = entry["template_id"]
        difficulty = entry.get("difficulty", DEFAULT_DIFFICULTY)
        if "seeds" in entry:
            seeds = entry["seeds"]
        elif "seed" in entry:
            seeds = [entry["seed"]]
        else:
            seeds = []
        if not seeds:
            raise ValueError(f"Suite entry for {template_id!r} must include 'seed' or 'seeds'.")
        for seed in seeds:
            task_id = f"{template_id}__seed_{int(seed):04d}"
            generated.append(generate_task(template_id, int(seed), difficulty, out_dir / task_id, clean=True))

    write_json(
        out_dir / "suite_manifest.json",
        {
            "schema_version": "greenfield_lablongrun.suite_manifest.v0",
            "suite_spec": str(suite_spec.resolve()),
            "task_count": len(generated),
            "tasks": [task.to_dict() for task in generated],
        },
    )
    return generated


def validate_generated_task(task_dir: Path) -> AdmissionResult:
    """Run admission checks and write admission.json for a generated bundle."""

    task_dir = task_dir.resolve()
    task = read_json(task_dir / "task.json")
    agent_task = read_json(task_dir / "agent_task.json")
    expectations = read_json(task_dir / "hidden" / "verifier_expectations.json")
    known_bad_doc = read_json(task_dir / "hidden" / "known_bad_plans.json")
    template = _get_template(task["template_id"])

    checks: list[dict[str, Any]] = []

    def add_check(name: str, ok: bool, details: dict[str, Any] | None = None) -> None:
        payload: dict[str, Any] = {"name": name, "ok": bool(ok)}
        if details:
            payload["details"] = details
        checks.append(payload)

    artifact_names = task.get("visible_artifacts", [])
    missing = [
        name
        for name in artifact_names
        if not (task_dir / "visible_artifacts" / name).is_file()
        or not (task_dir / "visible_artifacts" / name).read_text(encoding="utf-8").strip()
    ]
    add_check("required_visible_artifacts_exist", not missing, {"missing": missing})

    visible_sets_match = sorted(agent_task.get("available_artifacts", [])) == sorted(artifact_names)
    add_check("visible_artifact_manifest_consistent", visible_sets_match)
    hidden_leak_tokens = _visible_hidden_leaks(task_dir)
    add_check("no_hidden_leakage", not hidden_leak_tokens, {"tokens": hidden_leak_tokens})
    add_check("initial_state_physically_possible", _initial_state_physically_possible(task_dir))

    projection_contract_ref = task.get("projection_contract_ref")
    domain_source_status = task.get("domain_source_status")
    stochastic_source_status = task.get("stochastic_source_status")
    environment_seed = task.get("environment_seed")
    projection_contract_path = _world_ref_path(projection_contract_ref) if isinstance(projection_contract_ref, str) else None
    expected_projection_metadata = _task_projection_metadata(template)
    actual_projection_metadata = {
        key: task.get(key)
        for key in (
            "projection_contract_ref",
            "domain_source_status",
            "stochastic_source_status",
            "attribution_labels",
        )
    }
    add_check(
        "domain_source_status_present",
        isinstance(domain_source_status, str) and bool(domain_source_status.strip()),
        {"domain_source_status": domain_source_status},
    )
    add_check(
        "projection_contract_ref_present",
        isinstance(projection_contract_ref, str) and bool(projection_contract_ref.strip()),
        {"projection_contract_ref": projection_contract_ref},
    )
    add_check(
        "stochastic_source_status_valid",
        stochastic_source_status in ALLOWED_STOCHASTIC_SOURCE_STATUSES,
        {"stochastic_source_status": stochastic_source_status, "allowed": sorted(ALLOWED_STOCHASTIC_SOURCE_STATUSES)},
    )
    add_check(
        "projection_contract_file_exists",
        projection_contract_path is not None and projection_contract_path.is_file(),
        {
            "projection_contract_ref": projection_contract_ref,
            "path": str(projection_contract_path) if projection_contract_path else None,
        },
    )
    add_check(
        "projection_metadata_matches_template",
        actual_projection_metadata == expected_projection_metadata,
        {"expected": expected_projection_metadata, "actual": actual_projection_metadata},
    )
    add_check(
        "environment_seed_present",
        isinstance(environment_seed, int),
        {"environment_seed": environment_seed},
    )
    schedule_refs = task.get("schedule_refs")
    add_check(
        "schedule_refs_present",
        schedule_refs == SCHEDULE_REFS,
        {"expected": SCHEDULE_REFS, "actual": schedule_refs},
    )
    schedule_details = {
        kind: _schedule_admission_details(task_dir, task, template, kind)
        for kind in sorted(SCHEDULE_REFS)
    }
    for kind, details in schedule_details.items():
        add_check(f"{kind}_schedule_exists", details["exists"], details)
        add_check(f"{kind}_schedule_deterministic_for_environment_seed", details["deterministic"], details)
    add_check(
        "stochastic_none_has_empty_schedules",
        stochastic_source_status != "none" or all(details["empty"] for details in schedule_details.values()),
        {"schedules": schedule_details},
    )

    template_matches = [
        item
        for item in _load_template_catalog()["templates"]
        if item["template_id"] == task["template_id"] and item["lab_failure_mode"] == task["failure_mode"]
    ]
    add_check(
        "task_maps_to_one_template_failure_mode",
        len(template_matches) == 1,
        {"template_id": task["template_id"], "failure_mode": task["failure_mode"], "matches": len(template_matches)},
    )
    add_check("verifier_predicates_non_vacuous", bool(template.get("verifier_predicates")))

    oracle_tool_calls = 0
    oracle_error: str | None = None
    try:
        from greenfield_lablongrun.worlds.lablongrun_wet_v0.oracle import run_oracle
        from greenfield_lablongrun.worlds.lablongrun_wet_v0.verifier import verify_run

        with tempfile.TemporaryDirectory(prefix="lablongrun_admission_") as tmp:
            oracle_run = run_oracle(task_dir, Path(tmp) / "oracle", clean=True)
            oracle_result = verify_run(oracle_run.run_dir)
            oracle_tool_calls = oracle_run.trace.counts()["tool_calls"]
        oracle_ok = oracle_result.ok
    except Exception as exc:  # pragma: no cover - written into admission for agent debugging.
        oracle_ok = False
        oracle_error = repr(exc)
    add_check("oracle_passes", oracle_ok, {"error": oracle_error} if oracle_error else None)

    horizon = task["expected_horizon"]
    add_check(
        "expected_horizon_bin_fits_oracle_tool_calls",
        oracle_ok and int(horizon["min_tool_calls"]) <= oracle_tool_calls <= int(horizon["max_tool_calls"]),
        {
            "min_tool_calls": horizon["min_tool_calls"],
            "max_tool_calls": horizon["max_tool_calls"],
            "oracle_tool_calls": oracle_tool_calls,
        },
    )

    known_bad_results = []
    try:
        from greenfield_lablongrun.worlds.lablongrun_wet_v0.oracle import run_known_bad_plan
        from greenfield_lablongrun.worlds.lablongrun_wet_v0.verifier import verify_run

        with tempfile.TemporaryDirectory(prefix="lablongrun_admission_bad_") as tmp:
            for plan in known_bad_doc.get("plans", []):
                plan_id = plan["plan_id"]
                expected_failure_type = plan.get("expected_failure_type")
                expected_failure_code = plan.get("expected_failure_code")
                plan_run_dir = Path(tmp) / f"known_bad_{plan_id}"
                try:
                    run = run_known_bad_plan(task_dir, plan_run_dir, plan_id=plan_id, clean=True)
                    result = verify_run(run.run_dir)
                    failed_verifier_checks = [item.name for item in result.checks if not item.ok]
                    matched = (
                        expected_failure_type == "verifier_check"
                        and expected_failure_code in failed_verifier_checks
                        and not result.ok
                    )
                    known_bad_results.append(
                        {
                            "plan_id": plan_id,
                            "executed": True,
                            "expected_failure_type": expected_failure_type,
                            "expected_failure_code": expected_failure_code,
                            "failed_verifier_checks": failed_verifier_checks,
                            "tool_error_codes": _trace_tool_error_codes(run.run_dir),
                            "verifier_ok": result.ok,
                            "matched_expected_failure": matched,
                            "tool_calls": run.trace.counts()["tool_calls"],
                        }
                    )
                except Exception as exc:  # pragma: no cover - written into admission for agent debugging.
                    tool_error_codes = _trace_tool_error_codes(plan_run_dir)
                    matched = expected_failure_type == "tool_error" and expected_failure_code in tool_error_codes
                    known_bad_results.append(
                        {
                            "plan_id": plan_id,
                            "executed": plan_run_dir.exists(),
                            "expected_failure_type": expected_failure_type,
                            "expected_failure_code": expected_failure_code,
                            "failed_verifier_checks": [],
                            "tool_error_codes": tool_error_codes,
                            "verifier_ok": None,
                            "matched_expected_failure": matched,
                            "error": repr(exc),
                        }
                    )
    except Exception as exc:  # pragma: no cover - written into admission for agent debugging.
        known_bad_results.append({"plan_id": "<loader>", "executed": False, "error": repr(exc)})
    add_check(
        "known_bad_expected_failure_codes_match",
        bool(known_bad_results) and all(item.get("matched_expected_failure") for item in known_bad_results),
        {"plans": known_bad_results},
    )

    expected_artifacts = sorted(expectations["required_artifacts_read"])
    add_check("task_has_one_template_failure_mode", bool(task["template_id"]) and bool(task["failure_mode"]))
    add_check("visible_artifacts_cover_required_reads", expected_artifacts == sorted(artifact_names))

    admitted = all(item["ok"] for item in checks)
    payload = {
        "schema_version": "greenfield_lablongrun.admission.v0",
        "task_id": task["task_id"],
        "template_id": task["template_id"],
        "failure_mode": task["failure_mode"],
        "seed": task["seed"],
        "environment_seed": environment_seed,
        "difficulty": task["difficulty"],
        "projection": actual_projection_metadata,
        "schedule_refs": schedule_refs,
        "admitted": admitted,
        "expected_horizon": {
            "bin": horizon["bin"],
            "min_tool_calls": horizon["min_tool_calls"],
            "max_tool_calls": horizon["max_tool_calls"],
            "oracle_tool_calls": oracle_tool_calls,
        },
        "checks": checks,
    }
    write_json(task_dir / "admission.json", payload)
    return AdmissionResult(task_dir=task_dir, admitted=admitted, checks=checks, payload=payload)


def generate_nominal_task_bundle(out_dir: Path, *, clean: bool = False) -> Path:
    """Backward-compatible helper for the Phase 1 demo."""

    return generate_task(DEFAULT_TEMPLATE_ID, 1, DEFAULT_DIFFICULTY, out_dir, clean=clean).task_dir


def oracle_steps(parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    params = parameters or _resolve_parameters(_get_template(DEFAULT_TEMPLATE_ID), 1)
    steps = [
        {"tool": "get_protocol_artifact", "arguments": {"artifact_name": "protocol_note.md"}},
        {"tool": "get_protocol_artifact", "arguments": {"artifact_name": "plate_map.csv"}},
        {"tool": "get_protocol_artifact", "arguments": {"artifact_name": "reagent_inventory.csv"}},
        {"tool": "get_protocol_artifact", "arguments": {"artifact_name": "prior_run_log.jsonl"}},
        {"tool": "get_deck_state", "arguments": {}},
        {"tool": "get_labware_state", "arguments": {"labware_id": "culture_tube"}},
        {"tool": "get_labware_state", "arguments": {"labware_id": "diluent_reservoir"}},
        {"tool": "get_labware_state", "arguments": {"labware_id": "tiprack_1"}},
        {"tool": "pick_up_tip", "arguments": {"tip_ref": "tiprack_1:A1"}},
        {"tool": "aspirate", "arguments": {"well_ref": "diluent_reservoir:R1", "volume_ul": params["diluent_volume_ul"]}},
        {"tool": "dispense", "arguments": {"well_ref": "dilution_plate:A1", "volume_ul": params["diluent_volume_ul"]}},
        {"tool": "drop_tip", "arguments": {}},
        {"tool": "pick_up_tip", "arguments": {"tip_ref": "tiprack_1:A2"}},
        {"tool": "aspirate", "arguments": {"well_ref": "culture_tube:S1", "volume_ul": params["culture_volume_ul"]}},
        {"tool": "dispense", "arguments": {"well_ref": "dilution_plate:A1", "volume_ul": params["culture_volume_ul"]}},
        {
            "tool": "mix",
            "arguments": {
                "well_ref": "dilution_plate:A1",
                "repetitions": int(params["mix_repetitions"]),
                "volume_ul": params["mix_volume_ul"],
            },
        },
        {"tool": "aspirate", "arguments": {"well_ref": "dilution_plate:A1", "volume_ul": params["qc_transfer_volume_ul"]}},
        {"tool": "dispense", "arguments": {"well_ref": "qc_plate:B1", "volume_ul": params["qc_transfer_volume_ul"]}},
        {"tool": "drop_tip", "arguments": {}},
        {
            "tool": "wait",
            "arguments": {
                "seconds": params["wait_seconds"],
                "reason": "Allow QC plate liquid to settle before OD600 read.",
            },
        },
        {
            "tool": "read_absorbance",
            "arguments": {
                "well_ref": "qc_plate:B1",
                "wavelength_nm": int(params["wavelength_nm"]),
                "dilution_factor": params["dilution_factor"],
            },
        },
        {
            "tool": "submit_protocol_decision",
            "arguments": {
                "decision": params["expected_decision"],
                "evidence_readout_id": "$last_readout_id",
                "target_well_ref": "qc_plate:B1",
                "rationale": "Corrected OD600 is inside the protocol acceptance band."
                if params["expected_decision"] == "continue"
                else "Corrected OD600 is outside the protocol acceptance band.",
            },
        },
    ]
    if float(params.get("partial_dispense_remainder_ul", 0.0)) > 0:
        qc_dispense_index = next(
            index
            for index, step in enumerate(steps)
            if step["tool"] == "dispense" and step["arguments"].get("well_ref") == "qc_plate:B1"
        )
        steps.insert(qc_dispense_index + 1, {"tool": "get_labware_state", "arguments": {"labware_id": "qc_plate"}})
        steps.insert(
            qc_dispense_index + 2,
            {
                "tool": "dispense",
                "arguments": {
                    "well_ref": "qc_plate:B1",
                    "volume_ul": params["partial_dispense_remainder_ul"],
                },
            },
        )
    return steps


def known_bad_steps_wrong_decision(parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    params = parameters or _resolve_parameters(_get_template(DEFAULT_TEMPLATE_ID), 1)
    steps = oracle_steps(params)
    bad_decision = "hold" if params["expected_decision"] == "continue" else "continue"
    steps[-1] = {
        "tool": "submit_protocol_decision",
        "arguments": {
            "decision": bad_decision,
            "evidence_readout_id": "$last_readout_id",
            "target_well_ref": "qc_plate:B1",
            "rationale": "Intentionally wrong negative-control decision.",
        },
    }
    return steps


def known_bad_steps_nominal_overdraws_low_source(parameters: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"tool": "get_protocol_artifact", "arguments": {"artifact_name": "protocol_note.md"}},
        {"tool": "get_protocol_artifact", "arguments": {"artifact_name": "plate_map.csv"}},
        {"tool": "get_protocol_artifact", "arguments": {"artifact_name": "reagent_inventory.csv"}},
        {"tool": "get_protocol_artifact", "arguments": {"artifact_name": "prior_run_log.jsonl"}},
        {"tool": "get_deck_state", "arguments": {}},
        {"tool": "get_labware_state", "arguments": {"labware_id": "culture_tube"}},
        {"tool": "pick_up_tip", "arguments": {"tip_ref": "tiprack_1:A1"}},
        {
            "tool": "aspirate",
            "arguments": {"well_ref": "diluent_reservoir:R1", "volume_ul": parameters["nominal_diluent_volume_ul"]},
        },
        {
            "tool": "dispense",
            "arguments": {"well_ref": "dilution_plate:A1", "volume_ul": parameters["nominal_diluent_volume_ul"]},
        },
        {"tool": "drop_tip", "arguments": {}},
        {"tool": "pick_up_tip", "arguments": {"tip_ref": "tiprack_1:A2"}},
        {
            "tool": "aspirate",
            "arguments": {"well_ref": "culture_tube:S1", "volume_ul": parameters["nominal_culture_volume_ul"]},
        },
    ]


def known_bad_steps_contaminate_diluent_with_sample_tip(parameters: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"tool": "get_protocol_artifact", "arguments": {"artifact_name": "protocol_note.md"}},
        {"tool": "get_protocol_artifact", "arguments": {"artifact_name": "plate_map.csv"}},
        {"tool": "get_protocol_artifact", "arguments": {"artifact_name": "reagent_inventory.csv"}},
        {"tool": "get_protocol_artifact", "arguments": {"artifact_name": "prior_run_log.jsonl"}},
        {"tool": "get_deck_state", "arguments": {}},
        {"tool": "get_labware_state", "arguments": {"labware_id": "culture_tube"}},
        {"tool": "get_labware_state", "arguments": {"labware_id": "diluent_reservoir"}},
        {"tool": "pick_up_tip", "arguments": {"tip_ref": "tiprack_1:A1"}},
        {"tool": "aspirate", "arguments": {"well_ref": "culture_tube:S1", "volume_ul": parameters["culture_volume_ul"]}},
        {"tool": "dispense", "arguments": {"well_ref": "dilution_plate:A1", "volume_ul": parameters["culture_volume_ul"]}},
        {"tool": "aspirate", "arguments": {"well_ref": "diluent_reservoir:R1", "volume_ul": parameters["diluent_volume_ul"]}},
        {"tool": "dispense", "arguments": {"well_ref": "dilution_plate:A1", "volume_ul": parameters["diluent_volume_ul"]}},
        {
            "tool": "mix",
            "arguments": {
                "well_ref": "dilution_plate:A1",
                "repetitions": int(parameters["mix_repetitions"]),
                "volume_ul": parameters["mix_volume_ul"],
            },
        },
        {"tool": "aspirate", "arguments": {"well_ref": "dilution_plate:A1", "volume_ul": parameters["qc_transfer_volume_ul"]}},
        {"tool": "dispense", "arguments": {"well_ref": "qc_plate:B1", "volume_ul": parameters["qc_transfer_volume_ul"]}},
        {"tool": "drop_tip", "arguments": {}},
        {"tool": "wait", "arguments": {"seconds": parameters["wait_seconds"], "reason": "Settle before OD600 read."}},
        {
            "tool": "read_absorbance",
            "arguments": {
                "well_ref": "qc_plate:B1",
                "wavelength_nm": int(parameters["wavelength_nm"]),
                "dilution_factor": parameters["dilution_factor"],
            },
        },
        {
            "tool": "submit_protocol_decision",
            "arguments": {
                "decision": parameters["expected_decision"],
                "evidence_readout_id": "$last_readout_id",
                "target_well_ref": "qc_plate:B1",
                "rationale": "Ignores protected reagent cross-contact.",
            },
        },
    ]


def known_bad_steps_skip_reader_busy_wait(parameters: dict[str, Any]) -> list[dict[str, Any]]:
    steps = oracle_steps(parameters)
    for step in steps:
        if step["tool"] == "wait":
            step["arguments"] = {
                "seconds": parameters["reader_busy_bad_wait_seconds"],
                "reason": "Insufficient wait before reader-ready gate.",
            }
            break
    return steps


def known_bad_steps_cite_stale_readout(parameters: dict[str, Any]) -> list[dict[str, Any]]:
    steps = [
        step
        for step in oracle_steps(parameters)
        if step["tool"] != "read_absorbance"
    ]
    steps[-1] = {
        "tool": "submit_protocol_decision",
        "arguments": {
            "decision": parameters["expected_decision"],
            "evidence_readout_id": parameters["stale_readout_id"],
            "target_well_ref": "qc_plate:B1",
            "rationale": "Uses a prior readout instead of producing fresh evidence.",
        },
    }
    return steps


def known_bad_steps_ignore_partial_dispense(parameters: dict[str, Any]) -> list[dict[str, Any]]:
    steps = []
    for step in oracle_steps(parameters):
        if step["tool"] == "get_labware_state" and step["arguments"].get("labware_id") == "qc_plate":
            continue
        if (
            step["tool"] == "dispense"
            and step["arguments"].get("well_ref") == "qc_plate:B1"
            and step["arguments"].get("volume_ul") == parameters["partial_dispense_remainder_ul"]
        ):
            continue
        if step["tool"] == "drop_tip":
            previous = steps[-1] if steps else {}
            if previous.get("tool") == "dispense" and previous.get("arguments", {}).get("well_ref") == "qc_plate:B1":
                continue
        steps.append(step)
    return steps


def source_refs() -> dict[str, Any]:
    return read_json(SOURCE_REFS_PATH)


def _load_template_catalog() -> dict[str, Any]:
    catalog = read_json(TEMPLATE_CATALOG)
    templates = catalog.get("templates")
    if not isinstance(templates, list) or not templates:
        raise ValueError(f"Template catalog is empty or malformed: {TEMPLATE_CATALOG}")
    ids = [template["template_id"] for template in templates]
    duplicates = sorted({template_id for template_id in ids if ids.count(template_id) > 1})
    if duplicates:
        raise ValueError(f"Template catalog has duplicate template ids: {duplicates}")
    return catalog


def _get_template(template_id: str) -> dict[str, Any]:
    for template in _load_template_catalog()["templates"]:
        if template["template_id"] == template_id:
            return template
    raise ValueError(f"No LabLongRun-Wet template named {template_id!r}.")


def _resolve_parameters(template: dict[str, Any], seed: int) -> dict[str, Any]:
    rng = _rng(template["template_id"], seed)
    params = {name: _resolve_parameter_value(spec, rng) for name, spec in template["parameters"].items()}
    dilution_total = float(params["diluent_volume_ul"]) + float(params["culture_volume_ul"])
    params["dilution_factor"] = round(dilution_total / float(params["culture_volume_ul"]), 6)
    corrected = round(
        float(params["stock_corrected_od600"])
        * float(params["culture_volume_ul"])
        / dilution_total
        * float(params["dilution_factor"]),
        6,
    )
    params["expected_corrected_od600"] = corrected
    params["expected_decision"] = (
        "continue" if float(params["acceptance_min"]) <= corrected <= float(params["acceptance_max"]) else "hold"
    )
    params.setdefault("nominal_diluent_volume_ul", 100.0)
    params.setdefault("nominal_culture_volume_ul", 10.0)
    params.setdefault("stale_readout_id", "stale_readout_001")
    params.setdefault("reader_busy_bad_wait_seconds", max(1.0, float(params["wait_seconds"]) / 2.0))
    params.setdefault("partial_dispense_delivered_ul", float(params["qc_transfer_volume_ul"]))
    params["partial_dispense_remainder_ul"] = round(
        float(params["qc_transfer_volume_ul"]) - float(params["partial_dispense_delivered_ul"]),
        6,
    )
    return params


def _resolve_parameter_value(spec: Any, rng: random.Random) -> Any:
    if not isinstance(spec, dict):
        return spec
    if "value" in spec:
        return spec["value"]
    if "choices" in spec:
        choices = spec["choices"]
        if not choices:
            raise ValueError("Parameter choices must not be empty.")
        return rng.choice(choices)
    if "min" in spec and "max" in spec:
        precision = int(spec.get("precision", 6))
        if precision == 0:
            return float(rng.randint(int(spec["min"]), int(spec["max"])))
        return round(rng.uniform(float(spec["min"]), float(spec["max"])), precision)
    raise ValueError(f"Unsupported parameter spec: {spec}")


def _rng(template_id: str, seed: int) -> random.Random:
    digest = hashlib.sha256(f"{template_id}:{seed}".encode("utf-8")).hexdigest()
    return random.Random(int(digest[:16], 16))


def _render_context(template: dict[str, Any], parameters: dict[str, Any], seed: int, difficulty: str) -> dict[str, str]:
    context = {name: _format_value(value) for name, value in parameters.items()}
    context.update(
        {
            "template_id": template["template_id"],
            "seed": str(seed),
            "difficulty": difficulty,
            "failure_mode": template["lab_failure_mode"],
        }
    )
    return context


def _format_value(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _render_string(text: str, context: dict[str, str]) -> str:
    return Template(text).substitute(context)


def _write_visible_artifacts(
    visible_dir: Path,
    template: dict[str, Any],
    parameters: dict[str, Any],
    seed: int,
    difficulty: str,
) -> None:
    context = _render_context(template, parameters, seed, difficulty)
    for artifact_name, lines in template["visible_artifacts"].items():
        rendered = "\n".join(_render_string(line, context) for line in lines) + "\n"
        (visible_dir / artifact_name).write_text(rendered, encoding="utf-8")


def _verifier_expectations(
    template: dict[str, Any],
    parameters: dict[str, Any],
    artifact_names: list[str],
    difficulty: str,
) -> dict[str, Any]:
    requirements = {
        key: _resolve_requirement_value(value, parameters)
        for key, value in template.get("verifier_requirements", {}).items()
    }
    return {
        "template_id": template["template_id"],
        "failure_mode": template["lab_failure_mode"],
        "expected_decision": parameters["expected_decision"],
        "target_well_ref": "qc_plate:B1",
        "evidence_wavelength_nm": int(parameters["wavelength_nm"]),
        "corrected_od600_band": {
            "min": float(parameters["acceptance_min"]),
            "max": float(parameters["acceptance_max"]),
        },
        "expected_final_volumes_ul": _expected_final_volumes(parameters),
        "required_artifacts_read": artifact_names,
        "expected_horizon": template["difficulty_targets"][difficulty],
        "verifier_predicates": template["verifier_predicates"],
        **requirements,
    }


def _resolve_requirement_value(value: Any, parameters: dict[str, Any]) -> Any:
    if isinstance(value, str) and value.startswith("$"):
        return parameters[value[1:]]
    return value


def _expected_final_volumes(parameters: dict[str, Any]) -> dict[str, float]:
    return {
        "culture_tube:S1": round(float(parameters["source_volume_ul"]) - float(parameters["culture_volume_ul"]), 6),
        "diluent_reservoir:R1": round(
            float(parameters["diluent_start_volume_ul"]) - float(parameters["diluent_volume_ul"]),
            6,
        ),
        "dilution_plate:A1": round(
            float(parameters["diluent_volume_ul"])
            + float(parameters["culture_volume_ul"])
            - float(parameters["qc_transfer_volume_ul"]),
            6,
        ),
        "qc_plate:B1": round(float(parameters["qc_transfer_volume_ul"]), 6),
    }


def _known_bad_plans(template: dict[str, Any], parameters: dict[str, Any]) -> list[dict[str, Any]]:
    plans = []
    for strategy in template["known_bad_plan_strategy"]:
        steps_builder = {
            "wrong_decision": known_bad_steps_wrong_decision,
            "nominal_overdraws_low_source": known_bad_steps_nominal_overdraws_low_source,
            "contaminate_diluent_with_sample_tip": known_bad_steps_contaminate_diluent_with_sample_tip,
            "skip_reader_busy_wait": known_bad_steps_skip_reader_busy_wait,
            "cite_stale_readout": known_bad_steps_cite_stale_readout,
            "ignore_partial_dispense": known_bad_steps_ignore_partial_dispense,
        }.get(strategy)
        if steps_builder is None:
            raise ValueError(f"Unsupported known-bad plan strategy: {strategy}")
        expected_failure = _expected_failure_for_strategy(template, strategy)
        plans.append(
            {
                "plan_id": strategy,
                "strategy": strategy,
                "expected_failure_type": expected_failure["type"],
                "expected_failure_code": expected_failure["code"],
                "steps": steps_builder(parameters),
            }
        )
    return plans


def _task_projection_metadata(template: dict[str, Any]) -> dict[str, Any]:
    return {
        "projection_contract_ref": template["projection_contract_ref"],
        "domain_source_status": template["domain_source_status"],
        "stochastic_source_status": template["stochastic_source_status"],
        "attribution_labels": template["attribution_labels"],
    }


def _expected_failure_for_strategy(template: dict[str, Any], strategy: str) -> dict[str, str]:
    expected_failure_codes = template["expected_failure_codes"]
    expected = expected_failure_codes.get(strategy)
    if not isinstance(expected, dict):
        raise ValueError(f"Template {template['template_id']!r} has no expected failure code for {strategy!r}.")
    failure_type = expected.get("type")
    code = expected.get("code")
    if failure_type not in ALLOWED_FAILURE_TYPES or not isinstance(code, str) or not code:
        raise ValueError(f"Invalid expected failure code for {template['template_id']!r}/{strategy!r}: {expected}")
    return {"type": failure_type, "code": code}


def _deterministic_schedule(
    kind: str,
    environment_seed: int,
    template: dict[str, Any],
    parameters: dict[str, Any],
    difficulty: str,
) -> dict[str, Any]:
    if kind not in SCHEDULE_REFS:
        raise ValueError(f"Unsupported schedule kind: {kind}")
    policy = template[f"{kind}_schedule_policy"]
    mode = policy.get("mode")
    if mode == "empty_deterministic":
        events: list[dict[str, Any]] = []
    elif mode == "template_events":
        context = _render_context(template, parameters, environment_seed, difficulty)
        events = [_render_json_value(event, context) for event in policy.get("events", [])]
    else:
        raise ValueError(f"Unsupported {kind} schedule policy mode: {mode!r}")
    return {
        "schema_version": f"greenfield_lablongrun.{kind}_schedule.v0",
        "kind": kind,
        "template_id": template["template_id"],
        "environment_seed": environment_seed,
        "source_status": template["stochastic_source_status"],
        "policy": policy,
        "events": events,
    }


def _render_json_value(value: Any, context: dict[str, str]) -> Any:
    if isinstance(value, str):
        rendered = _render_string(value, context)
        try:
            if "." in rendered:
                return float(rendered)
            return int(rendered)
        except ValueError:
            return rendered
    if isinstance(value, list):
        return [_render_json_value(item, context) for item in value]
    if isinstance(value, dict):
        return {key: _render_json_value(item, context) for key, item in value.items()}
    return value


def _world_ref_path(ref: str) -> Path | None:
    path = Path(ref)
    if path.is_absolute() or ".." in path.parts or not ref.strip():
        return None
    return WORLD_DIR / path


def _schedule_admission_details(task_dir: Path, task: dict[str, Any], template: dict[str, Any], kind: str) -> dict[str, Any]:
    schedule_refs = task.get("schedule_refs") if isinstance(task.get("schedule_refs"), dict) else {}
    ref = schedule_refs.get(kind)
    path = task_dir / ref if isinstance(ref, str) else None
    exists = path is not None and path.is_file()
    actual = read_json(path) if exists and path is not None else None
    environment_seed = task.get("environment_seed")
    parameters = _resolve_parameters(template, int(task["seed"])) if isinstance(environment_seed, int) else {}
    expected = (
        _deterministic_schedule(kind, environment_seed, template, parameters, task["difficulty"])
        if isinstance(environment_seed, int)
        else None
    )
    return {
        "kind": kind,
        "ref": ref,
        "path": str(path) if path else None,
        "exists": exists,
        "deterministic": actual == expected,
        "empty": isinstance(actual, dict) and actual.get("events") == [],
        "environment_seed": environment_seed,
    }


def _trace_tool_error_codes(run_dir: Path) -> list[str]:
    path = run_dir / "tool_calls.jsonl"
    if not path.exists():
        return []
    return sorted(
        {
            record["error_code"]
            for record in _read_jsonl_records(path)
            if isinstance(record.get("error_code"), str) and record["error_code"]
        }
    )


def _read_jsonl_records(path: Path) -> list[dict[str, Any]]:
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def _visible_hidden_leaks(task_dir: Path) -> list[str]:
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((task_dir / "visible_artifacts").iterdir())
        if path.is_file()
    ).lower()
    return [token for token in HIDDEN_LEAK_TOKENS if token in text]


def _initial_state_physically_possible(task_dir: Path) -> bool:
    with state.connect(task_dir / "initial_state.sqlite") as conn:
        negative = conn.execute("SELECT 1 FROM wells WHERE volume_ul < 0 LIMIT 1").fetchone()
        dry_run = bool(state.get_metadata(conn, "dry_run", False))
        source = conn.execute(
            "SELECT volume_ul FROM wells WHERE labware_id = ? AND well_id = ?",
            ("culture_tube", "S1"),
        ).fetchone()
        return negative is None and dry_run and source is not None and float(source["volume_ul"]) > DEAD_VOLUME_UL
