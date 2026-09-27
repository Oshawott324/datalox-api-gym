"""Offline consumer example joining the native worker to the OT-2 motion world.

This is a host-process smoke test. It does not establish container network/device
isolation or physical OT-2 accuracy. The collision scene is an authored sphere
and wall fixture, not a pipette, tip, labware, or whole-instrument model.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from datalox_gated_runtime.sdk_adapters.opentrons_ot2_motion import (
    PINNED_SOURCE_HASHES,
    MoveToDeckPoint,
    MoveToWell,
    OpentronsOT2MotionManager,
    OpentronsOT2WorkerLauncher,
    ResolveWellLocation,
    Vector3,
    request_from_dict,
)

from api_gym.instrument_models.opentrons_ot2_v0.observations import ObservationCatalog
from api_gym.worlds.ot2_motion_v0.runtime_adapter import (
    RuntimeMotionBackend,
    build_authored_fixture,
    declared_setup_from_native,
)
from api_gym.worlds.ot2_motion_v0.tasks import (
    TASKS_BY_ID,
    ResolvedGoal,
    native_binary64_goal_tolerance_mm,
)
from api_gym.worlds.ot2_motion_v0.verifier import verify_episode
from api_gym.worlds.ot2_motion_v0.world import MotionAction, OT2MotionWorld


def run_example(
    *,
    native_python: Path,
    custom_requests: Sequence[MoveToWell | MoveToDeckPoint] = (),
) -> dict[str, Any]:
    launcher = OpentronsOT2WorkerLauncher(
        python_executable=native_python,
        expected_source_hashes=PINNED_SOURCE_HASHES,
    )
    with OpentronsOT2MotionManager(launcher, command_timeout_s=30.0) as manager:
        manager.start()
        first_generation = manager.generation_id
        if custom_requests:
            episodes = [_run_episode(manager, custom_requests)]
            reset_evidence = None
        else:
            direct = MoveToWell(
                "3",
                "A1",
                "top",
                Vector3(0, 0, 5),
                force_direct=True,
            )
            raised = MoveToWell("3", "A1", "top", Vector3(0, 0, 5))
            episodes = [_run_episode(manager, (direct,))]
            manager.reset()
            second_generation = manager.generation_id
            episodes.append(_run_episode(manager, (raised,)))
            if episodes[0]["agent_pre_action"] != episodes[1]["agent_pre_action"]:
                raise RuntimeError("Reset changed the declared pre-action observation")
            reset_evidence = {
                "generation_changed": first_generation != second_generation,
                "fresh_command_sequence": episodes[1]["native_command_ids"][0]
                == "command-00000003",
            }
    return {
        "schema_version": "api_gym.example.ot2_motion_v0.v1",
        "claim": "interactive native simulator plus authored geometric fixture",
        "runtime_isolation_claim": (
            "host-process smoke only; network/device isolation requires the runtime container boundary"
        ),
        "physical_validation": "not_performed",
        "reset": reset_evidence,
        "episodes": episodes,
    }


def _run_episode(
    manager: OpentronsOT2MotionManager,
    requests: Sequence[MoveToWell | MoveToDeckPoint],
) -> dict[str, Any]:
    native_setup = manager.setup
    declared_setup = declared_setup_from_native(native_setup)
    initial = manager.resolve_well_location(
        ResolveWellLocation("1", "A1", "top", Vector3(0, 0, 5))
    )
    target = manager.resolve_well_location(
        ResolveWellLocation("3", "A1", "top", Vector3(0, 0, 5))
    )
    resolved_goal = ResolvedGoal(
        goal_id=f"goal-{target.resolution_digest.removeprefix('sha256:')[:16]}",
        native_frame=target.native_frame,
        native_critical_point=target.native_critical_point,
        target_mm=_vector(target.position_mm),
        position_tolerance_mm=native_binary64_goal_tolerance_mm(
            _vector(target.position_mm)
        ),
        declared_setup_revision=declared_setup.revision,
        definition_digest=target.labware_definition_sha256,
        resolver_source_version=target.resolver_source_version,
        resolution_digest=target.resolution_digest,
    )
    world = OT2MotionWorld(
        task=TASKS_BY_ID["engineering_control_02"],
        declared_setup=declared_setup,
        physical_setup=build_authored_fixture(
            initial_mm=_vector(initial.position_mm),
            goal_mm=_vector(target.position_mm),
        ),
        backend=RuntimeMotionBackend(manager),
        observation_catalog=ObservationCatalog(()),
        resolved_goal=resolved_goal,
        observable_setup_epoch="visible-setup-epoch-1",
        initial_pose_mm=_vector(initial.position_mm),
        initial_native_frame=initial.native_frame,
        initial_critical_point=initial.native_critical_point,
    )
    pre_action = world.observe()
    action_records = []
    for request in requests:
        if world.state.terminal:
            break
        response = world.execute_motion(MotionAction(request))
        action_records.append({"request": request.to_dict(), "observation": response})
    verification = verify_episode(world.state).to_dict()
    return {
        "agent_pre_action": pre_action,
        "actions": action_records,
        "native_command_ids": [event.command_id for event in world.state.events],
        "verification": verification,
    }


def _vector(value: Any) -> tuple[float, float, float]:
    return (float(value.x), float(value.y), float(value.z))


def _parse_custom_requests(values: Sequence[str]) -> tuple[MoveToWell | MoveToDeckPoint, ...]:
    requests = []
    for value in values:
        request = request_from_dict(json.loads(value))
        if not isinstance(request, (MoveToWell, MoveToDeckPoint)):
            raise ValueError("Custom requests must be move_to_well or move_to_deck_point")
        requests.append(request)
    return tuple(requests)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--native-python",
        type=Path,
        required=True,
        help="Trusted interpreter containing pinned Opentrons 9.1.1 dependencies.",
    )
    parser.add_argument(
        "--request-json",
        action="append",
        default=[],
        help="Strict typed movement request JSON; repeat for an arbitrary sequence.",
    )
    args = parser.parse_args()
    result = run_example(
        native_python=args.native_python,
        custom_requests=_parse_custom_requests(args.request_json),
    )
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
