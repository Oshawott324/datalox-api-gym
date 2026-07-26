"""Stable errors for local PyLabRobot component execution."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

_EXCEPTION_CODES = {
    "HasTipError": "PYLABROBOT_HAS_TIP",
    "NoFreeSiteError": "PYLABROBOT_NO_FREE_SITE",
    "NoPlateError": "PYLABROBOT_NO_PLATE",
    "NoTipError": "PYLABROBOT_NO_TIP",
    "ResourceNotFoundError": "PYLABROBOT_RESOURCE_NOT_FOUND",
    "TooLittleLiquidError": "PYLABROBOT_TOO_LITTLE_LIQUID",
    "TooLittleVolumeError": "PYLABROBOT_TOO_LITTLE_VOLUME",
}


class PyLabRobotComponentError(RuntimeError):
    """A normalized exception raised by the pinned local provider component."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        operation_id: str,
        details: dict[str, Any],
    ) -> None:
        super().__init__(message)
        self.code = code
        self.operation_id = operation_id
        self.details = deepcopy(details)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": str(self),
            "operation_id": self.operation_id,
            "details": deepcopy(self.details),
        }


def normalize_plr_exception(
    error: Exception,
    *,
    operation_id: str,
) -> PyLabRobotComponentError:
    exception_name = type(error).__name__
    exception_type = f"{type(error).__module__}.{exception_name}"
    code = _EXCEPTION_CODES.get(exception_name, "PYLABROBOT_EXECUTION_ERROR")
    return PyLabRobotComponentError(
        code,
        str(error),
        operation_id=operation_id,
        details={
            "exception_type": exception_type,
            "hardware_execution_attempted": False,
        },
    )
