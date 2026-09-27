"""Content-hashed bundle entry point for the packaged API Gym adapter."""

from api_gym.worlds.ot2_motion_v0.runtime_adapter import create_world

__all__ = ["create_world"]
