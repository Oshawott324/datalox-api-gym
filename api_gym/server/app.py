"""HTTP app factory for API Gym run directories."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from api_gym.worlds.registry import get_runtime_for_run


def create_app(run_dir: Path) -> FastAPI:
    """Create the FastAPI app for the run's world."""
    runtime = get_runtime_for_run(run_dir)
    if runtime.create_http_app is None:
        raise ValueError(f"World '{runtime.world}' does not expose an HTTP app.")
    return runtime.create_http_app(run_dir)
