"""PyLabRobot Hamilton STAR world for API Gym.

Provides a dry-run Hamilton STAR(let) lab environment powered by the
STARChatterboxBackend.  Supports 8-channel pipetting, optional 96-head,
iSWAP robotic arm, liquid classes, troughs, and tube racks.
"""

from api_gym.worlds.pylabrobot_star_v0.sampler import SCENARIOS, sample_episode
from api_gym.worlds.pylabrobot_star_v0.verifier import verify_run

__all__ = ["SCENARIOS", "sample_episode", "verify_run"]
