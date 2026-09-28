from __future__ import annotations

import pytest

from api_gym.instrument_models.plate_reader_v0.contracts import (
    AcquisitionSettings,
    ReaderProfile,
)
from api_gym.instrument_models.plate_reader_v0.dynamics import PlateReaderDynamics
from api_gym.worlds.enzyme_activity_v0.chemistry import ReactionParameters, advance_reaction
from api_gym.worlds.enzyme_activity_v0.state import Mixture


PARAMETERS = ReactionParameters(kcat_per_s=0.08, km_mM=0.25)


def profile(*, detector_max_abs: float = 2.0) -> ReaderProfile:
    return ReaderProfile(
        profile_id="test-reader-v0",
        wavelength_nm=405,
        temperature_c=37,
        compatible_plate_load_name="corning_96_wellplate_360ul_flat",
        reaction_volume_min_ul=80,
        reaction_volume_max_ul=200,
        optical_path_cm=0.5,
        product_extinction_per_mM_cm=18.5,
        blank_intercept_abs=0.04,
        blank_drift_abs_per_s=0.00001,
        noise_sd_abs=0.002,
        detector_min_abs=0,
        detector_max_abs=detector_max_abs,
        per_well_delay_s=0.2,
    )


def settings() -> AcquisitionSettings:
    return AcquisitionSettings(405, 37, ("A1", "A2"), (0, 30, 60, 90))


def starting_mixtures() -> dict[str, Mixture]:
    return {
        "A1": Mixture.pure(
            source_id="sample",
            volume_ul=100,
            enzyme_concentration_mM=0.001,
            substrate_concentration_mM=1,
        ),
        "A2": Mixture.pure(
            source_id="blank",
            volume_ul=100,
            substrate_concentration_mM=1,
        ),
    }


def run(seed: int) -> tuple[PlateReaderDynamics, str]:
    mixtures = starting_mixtures()
    reader = PlateReaderDynamics(profile(), noise_seed=seed)
    job_id = reader.start_series(
        plate_id="plate-1", plate_revision=3, start_s=10, settings=settings()
    )
    reader.acquire_due(
        job_id,
        now_s=200,
        mixture_at=lambda well, at_s: advance_reaction(mixtures[well], at_s, PARAMETERS),
    )
    return reader, job_id


def test_schedule_has_individual_timestamps_and_fetch_is_immutable() -> None:
    mixtures = starting_mixtures()
    reader = PlateReaderDynamics(profile(), noise_seed=7)
    job_id = reader.start_series(
        plate_id="plate-1", plate_revision=3, start_s=10, settings=settings()
    )
    reader.acquire_due(
        job_id,
        now_s=40.2,
        mixture_at=lambda well, at_s: advance_reaction(mixtures[well], at_s, PARAMETERS),
    )
    partial = reader.get_data(job_id)
    assert [item["acquired_at_s"] for item in partial] == pytest.approx([10, 10.2, 40, 40.2])
    assert reader.get_job(job_id)["status"] == "running"
    first_fetch = reader.get_data(job_id)
    second_fetch = reader.get_data(job_id)
    assert first_fetch == second_fetch


def test_reset_seed_reproduces_noise_and_independent_seed_changes_it() -> None:
    first, first_job = run(22)
    repeated, repeated_job = run(22)
    independent, independent_job = run(23)
    first_values = [item["absorbance"] for item in first.get_data(first_job)]
    assert first_values == [item["absorbance"] for item in repeated.get_data(repeated_job)]
    assert first_values != [
        item["absorbance"] for item in independent.get_data(independent_job)
    ]


def test_missing_and_overrange_are_explicit_and_never_numeric_zeros() -> None:
    mixture = Mixture.pure(
        source_id="high-product",
        volume_ul=100,
        product_concentration_mM=0.1,
    )
    reader = PlateReaderDynamics(
        profile(detector_max_abs=0.5),
        noise_seed=1,
        missing_measurement_indices=frozenset({0}),
    )
    job_id = reader.start_series(
        plate_id="plate-1",
        plate_revision=1,
        start_s=0,
        settings=AcquisitionSettings(405, 37, ("A1",), (0, 10)),
    )
    reader.acquire_due(job_id, now_s=20, mixture_at=lambda well, at_s: mixture)
    data = reader.get_data(job_id)
    assert [item["status"] for item in data] == ["missing", "overrange"]
    assert [item["absorbance"] for item in data] == [None, None]
