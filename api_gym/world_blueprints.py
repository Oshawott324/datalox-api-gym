"""Research world blueprint validation and scaffolding helpers."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from api_gym.worlds.specs import PROJECT_ROOT

BLUEPRINT_SCHEMA_VERSION = "api_gym.research_world_blueprint.v0"
TASK_DESIGN_SCHEMA_VERSION = "api_gym.research_world_task_design.v0"
WORLD_SOURCE_REFS_SCHEMA_VERSION = "api_gym.world_source_refs.v0"


class WorldBlueprintError(ValueError):
    """Structured error for agent-readable blueprint failures."""

    def __init__(self, code: str, message: str, details: dict[str, object]):
        super().__init__(message)
        self.code = code
        self.details = details


def validate_research_world_blueprint(path: Path) -> dict[str, object]:
    """Validate one research-world blueprint and return a JSON-serializable summary."""
    blueprint = _load_json_object(path)
    errors = _collect_blueprint_errors(blueprint)
    if errors:
        raise WorldBlueprintError(
            "invalid_research_world_blueprint",
            "Research world blueprint is not valid.",
            {"path": str(path), "errors": errors},
        )

    scenario_names = [scenario["name"] for scenario in blueprint["scenarios"]]
    action_names = [action["name"] for action in blueprint["action_surface"]]
    verifier_names = [check["name"] for check in blueprint["verifier_checks"]]
    return {
        "ok": True,
        "path": str(path),
        "world": blueprint["world"],
        "world_id": blueprint["id"],
        "scenario_count": len(scenario_names),
        "scenarios": scenario_names,
        "action_count": len(action_names),
        "actions": action_names,
        "verifier_check_count": len(verifier_names),
        "verifier_checks": verifier_names,
    }


def scaffold_research_world_from_blueprint(
    path: Path,
    *,
    out_root: Path = PROJECT_ROOT,
    overwrite: bool = False,
) -> dict[str, object]:
    """Write a non-registered world scaffold from a validated research-world blueprint."""
    validation = validate_research_world_blueprint(path)
    blueprint = _load_json_object(path)
    out_root = out_root.resolve()
    world = str(blueprint["world"])

    world_dir = out_root / "worlds" / world
    runtime_dir = out_root / "api_gym" / "worlds" / world
    files = {
        world_dir / "spec.json": _render_spec_json(blueprint),
        world_dir / "README.md": _render_world_readme(blueprint),
        world_dir / "source_refs.json": _render_source_refs_json(blueprint),
        world_dir / "policies" / "environment-contract.md": _render_environment_contract(blueprint),
        runtime_dir / "__init__.py": _render_runtime_init(blueprint),
        runtime_dir / "README.md": _render_runtime_readme(blueprint),
    }
    for scenario in blueprint["scenarios"]:
        scenario_name = str(scenario["name"])
        files[world_dir / "tasks" / f"{scenario_name}.json"] = _render_task_design_json(
            blueprint,
            scenario,
        )

    collisions = [str(file_path) for file_path in files if file_path.exists()]
    if collisions and not overwrite:
        raise WorldBlueprintError(
            "world_scaffold_already_exists",
            "World scaffold target files already exist.",
            {"path": str(path), "out_root": str(out_root), "collisions": collisions},
        )

    written: list[str] = []
    for file_path, content in files.items():
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        written.append(str(file_path))

    return {
        **validation,
        "out_root": str(out_root),
        "world_dir": str(world_dir),
        "runtime_dir": str(runtime_dir),
        "files_written": written,
        "registered": False,
        "next_steps": [
            f"Implement api_gym.worlds.{world}.sampler with resettable state.",
            f"Implement api_gym.worlds.{world}.tools from worlds/{world}/spec.json action_surface.",
            f"Implement api_gym.worlds.{world}.verifier from policies/environment-contract.md.",
            "Add the world to api_gym.worlds.registry only after runtime tests pass.",
        ],
    }


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise WorldBlueprintError(
            "research_world_blueprint_not_found",
            "Research world blueprint file was not found.",
            {"path": str(path)},
        ) from exc
    except json.JSONDecodeError as exc:
        raise WorldBlueprintError(
            "invalid_research_world_blueprint_json",
            "Research world blueprint is not valid JSON.",
            {"path": str(path), "line": exc.lineno, "column": exc.colno, "message": exc.msg},
        ) from exc
    if not isinstance(payload, dict):
        raise WorldBlueprintError(
            "invalid_research_world_blueprint_json",
            "Research world blueprint must contain a JSON object.",
            {"path": str(path)},
        )
    return payload


def _collect_blueprint_errors(blueprint: dict[str, Any]) -> list[dict[str, object]]:
    errors: list[dict[str, object]] = []
    _require_string(blueprint, "schema_version", errors)
    if blueprint.get("schema_version") != BLUEPRINT_SCHEMA_VERSION:
        errors.append(
            {
                "path": "schema_version",
                "code": "unsupported_schema_version",
                "expected": BLUEPRINT_SCHEMA_VERSION,
                "actual": blueprint.get("schema_version"),
            }
        )

    for field in ["id", "world", "title", "version", "summary"]:
        _require_string(blueprint, field, errors)
    if isinstance(blueprint.get("world"), str) and not re.fullmatch(r"[a-z][a-z0-9_]*_v[0-9]+", blueprint["world"]):
        errors.append(
            {
                "path": "world",
                "code": "invalid_world_name",
                "message": "world must be snake_case and end with _v<integer>.",
            }
        )
    if isinstance(blueprint.get("id"), str) and not re.fullmatch(r"[a-z][a-z0-9-]*-v[0-9]+", blueprint["id"]):
        errors.append(
            {
                "path": "id",
                "code": "invalid_world_id",
                "message": "id must be kebab-case and end with -v<integer>.",
            }
        )

    _validate_research_value(blueprint, errors)
    _validate_boundaries(blueprint, errors)
    _validate_object_list(
        blueprint,
        "substrates",
        errors,
        ["name", "kind", "role", "boundary", "source_refs"],
        min_items=1,
    )
    _validate_object_list(
        blueprint,
        "state_model",
        errors,
        ["name", "owner", "agent_visible", "description"],
        min_items=3,
    )
    _validate_object_list(
        blueprint,
        "action_surface",
        errors,
        ["name", "description", "inputs", "effects", "failure_modes"],
        min_items=3,
    )
    _validate_object_list(
        blueprint,
        "observations",
        errors,
        ["name", "description", "agent_visible"],
        min_items=2,
    )
    _validate_object_list(
        blueprint,
        "verifier_checks",
        errors,
        ["name", "description", "hidden_from_agent", "repairable"],
        min_items=5,
    )
    _validate_object_list(
        blueprint,
        "evidence_exports",
        errors,
        ["name", "description", "consumer"],
        min_items=3,
    )
    _validate_scenarios(blueprint, errors)
    return errors


def _validate_research_value(blueprint: dict[str, Any], errors: list[dict[str, object]]) -> None:
    value = blueprint.get("research_value")
    if not isinstance(value, dict):
        errors.append({"path": "research_value", "code": "required_object"})
        return
    for field in ["target_users", "practical_value", "community_artifact", "non_toy_signals"]:
        if field not in value:
            errors.append({"path": f"research_value.{field}", "code": "required"})
    _require_string(value, "practical_value", errors, prefix="research_value.")
    _require_string(value, "community_artifact", errors, prefix="research_value.")
    _require_nonempty_string_list(value, "target_users", errors, prefix="research_value.", min_items=1)
    _require_nonempty_string_list(value, "non_toy_signals", errors, prefix="research_value.", min_items=3)


def _validate_boundaries(blueprint: dict[str, Any], errors: list[dict[str, object]]) -> None:
    boundaries = blueprint.get("boundaries")
    if not isinstance(boundaries, dict):
        errors.append({"path": "boundaries", "code": "required_object"})
        return
    for field in ["live_execution_allowed", "dry_run_required", "agent_receives_hidden_verifier_state"]:
        if not isinstance(boundaries.get(field), bool):
            errors.append({"path": f"boundaries.{field}", "code": "required_boolean"})
    if boundaries.get("live_execution_allowed") is not False:
        errors.append({"path": "boundaries.live_execution_allowed", "code": "must_be_false_for_blueprint_v0"})
    if boundaries.get("agent_receives_hidden_verifier_state") is not False:
        errors.append(
            {
                "path": "boundaries.agent_receives_hidden_verifier_state",
                "code": "must_be_false",
            }
        )


def _validate_scenarios(blueprint: dict[str, Any], errors: list[dict[str, object]]) -> None:
    scenarios = blueprint.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        errors.append({"path": "scenarios", "code": "required_nonempty_array"})
        return
    seen: set[str] = set()
    for idx, scenario in enumerate(scenarios):
        path = f"scenarios[{idx}]"
        if not isinstance(scenario, dict):
            errors.append({"path": path, "code": "required_object"})
            continue
        for field in ["name", "objective", "agent_task", "practical_use"]:
            _require_string(scenario, field, errors, prefix=f"{path}.")
        for field, min_items in [
            ("workflow_stages", 3),
            ("success_criteria", 3),
            ("required_state", 2),
            ("expected_repairs", 1),
        ]:
            _require_nonempty_string_list(scenario, field, errors, prefix=f"{path}.", min_items=min_items)
        name = scenario.get("name")
        if isinstance(name, str):
            if name in seen:
                errors.append({"path": f"{path}.name", "code": "duplicate_scenario_name", "name": name})
            seen.add(name)
            if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
                errors.append({"path": f"{path}.name", "code": "invalid_scenario_name"})


def _validate_object_list(
    blueprint: dict[str, Any],
    field: str,
    errors: list[dict[str, object]],
    required_fields: list[str],
    *,
    min_items: int,
) -> None:
    value = blueprint.get(field)
    if not isinstance(value, list) or len(value) < min_items:
        errors.append({"path": field, "code": "required_array", "min_items": min_items})
        return
    seen_names: set[str] = set()
    for idx, item in enumerate(value):
        item_path = f"{field}[{idx}]"
        if not isinstance(item, dict):
            errors.append({"path": item_path, "code": "required_object"})
            continue
        for required_field in required_fields:
            if required_field not in item:
                errors.append({"path": f"{item_path}.{required_field}", "code": "required"})
        name = item.get("name")
        if isinstance(name, str):
            if name in seen_names:
                errors.append({"path": f"{item_path}.name", "code": "duplicate_name", "name": name})
            seen_names.add(name)


def _require_string(
    obj: dict[str, Any],
    field: str,
    errors: list[dict[str, object]],
    *,
    prefix: str = "",
) -> None:
    value = obj.get(field)
    if not isinstance(value, str) or not value.strip():
        errors.append({"path": f"{prefix}{field}", "code": "required_string"})


def _require_nonempty_string_list(
    obj: dict[str, Any],
    field: str,
    errors: list[dict[str, object]],
    *,
    prefix: str = "",
    min_items: int,
) -> None:
    value = obj.get(field)
    path = f"{prefix}{field}"
    if not isinstance(value, list) or len(value) < min_items:
        errors.append({"path": path, "code": "required_string_array", "min_items": min_items})
        return
    for idx, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            errors.append({"path": f"{path}[{idx}]", "code": "required_string"})


def _render_spec_json(blueprint: dict[str, Any]) -> str:
    payload = {
        "id": blueprint["id"],
        "world": blueprint["world"],
        "title": blueprint["title"],
        "version": blueprint["version"],
        "description": blueprint["summary"],
        "scenarios": [
            {
                "name": scenario["name"],
                "objective": scenario["objective"],
                "summary": scenario["practical_use"],
            }
            for scenario in blueprint["scenarios"]
        ],
        "runtime": {
            "package": f"api_gym.worlds.{blueprint['world']}",
            "state_db": "state.sqlite",
            "task": "task.json",
            "run_metadata": "run.json",
            "status": "scaffolded_not_registered",
        },
        "tools": [action["name"] for action in blueprint["action_surface"]],
        "environment_shape": {
            "substrates": [substrate["name"] for substrate in blueprint["substrates"]],
            "state_model": [state["name"] for state in blueprint["state_model"]],
            "observations": [observation["name"] for observation in blueprint["observations"]],
            "verifier_checks": [check["name"] for check in blueprint["verifier_checks"]],
            "evidence_exports": [evidence["name"] for evidence in blueprint["evidence_exports"]],
            "boundaries": blueprint["boundaries"],
        },
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _render_task_design_json(blueprint: dict[str, Any], scenario: dict[str, Any]) -> str:
    payload = {
        "schema_version": TASK_DESIGN_SCHEMA_VERSION,
        "world": blueprint["world"],
        "world_id": blueprint["id"],
        "scenario": scenario["name"],
        "objective": scenario["objective"],
        "agent_task": scenario["agent_task"],
        "practical_use": scenario["practical_use"],
        "workflow_stages": scenario["workflow_stages"],
        "required_state": scenario["required_state"],
        "success_criteria": scenario["success_criteria"],
        "expected_repairs": scenario["expected_repairs"],
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _render_source_refs_json(blueprint: dict[str, Any]) -> str:
    references: list[dict[str, object]] = []
    for substrate in blueprint["substrates"]:
        for source_ref in substrate["source_refs"]:
            references.append(
                {
                    "substrate": substrate["name"],
                    "kind": substrate["kind"],
                    "source_ref": source_ref,
                }
            )
    payload = {
        "schema_version": WORLD_SOURCE_REFS_SCHEMA_VERSION,
        "world": blueprint["world"],
        "world_id": blueprint["id"],
        "references": references,
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _render_world_readme(blueprint: dict[str, Any]) -> str:
    scenario_lines = "\n".join(
        f"- `{scenario['name']}`: {scenario['objective']}" for scenario in blueprint["scenarios"]
    )
    substrate_lines = "\n".join(
        f"- `{substrate['name']}` ({substrate['kind']}): {substrate['role']}"
        for substrate in blueprint["substrates"]
    )
    tool_lines = "\n".join(
        f"- `{action['name']}`: {action['description']}" for action in blueprint["action_surface"]
    )
    verifier_lines = "\n".join(
        f"- `{check['name']}`: {check['description']}" for check in blueprint["verifier_checks"]
    )
    return f"""# {blueprint['title']}

`{blueprint['world']}` is a scaffolded API Gym research environment.

{blueprint['summary']}

## Practical Value

{blueprint['research_value']['practical_value']}

Community artifact: {blueprint['research_value']['community_artifact']}

## Scenarios

{scenario_lines}

## Substrates

{substrate_lines}

## Agent Tools

{tool_lines}

## Hidden Verifier Checks

{verifier_lines}

## Boundaries

- live execution allowed: `{str(blueprint['boundaries']['live_execution_allowed']).lower()}`
- dry-run required: `{str(blueprint['boundaries']['dry_run_required']).lower()}`
- agent receives hidden verifier state: `{str(blueprint['boundaries']['agent_receives_hidden_verifier_state']).lower()}`

## Implementation Status

This scaffold is not registered in `api_gym.worlds.registry`.
Implement sampler, state, tools, services, and verifier modules with tests before
adding it to `SUPPORTED_WORLDS`.
"""


def _render_environment_contract(blueprint: dict[str, Any]) -> str:
    state_lines = "\n".join(
        f"- `{state['name']}` ({state['owner']}, agent_visible={state['agent_visible']}): {state['description']}"
        for state in blueprint["state_model"]
    )
    observation_lines = "\n".join(
        f"- `{observation['name']}` (agent_visible={observation['agent_visible']}): {observation['description']}"
        for observation in blueprint["observations"]
    )
    evidence_lines = "\n".join(
        f"- `{evidence['name']}` ({evidence['consumer']}): {evidence['description']}"
        for evidence in blueprint["evidence_exports"]
    )
    return f"""# Environment Contract

World: `{blueprint['world']}`

## State Model

{state_lines}

## Observations

{observation_lines}

## Evidence Exports

{evidence_lines}

## Boundary Policy

```json
{json.dumps(blueprint['boundaries'], indent=2, sort_keys=True)}
```

## Verifier Rule

The verifier must read world state and evidence artifacts. It must not grade
transcript text, reveal hidden state to the agent, or accept live hardware
execution in this dry-run blueprint.
"""


def _render_runtime_init(blueprint: dict[str, Any]) -> str:
    return f'"""Runtime scaffold for {blueprint["world"]}."""\n'


def _render_runtime_readme(blueprint: dict[str, Any]) -> str:
    return f"""# Runtime Scaffold

This package is reserved for `{blueprint['world']}` runtime code.

Required modules before registration:

- `state.py`
- `sampler.py`
- `services.py`
- `tools.py`
- `verifier.py`

Keep the environment source-backed, resettable, dry-run, and verifier-hidden.
"""
