"""Deterministic scheduling and stochastic absorbance acquisition."""

from __future__ import annotations

import copy
import random
from dataclasses import dataclass, replace
from typing import Any, Callable, Literal

from api_gym.worlds.enzyme_activity_v0.state import Mixture

from .contracts import AcquisitionSettings, ReaderProfile


AcquisitionStatus = Literal["pending", "acquired", "missing", "overrange"]


@dataclass(frozen=True)
class AcquisitionPoint:
    measurement_id: str
    well: str
    scheduled_at_s: float
    acquired_at_s: float | None
    status: AcquisitionStatus
    absorbance: float | None
    units: Literal["absorbance"] = "absorbance"

    def public_dict(self) -> dict[str, Any]:
        if self.status == "pending":
            raise ValueError("pending acquisitions are not public observations")
        return {
            "measurement_id": self.measurement_id,
            "well": self.well,
            "acquired_at_s": self.acquired_at_s,
            "status": self.status,
            "absorbance": self.absorbance,
            "units": self.units,
        }


@dataclass
class ReaderJob:
    job_id: str
    plate_id: str
    plate_revision: int
    settings: AcquisitionSettings
    settings_digest: str
    created_at_s: float
    points: list[AcquisitionPoint]

    @property
    def status(self) -> Literal["pending", "running", "completed"]:
        completed = sum(point.status != "pending" for point in self.points)
        if completed == 0:
            return "pending"
        if completed == len(self.points):
            return "completed"
        return "running"

    def public_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "plate_id": self.plate_id,
            "plate_revision": self.plate_revision,
            "settings": self.settings.to_dict(),
            "settings_digest": self.settings_digest,
            "created_at_s": self.created_at_s,
            "status": self.status,
            "measurements": [
                point.public_dict() for point in self.points if point.status != "pending"
            ],
        }


MixtureAt = Callable[[str, float], Mixture]


class PlateReaderDynamics:
    """Task-independent reader whose only stochastic draw occurs at acquisition."""

    def __init__(
        self,
        profile: ReaderProfile,
        *,
        noise_seed: int,
        missing_measurement_indices: frozenset[int] = frozenset(),
    ) -> None:
        if type(noise_seed) is not int:
            raise TypeError("noise_seed must be an integer")
        if any(type(index) is not int or index < 0 for index in missing_measurement_indices):
            raise ValueError("missing measurement indices must be non-negative integers")
        self.profile = profile
        self._rng = random.Random(noise_seed)
        self._missing = missing_measurement_indices
        self._jobs: dict[str, ReaderJob] = {}
        self._next_job = 1

    def start_series(
        self,
        *,
        plate_id: str,
        plate_revision: int,
        start_s: float,
        settings: AcquisitionSettings,
    ) -> str:
        settings.validate_for(self.profile)
        if not plate_id or type(plate_revision) is not int or plate_revision < 1:
            raise ValueError("plate identity and positive revision are required")
        if start_s < 0:
            raise ValueError("start_s must be non-negative")
        job_id = f"reader-job-{self._next_job:04d}"
        self._next_job += 1
        points: list[AcquisitionPoint] = []
        sequence = 0
        for offset_s in settings.time_offsets_s:
            for well_index, well in enumerate(settings.wells):
                points.append(
                    AcquisitionPoint(
                        measurement_id=f"{job_id}-measurement-{sequence + 1:04d}",
                        well=well,
                        scheduled_at_s=(
                            float(start_s)
                            + offset_s
                            + well_index * self.profile.per_well_delay_s
                        ),
                        acquired_at_s=None,
                        status="pending",
                        absorbance=None,
                    )
                )
                sequence += 1
        self._jobs[job_id] = ReaderJob(
            job_id=job_id,
            plate_id=plate_id,
            plate_revision=plate_revision,
            settings=settings,
            settings_digest=settings.digest,
            created_at_s=float(start_s),
            points=points,
        )
        return job_id

    def acquire_due(self, job_id: str, *, now_s: float, mixture_at: MixtureAt) -> None:
        job = self._job(job_id)
        for index, point in enumerate(job.points):
            if point.status != "pending" or point.scheduled_at_s > now_s:
                continue
            if index in self._missing:
                job.points[index] = replace(
                    point,
                    acquired_at_s=point.scheduled_at_s,
                    status="missing",
                )
                continue
            mixture = mixture_at(point.well, point.scheduled_at_s)
            if not (
                self.profile.reaction_volume_min_ul
                <= mixture.volume_ul
                <= self.profile.reaction_volume_max_ul
            ):
                raise ValueError("well volume is outside the reader profile")
            blank = (
                self.profile.blank_intercept_abs
                + self.profile.blank_drift_abs_per_s * point.scheduled_at_s
            )
            modeled = (
                blank
                + self.profile.product_extinction_per_mM_cm
                * self.profile.optical_path_cm
                * mixture.concentration_mM("product")
            )
            observed = modeled + self._rng.gauss(0.0, self.profile.noise_sd_abs)
            if not self.profile.detector_min_abs <= observed <= self.profile.detector_max_abs:
                status: AcquisitionStatus = "overrange"
                value = None
            else:
                status = "acquired"
                value = observed
            job.points[index] = replace(
                point,
                acquired_at_s=point.scheduled_at_s,
                status=status,
                absorbance=value,
            )

    def get_job(self, job_id: str) -> dict[str, Any]:
        return copy.deepcopy(self._job(job_id).public_dict())

    def get_data(self, job_id: str) -> tuple[dict[str, Any], ...]:
        public = self._job(job_id).public_dict()["measurements"]
        return tuple(copy.deepcopy(public))

    @property
    def job_ids(self) -> tuple[str, ...]:
        return tuple(self._jobs)

    @property
    def all_jobs_complete(self) -> bool:
        return bool(self._jobs) and all(job.status == "completed" for job in self._jobs.values())

    def _job(self, job_id: str) -> ReaderJob:
        try:
            return self._jobs[job_id]
        except KeyError as exc:
            raise ValueError(f"unknown reader job {job_id!r}") from exc
