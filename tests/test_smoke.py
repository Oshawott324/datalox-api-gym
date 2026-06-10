from __future__ import annotations

import api_gym
from api_gym.worlds import load_world_spec, world_spec_path


def test_package_imports() -> None:
    assert api_gym.__version__ == "0.0.0"


def test_billing_support_spec_exists() -> None:
    spec_path = world_spec_path("billing_support_v0")

    assert spec_path.exists()

    spec = load_world_spec("billing_support_v0")
    assert spec["id"] == "billing-support-v0"
    assert spec["schema_version"] == "api_gym.world_spec.v0"
