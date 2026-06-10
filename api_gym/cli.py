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
from api_gym.runner.openai_compatible import run_openai_compatible_agent
from api_gym.server.app import create_app
from api_gym.worlds.billing_support_v0.sampler import SCENARIOS, sample_episode
from api_gym.worlds.billing_support_v0.oracle import resolve_run
from api_gym.worlds.billing_support_v0.verifier import verify_run

app = typer.Typer(help="Datalox API Gym command line tools.")


@app.command()
def sample(
    world: Annotated[str, typer.Option(help="World directory id.")] = "billing_support_v0",
    scenario: Annotated[str, typer.Option(help="Scenario name.")] = "duplicate_payment_refund",
    seed: Annotated[int, typer.Option(help="Deterministic scenario seed.")] = 0,
    out: Annotated[Path, typer.Option(help="Output run directory.")] = Path("run"),
) -> None:
    """Sample a deterministic API Gym episode."""
    if world != "billing_support_v0":
        _exit_error("unsupported_world", f"Unsupported world '{world}'.", {"supported_worlds": ["billing_support_v0"]})
    if scenario not in SCENARIOS:
        _exit_error("unsupported_scenario", f"Unsupported scenario '{scenario}'.", {"supported_scenarios": sorted(SCENARIOS)})

    try:
        episode = sample_episode(scenario=scenario, seed=seed, out_dir=out)
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
    result = verify_run(run)
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
    scenarios: Annotated[str, typer.Option(help="Comma-separated scenario names.")] = ",".join(sorted(SCENARIOS)),
    seeds: Annotated[str, typer.Option(help="Comma-separated deterministic scenario seeds.")] = "1",
    model: Annotated[str, typer.Option(help="OpenAI-compatible model name.")] = ...,
    base_url: Annotated[str, typer.Option(help="OpenAI-compatible API base URL, usually ending in /v1.")] = ...,
    api_key: Annotated[str | None, typer.Option(help="API key for the OpenAI-compatible endpoint.")] = None,
    out: Annotated[Path, typer.Option(help="Output JSONL path for eval rows.")] = ...,
    max_turns: Annotated[int, typer.Option(help="Maximum assistant turns per task.")] = 12,
) -> None:
    """Evaluate an OpenAI-compatible model across sampled tasks."""
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


@app.command()
def report(input: Annotated[Path, typer.Option(help="Eval JSONL path.")]) -> None:
    """Print aggregate pass-rate stats for an eval JSONL file."""
    try:
        summary = summarize_eval_report(input)
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        _exit_error("report_failed", str(exc), {"input": str(input)})
    typer.echo(json.dumps(summary, indent=2, sort_keys=True))


def _exit_error(code: str, message: str, details: dict[str, object]) -> None:
    typer.echo(json.dumps({"ok": False, "error": {"code": code, "message": message, "details": details}}, indent=2), err=True)
    raise typer.Exit(2)


if __name__ == "__main__":
    app()
