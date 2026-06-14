"""Typer CLI for API Gym."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from api_gym.agent_harness import (
    build_agent_task_package,
    run_host_command,
    serve_mcp_stdio,
    write_agent_task_package,
)
from api_gym.evaluation import parse_csv_list, parse_seed_list, run_eval_suite, summarize_eval_report
from api_gym.exports.run_export import build_run_export, write_run_export
from api_gym.runner.openai_compatible import run_openai_compatible_agent
from api_gym.server.app import create_app
from api_gym.session import check_session_tools, create_world_session, finalize_world_session
from api_gym.source_pack_gate_server import create_gate_app
from api_gym.source_pack_gate import (
    SourcePackGateError,
    build_gate_response,
    choose_response_case,
    find_operation,
)
from api_gym.source_packs import SourcePackValidationError, validate_source_pack
from api_gym.worlds.billing_support_v0.sampler import SCENARIOS as BILLING_SCENARIOS
from api_gym.worlds.billing_support_v0.oracle import resolve_run
from api_gym.worlds.registry import SUPPORTED_WORLDS, get_runtime_for_run, get_world_runtime
from api_gym.worlds.unitelabs_plate_qc_v0.api_contract_sampler import (
    UnitelabsApiContractSamplingError,
    write_openapi_contract_sample,
)

app = typer.Typer(help="Datalox API Gym command line tools.")
session_app = typer.Typer(help="World session lifecycle commands.")
gate_app = typer.Typer(help="API source-pack HTTP gate commands.")
source_pack_app = typer.Typer(help="API source-pack commands.")
unitelabs_app = typer.Typer(help="Unitelabs-specific grounding commands.")
app.add_typer(session_app, name="session")
app.add_typer(gate_app, name="gate")
app.add_typer(source_pack_app, name="source-pack")
app.add_typer(unitelabs_app, name="unitelabs")


@app.command()
def sample(
    world: Annotated[str, typer.Option(help="World directory id.")] = "billing_support_v0",
    scenario: Annotated[str, typer.Option(help="Scenario name.")] = "duplicate_payment_refund",
    seed: Annotated[int, typer.Option(help="Deterministic scenario seed.")] = 0,
    out: Annotated[Path, typer.Option(help="Output run directory.")] = Path("run"),
) -> None:
    """Sample a deterministic API Gym episode."""
    try:
        runtime = get_world_runtime(world)
    except ValueError as exc:
        _exit_error("unsupported_world", str(exc), {"supported_worlds": list(SUPPORTED_WORLDS)})
    if scenario not in runtime.scenarios:
        _exit_error("unsupported_scenario", f"Unsupported scenario '{scenario}'.", {"supported_scenarios": sorted(runtime.scenarios)})

    try:
        episode = runtime.sample_episode(scenario=scenario, seed=seed, out_dir=out)
    except FileExistsError as exc:
        _exit_error("run_dir_already_initialized", str(exc), {"out": str(out)})

    typer.echo(
        json.dumps(
            {
                "ok": True,
                "run_dir": str(episode.run_dir),
                "state_db": str(episode.db_path),
                "task": episode.task,
            },
            indent=2,
            sort_keys=True,
        )
    )


@app.command()
def verify(run: Annotated[Path, typer.Option(help="Run directory created by api-gym sample.")]) -> None:
    """Verify an API Gym episode from final SQLite state."""
    try:
        runtime = get_runtime_for_run(run)
        result = runtime.verify_run(run)
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        _exit_error("invalid_run", str(exc), {"run": str(run)})
    typer.echo(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    if not result.ok:
        raise typer.Exit(1)


@app.command()
def serve(
    run: Annotated[Path, typer.Option(help="Run directory created by api-gym sample.")],
    host: Annotated[str, typer.Option(help="Host interface for the HTTP server.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Port for the HTTP server.")] = 8080,
) -> None:
    """Serve one sampled run through the FastAPI HTTP surface."""
    _ensure_billing_run_surface(run, "serve")
    try:
        fastapi_app = create_app(run)
    except (FileNotFoundError, ValueError) as exc:
        _exit_error("invalid_run", str(exc), {"run": str(run)})

    import uvicorn

    uvicorn.run(fastapi_app, host=host, port=port)


@app.command()
def task(
    run: Annotated[Path, typer.Option(help="Run directory created by api-gym sample.")],
    out: Annotated[Path | None, typer.Option(help="Optional path to write the task package JSON.")] = None,
) -> None:
    """Print an agent-host task package for one sampled run."""
    try:
        package = build_agent_task_package(run)
        if out is not None:
            task_package_path = str(write_agent_task_package(run, out))
            package["task_package_path"] = task_package_path
            package["environment"]["API_GYM_TASK_JSON"] = task_package_path
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        _exit_error("task_package_failed", str(exc), {"run": str(run), "out": None if out is None else str(out)})
    typer.echo(json.dumps(package, indent=2, sort_keys=True))


@app.command()
def mcp(run: Annotated[Path, typer.Option(help="Run directory created by api-gym sample.")]) -> None:
    """Serve one sampled run through an MCP stdio tool server."""
    try:
        serve_mcp_stdio(run)
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        _exit_error("mcp_failed", str(exc), {"run": str(run)})


@app.command("run-host", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def run_host(
    ctx: typer.Context,
    run: Annotated[Path, typer.Option(help="Run directory created by api-gym sample.")],
    result_out: Annotated[Path | None, typer.Option(help="Optional path to write host result JSON.")] = None,
) -> None:
    """Run a generic agent host command, then verify the sampled run."""
    command = list(ctx.args)
    if command and command[0] == "--":
        command = command[1:]
    try:
        result = run_host_command(run_dir=run, command=command, result_out=result_out)
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError) as exc:
        _exit_error("run_host_failed", str(exc), {"run": str(run), "command": command})
    typer.echo(json.dumps(result, indent=2, sort_keys=True))
    if not result["ok"]:
        raise typer.Exit(1)


@app.command()
def resolve(
    run: Annotated[Path, typer.Option(help="Run directory created by api-gym sample.")],
    policy: Annotated[str, typer.Option(help="Resolver policy.")] = "oracle",
) -> None:
    """Resolve an episode through a scripted oracle policy."""
    _ensure_billing_run_surface(run, "resolve")
    try:
        result = resolve_run(run, policy=policy)
    except (FileNotFoundError, ValueError) as exc:
        _exit_error("invalid_run", str(exc), {"run": str(run)})
    typer.echo(json.dumps(result, indent=2, sort_keys=True))
    if not result["ok"]:
        raise typer.Exit(1)


@app.command("run")
def run_agent(
    run: Annotated[Path, typer.Option(help="Run directory created by api-gym sample.")],
    model: Annotated[str, typer.Option(help="OpenAI-compatible model name.")],
    base_url: Annotated[str, typer.Option(help="OpenAI-compatible API base URL, usually ending in /v1.")],
    api_key: Annotated[str | None, typer.Option(help="API key for the OpenAI-compatible endpoint.")] = None,
    max_turns: Annotated[int, typer.Option(help="Maximum assistant turns.")] = 12,
) -> None:
    """Run an OpenAI-compatible tool-calling agent against one sampled run."""
    _ensure_billing_run_surface(run, "run")
    try:
        result = run_openai_compatible_agent(
            run_dir=run,
            model=model,
            base_url=base_url,
            api_key=api_key,
            max_turns=max_turns,
        )
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        _exit_error("agent_run_failed", str(exc), {"run": str(run), "base_url": base_url, "model": model})
    typer.echo(json.dumps(result, indent=2, sort_keys=True))
    if not result["ok"]:
        raise typer.Exit(1)


@app.command("eval")
def eval_suite(
    world: Annotated[str, typer.Option(help="World directory id.")] = "billing_support_v0",
    scenarios: Annotated[str, typer.Option(help="Comma-separated scenario names.")] = ",".join(sorted(BILLING_SCENARIOS)),
    seeds: Annotated[str, typer.Option(help="Comma-separated deterministic scenario seeds.")] = "1",
    model: Annotated[str, typer.Option(help="OpenAI-compatible model name.")] = ...,
    base_url: Annotated[str, typer.Option(help="OpenAI-compatible API base URL, usually ending in /v1.")] = ...,
    api_key: Annotated[str | None, typer.Option(help="API key for the OpenAI-compatible endpoint.")] = None,
    out: Annotated[Path, typer.Option(help="Output JSONL path for eval rows.")] = ...,
    max_turns: Annotated[int, typer.Option(help="Maximum assistant turns per task.")] = 12,
) -> None:
    """Evaluate an OpenAI-compatible model across sampled tasks."""
    _ensure_billing_world_surface(world, "eval")
    try:
        rows = run_eval_suite(
            world=world,
            scenarios=parse_csv_list(scenarios),
            seeds=parse_seed_list(seeds),
            model=model,
            base_url=base_url,
            api_key=api_key,
            out=out,
            max_turns=max_turns,
        )
    except (FileExistsError, FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
        _exit_error(
            "eval_failed",
            str(exc),
            {"world": world, "scenarios": scenarios, "seeds": seeds, "base_url": base_url, "model": model, "out": str(out)},
        )
    typer.echo(json.dumps({"ok": True, "out": str(out), "total": len(rows)}, indent=2, sort_keys=True))


@app.command("export")
def export_run(
    run: Annotated[Path, typer.Option(help="Run directory created by api-gym sample.")],
    out: Annotated[Path | None, typer.Option(help="Optional path to write the run export JSON.")] = None,
) -> None:
    """Export task, tool trace, and verifier evidence for one sampled run."""
    try:
        payload = write_run_export(run, out) if out is not None else build_run_export(run)
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        _exit_error("export_failed", str(exc), {"run": str(run), "out": None if out is None else str(out)})
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@app.command()
def report(input: Annotated[Path, typer.Option(help="Eval JSONL path.")]) -> None:
    """Print aggregate pass-rate stats for an eval JSONL file."""
    try:
        summary = summarize_eval_report(input)
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        _exit_error("report_failed", str(exc), {"input": str(input)})
    typer.echo(json.dumps(summary, indent=2, sort_keys=True))


@source_pack_app.command("validate")
def source_pack_validate(path: Annotated[Path, typer.Argument(help="Source-pack directory or source_pack.json path.")]) -> None:
    """Validate one API source pack."""
    try:
        result = validate_source_pack(path)
    except SourcePackValidationError as exc:
        _exit_error(exc.code, str(exc), exc.details)
    _echo_json(result)


@source_pack_app.command("respond")
def source_pack_respond(
    provider: Annotated[str, typer.Option(help="API source-pack provider id.")],
    method: Annotated[str, typer.Option(help="HTTP method to match.")],
    path: Annotated[str, typer.Option(help="HTTP path to match.")],
    case: Annotated[str, typer.Option(help="Response case selector.")] = "success",
    version: Annotated[str | None, typer.Option(help="Optional source-pack version.")] = None,
) -> None:
    """Build a grounded dry-run response from a source-pack response case."""
    try:
        operation = find_operation(provider, method, path, version=version)
        response_case = choose_response_case(provider, operation["id"], case=case, version=version)
        response = build_gate_response(response_case)
    except SourcePackGateError as exc:
        _exit_error(exc.code, str(exc), exc.details)

    payload: dict[str, object] = {
        "ok": True,
        "provider": provider,
        "operation": operation,
        "response_case": response_case,
        "response": response,
    }
    source_pack_version = version or _source_pack_version(provider, operation)
    if source_pack_version is not None:
        payload["version"] = source_pack_version
    _echo_json(payload)


@gate_app.command("serve")
def gate_serve(
    provider: Annotated[str, typer.Option(help="API source-pack provider id.")],
    version: Annotated[str | None, typer.Option(help="Optional source-pack version.")] = None,
    host: Annotated[str, typer.Option(help="Host interface for the HTTP gate server.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Port for the HTTP gate server.")] = 8787,
    response_case: Annotated[str, typer.Option("--case", help="Default response case selector.")] = "success",
    trace: Annotated[Path | None, typer.Option(help="Optional JSONL path for gated-call evidence rows.")] = None,
) -> None:
    """Serve source-pack response cases through an original-shaped HTTP gate."""
    fastapi_app = create_gate_app(provider, version=version, default_case=response_case, evidence_path=trace)

    import uvicorn

    uvicorn.run(fastapi_app, host=host, port=port)


@unitelabs_app.command("sample-api-contract")
def unitelabs_sample_api_contract(
    out: Annotated[Path, typer.Option(help="Path to write the normalized API contract sample JSON.")],
    openapi_file: Annotated[Path | None, typer.Option(help="Explicit local UniteLabs OpenAPI JSON file.")] = None,
    openapi_url: Annotated[str | None, typer.Option(help="Explicit UniteLabs OpenAPI JSON URL to fetch with GET.")] = None,
    bearer_token_env: Annotated[
        str | None,
        typer.Option(help="Optional env var containing a bearer token for --openapi-url."),
    ] = None,
) -> None:
    """Sample a UniteLabs OpenAPI contract without executing workflow or hardware actions."""
    try:
        sample_payload = write_openapi_contract_sample(
            out=out,
            openapi_file=openapi_file,
            openapi_url=openapi_url,
            bearer_token_env=bearer_token_env,
        )
    except UnitelabsApiContractSamplingError as exc:
        _exit_error(exc.code, str(exc), exc.details)
    _echo_json({"ok": True, "out": str(out), "sample": sample_payload})


@session_app.command("create")
def session_create(
    world: Annotated[str, typer.Option(help="World directory id.")],
    scenario: Annotated[str, typer.Option(help="Scenario name.")],
    seed: Annotated[int, typer.Option(help="Deterministic scenario seed.")] = 0,
    out: Annotated[Path, typer.Option(help="Output run directory.")] = Path("run"),
    json_output: Annotated[bool, typer.Option("--json", help="Accepted for compatibility; output is always JSON.")] = False,
) -> None:
    """Create a sampled world session and emit one agent-runtime manifest."""
    _ = json_output
    try:
        manifest = create_world_session(world=world, scenario=scenario, seed=seed, out_dir=out)
    except (FileExistsError, ValueError) as exc:
        _exit_error("session_create_failed", str(exc), {"world": world, "scenario": scenario, "seed": seed, "out": str(out)})
    _echo_json(manifest)


@session_app.command("check-tools")
def session_check_tools(run: Annotated[Path, typer.Option(help="Run directory created by session create.")]) -> None:
    """Verify the Datalox MCP server lists the expected tools."""
    try:
        result = check_session_tools(run)
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        _exit_error("session_check_tools_failed", str(exc), {"run": str(run)})
    _echo_json(result)
    if not result["ok"]:
        raise typer.Exit(1)


@session_app.command("finalize")
def session_finalize(
    run: Annotated[Path, typer.Option(help="Run directory created by session create.")],
    json_output: Annotated[bool, typer.Option("--json", help="Accepted for compatibility; output is always JSON.")] = False,
) -> None:
    """Verify a session and export evidence."""
    _ = json_output
    try:
        result = finalize_world_session(run)
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        _exit_error("session_finalize_failed", str(exc), {"run": str(run)})
    _echo_json(result)
    if not result["ok"]:
        raise typer.Exit(1)


def _exit_error(code: str, message: str, details: dict[str, object]) -> None:
    typer.echo(json.dumps({"ok": False, "error": {"code": code, "message": message, "details": details}}, indent=2), err=True)
    raise typer.Exit(2)


def _echo_json(payload: dict[str, object]) -> None:
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


def _source_pack_version(provider: str, operation: dict[str, object]) -> str | None:
    source_pack_id = operation.get("source_pack_id")
    if not isinstance(source_pack_id, str):
        return None
    prefix = f"api.{provider}."
    if not source_pack_id.startswith(prefix):
        return None
    return source_pack_id.removeprefix(prefix)


def _ensure_billing_run_surface(run: Path, surface: str) -> None:
    try:
        runtime = get_runtime_for_run(run)
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        _exit_error("invalid_run", str(exc), {"run": str(run), "surface": surface})
    _ensure_billing_world_surface(runtime.world, surface)


def _ensure_billing_world_surface(world: str, surface: str) -> None:
    if world != "billing_support_v0":
        _exit_error(
            "unsupported_world_surface",
            f"api-gym {surface} currently supports only billing_support_v0.",
            {
                "world": world,
                "surface": surface,
                "supported_worlds": ["billing_support_v0"],
            },
        )


if __name__ == "__main__":
    app()
