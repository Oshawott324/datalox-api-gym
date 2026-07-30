#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
WORLD = ROOT / "worlds" / "science_elabftw_cromwell_v0"
V1 = WORLD / "world" / "v1"
ELABFTW_SOURCE = (
    ROOT
    / "api_gym"
    / "provider_components"
    / "elabftw"
    / "analysis_projection.py"
)
CROMWELL_SOURCE = (
    ROOT
    / "api_gym"
    / "provider_components"
    / "cromwell"
    / "analysis_projection.py"
)
ELABFTW_DESTINATION = V1 / "provider_elabftw.py"
CROMWELL_DESTINATION = V1 / "provider_cromwell.py"

WORLD_ID = "science_elabftw_cromwell_v0"
SOURCE_OWNED_WORLD_FILES = frozenset(
    {
        "world/v1/contract.py",
        "world/v1/dynamics.py",
        "world/v1/implementation.py",
        "world/v1/verifier.py",
    }
)
EXPECTED_WORLD_FILES = frozenset(
    {
        "README.md",
        "compatibility.json",
        "evidence/cromwell_workflow_abort_v1.json",
        "evidence/cromwell_workflow_failure_v1.json",
        "evidence/cromwell_workflow_success_v1.json",
        "evidence/elabftw_experiments_patch_complete_v1.json",
        *(
            f"family_contracts/{family}.json"
            for family in (
                "analysis_nominal_v1",
                "analysis_transient_visibility_v1",
                "analysis_existing_run_resume_v1",
                "analysis_failure_recovery_v1",
                "analysis_superseded_abort_v1",
                "analysis_stale_revision_v1",
            )
        ),
        "gate_config.json",
        "grounding_matrix.json",
        "projection_contract.md",
        "replay_script.json",
        "skills/SKILL.md",
        "source_refs.json",
        "task.json",
        "tests/trajectories/analysis.json",
        "world/manifest.json",
        "world/v1/construction.json",
        "world/v1/contract.py",
        "world/v1/dynamics.py",
        "world/v1/episodes.jsonl",
        "world/v1/implementation.py",
        "world/v1/provider_cromwell.py",
        "world/v1/provider_cromwell_facts.json",
        "world/v1/provider_cromwell_facts.py",
        "world/v1/provider_elabftw.py",
        "world/v1/provider_elabftw_facts.json",
        "world/v1/provider_elabftw_facts.py",
        "world/v1/roles.json",
        "world/v1/sources.json",
        "world/v1/tools.json",
        "world/v1/verifier.json",
        "world/v1/verifier.py",
    }
)
RESULT_TITLE = "Analysis-control qualification handoff"
RESULT_BODY = (
    "The captured Cromwell program qualified for evidence handoff. "
    "This record makes no biological or scientific inference."
)
COMMON_PUBLIC_REQUIREMENTS = (
    (
        "SCI-PUB-001",
        "Inspect the eLabFTW source before taking workflow action, and submit only "
        "workflow source and inputs from the revision observed by that read.",
    ),
    (
        "SCI-PUB-002",
        "Benchmark time changes only through clock.advance. Repeated polling "
        "without clock.advance neither progresses a workflow nor delivers a "
        "scheduled source revision.",
    ),
    (
        "SCI-PUB-003",
        "Accept only a current Cromwell workflow explicitly observed in terminal "
        "Succeeded status, then inspect both its successful outputs and its entire "
        "metadata response before result writeback.",
    ),
    (
        "SCI-PUB-004",
        "After inspecting the successful outputs and metadata, re-read the source "
        "immediately before creating or writing the result; use the current "
        "source_revision and source_content_digest from that re-read.",
    ),
    (
        "SCI-PUB-005",
        "outputs_digest is exactly 'sha256:' plus the lowercase SHA-256 hex digest "
        "of canonical JSON (sorted keys, compact separators) of the outputs object "
        "inside the body returned by cromwell.get_workflow_outputs.",
    ),
    (
        "SCI-PUB-006",
        "metadata_digest is exactly 'sha256:' plus the lowercase SHA-256 hex digest "
        "of canonical JSON (sorted keys, compact separators) of the entire body "
        "returned by cromwell.get_workflow_metadata.",
    ),
    (
        "SCI-PUB-007",
        "Create, patch, and read back exactly one eLabFTW result record, after the "
        "accepted workflow is observed Succeeded and its outputs and metadata are "
        "inspected.",
    ),
    (
        "SCI-PUB-008",
        "The result title is exactly 'Analysis-control qualification handoff' and "
        "the result body is exactly 'The captured Cromwell program qualified for "
        "evidence handoff. This record makes no biological or scientific "
        "inference.' Preserve this analysis-control/qualification evidence scope "
        "and make no biological or scientific inference.",
    ),
    (
        "SCI-PUB-009",
        "Result metadata contains exactly these eight keys and no others: "
        "handoff_kind, source_experiment_id, source_revision, "
        "source_content_digest, cromwell_workflow_id, "
        "cromwell_terminal_status, outputs_digest, metadata_digest. Set "
        "handoff_kind to 'analysis-control/qualification' and "
        "cromwell_terminal_status to 'Succeeded'; join every other value to the "
        "accepted workflow and the current source re-read.",
    ),
    (
        "SCI-PUB-010",
        "Create no unnecessary workflow submissions or result records, and do not "
        "abort or otherwise modify a workflow unless the family instruction "
        "explicitly requires it.",
    ),
)
TRANSIENT_PUBLIC_REQUIREMENT = (
    "SCI-PUB-TR-001",
    "For this transient-visibility task, make exactly one workflow submission and "
    "observe its status in this order: HTTP 404, then Submitted, then Succeeded. "
    "Call clock.advance between each of those three status observations; never "
    "resubmit after the 404 or Submitted observation.",
)
FAMILY_PUBLIC_REQUIREMENTS = {
    "analysis_transient_visibility_v1": TRANSIENT_PUBLIC_REQUIREMENT,
    "analysis_existing_run_resume_v1": (
        "SCI-PUB-ER-001",
        "For this existing-run resume task, inspect and resume the in-flight "
        "workflow referenced by the source, and make no duplicate workflow "
        "submission.",
    ),
    "analysis_failure_recovery_v1": (
        "SCI-PUB-FR-001",
        "For this failure-recovery task, explicitly observe the failed workflow "
        "in Failed status, then inspect both its logs and its entire metadata "
        "response, then re-read the corrected current source before making a new "
        "workflow submission.",
    ),
    "analysis_superseded_abort_v1": (
        "SCI-PUB-SA-001",
        "For this superseded-abort task, explicitly observe the workflow "
        "referenced by the source in Running status, then abort it, explicitly "
        "observe it in Aborted status, then submit the current source.",
    ),
    "analysis_stale_revision_v1": (
        "SCI-PUB-SR-001",
        "For this stale-recovery task, explicitly observe the older completed "
        "workflow in terminal Succeeded status, inspect its outputs and its entire "
        "metadata response, re-read the current source, then make exactly one "
        "current workflow submission and do not attach evidence from the stale "
        "workflow.",
    ),
}
FAMILIES = (
    "analysis_nominal_v1",
    "analysis_transient_visibility_v1",
    "analysis_existing_run_resume_v1",
    "analysis_failure_recovery_v1",
    "analysis_superseded_abort_v1",
    "analysis_stale_revision_v1",
)
FAILURE_CODES = [
    "analysis.source_inspected_before_action",
    "analysis.submissions_match_source",
    "analysis.no_unnecessary_duplicate_submission",
    "analysis.required_transient_observation",
    "analysis.current_terminal_success",
    "analysis.required_failure_recovery",
    "analysis.required_superseded_abort",
    "analysis.required_stale_recovery",
    "analysis.success_outputs_metadata_inspected",
    "analysis.result_record_lifecycle",
    "analysis.result_record_content_contract",
    "analysis.result_record_exact_join",
    "analysis.writeback_source_current",
    "analysis.cross_provider_ordering",
    "analysis.no_forbidden_collateral",
]
EMPTY_FAILURE_CODES = {
    "analysis_nominal_v1": [
        FAILURE_CODES[index] for index in (0, 4, 8, 9, 10, 11, 12, 13)
    ],
    "analysis_transient_visibility_v1": [
        FAILURE_CODES[index] for index in (0, 3, 4, 8, 9, 10, 11, 12, 13)
    ],
    "analysis_existing_run_resume_v1": [
        FAILURE_CODES[index] for index in (0, 4, 8, 9, 10, 11, 12, 13)
    ],
    "analysis_failure_recovery_v1": [
        FAILURE_CODES[index] for index in (0, 4, 5, 8, 9, 10, 11, 12, 13)
    ],
    "analysis_superseded_abort_v1": [
        FAILURE_CODES[index] for index in (0, 4, 6, 8, 9, 10, 11, 12, 13)
    ],
    "analysis_stale_revision_v1": [
        FAILURE_CODES[index] for index in (0, 4, 7, 8, 9, 10, 11, 12, 13)
    ],
}
KNOWN_BAD_FAILURE_CODES = {
    "analysis_nominal_v1": [
        "analysis.current_terminal_success",
        "analysis.success_outputs_metadata_inspected",
        "analysis.result_record_exact_join",
        "analysis.cross_provider_ordering",
    ],
    "analysis_transient_visibility_v1": [
        "analysis.no_unnecessary_duplicate_submission",
        "analysis.required_transient_observation",
        "analysis.no_forbidden_collateral",
    ],
    "analysis_existing_run_resume_v1": [
        "analysis.no_unnecessary_duplicate_submission",
        "analysis.result_record_exact_join",
        "analysis.no_forbidden_collateral",
    ],
    "analysis_failure_recovery_v1": [
        "analysis.current_terminal_success",
        "analysis.required_failure_recovery",
        "analysis.success_outputs_metadata_inspected",
        "analysis.result_record_exact_join",
        "analysis.writeback_source_current",
        "analysis.cross_provider_ordering",
    ],
    "analysis_superseded_abort_v1": [
        "analysis.required_superseded_abort",
        "analysis.result_record_exact_join",
        "analysis.no_forbidden_collateral",
    ],
    "analysis_stale_revision_v1": [
        "analysis.current_terminal_success",
        "analysis.required_stale_recovery",
        "analysis.result_record_exact_join",
        "analysis.writeback_source_current",
    ],
}
EXPECTED_AGENT_SUBMISSIONS = {
    "analysis_nominal_v1": 1,
    "analysis_transient_visibility_v1": 1,
    "analysis_existing_run_resume_v1": 0,
    "analysis_failure_recovery_v1": 2,
    "analysis_superseded_abort_v1": 1,
    "analysis_stale_revision_v1": 1,
}


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: Path, values: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(value, sort_keys=True, allow_nan=False) + "\n"
            for value in values
        ),
        encoding="utf-8",
    )


def write_python_facts(path: Path, value: dict[str, Any]) -> None:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    chunks = [payload[index : index + 88] for index in range(0, len(payload), 88)]
    source = (
        "from __future__ import annotations\n\n"
        "import json\n\n"
        "# Generated from hash-checked capture-derived facts. Do not edit.\n"
        "_FACTS_JSON = (\n"
        + "".join(f"    {chunk!r}\n" for chunk in chunks)
        + ")\n\n"
        "FACTS: dict[str, object] = json.loads(_FACTS_JSON)\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def mcp(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "surface": "mcp",
        "tool_name": tool_name,
        "arguments": deepcopy(arguments),
        "actor_role": "scientist_agent",
        "actor_id": "science-agent-001",
    }


def _revision(
    program: str,
    *,
    qualification_context: dict[str, Any],
    cromwell_facts: dict[str, Any],
    canonical_digest: Any,
) -> dict[str, Any]:
    selected = cromwell_facts["programs"][program]
    workflow_source = selected["workflow_source"]
    workflow_inputs = deepcopy(selected["workflow_inputs"])
    workflow_digest = canonical_digest(
        {
            "workflowInputs": workflow_inputs,
            "workflowSource": workflow_source,
        }
    )
    return {
        "program": program,
        "workflow_source": workflow_source,
        "workflow_inputs": workflow_inputs,
        "workflow_digest": workflow_digest,
        "qualification_context": deepcopy(qualification_context),
        "content_digest": canonical_digest(
            {
                "qualificationContext": qualification_context,
                "workflowInputs": workflow_inputs,
                "workflowSource": workflow_source,
            }
        ),
    }


def build_episodes(
    *,
    cromwell_facts: dict[str, Any],
    canonical_digest: Any,
    deterministic_experiment_id: Any,
    deterministic_workflow_id: Any,
) -> list[dict[str, Any]]:
    episodes: list[dict[str, Any]] = []
    initial_time = datetime.fromisoformat("2026-07-30T08:00:00+00:00")
    for seed in range(12):
        family = FAMILIES[seed // 2]
        source_id = 4100 + seed
        if family == "analysis_failure_recovery_v1":
            revision_programs = ("failure", "success")
            revision_event = {"after_seconds": 30, "revision": 2}
        elif family == "analysis_superseded_abort_v1":
            revision_programs = ("abort", "success")
            revision_event = {"after_seconds": 10, "revision": 2}
        elif family == "analysis_stale_revision_v1":
            revision_programs = ("success", "success")
            revision_event = None
        else:
            revision_programs = ("success",)
            revision_event = None
        revisions = {
            str(index + 1): _revision(
                program,
                qualification_context={
                    "qualification_batch": f"analysis-{seed:03d}-r{index + 1}",
                },
                cromwell_facts=cromwell_facts,
                canonical_digest=canonical_digest,
            )
            for index, program in enumerate(revision_programs)
        }

        workflows: dict[str, Any] = {}
        current_workflow_id = None
        next_ordinal = 0
        superseded_workflow_id = None
        if family in {
            "analysis_existing_run_resume_v1",
            "analysis_superseded_abort_v1",
            "analysis_stale_revision_v1",
        }:
            program = (
                "abort" if family == "analysis_superseded_abort_v1" else "success"
            )
            current_workflow_id = deterministic_workflow_id(
                seed=seed, ordinal=0
            )
            superseded_workflow_id = (
                current_workflow_id
                if family == "analysis_superseded_abort_v1"
                else None
            )
            revision = revisions["1"]
            workflows[current_workflow_id] = {
                "workflow_id": current_workflow_id,
                "ordinal": 0,
                "program": program,
                "workflow_source": revision["workflow_source"],
                "workflow_inputs": deepcopy(revision["workflow_inputs"]),
                "submitted_content_digest": revision["workflow_digest"],
                "source_experiment_id": source_id,
                "source_revision_at_submit": 1,
                "source_digest_at_submit": revision["content_digest"],
                "submitted_at": (
                    initial_time
                    - timedelta(
                        seconds=(
                            45
                            if family == "analysis_stale_revision_v1"
                            else 15
                        )
                    )
                ).isoformat(),
                "visible_after_seconds": 5,
                "running_after_seconds": 10,
                "terminal_after_seconds": 30 if program == "success" else None,
                "terminal_status": (
                    "Succeeded" if program == "success" else "Aborted"
                ),
                "abort_requested_at": None,
                "observed_statuses": [],
                "outputs_inspected": False,
                "logs_inspected": False,
                "metadata_inspected": False,
                "seeded_existing": True,
            }
            next_ordinal = 1

        expected_agent_submissions = EXPECTED_AGENT_SUBMISSIONS[family]
        current_revision = 2 if family == "analysis_stale_revision_v1" else 1
        result_id = deterministic_experiment_id(seed=seed, ordinal=50)
        task = _task(
            family=family,
            seed=seed,
            source_id=source_id,
        )
        metadata: dict[str, Any] = {
            "clock": initial_time.isoformat(),
            "grounding": {
                "elabftw_behavior": "G2_LOCAL_EXECUTED",
                "cromwell_behavior": "G2_LOCAL_EXECUTED",
                "logical_schedule": "G0_BENCHMARK_DEFINED",
                "scientific_job_meaning": "G0_BENCHMARK_DEFINED",
            },
        }
        if revision_event is not None:
            metadata["revision_event"] = revision_event
        episodes.append(
            {
                "id": f"science-analysis-{seed:03d}",
                "family_id": family,
                "seed": seed,
                "metadata": metadata,
                "state": {
                    "source": {
                        "experiment_id": source_id,
                        "current_revision": current_revision,
                        "current_workflow_id": current_workflow_id,
                        "revisions": revisions,
                        "created_at": initial_time.isoformat(),
                        "modified_at": initial_time.isoformat(),
                    },
                    "elabftw": {
                        "provider_version": "5.6.10",
                        "next_result_id": result_id,
                        "result_records": {},
                    },
                    "cromwell": {
                        "provider_version": "92",
                        "next_ordinal": next_ordinal,
                        "workflows": workflows,
                    },
                    "scenario": {
                        "seed": seed,
                        "family_id": family,
                        "expected_agent_submission_count": (
                            expected_agent_submissions
                        ),
                        "expected_total_workflow_count": (
                            expected_agent_submissions + len(workflows)
                        ),
                        "superseded_workflow_id": superseded_workflow_id,
                    },
                    "facts": {"result_record_id": None},
                },
                "task": task,
            }
        )
    return episodes


def _task(*, family: str, seed: int, source_id: int) -> dict[str, Any]:
    family_direction = {
        "analysis_nominal_v1": (
            "Submit the current source once and complete the successful handoff."
        ),
        "analysis_transient_visibility_v1": (
            "Follow the transient-visibility requirement SCI-PUB-TR-001."
        ),
        "analysis_existing_run_resume_v1": (
            "The source references an in-flight workflow. Resume it without a "
            "duplicate submission."
        ),
        "analysis_failure_recovery_v1": (
            "Diagnose the captured failed run from logs and metadata, re-read the "
            "corrected source revision, then run the current success program."
        ),
        "analysis_superseded_abort_v1": (
            "When the source revision supersedes its running workflow, abort it, "
            "observe Aborted, then run the current success program."
        ),
        "analysis_stale_revision_v1": (
            "The source references a completed workflow from an older qualification "
            "revision. Inspect its status, outputs, and metadata, re-read the current "
            "source, then submit one current workflow instead of attaching stale evidence."
        ),
    }[family]
    requirement_ids = [item[0] for item in COMMON_PUBLIC_REQUIREMENTS]
    family_requirement = FAMILY_PUBLIC_REQUIREMENTS.get(family)
    if family_requirement is not None:
        requirement_ids.append(family_requirement[0])
    instructions = (
        f"Inspect eLabFTW source experiment {source_id}. {family_direction} "
        "Satisfy every applicable public requirement listed in success_criteria: "
        + ", ".join(requirement_ids)
        + "."
    )
    success_criteria = [
        f"[{requirement_id}] {requirement}"
        for requirement_id, requirement in COMMON_PUBLIC_REQUIREMENTS
    ]
    if family_requirement is not None:
        requirement_id, requirement = family_requirement
        success_criteria.append(f"[{requirement_id}] {requirement}")
    return {
        "task_id": f"science-analysis-{seed:03d}",
        "title": "Complete an analysis-control qualification handoff",
        "instructions": instructions,
        "success_criteria": success_criteria,
    }


def _source_get(item: dict[str, Any]) -> dict[str, Any]:
    return mcp(
        "elabftw.get_experiment",
        {"experiment_id": item["state"]["source"]["experiment_id"]},
    )


def _submit(
    revision: dict[str, Any],
) -> dict[str, Any]:
    return mcp(
        "cromwell.submit_workflow",
        {
            "workflowSource": revision["workflow_source"],
            "workflowInputs": revision["workflow_inputs"],
        },
    )


def _poll_new_to_success(workflow_id: str) -> list[dict[str, Any]]:
    return [
        mcp("cromwell.get_workflow_status", {"workflow_id": workflow_id}),
        mcp("clock.advance", {"seconds": 5}),
        mcp("cromwell.get_workflow_status", {"workflow_id": workflow_id}),
        mcp("clock.advance", {"seconds": 5}),
        mcp("cromwell.get_workflow_status", {"workflow_id": workflow_id}),
        mcp("clock.advance", {"seconds": 20}),
        mcp("cromwell.get_workflow_status", {"workflow_id": workflow_id}),
    ]


def _success_evidence(workflow_id: str) -> list[dict[str, Any]]:
    return [
        mcp("cromwell.get_workflow_outputs", {"workflow_id": workflow_id}),
        mcp("cromwell.get_workflow_metadata", {"workflow_id": workflow_id}),
    ]


def _handoff_metadata(
    *,
    item: dict[str, Any],
    revision: int,
    workflow_id: str,
    cromwell_facts: dict[str, Any],
    canonical_digest: Any,
) -> dict[str, Any]:
    source = item["state"]["source"]
    selected = source["revisions"][str(revision)]
    from api_gym.provider_components.cromwell.analysis_projection import (
        render_metadata,
        render_outputs,
    )

    outputs = render_outputs(cromwell_facts, "success", workflow_id)["outputs"]
    metadata = render_metadata(
        cromwell_facts,
        "success",
        workflow_id,
        projected_timing=_success_projection_timing(item, revision),
    )
    return {
        "cromwell_terminal_status": "Succeeded",
        "cromwell_workflow_id": workflow_id,
        "handoff_kind": "analysis-control/qualification",
        "metadata_digest": canonical_digest(metadata),
        "outputs_digest": canonical_digest(outputs),
        "source_content_digest": selected["content_digest"],
        "source_experiment_id": source["experiment_id"],
        "source_revision": revision,
    }


def _success_projection_timing(
    item: dict[str, Any],
    revision: int,
) -> dict[str, str]:
    initial = datetime.fromisoformat(str(item["metadata"]["clock"]))
    family = str(item["family_id"])
    source = item["state"]["source"]
    if family == "analysis_existing_run_resume_v1":
        workflow_id = source["current_workflow_id"]
        submitted = datetime.fromisoformat(
            str(item["state"]["cromwell"]["workflows"][workflow_id]["submitted_at"])
        )
    elif family == "analysis_failure_recovery_v1" and revision == 2:
        submitted = initial + timedelta(seconds=30)
    elif family == "analysis_superseded_abort_v1" and revision == 2:
        submitted = initial + timedelta(seconds=15)
    else:
        submitted = initial
    return {
        "submitted_at": submitted.isoformat(),
        "started_at": (submitted + timedelta(seconds=10)).isoformat(),
        "ended_at": (submitted + timedelta(seconds=30)).isoformat(),
    }


def _handoff_steps(
    *,
    item: dict[str, Any],
    revision: int,
    workflow_id: str,
    cromwell_facts: dict[str, Any],
    canonical_digest: Any,
    include_source_reread: bool = True,
) -> list[dict[str, Any]]:
    result_id = item["state"]["elabftw"]["next_result_id"]
    metadata = _handoff_metadata(
        item=item,
        revision=revision,
        workflow_id=workflow_id,
        cromwell_facts=cromwell_facts,
        canonical_digest=canonical_digest,
    )
    steps = [_source_get(item)] if include_source_reread else []
    steps.extend(
        [
            mcp("elabftw.create_experiment", {}),
            mcp(
                "elabftw.patch_experiment",
                {
                    "experiment_id": result_id,
                    "title": RESULT_TITLE,
                    "body": RESULT_BODY,
                    "metadata": json.dumps(
                        metadata,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                },
            ),
            mcp(
                "elabftw.get_experiment",
                {"experiment_id": result_id},
            ),
        ]
    )
    return steps


def reference_steps(
    item: dict[str, Any],
    *,
    cromwell_facts: dict[str, Any],
    canonical_digest: Any,
    deterministic_workflow_id: Any,
    alternative_failure_order: bool = False,
) -> list[dict[str, Any]]:
    seed = int(item["seed"])
    family = item["family_id"]
    source = item["state"]["source"]
    revisions = source["revisions"]
    steps = [_source_get(item)]

    if family == "analysis_existing_run_resume_v1":
        workflow_id = source["current_workflow_id"]
        steps.extend(
            [
                mcp(
                    "cromwell.get_workflow_status",
                    {"workflow_id": workflow_id},
                ),
                mcp("clock.advance", {"seconds": 15}),
                mcp(
                    "cromwell.get_workflow_status",
                    {"workflow_id": workflow_id},
                ),
                *_success_evidence(workflow_id),
                *_handoff_steps(
                    item=item,
                    revision=1,
                    workflow_id=workflow_id,
                    cromwell_facts=cromwell_facts,
                    canonical_digest=canonical_digest,
                ),
            ]
        )
        return steps

    if family == "analysis_failure_recovery_v1":
        failed_id = deterministic_workflow_id(seed=seed, ordinal=0)
        success_id = deterministic_workflow_id(seed=seed, ordinal=1)
        diagnostics = [
            mcp("cromwell.get_workflow_logs", {"workflow_id": failed_id}),
            mcp("cromwell.get_workflow_metadata", {"workflow_id": failed_id}),
        ]
        if alternative_failure_order:
            diagnostics.reverse()
        steps.extend(
            [
                _submit(revisions["1"]),
                mcp("clock.advance", {"seconds": 30}),
                mcp(
                    "cromwell.get_workflow_status",
                    {"workflow_id": failed_id},
                ),
                *diagnostics,
                _source_get(item),
                _submit(revisions["2"]),
                *_poll_new_to_success(success_id),
                *_success_evidence(success_id),
                *_handoff_steps(
                    item=item,
                    revision=2,
                    workflow_id=success_id,
                    cromwell_facts=cromwell_facts,
                    canonical_digest=canonical_digest,
                ),
            ]
        )
        return steps

    if family == "analysis_superseded_abort_v1":
        stale_id = source["current_workflow_id"]
        success_id = deterministic_workflow_id(seed=seed, ordinal=1)
        steps.extend(
            [
                mcp("cromwell.get_workflow_status", {"workflow_id": stale_id}),
                mcp("clock.advance", {"seconds": 10}),
                _source_get(item),
                mcp("cromwell.abort_workflow", {"workflow_id": stale_id}),
                mcp("clock.advance", {"seconds": 5}),
                mcp("cromwell.get_workflow_status", {"workflow_id": stale_id}),
                _submit(revisions["2"]),
                *_poll_new_to_success(success_id),
                *_success_evidence(success_id),
                *_handoff_steps(
                    item=item,
                    revision=2,
                    workflow_id=success_id,
                    cromwell_facts=cromwell_facts,
                    canonical_digest=canonical_digest,
                ),
            ]
        )
        return steps

    if family == "analysis_stale_revision_v1":
        stale_id = source["current_workflow_id"]
        success_id = deterministic_workflow_id(seed=seed, ordinal=1)
        steps.extend(
            [
                mcp(
                    "cromwell.get_workflow_status",
                    {"workflow_id": stale_id},
                ),
                *_success_evidence(stale_id),
                _source_get(item),
                _submit(revisions["2"]),
                *_poll_new_to_success(success_id),
                *_success_evidence(success_id),
                *_handoff_steps(
                    item=item,
                    revision=2,
                    workflow_id=success_id,
                    cromwell_facts=cromwell_facts,
                    canonical_digest=canonical_digest,
                ),
            ]
        )
        return steps

    first_id = deterministic_workflow_id(seed=seed, ordinal=0)
    steps.extend([_submit(revisions["1"]), *_poll_new_to_success(first_id)])
    steps.extend(_success_evidence(first_id))
    steps.extend(
        _handoff_steps(
            item=item,
            revision=1,
            workflow_id=first_id,
            cromwell_facts=cromwell_facts,
            canonical_digest=canonical_digest,
        )
    )
    return steps


def build_trajectories(
    episodes: list[dict[str, Any]],
    *,
    cromwell_facts: dict[str, Any],
    canonical_digest: Any,
    deterministic_workflow_id: Any,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in episodes:
        rows.append(
            {
                "id": f"reference-{item['id']}",
                "kind": "reference",
                "family_id": item["family_id"],
                "episode_id": item["id"],
                "steps": reference_steps(
                    item,
                    cromwell_facts=cromwell_facts,
                    canonical_digest=canonical_digest,
                    deterministic_workflow_id=deterministic_workflow_id,
                ),
                "expected": {"passed": True, "failure_codes": []},
            }
        )
    alternative = episodes[7]
    rows.append(
        {
            "id": "alternative-failure-recovery",
            "kind": "reference",
            "family_id": alternative["family_id"],
            "episode_id": alternative["id"],
            "steps": reference_steps(
                alternative,
                cromwell_facts=cromwell_facts,
                canonical_digest=canonical_digest,
                deterministic_workflow_id=deterministic_workflow_id,
                alternative_failure_order=True,
            ),
            "expected": {"passed": True, "failure_codes": []},
        }
    )

    first_by_family = {
        family: next(item for item in episodes if item["family_id"] == family)
        for family in FAMILIES
    }
    for family, item in first_by_family.items():
        rows.append(
            {
                "id": f"negative-empty-{family}",
                "kind": "negative",
                "family_id": family,
                "episode_id": item["id"],
                "steps": [],
                "expected": {
                    "passed": False,
                    "failure_codes": EMPTY_FAILURE_CODES[family],
                },
            }
        )

    mutants = _mutant_steps(
        first_by_family,
        cromwell_facts=cromwell_facts,
        canonical_digest=canonical_digest,
        deterministic_workflow_id=deterministic_workflow_id,
    )
    for family, steps in mutants.items():
        item = first_by_family[family]
        rows.append(
            {
                "id": f"negative-mutant-{family}",
                "kind": "negative",
                "family_id": family,
                "episode_id": item["id"],
                "steps": steps,
                "expected": {
                    "passed": False,
                    "failure_codes": KNOWN_BAD_FAILURE_CODES[family],
                },
            }
        )

    nominal = episodes[0]
    resume = episodes[4]
    nominal_revision = nominal["state"]["source"]["revisions"]["1"]
    resume_workflow = resume["state"]["source"]["current_workflow_id"]
    rows.extend(
        [
            {
                "id": "parity-elabftw-get-source",
                "kind": "parity",
                "episode_id": nominal["id"],
                "http_step": {
                    "surface": "http",
                    "method": "GET",
                    "path": (
                        f"/api/v2/experiments/"
                        f"{nominal['state']['source']['experiment_id']}"
                    ),
                    "query": {},
                    "body": None,
                    "actor_role": "scientist_agent",
                    "actor_id": "science-http-001",
                },
                "mcp_step": _source_get(nominal),
                "expected": {"matched": True},
            },
            {
                "id": "parity-cromwell-running-status",
                "kind": "parity",
                "episode_id": resume["id"],
                "http_step": {
                    "surface": "http",
                    "method": "GET",
                    "path": f"/api/workflows/v1/{resume_workflow}/status",
                    "query": {},
                    "body": None,
                    "actor_role": "scientist_agent",
                    "actor_id": "science-http-002",
                },
                "mcp_step": mcp(
                    "cromwell.get_workflow_status",
                    {"workflow_id": resume_workflow},
                ),
                "expected": {"matched": True},
            },
            {
                "id": "parity-cromwell-submit",
                "kind": "parity",
                "episode_id": nominal["id"],
                "http_step": {
                    "surface": "http",
                    "method": "POST",
                    "path": "/api/workflows/v1",
                    "query": {},
                    "body": {
                        "workflowSource": nominal_revision["workflow_source"],
                        "workflowInputs": nominal_revision["workflow_inputs"],
                    },
                    "actor_role": "scientist_agent",
                    "actor_id": "science-http-003",
                },
                "mcp_step": _submit(nominal_revision),
                "expected": {"matched": True},
            },
        ]
    )
    return rows


def _mutant_steps(
    first_by_family: dict[str, dict[str, Any]],
    *,
    cromwell_facts: dict[str, Any],
    canonical_digest: Any,
    deterministic_workflow_id: Any,
) -> dict[str, list[dict[str, Any]]]:
    from api_gym.provider_components.cromwell.analysis_projection import (
        render_metadata,
        render_outputs,
    )

    nominal = first_by_family["analysis_nominal_v1"]
    nominal_id = deterministic_workflow_id(seed=nominal["seed"], ordinal=0)
    premature = [
        _source_get(nominal),
        _submit(nominal["state"]["source"]["revisions"]["1"]),
        *_handoff_steps(
            item=nominal,
            revision=1,
            workflow_id=nominal_id,
            cromwell_facts=cromwell_facts,
            canonical_digest=canonical_digest,
        ),
    ]

    transient = first_by_family["analysis_transient_visibility_v1"]
    transient_reference = reference_steps(
        transient,
        cromwell_facts=cromwell_facts,
        canonical_digest=canonical_digest,
        deterministic_workflow_id=deterministic_workflow_id,
    )
    first_status = next(
        index
        for index, step in enumerate(transient_reference)
        if step["tool_name"] == "cromwell.get_workflow_status"
    )
    transient_duplicate = (
        transient_reference[: first_status + 1]
        + [_submit(transient["state"]["source"]["revisions"]["1"])]
        + transient_reference[first_status + 1 :]
    )

    resume = first_by_family["analysis_existing_run_resume_v1"]
    resume_new_id = deterministic_workflow_id(seed=resume["seed"], ordinal=1)
    resume_duplicate = [
        _source_get(resume),
        _submit(resume["state"]["source"]["revisions"]["1"]),
        *_poll_new_to_success(resume_new_id),
        *_success_evidence(resume_new_id),
        *_handoff_steps(
            item=resume,
            revision=1,
            workflow_id=resume_new_id,
            cromwell_facts=cromwell_facts,
            canonical_digest=canonical_digest,
        ),
    ]

    failure = first_by_family["analysis_failure_recovery_v1"]
    failed_id = deterministic_workflow_id(seed=failure["seed"], ordinal=0)
    source = failure["state"]["source"]
    failed_revision = source["revisions"]["1"]
    failed_metadata = {
        "cromwell_terminal_status": "Succeeded",
        "cromwell_workflow_id": failed_id,
        "handoff_kind": "analysis-control/qualification",
        "metadata_digest": canonical_digest(
            render_metadata(
                cromwell_facts,
                "failure",
                failed_id,
                projected_timing=_success_projection_timing(failure, 1),
            )
        ),
        "outputs_digest": canonical_digest(
            render_outputs(cromwell_facts, "failure", failed_id)["outputs"]
        ),
        "source_content_digest": failed_revision["content_digest"],
        "source_experiment_id": source["experiment_id"],
        "source_revision": 1,
    }
    result_id = failure["state"]["elabftw"]["next_result_id"]
    failure_as_success = [
        _source_get(failure),
        _submit(failure["state"]["source"]["revisions"]["1"]),
        mcp("clock.advance", {"seconds": 30}),
        mcp("cromwell.get_workflow_status", {"workflow_id": failed_id}),
        mcp("elabftw.create_experiment", {}),
        mcp(
            "elabftw.patch_experiment",
            {
                "experiment_id": result_id,
                "title": RESULT_TITLE,
                "body": RESULT_BODY,
                "metadata": json.dumps(
                    failed_metadata,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            },
        ),
        mcp("elabftw.get_experiment", {"experiment_id": result_id}),
    ]

    superseded = first_by_family["analysis_superseded_abort_v1"]
    stale_id = superseded["state"]["source"]["current_workflow_id"]
    superseded_success_id = deterministic_workflow_id(
        seed=superseded["seed"], ordinal=1
    )
    no_abort = [
        _source_get(superseded),
        mcp("cromwell.get_workflow_status", {"workflow_id": stale_id}),
        mcp("clock.advance", {"seconds": 10}),
        _source_get(superseded),
        _submit(superseded["state"]["source"]["revisions"]["2"]),
        *_poll_new_to_success(superseded_success_id),
        *_success_evidence(superseded_success_id),
        *_handoff_steps(
            item=superseded,
            revision=2,
            workflow_id=superseded_success_id,
            cromwell_facts=cromwell_facts,
            canonical_digest=canonical_digest,
        ),
    ]

    stale = first_by_family["analysis_stale_revision_v1"]
    old_id = stale["state"]["source"]["current_workflow_id"]
    stale_attachment = [
        _source_get(stale),
        mcp("cromwell.get_workflow_status", {"workflow_id": old_id}),
        *_success_evidence(old_id),
        _source_get(stale),
        *_handoff_steps(
            item=stale,
            revision=1,
            workflow_id=old_id,
            cromwell_facts=cromwell_facts,
            canonical_digest=canonical_digest,
            include_source_reread=False,
        ),
    ]
    return {
        "analysis_nominal_v1": premature,
        "analysis_transient_visibility_v1": transient_duplicate,
        "analysis_existing_run_resume_v1": resume_duplicate,
        "analysis_failure_recovery_v1": failure_as_success,
        "analysis_superseded_abort_v1": no_abort,
        "analysis_stale_revision_v1": stale_attachment,
    }


def _family_contract(family: str) -> dict[str, Any]:
    mutant = {
        "analysis_nominal_v1": "premature_success_writeback",
        "analysis_transient_visibility_v1": "duplicate_submit_after_transient_404",
        "analysis_existing_run_resume_v1": "duplicate_submit_instead_of_resume",
        "analysis_failure_recovery_v1": "failed_treated_as_success_without_diagnosis",
        "analysis_superseded_abort_v1": "superseded_workflow_not_aborted",
        "analysis_stale_revision_v1": "stale_revision_attached",
    }[family]
    return {
        "schema_version": "api_gym.science_family_contract.v1",
        "family_id": family,
        "scientific_scope": "analysis-control/qualification evidence handoff",
        "grounding": {
            "provider_operations": "G2_LOCAL_EXECUTED",
            "logical_timing_and_cross_provider_rules": "G0_BENCHMARK_DEFINED",
        },
        "initial_state_contract": {
            "source_experiment_count": 1,
            "result_experiment_count": 0,
        },
        "obligations": [
            {"id": code, "failure_code": code, "type": "implementation_check"}
            for code in FAILURE_CODES
        ],
        "valid_alternatives": (
            ["failure_logs_and_metadata_may_be_inspected_in_either_order"]
            if family == "analysis_failure_recovery_v1"
            else []
        ),
        "mutant_families": [mutant],
        "admission": {
            "empty_failure_codes": EMPTY_FAILURE_CODES[family],
            "known_bad_failure_codes": KNOWN_BAD_FAILURE_CODES[family],
        },
    }


def _configure_world_root(world_root: Path) -> None:
    global WORLD, V1, ELABFTW_DESTINATION, CROMWELL_DESTINATION
    WORLD = world_root
    V1 = WORLD / "world" / "v1"
    ELABFTW_DESTINATION = V1 / "provider_elabftw.py"
    CROMWELL_DESTINATION = V1 / "provider_cromwell.py"


def build(world_root: Path = WORLD) -> None:
    _configure_world_root(world_root)
    sys.path.insert(0, str(ROOT))
    from api_gym.provider_components.cromwell.analysis_projection import (
        build_capture_facts as build_cromwell_facts,
    )
    from api_gym.provider_components.cromwell.analysis_projection import (
        canonical_digest,
        deterministic_workflow_id,
    )
    from api_gym.provider_components.elabftw.analysis_projection import (
        build_capture_facts as build_elabftw_facts,
    )
    from api_gym.provider_components.elabftw.analysis_projection import (
        deterministic_experiment_id,
    )

    elabftw_facts = build_elabftw_facts()
    cromwell_facts = build_cromwell_facts()
    episodes = build_episodes(
        cromwell_facts=cromwell_facts,
        canonical_digest=canonical_digest,
        deterministic_experiment_id=deterministic_experiment_id,
        deterministic_workflow_id=deterministic_workflow_id,
    )
    trajectories = build_trajectories(
        episodes,
        cromwell_facts=cromwell_facts,
        canonical_digest=canonical_digest,
        deterministic_workflow_id=deterministic_workflow_id,
    )

    V1.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ELABFTW_SOURCE, ELABFTW_DESTINATION)
    shutil.copy2(CROMWELL_SOURCE, CROMWELL_DESTINATION)
    write_json(V1 / "provider_elabftw_facts.json", elabftw_facts)
    write_json(V1 / "provider_cromwell_facts.json", cromwell_facts)
    write_python_facts(V1 / "provider_elabftw_facts.py", elabftw_facts)
    write_python_facts(V1 / "provider_cromwell_facts.py", cromwell_facts)
    write_jsonl(V1 / "episodes.jsonl", episodes)

    from worlds.science_elabftw_cromwell_v0.world.v1.contract import TOOLS

    write_json(V1 / "tools.json", {"tools": list(TOOLS)})
    write_json(
        V1 / "roles.json",
        {
            "roles": [
                {
                    "id": "scientist_agent",
                    "description": (
                        "Executes a bounded analysis-control and evidence-handoff "
                        "workflow."
                    ),
                }
            ]
        },
    )
    write_json(
        V1 / "verifier.json",
        {
            "schema_version": "science_elabftw_cromwell_verifier_v1",
            "assertions": [
                {"type": "implementation_check", "failure_code": code}
                for code in FAILURE_CODES
            ],
            "semantic_rubrics": [],
            "scalar_reward_owned_here": False,
        },
    )
    write_json(
        V1 / "sources.json",
        {
            "sources": [
                {
                    "id": "elabftw_complete_capture",
                    "kind": "authorized_local_fixture_capture",
                    "grounding_level": "G2_LOCAL_EXECUTED",
                    "locator": (
                        "evidence/elabftw_experiments_patch_complete_v1.json"
                    ),
                    "derivation": (
                        "eLabFTW 5.6.10 create/list/get/PATCH status, request, "
                        "and response shapes derived from the checked complete "
                        "case. List is grounded but intentionally unexposed."
                    ),
                    "supports": [
                        "operation:elabftw.get_experiment",
                        "operation:elabftw.create_experiment",
                        "operation:elabftw.patch_experiment",
                        "provider_behavior:elabftw.list_experiments",
                    ],
                },
                {
                    "id": "cromwell_complete_captures",
                    "kind": "authorized_local_fixture_captures",
                    "grounding_level": "G2_LOCAL_EXECUTED",
                    "locator": (
                        "evidence/cromwell_workflow_success_v1.json; "
                        "evidence/cromwell_workflow_failure_v1.json; "
                        "evidence/cromwell_workflow_abort_v1.json"
                    ),
                    "derivation": (
                        "Cromwell 92 submit, status, outputs, logs, metadata, "
                        "and abort shapes derived from three checked cases."
                    ),
                    "supports": [
                        "operation:cromwell.submit_workflow",
                        "operation:cromwell.get_workflow_status",
                        "operation:cromwell.get_workflow_outputs",
                        "operation:cromwell.get_workflow_logs",
                        "operation:cromwell.get_workflow_metadata",
                        "operation:cromwell.abort_workflow",
                    ],
                },
                {
                    "id": "analysis_projection_contract",
                    "kind": "benchmark_projection",
                    "grounding_level": "G0_BENCHMARK_DEFINED",
                    "locator": "projection_contract.md",
                    "derivation": (
                        "Defines compressed logical timing, source revisions, "
                        "joins, qualification meaning, and family obligations."
                    ),
                    "supports": [
                        "dynamics:logical_time",
                        "dynamics:source_revision",
                        "workflow:analysis_control_handoff",
                    ],
                },
            ],
            "grounding_gaps": [
                {
                    "operation_family": "production_provider_equivalence",
                    "status": "unsupported",
                    "reason": (
                        "The checked cases are disposable local references and "
                        "do not establish production or reset equivalence."
                    ),
                },
                {
                    "operation_family": "arbitrary_cromwell_workflow_logic",
                    "status": "unsupported",
                    "reason": (
                        "Only the exact success, failure, and abort WDL/input "
                        "families are executable."
                    ),
                },
                {
                    "operation_family": "biological_analysis",
                    "status": "unsupported",
                    "reason": (
                        "The captured WDL programs qualify analysis-control "
                        "handoff behavior and perform no biological inference."
                    ),
                },
            ],
        },
    )
    write_json(
        V1 / "construction.json",
        {
            "schema_version": "datalox_science_world_construction_v1",
            "world_id": WORLD_ID,
            "episode_count": len(episodes),
            "family_ids": list(FAMILIES),
            "provider_projects": ["eLabFTW", "Cromwell"],
            "network_access_required": False,
            "hardware_execution_allowed": False,
            "scalar_reward_owned_here": False,
            "verifier_complexity": {
                "state_loads": 1,
                "event_passes": 1,
                "assertion_count": len(FAILURE_CODES),
            },
            "provider_source_sha256": {
                "elabftw": (
                    "sha256:"
                    + hashlib.sha256(ELABFTW_SOURCE.read_bytes()).hexdigest()
                ),
                "cromwell": (
                    "sha256:"
                    + hashlib.sha256(CROMWELL_SOURCE.read_bytes()).hexdigest()
                ),
            },
        },
    )
    write_json(
        WORLD / "tests" / "trajectories" / "analysis.json",
        {"trajectories": trajectories},
    )
    for family in FAMILIES:
        write_json(
            WORLD / "family_contracts" / f"{family}.json",
            _family_contract(family),
        )
    _write_evidence(elabftw_facts, cromwell_facts)
    _write_world_documents(episodes)

    from datalox_gated_runtime.world_v1.bundle import compute_bundle_hashes

    write_json(
        WORLD / "world" / "manifest.json",
        {
            "schema_version": "datalox_world_bundle_v1",
            "world_id": WORLD_ID,
            "bundle_version": "0.1.0",
            "implementation": "world/v1/implementation.py:create_world",
            "episodes_path": "world/v1/episodes.jsonl",
            "roles_path": "world/v1/roles.json",
            "tools_path": "world/v1/tools.json",
            "verifier_path": "world/v1/verifier.json",
            "sources_path": "world/v1/sources.json",
            "default_actor_role": "scientist_agent",
            "required_runtime_capabilities": [
                "actors",
                "role_scoped_tools",
                "transactions",
                "clock",
                "scheduled_events",
            ],
            "trajectory_paths": ["tests/trajectories/analysis.json"],
            "content_hashes": compute_bundle_hashes(WORLD),
        },
    )


def _write_evidence(
    elabftw_facts: dict[str, Any],
    cromwell_facts: dict[str, Any],
) -> None:
    write_json(
        WORLD / "evidence" / "elabftw_experiments_patch_complete_v1.json",
        {
            "schema_version": "api_gym.selected_behavior_evidence.v1",
            "provider": "elabftw",
            "provider_version": "5.6.10",
            "grounding": elabftw_facts["grounding"],
            "projection": elabftw_facts["projection"],
            "operations": elabftw_facts["operations"],
            "response_headers": elabftw_facts["response_headers"],
            "claims": {
                "projection": "captured_program_family_only",
                "production_equivalence": "not_claimed",
            },
        },
    )
    for program, case_name in (
        ("success", "workflow_success_v1"),
        ("failure", "workflow_failure_v1"),
        ("abort", "workflow_abort_v1"),
    ):
        selected = cromwell_facts["programs"][program]
        write_json(
            WORLD / "evidence" / f"cromwell_{case_name}.json",
            {
                "schema_version": "api_gym.selected_behavior_evidence.v1",
                "provider": "cromwell",
                "provider_version": "92",
                "case_name": case_name,
                "grounding": cromwell_facts["grounding"]["cases"][program],
                "projection": cromwell_facts["projection"],
                "workflow_sha256": selected["workflow_sha256"],
                "inputs_sha256": selected["inputs_sha256"],
                "terminal_status": selected["terminal_status"],
                "claims": {
                    "projection": "captured_program_family_only",
                    "production_equivalence": "not_claimed",
                    "paths_dereferenced": False,
                },
            },
        )


def _write_world_documents(episodes: list[dict[str, Any]]) -> None:
    write_json(
        WORLD / "source_refs.json",
        {
            "schema_version": "api_gym.world_source_refs.v0",
            "world": WORLD_ID,
            "source_packs": [],
            "world_evidence": [
                {
                    "path": "evidence/elabftw_experiments_patch_complete_v1.json",
                    "role": "elabftw_complete_behavior",
                },
                {
                    "path": "evidence/cromwell_workflow_success_v1.json",
                    "role": "cromwell_success_behavior",
                },
                {
                    "path": "evidence/cromwell_workflow_failure_v1.json",
                    "role": "cromwell_failure_behavior",
                },
                {
                    "path": "evidence/cromwell_workflow_abort_v1.json",
                    "role": "cromwell_abort_behavior",
                },
            ],
        },
    )
    write_json(
        WORLD / "grounding_matrix.json",
        {
            "schema_version": "api_gym.science_grounding_matrix.v1",
            "world_id": WORLD_ID,
            "claims": [
                {
                    "scope": "elabftw_create_list_get_patch_shapes",
                    "level": "G2_LOCAL_EXECUTED",
                    "source": "experiments_patch_complete_v1",
                },
                {
                    "scope": "cromwell_submit_status_outputs_logs_metadata",
                    "level": "G2_LOCAL_EXECUTED",
                    "source": "workflow_success_v1; workflow_failure_v1",
                },
                {
                    "scope": "cromwell_abort",
                    "level": "G2_LOCAL_EXECUTED",
                    "source": "workflow_abort_v1",
                },
                {
                    "scope": (
                        "logical_timing_revisions_joins_dynamic_provider_fields_"
                        "and_qualification_meaning"
                    ),
                    "level": "G0_BENCHMARK_DEFINED",
                    "source": "projection_contract.md",
                },
            ],
        },
    )
    write_json(
        WORLD / "gate_config.json",
        {
            "config_id": WORLD_ID,
            "response_cases": [],
            "audit_rules": [],
            "policy": {"deny": [], "shadow_write": [], "live_capture": []},
            "world": {"kind": "world_bundle_v1", "seed": 0},
        },
    )
    write_json(
        WORLD / "compatibility.json",
        {
            "schema_version": "datalox_world_compatibility_v1",
            "python": {"tested_version": "3.12"},
            "runtime": {
                "package": "datalox-gated-runtime",
                "tested_version": "0.1.0",
                "tested_git_commit": "15689da",
                "repository": (
                    "https://github.com/Oshawott324/datalox-gated-runtime"
                ),
            },
            "providers": {
                "elabftw": {
                    "captured_version": "5.6.10",
                    "execution_mode": "capture_derived_projection",
                },
                "cromwell": {
                    "captured_version": "92",
                    "execution_mode": "capture_derived_projection",
                },
            },
        },
    )
    write_json(WORLD / "task.json", episodes[0]["task"])
    write_json(WORLD / "replay_script.json", {"calls": []})
    (WORLD / "README.md").write_text(
        "# Science eLabFTW Cromwell v0\n\n"
        "A resettable two-service analysis-control and qualification-evidence "
        "handoff world. Six families and twelve deterministic episodes compose "
        "capture-derived eLabFTW 5.6.10 and Cromwell 92 response behavior with "
        "benchmark-defined logical timing, revisions, and joins. The captured "
        "WDL programs do not perform biological analysis.\n\n"
        "```bash\n"
        "python scripts/worlds/build_science_elabftw_cromwell.py\n"
        "python scripts/worlds/build_science_elabftw_cromwell.py --check\n"
        "datalox-gate env admit-world --env "
        "worlds/science_elabftw_cromwell_v0 --json\n"
        "```\n",
        encoding="utf-8",
    )
    (WORLD / "projection_contract.md").write_text(
        "# Projection And Grounding Contract\n\n"
        "eLabFTW create, get, and PATCH status/request/response shapes are "
        "derived from the checked disposable eLabFTW 5.6.10 "
        "`experiments_patch_complete_v1` case. Cromwell submit, status, outputs, "
        "logs, and metadata shapes are derived from checked Cromwell 92 success "
        "and failure cases; abort shapes are derived from the checked abort case. "
        "These are G2 local reference-executed claims bounded to the captured "
        "program families.\n\n"
        "Compressed timing, source revision schedules, deterministic IDs, "
        "cross-provider joins, and analysis-control qualification meaning are "
        "G0 benchmark-defined. Agent-visible provider timestamps are normalized "
        "to the episode clock, eLabFTW changelog entries are reconstructed from "
        "world mutations, and external links are replaced with non-network "
        "`datalox-world://` identifiers; these dynamic fields are G0 projections, "
        "not captured values. Log and output paths are projected to "
        "`datalox-world://cromwell/...` and are never dereferenced. All writes "
        "remain in the run-private SQLite world state. Network and hardware "
        "actions are inexpressible.\n\n"
        "No production equivalence, reset equivalence, arbitrary Cromwell "
        "business logic, biological analysis, or scientific inference is "
        "claimed.\n",
        encoding="utf-8",
    )
    (WORLD / "skills").mkdir(parents=True, exist_ok=True)
    (WORLD / "skills" / "SKILL.md").write_text(
        "# Analysis-control qualification handoff\n\n"
        "Use provider state as authority. Read the eLabFTW source before each "
        "submission and again before writeback. A Cromwell status 404 immediately "
        "after submit is transient evidence, not permission to resubmit. Resume "
        "a referenced in-flight UUID. Diagnose Failed from both logs and metadata. "
        "Abort a superseded Running workflow and observe Aborted. Inspect outputs "
        "and metadata only after Succeeded.\n\n"
        "Compute required digests with code:\n\n"
        "```python\n"
        "import hashlib, json\n"
        "\n"
        "def digest(value):\n"
        "    body = json.dumps(value, sort_keys=True, separators=(\",\", \":\"))\n"
        "    return \"sha256:\" + hashlib.sha256(body.encode()).hexdigest()\n"
        "```\n\n"
        "PATCH metadata is a JSON string. Call the result an "
        "analysis-control/qualification handoff. Do not claim the captured WDL "
        "performed biological or scientific inference.\n",
        encoding="utf-8",
    )


def snapshot(world_root: Path) -> dict[str, bytes]:
    if not world_root.exists():
        return {}
    return {
        path.relative_to(world_root).as_posix(): path.read_bytes()
        for path in world_root.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.name != "world_admission.json"
    }


def _unexpected_files(world_root: Path) -> set[str]:
    return set(snapshot(world_root)) - EXPECTED_WORLD_FILES


def _copy_source_owned_files(source: Path, destination: Path) -> None:
    for relative in sorted(SOURCE_OWNED_WORLD_FILES):
        source_path = source / relative
        if not source_path.is_file():
            raise FileNotFoundError(
                f"required source-owned world file is missing: {relative}"
            )
        destination_path = destination / relative
        if source_path.resolve() == destination_path.resolve():
            continue
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination_path)


def _report_unexpected(world_root: Path) -> bool:
    unexpected = sorted(_unexpected_files(world_root))
    if not unexpected:
        return False
    print(
        "science eLabFTW Cromwell world contains unexpected files: "
        + ", ".join(unexpected),
        file=sys.stderr,
    )
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--world-root", type=Path, default=WORLD)
    args = parser.parse_args()
    world_root = args.world_root.resolve()
    if _report_unexpected(world_root):
        return 2
    if args.check:
        before = snapshot(world_root)
        try:
            with tempfile.TemporaryDirectory(
                prefix="science-elabftw-cromwell-check-"
            ) as temporary:
                candidate = Path(temporary) / WORLD_ID
                _copy_source_owned_files(world_root, candidate)
                build(candidate)
                after = snapshot(candidate)
        except (FileNotFoundError, OSError) as error:
            print(str(error), file=sys.stderr)
            return 2
        if before != after:
            print(
                "science eLabFTW Cromwell generated artifacts were stale.",
                file=sys.stderr,
            )
            return 1
        print("science eLabFTW Cromwell generated artifacts are current.")
        return 0
    try:
        _copy_source_owned_files(world_root, world_root)
        build(world_root)
    except (FileNotFoundError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 2
    if _report_unexpected(world_root):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
