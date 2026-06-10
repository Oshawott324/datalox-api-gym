"""HTTP app factory for API Gym run directories."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from api_gym.worlds.billing_support_v0.http import create_app as create_billing_support_app


def create_app(run_dir: Path) -> FastAPI:
    """Create the FastAPI app for the run's world."""
    return create_billing_support_app(run_dir)
