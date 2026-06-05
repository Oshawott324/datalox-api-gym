from __future__ import annotations

from pathlib import Path

from .driver import WorldDriver
from .drivers.runnable_world import RunnableWorldDriver
from .drivers.sandbox_command import SandboxCommandDriver
from .io import read_json


def load_driver(world_spec_path: str | Path) -> WorldDriver:
    spec_path = Path(world_spec_path).resolve()
    spec = read_json(spec_path)
    driver = spec.get("driver")
    if not isinstance(driver, dict):
        raise ValueError("world spec requires driver object")
    driver_type = driver.get("type")
    if driver_type == "runnable_world":
        runnable_root = driver.get("runnable_world_root")
        if not isinstance(runnable_root, str):
            raise ValueError("runnable_world driver requires runnable_world_root")
        return RunnableWorldDriver(spec_path, (spec_path.parent / runnable_root).resolve())
    if driver_type == "sandbox_command":
        return SandboxCommandDriver(driver)
    raise ValueError(f"Unsupported world driver type: {driver_type}")
